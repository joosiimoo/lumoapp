FROM alpine:3.20

RUN apk add --no-cache \
    python3 \
    py3-pip \
    python3-dev \
    gcc \
    musl-dev \
    libpq \
    postgresql-dev \
    linux-headers \
    tzdata

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_BREAK_SYSTEM_PACKAGES=1

COPY pyproject.toml alembic.ini /app/
COPY app /app/app
COPY migrations /app/migrations
RUN python3 -m pip install --no-cache-dir .

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.bootstrap.app:create_app --factory --host 0.0.0.0 --port 8000"]
