# Use multi-stage builds
# Stage 1: Build stage
FROM python:3.12-alpine as builder

# Set environment variables for build
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install build dependencies
RUN apk add --no-cache \
    build-base \
    python3-dev \
    postgresql-dev \
    jpeg-dev \
    zlib-dev \
    libffi-dev

# Create virtual environment to isolate dependencies
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: Run stage
FROM python:3.12-alpine

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install ONLY runtime dependencies (smaller than -dev packages)
RUN apk add --no-cache \
    libpq \
    libjpeg-turbo \
    && rm -rf /var/cache/apk/*

# Copy only the required source code
COPY crawler ./crawler

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# The --chdir /app/crawler flag ensures gunicorn finds manage.py and the wsgi file
CMD ["gunicorn", "--reload", "--workers=2", "--worker-tmp-dir", "/dev/shm", "--bind=0.0.0.0:80", "--chdir", "/app/crawler", "crawler.wsgi"]
