"""Pruebas del microservicio de IA (las ejecuta el workflow antes del build)."""
from fastapi.testclient import TestClient

from app.main import app

ENTRADA_RIESGOSA = {
    "transaccion_id": "TX-TEST-1", "monto_usd": 180.0, "hora_local": 3, "canal": "api", "mcc": "7995",
    "pais_transaccion": "NG", "intentos_previos_1h": 12, "tx_usuario_10min": 4, "ip_valida": 0,
    "u_pais": "CL", "u_segmento": "persona", "u_nivel_kyc": 0, "u_edad_cuenta_dias": 3,
    "d_tipo": "android", "d_usuarios_distintos": 30,
}
ENTRADA_NORMAL = {
    "transaccion_id": "TX-TEST-2", "monto_usd": 6.5, "hora_local": 13, "canal": "pos", "mcc": "5411",
    "pais_transaccion": "CL", "intentos_previos_1h": 0, "u_pais": "CL", "u_segmento": "persona",
    "u_nivel_kyc": 2, "u_verificado": 1, "u_edad_cuenta_dias": 900, "d_tipo": "pos", "d_usuarios_distintos": 1,
}


def test_health():
    with TestClient(app) as c:
        r = c.get("/health")
        assert r.status_code == 200
        assert r.json()["version_modelo"]


def test_predict_entrada_conocida_devuelve_prediccion_valida():
    with TestClient(app) as c:
        r = c.post("/predict", json=ENTRADA_RIESGOSA)
        assert r.status_code == 200
        b = r.json()
        assert 0.0 <= b["probabilidad_fraude"] <= 1.0
        assert b["version_modelo"]
        assert len(b["razones"]) >= 1
        pesos = [abs(x["aporte"]) for x in b["razones"]]
        assert pesos == sorted(pesos, reverse=True)  # RF2: ordenadas por peso


def test_modelo_distingue_riesgo():
    with TestClient(app) as c:
        alto = c.post("/predict", json=ENTRADA_RIESGOSA).json()["probabilidad_fraude"]
        bajo = c.post("/predict", json=ENTRADA_NORMAL).json()["probabilidad_fraude"]
        assert alto > 0.5 > bajo


def test_entrada_invalida_422():
    with TestClient(app) as c:
        malo = dict(ENTRADA_NORMAL, monto_usd=-5, canal="fax")
        assert c.post("/predict", json=malo).status_code == 422
