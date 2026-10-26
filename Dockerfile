FROM python:3.12-slim

ARG COMMIT=unknown
ENV PLANWERK_COMMIT=$COMMIT \
    PLANWERK_HOME=/app \
    PLANWERK_LOG_DIR=/app/logs \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml README.md ./
COPY planwerk ./planwerk
RUN pip install --no-cache-dir ".[ai]"
COPY web ./web
COPY data/sample_case.json ./data/sample_case.json

RUN useradd --system --uid 10001 planwerk && mkdir -p /app/logs && chown planwerk /app/logs
USER planwerk
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/health')"
CMD ["uvicorn", "planwerk.api:app", "--host", "0.0.0.0", "--port", "8765"]
