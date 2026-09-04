# Dockerfile for 24/7 Persistent Worker Engine & Playwright Headless Browsers
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies & Playwright browser libraries
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    curl \
    git \
    libglib2.0-0 \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libxkbcommon0 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

COPY jobpilot/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir playwright scrapfly-sdk arq
RUN playwright install chromium --with-deps

COPY . .

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

CMD ["python", "jobpilot/run.py"]
