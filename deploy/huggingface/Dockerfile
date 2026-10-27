# All-in-one image for the public demo on Hugging Face Spaces (Docker SDK, one exposed port).
#
# The production layout is docker-compose.yml (separate db / redis / api / worker / web
# containers). A Space runs a single container, so here the same services run under
# supervisord: PostgreSQL 16 + pgvector, Redis, FastAPI, Celery worker, Next.js on :7860.
#
# The source is cloned from GitHub at build time, so the Space repo only contains this
# Dockerfile and a README. Build locally from the working tree instead with:
#   docker build --build-context src=. -f deploy/huggingface/Dockerfile -t docintel-demo .

ARG REPO_URL=https://github.com/piyaldeb/ai-document-intelligence.git
# Pinned by scripts/deploy-hf-space.sh to the commit being deployed (reproducible builds;
# a new value also invalidates the build cache).
ARG GIT_REF=main

# ---------------------------------------------------------------- source
FROM alpine:3.20 AS clone
ARG REPO_URL
ARG GIT_REF
RUN apk add --no-cache git \
    && git init -q /repo && cd /repo \
    && git remote add origin "$REPO_URL" \
    && git fetch -q --depth 1 origin "$GIT_REF" \
    && git checkout -q FETCH_HEAD \
    && rm -rf /repo/.git

FROM scratch AS src
COPY --from=clone /repo/ /

# ---------------------------------------------------------------- web build
FROM node:22-bookworm-slim AS web
WORKDIR /web
COPY --from=src /frontend/package.json /frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY --from=src /frontend/app ./app
COPY --from=src /frontend/components ./components
COPY --from=src /frontend/lib ./lib
COPY --from=src /frontend/public ./public
COPY --from=src /frontend/next.config.ts /frontend/tsconfig.json /frontend/postcss.config.mjs /frontend/eslint.config.mjs ./
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# ---------------------------------------------------------------- runtime
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    OMP_THREAD_LIMIT=1 NEXT_TELEMETRY_DISABLED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates gnupg \
    && install -d /usr/share/postgresql-common/pgdg \
    && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
    && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" \
       > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
       postgresql-16 postgresql-16-pgvector redis-server supervisor \
       tesseract-ocr tesseract-ocr-eng tesseract-ocr-osd libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=node:22-bookworm-slim /usr/local/bin/node /usr/local/bin/node

WORKDIR /app
COPY --from=src /backend/requirements.txt ./
RUN pip install -r requirements.txt
RUN mkdir -p /models \
    && python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5', cache_dir='/models')"

COPY --from=src /backend/ /app/
COPY --from=web /web/.next/standalone /web
COPY --from=web /web/.next/static /web/.next/static
COPY --from=web /web/public /web/public
COPY --from=src /eval/dataset/ /opt/docintel/samples/
COPY --from=src /deploy/huggingface/start.sh /deploy/huggingface/supervisord.conf /deploy/huggingface/seed_demo.py /opt/docintel/

# Spaces run the container as uid 1000.
RUN useradd --uid 1000 --create-home user \
    && chmod +x /opt/docintel/start.sh \
    && chown -R user:user /app /web /models /opt/docintel
USER user

ENV HOME=/home/user \
    DATA_DIR=/home/user/data \
    PATH=/usr/lib/postgresql/16/bin:$PATH \
    DATABASE_URL=postgresql+psycopg://docintel@127.0.0.1:5432/docintel \
    REDIS_URL=redis://127.0.0.1:6379/0 \
    STORAGE_DIR=/home/user/data/uploads \
    EMBEDDING_CACHE_DIR=/models \
    BACKEND_URL=http://127.0.0.1:8000 \
    EXTRACTION_PROVIDER=rules \
    DEMO_MODE=true \
    DEMO_RESET_HOURS=24 \
    MAX_UPLOAD_MB=15 \
    MAX_FILES_PER_REQUEST=20 \
    MAX_PDF_PAGES=300 \
    RATE_LIMIT_PER_MINUTE=300 \
    OCR_WORKERS=2 \
    LLM_MAX_CONCURRENCY=2

EXPOSE 7860
CMD ["/opt/docintel/start.sh"]
