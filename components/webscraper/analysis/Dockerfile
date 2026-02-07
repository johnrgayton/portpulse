FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY delay_detector.py /app/delay_detector.py

RUN useradd --create-home appuser
USER appuser

CMD ["python", "/app/delay_detector.py"]
