FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY news_scraper.py /app/news_scraper.py
COPY sources.py /app/sources.py

RUN useradd --create-home appuser
USER appuser

CMD ["python", "/app/news_scraper.py"]
