FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# 패키지 버전 고정: requirements.txt(직접 의존성) + constraints.txt(간접 의존성까지 전체)
COPY requirements.txt constraints.txt ./
RUN pip install --no-cache-dir -r requirements.txt -c constraints.txt

COPY . .

# 시작 시 DB 마이그레이션(web 서비스에서만) 후 커맨드 실행
RUN chmod +x /app/docker-entrypoint.sh
ENTRYPOINT ["/app/docker-entrypoint.sh"]

EXPOSE 8000

CMD ["gunicorn", "app.main:app", "-k", "uvicorn_worker.UvicornWorker", "-w", "2", "-b", "0.0.0.0:8000", "--timeout", "180", "--forwarded-allow-ips", "*"]
