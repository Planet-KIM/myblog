FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["gunicorn", "app.main:app", "-k", "uvicorn_worker.UvicornWorker", "-w", "2", "-b", "0.0.0.0:8000", "--timeout", "180", "--forwarded-allow-ips", "*"]
