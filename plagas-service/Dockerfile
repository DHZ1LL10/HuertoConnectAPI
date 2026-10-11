FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y libgl1 libglib2.0-0 libsm6 libxext6 libxrender-dev libxcb1 && rm -rf /var/lib/apt/lists/*

COPY plagas-service/requirements.txt .
RUN pip install --no-cache-dir --default-timeout=600 -r requirements.txt

COPY shared/ /app/shared/
COPY migrations/ /app/migrations/
COPY alembic.ini /app/alembic.ini
COPY plagas-service/app/ /app/app/

ENV PYTHONPATH=/app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 YOLO_CONFIG_DIR=/tmp/ultralytics

RUN adduser --disabled-password --gecos "" plagasuser
USER plagasuser

EXPOSE 8003

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003"]
