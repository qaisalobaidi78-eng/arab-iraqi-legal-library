"""Import authorized JSONL legal documents. No website crawling.
Each JSONL line: title,jurisdiction,doc_type,citation,publication_date,
source_url,rights_note,text_body,authorization_confirmed=true.
"""
import argparse
import json
from pathlib import Path
from server import connect


def main():
    p = argparse.ArgumentParser()
    p.add_argument("jsonl", type=Path)
    p.add_argument("--confirm-rights", action="store_true", help="Confirm permission to index and use these texts")
    args = p.parse_args()
    if not args.confirm_rights:
        p.error("Explicit --confirm-rights required")
    con = connect()
    count = 0
    try:
        for line_no, line in enumerate(args.jsonl.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            item = json.loads(line)
            required = ("title", "jurisdiction", "doc_type", "source_url", "rights_note", "text_body")
            if not all(item.get(k) for k in required) or item.get("authorization_confirmed") is not True:
                raise ValueError(f"Line {line_no}: required fields or rights confirmation missing")
            if not item["source_url"].startswith("https://"):
                raise ValueError(f"Line {line_no}: HTTPS source_url required")
            con.execute("""INSERT INTO documents
                (title,jurisdiction,doc_type,citation,publication_date,source_url,rights_note,text_body)
                VALUES (?,?,?,?,?,?,?,?)""", tuple(item.get(k, "") for k in
                ("title", "jurisdiction", "doc_type", "citation", "publication_date", "source_url", "rights_note", "text_body")))
            count += 1
        con.commit()
    finally:
        con.close()
    print(f"Imported {count} authorized documents")


if __name__ == "__main__":
    main()
