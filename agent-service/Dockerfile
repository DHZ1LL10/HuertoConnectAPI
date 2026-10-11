FROM python:3.12-slim

WORKDIR /app

# Instalar dependencias Python (capa cacheada eficientemente)
COPY agent-service/requirements.txt .
RUN pip install --no-cache-dir --default-timeout=600 -r requirements.txt

# Copiar el código del agente
COPY agent-service/app/ /app/app/

# Usuario no-root por seguridad en producción
RUN adduser --disabled-password --gecos "" agentuser \
    && chown -R agentuser:agentuser /app
USER agentuser

ENV PYTHONPATH=/app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

EXPOSE 8006

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8006"]
