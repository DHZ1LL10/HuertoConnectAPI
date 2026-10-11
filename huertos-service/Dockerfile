FROM python:3.12-slim

WORKDIR /app

COPY huertos-service/requirements.txt .
RUN pip install --no-cache-dir --default-timeout=600 -r requirements.txt

COPY shared/ /app/shared/
COPY huertos-service/app/ /app/app/
COPY scripts/migrate_veracruz_regions.py /app/scripts/migrate_veracruz_regions.py

ENV PYTHONPATH=/app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

RUN adduser --disabled-password --gecos "" huertosuser
USER huertosuser

EXPOSE 8002

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
