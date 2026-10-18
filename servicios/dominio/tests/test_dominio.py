"""Pruebas del microservicio de dominio.

- Unitarias (sin base): contrato de entrada, PAN rechazado, política de reserva.
- Integración (si existe DATABASE_URL): flujo /evaluar completo contra PostgreSQL real,
  con el servicio de IA simulado (y caído) mediante httpx.MockTransport.
"""
import os

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main
from app.main import Transaccion, app, ip_valida, politica_reserva

BASE = {"usuario_id": "KP300532", "monto": 25000, "moneda": "CLP", "canal": "app", "mcc": "5411",
        "pais_transaccion": "cl"}


def test_pan_completo_es_rechazado():
    with pytest.raises(ValueError):
        Transaccion(**BASE, tarjeta_enmascarada="4111 1111 1111 1111")
    assert Transaccion(**BASE, tarjeta_enmascarada="****1111").pais_transaccion == "CL"


def test_ip_valida():
    assert ip_valida("10.0.0.1") == 1
    assert ip_valida("999.1.1.1") == 0 and ip_valida("0.0.0.0") == 0 and ip_valida(None) == 0


def test_politica_reserva():
    t = Transaccion(**BASE)
    assert politica_reserva("aprobar", t, 26, None)[0] == "aprobar"
    assert politica_reserva("bloquear", t, 26, None)[0] == "bloquear"
    assert politica_reserva("reglas", t, 26, None)[0] == "aprobar"
    assert politica_reserva("reglas", t, 500, None)[0] == "revisar"
    assert politica_reserva("aprobar", t, 26, "bloquear")[0] == "bloquear"  # la regla dura siempre manda


requiere_db = pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="sin base de datos")


def ia_simulada(request: httpx.Request) -> httpx.Response:
    cuerpo = __import__("json").loads(request.content)
    return httpx.Response(200, json={"transaccion_id": cuerpo["transaccion_id"], "probabilidad_fraude": 0.91,
                                     "razones": [{"variable": "monto_usd_log", "aporte": 1.2, "valor": 5.1}],
                                     "version_modelo": "test", "replica": "ia-test", "latencia_ms": 1.0})


def ia_caida(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("ia caída")


@requiere_db
def test_evaluar_guarda_prediccion(monkeypatch):
    monkeypatch.setattr(main, "http", httpx.Client(transport=httpx.MockTransport(ia_simulada)))
    with TestClient(app) as c:
        assert c.get("/health").status_code == 200
        r = c.post("/evaluar", json=BASE)
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["decision"] == "bloquear" and b["origen"] == "modelo" and b["version_modelo"] == "test"
        rep = c.get(f"/predicciones/{b['transaccion_id']}").json()
        assert rep[0]["version_umbrales"] == b["version_umbrales"]


@requiere_db
def test_ia_caida_aplica_politica_de_reserva(monkeypatch):
    monkeypatch.setattr(main, "http", httpx.Client(transport=httpx.MockTransport(ia_caida)))
    with TestClient(app) as c:
        b = c.post("/evaluar", json=BASE).json()
        assert b["origen"] == "reserva" and b["decision"] in ("aprobar", "revisar", "bloquear")


@requiere_db
def test_umbrales_protegidos():
    with TestClient(app) as c:
        r = c.post("/umbrales", json={"umbral_revisar": 0.4, "umbral_bloquear": 0.9, "autor": "x" * 3,
                                      "motivo": "prueba de acceso"})
        assert r.status_code == 403
