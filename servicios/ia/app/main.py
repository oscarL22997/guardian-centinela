"""Microservicio de IA de Guardián Centinela.

Componentes (figura 5.3 del arc42):
  1. Cargador del modelo     -> lee modelo/modelo.json y metadata.json al arrancar
  2. Validador de entrada    -> esquema Pydantic EntradaPrediccion (422 si no cumple)
  3. Vectorizador            -> app.features.vectorizar (mismo código que el entrenamiento)
  4. Motor de inferencia     -> XGBoost Booster.predict(pred_contribs=True)
  5. Explicador              -> aportes TreeSHAP ordenados por peso (RF2)
  6. Respuesta + métricas    -> JSON con versión del modelo; /metrics para Prometheus

No accede a la base de datos: recibe todo lo que necesita en la petición.
"""
from __future__ import annotations

import json
import math
import os
import socket
import time
from pathlib import Path
from typing import Literal, Optional

import numpy as np
import xgboost as xgb
from fastapi import FastAPI, HTTPException, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel, Field

from .features import NOMBRES, vectorizar

DIR_MODELO = Path(os.getenv("DIR_MODELO", Path(__file__).resolve().parent.parent / "modelo"))
REPLICA = os.getenv("NOMBRE_REPLICA") or socket.gethostname()

# ---------------------------------------------------------------- 1. carga del modelo
_booster: Optional[xgb.Booster] = None
_meta: dict = {}


def cargar_modelo() -> None:
    global _booster, _meta
    b = xgb.Booster()
    b.load_model(str(DIR_MODELO / "modelo.json"))
    b.set_param({"nthread": 1})
    _booster = b
    _meta = json.loads((DIR_MODELO / "metadata.json").read_text())


app = FastAPI(title="Guardián Centinela · IA", version="1.0.0", root_path=os.getenv("ROOT_PATH", ""))
PREDICCIONES = Counter("gc_ia_predicciones_total", "Predicciones servidas", ["resultado"])
LATENCIA = Histogram("gc_ia_latencia_segundos", "Latencia de /predict dentro del servicio",
                     buckets=(.001, .0025, .005, .01, .025, .05, .1, .25))


@app.on_event("startup")
def _startup() -> None:
    cargar_modelo()

# ---------------------------------------------------------------- 2. validación de entrada


class EntradaPrediccion(BaseModel):
    transaccion_id: str = Field(min_length=1, max_length=40)
    monto_usd: float = Field(gt=0, le=1_000_000)
    hora_local: int = Field(ge=0, le=23)
    canal: Literal["app", "web", "pos", "api"]
    mcc: str = Field(pattern=r"^\d{4}$")
    pais_transaccion: str = Field(min_length=2, max_length=2)
    intentos_previos_1h: Optional[int] = Field(default=None, ge=0, le=100)
    tx_usuario_10min: int = Field(default=0, ge=0)
    tx_usuario_24h: int = Field(default=0, ge=0)
    tx_dispositivo_1h: int = Field(default=0, ge=0)
    ip_valida: int = Field(default=1, ge=0, le=1)
    coordenadas_validas: int = Field(default=1, ge=0, le=1)
    en_lista_negra: int = Field(default=0, ge=0, le=1)
    usuario_conocido: int = Field(default=1, ge=0, le=1)
    u_pais: Optional[str] = None
    u_segmento: Optional[str] = None
    u_nivel_kyc: Optional[int] = Field(default=None, ge=0, le=3)
    u_verificado: Optional[int] = Field(default=None, ge=0, le=1)
    u_edad_cuenta_dias: Optional[int] = Field(default=None, ge=0)
    u_transacciones_previas: Optional[int] = Field(default=None, ge=0)
    u_email_desechable: Optional[int] = Field(default=None, ge=0, le=1)
    u_telefono_verificado: Optional[int] = Field(default=None, ge=0, le=1)
    d_tipo: Optional[str] = None
    d_usuarios_distintos: Optional[int] = Field(default=None, ge=0)
    d_emulador: Optional[int] = Field(default=None, ge=0, le=1)
    d_so_inconsistente: Optional[int] = Field(default=None, ge=0, le=1)


class Razon(BaseModel):
    variable: str
    aporte: float
    valor: Optional[float]


class SalidaPrediccion(BaseModel):
    transaccion_id: str
    probabilidad_fraude: float
    razones: list[Razon]
    version_modelo: str
    replica: str
    latencia_ms: float

# ---------------------------------------------------------------- endpoints


@app.get("/health")
def health():
    if _booster is None:
        raise HTTPException(503, "modelo no cargado")
    return {"estado": "ok", "servicio": "ia", "version_modelo": _meta.get("version_modelo"), "replica": REPLICA}


@app.get("/modelo")
def modelo():
    return _meta


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/predict", response_model=SalidaPrediccion)
def predict(e: EntradaPrediccion):
    t0 = time.perf_counter()
    # 3. vectorizar
    x = np.array([vectorizar(e.model_dump())], dtype=np.float32)
    # 4. inferencia + 5. explicación en una sola pasada (TreeSHAP)
    contrib = _booster.predict(xgb.DMatrix(x, missing=np.nan, feature_names=NOMBRES), pred_contribs=True)[0]
    margen = float(contrib.sum())
    prob = 1.0 / (1.0 + math.exp(-margen))
    aportes = contrib[:-1]  # el último es el sesgo (bias)
    orden = np.argsort(-np.abs(aportes))[:5]
    razones = [Razon(variable=NOMBRES[i], aporte=round(float(aportes[i]), 4),
                     valor=None if np.isnan(x[0, i]) else round(float(x[0, i]), 4))
               for i in orden if abs(aportes[i]) > 1e-6]
    dt = time.perf_counter() - t0
    LATENCIA.observe(dt)
    PREDICCIONES.labels("alto" if prob >= 0.5 else "bajo").inc()
    return SalidaPrediccion(transaccion_id=e.transaccion_id, probabilidad_fraude=round(prob, 4), razones=razones,
                            version_modelo=_meta["version_modelo"], replica=REPLICA,
                            latencia_ms=round(dt * 1000, 3))
