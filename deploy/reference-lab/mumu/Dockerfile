# syntax=docker/dockerfile:1.7
# Upstream source context must be pinned to 743e5abec18beb8d73426527e6579538053bc6fd.
FROM node:22-alpine AS frontend
WORKDIR /frontend
ENV NODE_OPTIONS=--max-old-space-size=768
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# Keep the original Vite config and emitted assets; skip only gzip size reporting.
RUN ./node_modules/.bin/tsc -b \
    && node --input-type=module -e \
       "import { build } from 'vite'; await build({ build: { reportCompressedSize: false } });"

FROM python:3.12-slim AS runtime
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    MUMU_UI_ONLY=true ONNX_EMBEDDING_OFFLINE=true \
    HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 ANONYMIZED_TELEMETRY=false \
    APP_HOST=0.0.0.0 APP_PORT=8000
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client netcat-traditional \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 mumu && useradd --uid 10001 --gid mumu --no-create-home mumu
COPY backend/ ./
COPY LICENSE /app/LICENSE
COPY --from=lab_mumu /patch_ui_only.py /tmp/patch_ui_only.py
RUN python /tmp/patch_ui_only.py /app \
    && pip install --no-cache-dir -r requirements.txt \
    && rm /tmp/patch_ui_only.py \
    && cp alembic-postgres.ini alembic.ini \
    && sed -i 's/\r$//' scripts/entrypoint.sh \
    && chmod +x scripts/entrypoint.sh \
    && mkdir -p data logs storage/generated_covers \
    && chown -R mumu:mumu /app
COPY --from=frontend --chown=mumu:mumu /backend/static ./static
LABEL org.opencontainers.image.source="https://github.com/xiamuceer-j/MuMuAINovel" \
    org.opencontainers.image.revision="743e5abec18beb8d73426527e6579538053bc6fd" \
    org.opencontainers.image.licenses="GPL-3.0-only"
USER mumu
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"
ENTRYPOINT ["/app/scripts/entrypoint.sh"]
