FROM python:3.11-slim

# Keep Python output unbuffered for logs in container environments.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first for better build caching.
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy application code last to avoid invalidating cached layers on every change.
COPY . /app

CMD ["python", "producer.py"]
