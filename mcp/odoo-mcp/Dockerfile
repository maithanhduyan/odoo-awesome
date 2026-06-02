FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml .
RUN uv sync --no-dev --frozen

COPY . .

EXPOSE 8080

# stdio transport (default for VS Code / Claude Desktop)
CMD ["uv", "run", "server.py"]
