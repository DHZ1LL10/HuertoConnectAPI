FROM python:3.12-slim

WORKDIR /app

# Dependencias del sistema necesarias para SQLite
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsqlite3-dev \
    && rm -rf /var/lib/apt/lists/*

# Instalar dependencias Python (capa cacheada eficientemente)
COPY agent-service/requirements.txt .
RUN pip install --no-cache-dir --default-timeout=600 -r requirements.txt

# Copiar el código del agente
COPY agent-service/app/ /app/app/

# Directorio para la base de datos SQLite persistida vía volumen Docker
RUN mkdir -p /app/data

# Usuario no-root por seguridad en producción
RUN adduser --disabled-password --gecos "" agentuser \
    && chown -R agentuser:agentuser /app
USER agentuser

ENV PYTHONPATH=/app

EXPOSE 8006

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8006"]
