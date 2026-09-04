FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY app ./app
COPY alembic.ini ./
COPY migrations ./migrations
COPY start.sh ./
RUN chmod +x start.sh

EXPOSE 8000

CMD ["./start.sh"]
