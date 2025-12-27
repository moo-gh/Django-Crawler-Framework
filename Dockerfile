# Use multi-stage builds
# Stage 1: Build stage
FROM python:3.12-alpine as builder
WORKDIR /app
COPY requirements.txt .

# Install build dependencies
RUN apk add --no-cache --virtual .build-deps \
    build-base python3-dev libpq postgresql-dev gcc jpeg-dev zlib-dev libffi-dev \
    && pip install --no-cache-dir -r requirements.txt \
    # Remove build dependencies
    && apk del .build-deps

# Stage 2: Run stage
FROM python:3.12-alpine
WORKDIR /app

# Copy installed python packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Install runtime dependencies
RUN apk add --no-cache postgresql-dev jpeg-dev \
    && rm -rf /var/cache/apk/*

COPY . .

ENV PYTHONUNBUFFERED 1
ENV PYTHONDONTWRITEBYTECODE 1

CMD ["gunicorn", "--reload", "--workers=2", "--worker-tmp-dir", "/dev/shm", "--bind=0.0.0.0:80", "--chdir", "/app/crawler", "crawler.wsgi"]
