FROM python:3.12-slim

WORKDIR /app

COPY shared/ /app/shared/

COPY huertos-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY huertos-service/app/ /app/app/

ENV PYTHONPATH=/app

EXPOSE 8002

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
