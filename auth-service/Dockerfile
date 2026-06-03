FROM python:3.12-slim

WORKDIR /app

# Copy shared library
COPY shared/ /app/shared/

# Copy service requirements and install
COPY auth-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy service code
COPY auth-service/app/ /app/app/

# Set Python path to include shared
ENV PYTHONPATH=/app

EXPOSE 8001

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
