FROM python:3.12-slim

WORKDIR /app

COPY shared/ /app/shared/

COPY gateway/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY gateway/app/ /app/app/

ENV PYTHONPATH=/app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
