# Single-container image for small hosts (Render free tier, Cloud Run, Fly, ...): the web app
# (Next.js) and the API (FastAPI) in one service, with an external PostgreSQL (+ pgvector).
#
# The service is stateless:
#   * file bytes are stored in Postgres (STORAGE_BACKEND=db)
#   * documents are processed inside the upload request (PROCESSING_MODE=inline), no worker/Redis
# The production layout with background workers is docker-compose.yml.
#   docker build -f deploy/container/Dockerfile -t docintel-app .

# ---------------------------------------------------------------- web build
FROM node:22-bookworm-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/app ./app
COPY frontend/components ./components
COPY frontend/lib ./lib
COPY frontend/public ./public
COPY frontend/next.config.ts frontend/tsconfig.json frontend/postcss.config.mjs frontend/eslint.config.mjs ./
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# ---------------------------------------------------------------- runtime
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    OMP_THREAD_LIMIT=1 NEXT_TELEMETRY_DISABLED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng tesseract-ocr-osd libgomp1 supervisor \
    && rm -rf /var/lib/apt/lists/*
COPY --from=node:22-bookworm-slim /usr/local/bin/node /usr/local/bin/node

WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install -r requirements.txt
RUN mkdir -p /models \
    && python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5', cache_dir='/models')"

COPY backend/app /app/app
COPY backend/alembic /app/alembic
COPY backend/alembic.ini /app/alembic.ini
COPY eval/dataset/pdf /app/demo_samples/pdf
COPY eval/dataset/spreadsheets /app/demo_samples/spreadsheets
COPY eval/dataset/validation /app/demo_samples/validation
COPY eval/dataset/images /app/demo_samples/images
COPY eval/dataset/scanned /app/demo_samples/scanned
COPY eval/dataset/crossverify /app/demo_samples/crossverify
COPY eval/dataset/corrupted /app/demo_samples/corrupted
COPY --from=web /web/.next/standalone /web
COPY --from=web /web/.next/static /web/.next/static
COPY --from=web /web/public /web/public
COPY deploy/container/supervisord.conf deploy/container/start.sh deploy/container/demo_seed.py /etc/docintel/

RUN useradd --uid 10001 --create-home app \
    && id app >/dev/null \
    && mkdir -p /tmp/docintel \
    && chmod +x /etc/docintel/start.sh \
    && chown -R app:app /app /web /models /tmp/docintel
USER app

ENV HOME=/home/app \
    PORT=8080 \
    BACKEND_URL=http://127.0.0.1:8000 \
    PROCESSING_MODE=inline \
    STORAGE_BACKEND=db \
    STORAGE_DIR=/tmp/docintel/uploads \
    REDIS_URL= \
    EMBEDDING_CACHE_DIR=/models \
    EXTRACTION_PROVIDER=rules \
    DEMO_MODE=true \
    DEMO_SAMPLES_DIR=/app/demo_samples \
    MAX_UPLOAD_MB=5 \
    MAX_FILES_PER_REQUEST=5 \
    MAX_PDF_PAGES=60 \
    MAX_OCR_PAGES=10 \
    DEMO_MAX_DOCUMENTS=120 \
    DEMO_SEED_SET=light \
    EMBEDDINGS_ENABLED=false \
    OCR_WORKERS=1 \
    OCR_DPI=200 \
    MALLOC_ARENA_MAX=2 \
    NODE_OPTIONS=--max-old-space-size=160

EXPOSE 8080
CMD ["/etc/docintel/start.sh"]
