# Imagen base: python:3.12-slim. Se ejecuta una sola vez y termina (restart: "no").
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt && useradd --system --uid 10001 app
COPY schema.sql carga.py ./
# Tablas tratadas: las produce datos/preparar.py en el pipeline; no se suben los CSV crudos a la imagen
COPY datos ./datos
USER app
CMD ["python", "carga.py"]
