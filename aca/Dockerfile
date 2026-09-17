# Judge demonstration image.
#
# Differs from tokenos/Dockerfile in two deliberate ways:
#
# 1. The Foundry extra (openai, azure-identity) is NOT installed. In simulated
#    mode those packages are never imported, and leaving them out means the
#    running image is physically incapable of reaching a model provider rather
#    than merely configured not to. If a future change accidentally selected the
#    Foundry adapter, it would fail at import instead of spending money.
#
# 2. The build context is the repository root, so this file can reach tokenos/
#    without duplicating the application into a second tree.
#
# Base images are pinned by tag. Both are official images pulled over TLS; no
# certificate verification is disabled anywhere in this build.

FROM node:22-slim AS web-build

WORKDIR /build/web
COPY tokenos/apps/web/package.json tokenos/apps/web/package-lock.json ./
RUN npm ci
COPY tokenos/apps/web/ ./
RUN npm run build

FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/usr/lib/python3/dist-packages \
    TOKENOS_MODEL_MODE=simulated \
    TOKENOS_STORAGE_ROOT=/data/tokenos \
    TOKENOS_WEB_DIST_ROOT=/app/services/tokenos-api/static

WORKDIR /app/services/tokenos-api

# Installed from the distribution rather than PyPI for the same reason as the
# production image: the build network here cannot complete a TLS handshake with
# files.pythonhosted.org. These are the only runtime dependencies the simulated
# build needs, because the provider SDK is deliberately absent.
RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        python3-fastapi \
        python3-pydantic \
        python3-python-multipart \
        python3-uvicorn \
    && rm -rf /var/lib/apt/lists/* \
    && addgroup --system tokenos \
    && adduser --system --ingroup tokenos --home /home/tokenos tokenos \
    && mkdir -p /data/tokenos \
    && chown -R tokenos:tokenos /data/tokenos /home/tokenos

COPY tokenos/services/tokenos-api/ ./
COPY --from=web-build /build/web/dist ./static

# Second line of defence behind the build-context allowlist. Tests are not
# shipped, and a stray SQLite file or .env would expose local run history or
# configuration to visitors.
RUN rm -rf tests .pytest_cache .venv \
    && find . -name '*.sqlite3' -delete \
    && find . -name '.env' -delete \
    && chown -R tokenos:tokenos /app

USER tokenos

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"

CMD ["python", "-m", "uvicorn", "tokenos_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
