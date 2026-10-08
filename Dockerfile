FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DATA_DIR=/data \
    PORT=8000 \
    TZ=Europe/Budapest

# tzdata: a napi mentés a helyi nap szerint készüljön
RUN apt-get update \
 && apt-get install -y --no-install-recommends tzdata \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --system --uid 10001 --no-create-home --home-dir /app app \
 && mkdir -p /data && chown 10001:10001 /data

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY static ./static
COPY examples ./examples

USER 10001
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD ["python", "-c", "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/api/health' % os.environ.get('PORT','8000'), timeout=4)"]

CMD ["sh", "-c", "exec uvicorn --factory app.main:create_app --host 0.0.0.0 --port \"$PORT\" --proxy-headers --forwarded-allow-ips='*' --no-server-header"]
