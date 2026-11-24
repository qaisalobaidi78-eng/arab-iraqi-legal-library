FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py import_documents.py ./
COPY data/sources.json data/sources.json
RUN mkdir -p data && useradd -r -u 10001 legal && chown -R legal:legal /app
USER legal
EXPOSE 8000
CMD ["python", "server.py"]
