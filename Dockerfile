FROM python:3.11.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock README.md ./
RUN pip install --no-cache-dir uv \
    && uv sync --frozen --no-dev

COPY src ./src
COPY scripts ./scripts
COPY get_data.py traverse_sitemap.py populate_db.py ./

EXPOSE 5000
CMD ["uv", "run", "--no-sync", "python", "src/api.py"]
