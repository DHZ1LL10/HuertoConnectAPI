FROM python:3.12-slim

WORKDIR /app

COPY shared/ /app/shared/
COPY migrations/ /app/migrations/
COPY alembic.ini /app/alembic.ini

COPY reportes-service/requirements.txt .
RUN pip install --no-cache-dir --default-timeout=600 -r requirements.txt

COPY reportes-service/app/ /app/app/

ENV PYTHONPATH=/app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

RUN adduser --disabled-password --gecos "" reportesuser
USER reportesuser

EXPOSE 8005

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8005"]
