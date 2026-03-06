# Fly.io デプロイ用（Google Cloud 不要）
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV PORT=8080

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py run_server.py config.py .
COPY static ./static

# Fly.io は PORT を渡す（run_server.py が読む）
EXPOSE 8080

CMD ["python", "run_server.py"]
