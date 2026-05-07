FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install -e .

# Default DB lives on a volume so data persists across restarts.
RUN mkdir -p /data
ENV DATABASE_URL=sqlite+aiosqlite:////data/factory.db

CMD ["python", "-m", "bot_factory"]
