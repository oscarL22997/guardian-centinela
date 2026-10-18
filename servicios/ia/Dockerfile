# Imagen base: python:3.12-slim (Debian, glibc): xgboost-cpu trae ruedas manylinux listas;
# en alpine (musl) habría que compilarlo. Sin CUDA ni PyTorch: la imagen queda ~330 MB.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt && useradd --system --uid 10001 app
COPY app ./app
# El modelo lo genera el pipeline (preparar.py + entrenar.py) antes del build; no está en el repositorio
COPY modelo ./modelo
USER app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
