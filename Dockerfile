FROM python:3.12-slim

# Install system deps (poppler for pdf2image, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    libmagic1 \
    tesseract-ocr \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    libcairo2 \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy project files needed for install
COPY pyproject.toml uv.lock README.md ./
COPY src/ src/

# Install dependencies
RUN uv sync --frozen --no-dev

COPY scripts/ scripts/
COPY alembic.ini ./

RUN chmod +x scripts/*.sh

EXPOSE 8000

CMD ["scripts/entrypoint.sh"]
