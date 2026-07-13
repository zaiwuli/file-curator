# syntax=docker/dockerfile:1.7

FROM node:22-alpine AS web-build
WORKDIR /build/apps/web

COPY apps/web/package.json apps/web/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci

COPY apps/web/ ./
ARG VITE_BASE_PATH=./
ARG FILE_CURATOR_VERSION=dev
ENV VITE_BASE_PATH=${VITE_BASE_PATH} \
    VITE_FILE_CURATOR_VERSION=${FILE_CURATOR_VERSION}
RUN npm run typecheck && npm run test && npm run build


FROM python:3.14-slim AS api-build
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /build

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip build
COPY apps/api/ ./apps/api/
RUN python -m build --wheel --outdir /build/wheels ./apps/api


FROM python:3.14-slim AS runtime
ARG FILE_CURATOR_VERSION=dev
ARG APP_UID=1000
ARG APP_GID=1000

LABEL org.opencontainers.image.title="File Curator" \
      org.opencontainers.image.description="Local-first, explainable file organization" \
      org.opencontainers.image.source="https://github.com/zaiwuli/file-curator" \
      org.opencontainers.image.version="${FILE_CURATOR_VERSION}"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FILE_CURATOR_HOST=0.0.0.0 \
    FILE_CURATOR_PORT=8080 \
    FILE_CURATOR_CONFIG_DIR=/config \
    FILE_CURATOR_SOURCES_DIR=/sources \
    FILE_CURATOR_UI_DIR=/app/static \
    FILE_CURATOR_BASE_PATH=/ \
    FILE_CURATOR_VERSION=${FILE_CURATOR_VERSION} \
    FILE_CURATOR_ALEMBIC_CONFIG=/app/alembic.ini \
    HOME=/tmp

RUN groupadd --gid "${APP_GID}" filecurator \
    && useradd --uid "${APP_UID}" --gid "${APP_GID}" --no-create-home --shell /usr/sbin/nologin filecurator \
    && mkdir -p /app/static /config /sources \
    && chown -R filecurator:filecurator /app /config /sources

COPY --from=api-build /build/wheels/*.whl /tmp/wheels/
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install /tmp/wheels/*.whl \
    && rm -rf /tmp/wheels
COPY --from=web-build --chown=filecurator:filecurator /build/apps/web/dist/ /app/static/
COPY --from=api-build --chown=filecurator:filecurator /build/apps/api/alembic.ini /app/alembic.ini
COPY --from=api-build --chown=filecurator:filecurator /build/apps/api/migrations/ /app/migrations/

WORKDIR /app
USER filecurator:filecurator
EXPOSE 8080
VOLUME ["/config", "/sources"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health/live', timeout=3)"]

CMD ["python", "-m", "file_curator"]
