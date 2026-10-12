# Build context is the repository root (so db/migrations can be copied in).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MIGRATIONS_PATH=/app/migrations \
    STORAGE_PATH=/data/storage

# WeasyPrint turns the application sheets into a PDF, and draws them with Pango and Cairo.
RUN apt-get update \
 && apt-get install --no-install-recommends -y \
      libpango-1.0-0 libpangoft2-1.0-0 libcairo2 libgdk-pixbuf-2.0-0 libffi8 fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY api/app ./app
COPY db/migrations ./migrations
COPY api/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh \
 && useradd --system --uid 10001 tripproof \
 && mkdir -p /data/storage && chown -R tripproof /data

USER tripproof
EXPOSE 8000
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
