"""Arab & Iraqi Legal Library MCP — initial, rights-aware implementation.

Sources marked directory_only are not scraped. Imported text is supplied by
an authorized operator and is NOT represented as independently verified.
"""
import json
import os
import secrets
from starlette.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlencode
import httpx
from mcp.server.fastmcp import FastMCP

ROOT = Path(__file__).resolve().parent
DB = Path(os.getenv("LEGAL_DB_PATH", str(ROOT / "data" / "legal.db")))
SOURCES = json.loads((ROOT / "data" / "sources.json").read_text(encoding="utf-8"))
mcp = FastMCP("Arab & Iraqi Legal Library", stateless_http=True, json_response=True,
              host=os.getenv("MCP_HOST", "127.0.0.1"),
              port=int(os.getenv("PORT", "8000")))


def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.execute("""CREATE TABLE IF NOT EXISTS documents (
        id INTEGER PRIMARY KEY, title TEXT NOT NULL, jurisdiction TEXT NOT NULL,
        doc_type TEXT NOT NULL, citation TEXT, publication_date TEXT,
        source_url TEXT NOT NULL, rights_note TEXT NOT NULL,
        text_body TEXT NOT NULL, imported_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    con.commit()
    return con


def local_search(query: str, jurisdiction: str = "", limit: int = 10):
    con = connect()
    try:
        terms = ["%" + query.strip().replace("%", "\\%").replace("_", "\\_") + "%"]
        sql = "SELECT id,title,jurisdiction,doc_type,citation,publication_date,source_url,rights_note,substr(text_body,1,900) AS excerpt FROM documents WHERE (title LIKE ? ESCAPE '\\' OR text_body LIKE ? ESCAPE '\\')"
        args = terms * 2
        if jurisdiction:
            sql += " AND jurisdiction=?"
            args.append(jurisdiction)
        sql += " ORDER BY id DESC LIMIT ?"
        args.append(max(1, min(limit, 30)))
        return [dict(row) for row in con.execute(sql, args)]
    finally:
        con.close()


@mcp.tool()
def list_legal_sources(country: str = "") -> dict:
    """List trusted legal source entry points and distinguish live APIs from directories."""
    return {"sources": [s for s in SOURCES if not country or country.lower() in s["country"].lower()],
            "warning": "directory_only sources are NOT live searchable through this server"}


@mcp.tool()
def search_local_legal_documents(query: str, jurisdiction: str = "", limit: int = 10) -> dict:
    """Search only legally imported, locally indexed documents, with provenance."""
    if not query.strip():
        return {"error": "Query must not be empty"}
    return {"results": local_search(query, jurisdiction, limit), "scope": "authorized_local_index_only",
            "warning": "Check the original and amendment status before relying on any legal text"}


@mcp.tool()
def get_local_legal_document(document_id: int) -> dict:
    """Return full text of an imported document with its provenance and rights note."""
    con = connect()
    try:
        row = con.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone()
        return dict(row) if row else {"error": "Document not found"}
    finally:
        con.close()


@mcp.tool()
async def search_uk_legislation(query: str, limit: int = 10) -> dict:
    """Search UK legislation using its documented public Atom feed (live API)."""
    if not query.strip():
        return {"error": "Query must not be empty"}
    params = urlencode({"text": query.strip(), "results-count": max(1, min(limit, 20))})
    url = f"https://www.legislation.gov.uk/all/data.feed?{params}"
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=False,
            headers={"User-Agent": "ArabIraqiLegalLibraryMCP/0.1 (academic research; contact: configure-operator-contact)"}) as client:
            response = await client.get(url)
            response.raise_for_status()
        root = ET.fromstring(response.content)
        ns = {"a": "http://www.w3.org/2005/Atom"}
        results = []
        for entry in root.findall("a:entry", ns):
            title = entry.findtext("a:title", default="", namespaces=ns)
            updated = entry.findtext("a:updated", default="", namespaces=ns)
            link = next((l.attrib.get("href", "") for l in entry.findall("a:link", ns)
                         if l.attrib.get("rel", "alternate") == "alternate"), "")
            results.append({"title": title, "updated": updated, "source_url": link,
                            "jurisdiction": "United Kingdom", "verification": "official_feed_metadata"})
        return {"results": results, "feed_url": url, "source": "legislation.gov.uk",
                "warning": "Check whether text is revised and whether amendments are in force"}
    except (httpx.HTTPError, ET.ParseError) as exc:
        return {"error": type(exc).__name__, "message": "UK legislation API temporarily unavailable or returned invalid data", "feed_url": url}


@mcp.tool()
def legal_citation_template(jurisdiction: str, title: str, citation: str,
                            source_url: str, publication_date: str = "") -> dict:
    """Format user-provided citation metadata; does not validate the cited source."""
    if not source_url.startswith("https://"):
        return {"error": "An HTTPS source URL is required"}
    return {"citation": f"{title}، {citation}، {jurisdiction}، {publication_date}، المصدر: {source_url}",
            "verified": False, "note": "بيانات التوثيق مقدمة من المستخدم ولم يتم التحقق منها"}


if __name__ == "__main__":
    if os.getenv("LEGAL_ENABLE_SERVER") != "true":
        raise RuntimeError("Server deployment disabled")
    connect()
    mcp.run(transport="streamable-http")
