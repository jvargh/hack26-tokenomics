FROM node:22-slim AS web-build

WORKDIR /build/web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci
COPY apps/web/ ./
RUN npm run build

FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/usr/lib/python3/dist-packages \
    TOKENOS_STORAGE_ROOT=/tmp/tokenos/runtime \
    TOKENOS_WEB_DIST_ROOT=/app/services/tokenos-api/static

WORKDIR /app/services/tokenos-api

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        python3-fastapi \
        python3-pydantic \
        python3-python-multipart \
        python3-uvicorn \
    && rm -rf /var/lib/apt/lists/* \
    && addgroup --system tokenos \
    && adduser --system --ingroup tokenos --home /home/tokenos tokenos \
    && mkdir -p /tmp/tokenos/runtime \
    && chown -R tokenos:tokenos /tmp/tokenos /home/tokenos

# Foundry extra (openai + azure-identity) is vendored as wheels: the container
# network in this environment cannot reach PyPI directly, so the wheels are
# pre-downloaded on the host (see vendor-wheels/README.md) and installed offline.
COPY vendor-wheels/ /tmp/vendor-wheels/
RUN pip install --no-index --find-links=/tmp/vendor-wheels --no-cache-dir --ignore-installed openai azure-identity aiohttp \
    && rm -rf /tmp/vendor-wheels

COPY services/tokenos-api/ ./
COPY --from=web-build /build/web/dist ./static

USER tokenos

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"

CMD ["python", "-m", "uvicorn", "tokenos_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
