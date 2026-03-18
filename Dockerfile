FROM python:3.10-slim

WORKDIR /app

# Copiar archivos del proyecto
COPY pyproject.toml .
COPY Makefile .
COPY README.md .
COPY SOUL.md .
COPY src/ ./src/
COPY docs/ ./docs/
COPY data/ ./data/

# Copiar script de entrada
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

# Instalar dependencias
RUN pip install --upgrade pip && \
    pip install -e . "langgraph-cli[inmem]"

# Crear directorios necesarios para la auditoría
RUN mkdir -p data/inbox data/processed data/review data/failed

# Exponer puerto si se usa LangGraph Studio en futuro
EXPOSE 3000 8000

# Ejecutar todos los servicios
ENTRYPOINT ["./entrypoint.sh"]
