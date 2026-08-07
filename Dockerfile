FROM python:3.11-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 appuser \
    && useradd --uid 10001 --gid appuser --create-home --shell /usr/sbin/nologin appuser

COPY --from=ghcr.io/astral-sh/uv:0.11.31 /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:${PATH}"

# Installed before copying app code so this layer is cached across code changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-cache

COPY app ./app

# /backups is baked in (empty) so a fresh named volume mounted here inherits
# appuser's ownership instead of root's.
RUN mkdir -p /backups && chown -R appuser:appuser /app /backups

USER appuser

# Documentation only - actual publishing happens via docker-compose `ports:`
# (or `docker run -p`) and must match config.yml's `server.port`.
EXPOSE 8080

ENTRYPOINT ["python", "-m", "app.main"]
CMD ["--config", "/app/config.yml"]
