"""Microservicio de dominio de Guardián Centinela.

Es el ÚNICO servicio que lee y escribe la base de datos. Orquesta la evaluación de una
transacción (RF1): valida la entrada, aplica las reglas duras (RF4, RF8), calcula la
velocidad (RF10), llama al microservicio de IA a través del gateway, aplica los umbrales
versionados (RF3) o la política de reserva (RNF3) y registra la decisión (RF7, RNF7).
"""
from __future__ import annotations

import os
import re
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional
from zoneinfo import ZoneInfo

import httpx
from fastapi import FastAPI, Header, HTTPException, Query, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool
from pydantic import BaseModel, Field, field_validator

DSN = os.getenv("DATABASE_URL", "postgresql://centinela:centinela@db:5432/centinela")
IA_URL = os.getenv("IA_URL", "http://gateway:8080/api/ia")
IA_TIMEOUT_S = float(os.getenv("IA_TIMEOUT_MS", "300")) / 1000
RIESGO_API_KEY = os.getenv("RIESGO_API_KEY", "")  # vacío = cambio de umbrales deshabilitado
CLP_POR_USD = 950.0
ZONA_CL = ZoneInfo("America/Santiago")
PAN_RE = re.compile(r"\d{13,19}")

pool: ConnectionPool  # se crea en el arranque (lifespan)
http = httpx.Client(timeout=IA_TIMEOUT_S)

DECISIONES = Counter("gc_dominio_decisiones_total", "Decisiones emitidas", ["decision", "origen"])
LATENCIA = Histogram("gc_dominio_latencia_segundos", "Latencia de /evaluar de punta a punta",
                     buckets=(.005, .01, .025, .05, .075, .1, .15, .25, .5, 1))
FALLAS_IA = Counter("gc_dominio_fallas_ia_total", "Llamadas a IA que fallaron o excedieron el tiempo", ["motivo"])


@asynccontextmanager
async def lifespan(_: FastAPI):
    global pool
    pool = ConnectionPool(DSN, min_size=1, max_size=int(os.getenv("DB_POOL_MAX", "8")), open=True,
                          kwargs={"row_factory": dict_row})
    yield
    pool.close()


app = FastAPI(title="Guardián Centinela · Dominio", version="1.0.0", lifespan=lifespan,
              root_path=os.getenv("ROOT_PATH", ""))

# ---------------------------------------------------------------- contrato


class Transaccion(BaseModel):
    transaccion_id: Optional[str] = Field(default=None, max_length=40)
    usuario_id: str = Field(min_length=3, max_length=20)
    dispositivo_id: Optional[str] = Field(default=None, max_length=40)
    comercio_id: Optional[str] = Field(default=None, max_length=20)
    monto: float = Field(gt=0, le=500_000_000)
    moneda: Literal["CLP", "USD"]
    canal: Literal["app", "web", "pos", "api"]
    mcc: str = Field(pattern=r"^\d{4}$")
    pais_transaccion: str = Field(min_length=2, max_length=2)
    ip: Optional[str] = None
    tarjeta_enmascarada: Optional[str] = None
    intentos_previos_1h: Optional[int] = Field(default=None, ge=0, le=100)
    timestamp_utc: Optional[datetime] = None

    @field_validator("tarjeta_enmascarada")
    @classmethod
    def sin_pan(cls, v):  # RNF5 / RT4: el PAN nunca entra al sistema
        if v and PAN_RE.search(v.replace(" ", "").replace("-", "")):
            raise ValueError("Se recibió un número de tarjeta completo (PAN). Solo se acepta el enmascarado ****NNNN")
        return v

    @field_validator("pais_transaccion")
    @classmethod
    def mayus(cls, v):
        return v.upper()


class NuevoUmbral(BaseModel):
    umbral_revisar: float = Field(ge=0, le=1)
    umbral_bloquear: float = Field(ge=0, le=1)
    politica_reserva: Literal["reglas", "aprobar", "bloquear"] = "reglas"
    modo: Literal["sombra", "activo"] = "sombra"
    autor: str = Field(min_length=3)
    motivo: str = Field(min_length=10)

# ---------------------------------------------------------------- utilidades


def ip_valida(ip: Optional[str]) -> int:
    if not ip:
        return 0
    partes = ip.split(".")
    return int(len(partes) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in partes) and ip != "0.0.0.0")


def umbrales_vigentes(cur) -> dict:
    cur.execute("SELECT * FROM umbrales ORDER BY version DESC LIMIT 1")
    u = cur.fetchone()
    if not u:
        raise HTTPException(503, "No hay umbrales cargados")
    return u


def reglas_duras(cur, t: Transaccion) -> tuple[Optional[str], list[dict]]:
    """RF4/RF8: listas negras vigentes. Mandan por sobre el modelo."""
    candidatos = [("dispositivo", t.dispositivo_id), ("ip", t.ip), ("tarjeta", t.tarjeta_enmascarada),
                  ("comercio", t.comercio_id)]
    candidatos = [(tp, v) for tp, v in candidatos if v]
    if not candidatos:
        return None, []
    cur.execute("SELECT tipo, valor, motivo, entrada_id FROM lista_negra WHERE vigente AND (tipo, valor) IN ("
                + ",".join(["(%s,%s)"] * len(candidatos)) + ")", [x for par in candidatos for x in par])
    hits = cur.fetchall()
    razones = [{"tipo": "regla", "variable": f"lista_negra_{h['tipo']}",
                "detalle": f"{h['valor']} vetado ({h['motivo']}, {h['entrada_id']})"} for h in hits]
    if any(h["tipo"] in ("dispositivo", "ip", "tarjeta") for h in hits):
        return "bloquear", razones
    if hits:  # un comercio vetado fuerza revisión, no bloqueo masivo (riesgo R7)
        return "revisar", razones
    return None, []


def velocidad(cur, usuario_id: str, dispositivo_id: Optional[str], ts: datetime) -> dict:
    """RF10: cuenta transacciones previas en ventanas cortas (historial + decisiones nuevas)."""
    cur.execute("""
        SELECT
          (SELECT count(*) FROM transacciones WHERE usuario_id=%(u)s AND ts_utc >= %(t)s - interval '10 min' AND ts_utc < %(t)s)
        + (SELECT count(*) FROM predicciones  WHERE usuario_id=%(u)s AND creado_utc >= %(t)s - interval '10 min' AND creado_utc < %(t)s) AS u10,
          (SELECT count(*) FROM transacciones WHERE usuario_id=%(u)s AND ts_utc >= %(t)s - interval '24 hours' AND ts_utc < %(t)s)
        + (SELECT count(*) FROM predicciones  WHERE usuario_id=%(u)s AND creado_utc >= %(t)s - interval '24 hours' AND creado_utc < %(t)s) AS u24,
          (SELECT count(*) FROM transacciones WHERE dispositivo_id=%(d)s AND ts_utc >= %(t)s - interval '1 hour' AND ts_utc < %(t)s)
        + (SELECT count(*) FROM predicciones  WHERE dispositivo_id=%(d)s AND creado_utc >= %(t)s - interval '1 hour' AND creado_utc < %(t)s) AS d1
    """, {"u": usuario_id, "d": dispositivo_id, "t": ts})
    r = cur.fetchone()
    return {"tx_usuario_10min": r["u10"], "tx_usuario_24h": r["u24"], "tx_dispositivo_1h": r["d1"] if dispositivo_id else 0}


def politica_reserva(politica: str, t: Transaccion, monto_usd: float, regla: Optional[str]) -> tuple[str, list]:
    """RNF3 / ADR-3: qué se decide si la IA no responde a tiempo. La elige riesgo en la tabla umbrales."""
    if politica == "aprobar":
        return regla or "aprobar", [{"tipo": "reserva", "variable": "politica_reserva", "detalle": "aprobar todo"}]
    if politica == "bloquear":
        return "bloquear", [{"tipo": "reserva", "variable": "politica_reserva", "detalle": "bloquear todo"}]
    # 'reglas': réplica mínima del motor actual (DA2)
    if regla:
        return regla, [{"tipo": "reserva", "variable": "politica_reserva", "detalle": "motor de reglas: lista negra"}]
    if monto_usd > 150 or (t.intentos_previos_1h or 0) >= 3 or t.pais_transaccion != "CL":
        return "revisar", [{"tipo": "reserva", "variable": "politica_reserva",
                            "detalle": "motor de reglas: monto > USD 150, 3+ intentos o país extranjero"}]
    return "aprobar", [{"tipo": "reserva", "variable": "politica_reserva", "detalle": "motor de reglas: sin alertas"}]

# ---------------------------------------------------------------- endpoints


@app.get("/health")
def health():
    try:
        with pool.connection(timeout=2) as con:
            con.execute("SELECT 1")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(503, f"base no disponible: {e.__class__.__name__}")
    return {"estado": "ok", "servicio": "dominio"}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/evaluar")
def evaluar(t: Transaccion):
    t0 = time.perf_counter()
    ts = (t.timestamp_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)
    tx_id = t.transaccion_id or f"TXN-{uuid.uuid4().hex[:12].upper()}"
    monto_usd = t.monto if t.moneda == "USD" else t.monto / CLP_POR_USD

    with pool.connection() as con, con.cursor() as cur:
        umb = umbrales_vigentes(cur)
        cur.execute("SELECT * FROM usuarios WHERE usuario_id=%s", (t.usuario_id,))
        usr = cur.fetchone()
        disp = None
        if t.dispositivo_id:
            cur.execute("SELECT * FROM dispositivos WHERE dispositivo_id=%s", (t.dispositivo_id,))
            disp = cur.fetchone()
        regla, razones_regla = reglas_duras(cur, t)
        vel = velocidad(cur, t.usuario_id, t.dispositivo_id, ts)
        t_bd = time.perf_counter()

        b = lambda v: None if v is None else int(v)  # noqa: E731
        entrada_ia = {
            "transaccion_id": tx_id, "monto_usd": round(monto_usd, 4), "hora_local": ts.astimezone(ZONA_CL).hour,
            "canal": t.canal, "mcc": t.mcc, "pais_transaccion": t.pais_transaccion,
            "intentos_previos_1h": t.intentos_previos_1h, **vel,
            "ip_valida": ip_valida(t.ip), "coordenadas_validas": 1, "en_lista_negra": int(bool(razones_regla)),
            "usuario_conocido": int(usr is not None),
            "u_pais": usr and usr["pais"], "u_segmento": usr and usr["segmento"],
            "u_nivel_kyc": usr and usr["nivel_kyc"], "u_verificado": b(usr and usr["verificado"]),
            "u_edad_cuenta_dias": usr and usr["edad_cuenta_dias"],
            "u_transacciones_previas": usr and usr["transacciones_previas"],
            "u_email_desechable": b(usr and usr["email_desechable"]),
            "u_telefono_verificado": b(usr and usr["telefono_verificado"]),
            "d_tipo": disp and disp["tipo"], "d_usuarios_distintos": disp and disp["usuarios_distintos"],
            "d_emulador": b(disp and disp["emulador"]), "d_so_inconsistente": b(disp and disp["so_inconsistente"]),
        }

        prob, version_modelo, replica, razones_modelo, origen, falla = None, None, None, [], "modelo", None
        try:
            r = http.post(f"{IA_URL}/predict", json=entrada_ia)
            r.raise_for_status()
            ia = r.json()
            prob, version_modelo, replica = ia["probabilidad_fraude"], ia["version_modelo"], ia["replica"]
            razones_modelo = [{"tipo": "modelo", **x} for x in ia["razones"]]
        except httpx.TimeoutException:
            falla = "timeout"
        except httpx.HTTPStatusError as e:
            falla = f"http_{e.response.status_code}: el gateway no obtuvo respuesta de la IA"
        except (httpx.HTTPError, KeyError, ValueError) as e:
            falla = f"error: {e.__class__.__name__}"

        t_ia = time.perf_counter()
        if falla:
            FALLAS_IA.labels(falla.split(":")[0]).inc()
            decision, razones = politica_reserva(umb["politica_reserva"], t, monto_usd, regla)
            razones = razones_regla + razones + [{"tipo": "reserva", "variable": "ia_no_disponible", "detalle": falla}]
            origen = "reserva"
        else:
            decision = "aprobar"
            if prob >= float(umb["umbral_bloquear"]):
                decision = "bloquear"
            elif prob >= float(umb["umbral_revisar"]):
                decision = "revisar"
            severidad = {"aprobar": 0, "revisar": 1, "bloquear": 2}
            if regla and severidad[regla] >= severidad[decision]:
                decision, origen = regla, "regla_dura"
            razones = razones_regla + razones_modelo

        lat_ms = (time.perf_counter() - t0) * 1000
        cur.execute("""
            INSERT INTO predicciones (transaccion_id, usuario_id, dispositivo_id, entrada, probabilidad, decision,
                origen, razones, version_modelo, version_umbrales, modo, replica_ia, latencia_ms, creado_utc)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING prediccion_id, creado_utc""",
                    (tx_id, t.usuario_id, t.dispositivo_id,
                     Jsonb({"solicitud": t.model_dump(mode="json"), "variables_ia": entrada_ia}),
                     prob, decision, origen, Jsonb(razones), version_modelo, umb["version"], umb["modo"], replica,
                     round(lat_ms, 3), ts))
        reg = cur.fetchone()
        con.commit()

    LATENCIA.observe(time.perf_counter() - t0)
    DECISIONES.labels(decision, origen).inc()
    return {"prediccion_id": reg["prediccion_id"], "transaccion_id": tx_id, "decision": decision, "origen": origen,
            "modo": umb["modo"], "aplicada": umb["modo"] == "activo",
            "probabilidad_fraude": prob, "razones": razones, "version_modelo": version_modelo,
            "version_umbrales": umb["version"],
            "umbrales": {"revisar": float(umb["umbral_revisar"]), "bloquear": float(umb["umbral_bloquear"])},
            "replica_ia": replica, "latencia_ms": round(lat_ms, 2),
            "desglose_ms": {"contexto_y_reglas_bd": round((t_bd - t0) * 1000, 2), "llamada_ia": round((t_ia - t_bd) * 1000, 2),
                            "registro_bd": round((time.perf_counter() - t_ia) * 1000, 2)},
            "fecha_utc": reg["creado_utc"].isoformat()}


@app.get("/predicciones")
def predicciones(limit: int = Query(20, ge=1, le=200)):
    with pool.connection() as con:
        return con.execute("""SELECT prediccion_id, transaccion_id, usuario_id, decision, origen, probabilidad,
                                      version_modelo, version_umbrales, modo, replica_ia, latencia_ms, creado_utc
                               FROM predicciones ORDER BY prediccion_id DESC LIMIT %s""", (limit,)).fetchall()


@app.get("/predicciones/{transaccion_id}")
def reproducir(transaccion_id: str):
    """RF7: qué versión del modelo, qué datos y qué umbral decidieron una transacción."""
    with pool.connection() as con:
        filas = con.execute("""SELECT p.*, u.umbral_revisar, u.umbral_bloquear, u.politica_reserva, u.autor AS umbral_autor
                               FROM predicciones p JOIN umbrales u ON u.version = p.version_umbrales
                               WHERE p.transaccion_id=%s ORDER BY p.prediccion_id""", (transaccion_id,)).fetchall()
    if not filas:
        raise HTTPException(404, "Sin decisiones registradas para esa transacción")
    return filas


@app.get("/resumen")
def resumen():
    with pool.connection() as con:
        dec = con.execute("SELECT decision, origen, count(*) n FROM predicciones GROUP BY 1,2 ORDER BY 1,2").fetchall()
        lat = con.execute("""SELECT count(*) n,
                                    percentile_cont(0.5) WITHIN GROUP (ORDER BY latencia_ms) p50,
                                    percentile_cont(0.99) WITHIN GROUP (ORDER BY latencia_ms) p99
                             FROM predicciones WHERE creado_utc > now() - interval '1 hour'""").fetchone()
        base = con.execute("""SELECT (SELECT count(*) FROM usuarios) usuarios, (SELECT count(*) FROM dispositivos) dispositivos,
                                     (SELECT count(*) FROM lista_negra WHERE vigente) lista_negra_vigente,
                                     (SELECT count(*) FROM transacciones) transacciones,
                                     (SELECT count(*) FROM predicciones) predicciones""").fetchone()
    return {"tablas": base, "decisiones": dec, "latencia_ultima_hora_ms": lat}


@app.get("/usuarios")
def usuarios(limit: int = Query(25, ge=1, le=200)):
    """Usuarios de ejemplo para el formulario del front (algunos con historial de fraude)."""
    with pool.connection() as con:
        return con.execute("""
            (SELECT u.usuario_id, u.pais, u.segmento, u.nivel_kyc, 'con_fraude' AS perfil,
                    (SELECT t.dispositivo_id FROM transacciones t WHERE t.usuario_id=u.usuario_id AND t.es_fraude
                     AND t.dispositivo_id IS NOT NULL LIMIT 1) dispositivo_id
             FROM usuarios u WHERE EXISTS (SELECT 1 FROM transacciones t WHERE t.usuario_id=u.usuario_id AND t.es_fraude
                                          AND t.dispositivo_id IS NOT NULL)
             ORDER BY u.usuario_id LIMIT %(n)s)
            UNION ALL
            (SELECT u.usuario_id, u.pais, u.segmento, u.nivel_kyc, 'normal',
                    (SELECT t.dispositivo_id FROM transacciones t WHERE t.usuario_id=u.usuario_id AND t.dispositivo_id IS NOT NULL LIMIT 1)
             FROM usuarios u WHERE u.verificado AND u.nivel_kyc >= 2 ORDER BY u.usuario_id LIMIT %(n)s)""",
                           {"n": limit}).fetchall()


@app.get("/usuarios/{usuario_id}")
def usuario(usuario_id: str):
    with pool.connection() as con:
        u = con.execute("SELECT * FROM usuarios WHERE usuario_id=%s", (usuario_id,)).fetchone()
    if not u:
        raise HTTPException(404, "usuario no encontrado")
    return u


@app.get("/lista-negra")
def lista_negra(tipo: Literal["ip", "dispositivo", "comercio", "tarjeta"], valor: str):
    with pool.connection() as con:
        r = con.execute("SELECT * FROM lista_negra WHERE tipo=%s AND valor=%s", (tipo, valor.strip())).fetchone()
    return {"vetado": bool(r and r["vigente"]), "entrada": r}


@app.get("/umbrales")
def get_umbrales():
    with pool.connection() as con:
        return con.execute("SELECT * FROM umbrales ORDER BY version DESC").fetchall()


@app.post("/umbrales", status_code=201)
def post_umbrales(n: NuevoUmbral, x_api_key: str = Header(default="")):
    """RF3 + RNF10 + RO5: riesgo publica una nueva versión; nunca se edita una existente."""
    if not RIESGO_API_KEY or x_api_key != RIESGO_API_KEY:
        raise HTTPException(403, "Solo el rol riesgo puede cambiar umbrales (X-Api-Key)")
    if n.umbral_revisar >= n.umbral_bloquear:
        raise HTTPException(422, "umbral_revisar debe ser menor que umbral_bloquear")
    with pool.connection() as con:
        r = con.execute("""INSERT INTO umbrales (umbral_revisar, umbral_bloquear, politica_reserva, modo, autor, motivo)
                           VALUES (%s,%s,%s,%s,%s,%s) RETURNING *""",
                        (n.umbral_revisar, n.umbral_bloquear, n.politica_reserva, n.modo, n.autor, n.motivo)).fetchone()
        con.commit()
    return r


@app.get("/info")
def info():
    return {"ia_url": IA_URL, "ia_timeout_ms": IA_TIMEOUT_S * 1000, "umbrales_editables": bool(RIESGO_API_KEY),
            "ahora_utc": datetime.now(timezone.utc).isoformat(), "zona": str(ZONA_CL),
            "ventanas_velocidad": [str(timedelta(minutes=10)), str(timedelta(hours=24)), str(timedelta(hours=1))]}

