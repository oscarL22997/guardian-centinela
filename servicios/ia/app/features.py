"""Construcción del vector de variables del modelo.

Es el ÚNICO lugar donde se transforma la entrada en números. Lo usan:
  - entrenar.py   (sobre datos/salida/dataset_modelo.csv)
  - app/main.py   (sobre el JSON que llega a POST /predict)
Así no hay diferencias entre entrenamiento y servicio (training/serving skew).
Los faltantes quedan como NaN: XGBoost aprende hacia qué rama enviarlos.
"""
from __future__ import annotations

import math
from typing import Any, Mapping

CANALES = ["app", "web", "pos", "api"]
MCC = ["4814", "4900", "5411", "5541", "5691", "5732", "5812", "5912", "5999", "6011", "7011", "7995"]
TIPOS_DISP = ["android", "ios", "web", "pos"]

NOMBRES: list[str] = (
    ["monto_usd_log", "hora_local", "nocturna_0_6", "pais_extranjero", "pais_distinto_usuario",
     "intentos_previos_1h", "tx_usuario_10min", "tx_usuario_24h", "tx_dispositivo_1h",
     "ip_valida", "coordenadas_validas", "en_lista_negra",
     "usuario_conocido", "u_nivel_kyc", "u_verificado", "u_edad_cuenta_dias", "u_transacciones_previas_log",
     "u_email_desechable", "u_telefono_verificado", "u_segmento_comercio",
     "dispositivo_presente", "d_usuarios_distintos", "d_emulador", "d_so_inconsistente"]
    + [f"canal_{c}" for c in CANALES]
    + [f"mcc_{m}" for m in MCC]
    + [f"d_tipo_{t}" for t in TIPOS_DISP]
)

NAN = float("nan")


def _num(v: Any) -> float:
    if v is None:
        return NAN
    try:
        f = float(v)
    except (TypeError, ValueError):
        return NAN
    return NAN if math.isnan(f) else f


def _txt(v: Any) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return ""
    return str(v).strip().lower()


def vectorizar(p: Mapping[str, Any]) -> list[float]:
    monto = _num(p.get("monto_usd"))
    hora = _num(p.get("hora_local"))
    pais_tx = _txt(p.get("pais_transaccion")).upper()
    pais_u = _txt(p.get("u_pais")).upper()
    canal = _txt(p.get("canal"))
    mcc = _txt(p.get("mcc")).split(".")[0]
    d_tipo = _txt(p.get("d_tipo"))
    previas = _num(p.get("u_transacciones_previas"))
    segmento = _txt(p.get("u_segmento"))
    disp_presente = 1.0 if d_tipo else 0.0

    v = [
        math.log1p(monto) if not math.isnan(monto) else NAN,
        hora,
        (1.0 if 0 <= hora < 6 else 0.0) if not math.isnan(hora) else NAN,
        (1.0 if pais_tx and pais_tx != "CL" else 0.0) if pais_tx else NAN,
        (1.0 if pais_tx != pais_u else 0.0) if (pais_tx and pais_u) else NAN,
        _num(p.get("intentos_previos_1h")),
        _num(p.get("tx_usuario_10min")),
        _num(p.get("tx_usuario_24h")),
        _num(p.get("tx_dispositivo_1h")),
        _num(p.get("ip_valida")),
        _num(p.get("coordenadas_validas")),
        _num(p.get("en_lista_negra")),
        _num(p.get("usuario_conocido")),
        _num(p.get("u_nivel_kyc")),
        _num(p.get("u_verificado")),
        _num(p.get("u_edad_cuenta_dias")),
        math.log1p(previas) if not math.isnan(previas) else NAN,
        _num(p.get("u_email_desechable")),
        _num(p.get("u_telefono_verificado")),
        (1.0 if segmento.startswith("comercio") else 0.0) if segmento else NAN,
        disp_presente,
        _num(p.get("d_usuarios_distintos")),
        _num(p.get("d_emulador")),
        _num(p.get("d_so_inconsistente")),
    ]
    v += [1.0 if canal == c else 0.0 for c in CANALES]
    v += [1.0 if mcc == m else 0.0 for m in MCC]
    v += [1.0 if d_tipo == t else 0.0 for t in TIPOS_DISP]
    assert len(v) == len(NOMBRES)
    return v
