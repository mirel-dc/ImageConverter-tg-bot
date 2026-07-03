# syntax=docker/dockerfile:1
FROM python:3.12-slim

# Install curl for uv installer and any system deps needed by PIL/Pillow
RUN set -eux; \
    for attempt in 1 2 3 4 5; do \
      apt-get -o Acquire::Retries=5 update \
      && apt-get -o Acquire::Retries=5 install -y --no-install-recommends \
         curl \
         libjpeg62-turbo \
         zlib1g \
         libpng16-16 \
         libwebp7 \
         libopenjp2-7 \
         libheif1 \
      && break; \
      if [ "$attempt" = "5" ]; then exit 1; fi; \
      apt-get clean; \
      rm -rf /var/lib/apt/lists/*; \
      sleep $((attempt * 5)); \
    done; \
    rm -rf /var/lib/apt/lists/*

# Install uv (Python package/dependency manager)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Create app directory
WORKDIR /app/src

# Copy project files
# Copy only what is needed first for better layer caching
COPY pyproject.toml uv.lock .python-version ./
# Then copy the source code
COPY . ./

# Pre-download dependencies into a virtualenv for faster startups.
# This will create .venv inside /app/src
RUN uv sync --frozen --no-dev

# Use .env via docker-compose; fallback to example for local runs
# (docker-compose will supply env_file at runtime)

# Run the bot
CMD ["uv", "run", "--no-dev", "python", "-m", "bot.bot"]
