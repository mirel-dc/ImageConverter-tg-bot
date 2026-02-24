# syntax=docker/dockerfile:1
FROM python:3.12-slim

# Install curl for uv installer and any system deps needed by PIL/Pillow
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       curl \
       libjpeg62-turbo \
       zlib1g \
       libpng16-16 \
       libwebp7 \
       libopenjp2-7 \
       libheif1 \
    && rm -rf /var/lib/apt/lists/*

# Install uv (Python package/dependency manager)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Create app directory
WORKDIR /app

# Copy project files
# Copy only what is needed first for better layer caching
COPY src/pyproject.toml src/uv.lock src/.python-version ./src/
# Then copy the source code
COPY src ./src

# Default working directory is the src folder where pyproject.toml resides
WORKDIR /app/src

# Pre-download dependencies into a virtualenv for faster startups (optional)
# This will create .venv inside /app/src
RUN uv sync --frozen --no-dev || true

# Use .env via docker-compose; fallback to example for local runs
# (docker-compose will supply env_file at runtime)

# Run the bot
CMD ["uv", "run", "python", "-m", "bot.bot"]
