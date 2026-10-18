"""
Guardián Centinela · Tratamiento de datos del caso 3 (Kipu Pagos).

Se ejecuta en el pipeline (job `datos` y job `ia`) y localmente con:

    python datos/preparar.py --crudos datos/crudos --salida datos/salida

Pasos (sección 2.2 del enunciado EP2):
  1. Perfilado antes/después  -> salida/perfilado.json
  2. Limpieza (una regla por problema, con decisión corregir/descartar/marcar)
  3. Integración por claves  (usuario_id, dispositivo_id, lista negra)
  4. Variables de entrada del modelo (mismo contrato que POST /predict)
  5. Separación entrenamiento/prueba temporal y fija (RF11)
  6. Salidas: tablas tratadas para el servicio de carga y dataset del modelo

No usa red ni secretos. Es determinista: dos ejecuciones producen los mismos archivos.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

ZONA_CL = "America/Santiago"
CLP_POR_USD = 950.0  # caso 3, sección 2: USD 26 ≈ $24.700 CLP

PAISES = {
    "cl": "CL", "chile": "CL",
    "ar": "AR", "argentina": "AR",
    "pe": "PE", "peru": "PE", "perú": "PE",
    "br": "BR", "brasil": "BR", "brazil": "BR",
    "co": "CO", "colombia": "CO",
    "us": "US", "usa": "US", "eeuu": "US", "estados unidos": "US",
    "ve": "VE", "venezuela": "VE",
    "ru": "RU", "russia": "RU", "rusia": "RU",
    "ng": "NG", "nigeria": "NG",
}
SEGMENTOS = {
    "persona": "persona", "individuo": "persona",
    "comercio_pequeno": "comercio_pequeno", "comercio pequeño": "comercio_pequeno",
    "comercio pequeno": "comercio_pequeno", "pyme": "comercio_pequeno",
    "comercio_grande": "comercio_grande", "comercio grande": "comercio_grande",
    "empresa": "comercio_grande",
}
CANALES = {"app": "app", "movil": "app", "web": "web", "pos": "pos",
           "punto_venta": "pos", "api": "api"}
TIPOS_LN = {"ip": "ip", "dispositivo": "dispositivo", "device": "dispositivo",
            "comercio": "comercio", "merchant": "comercio",
            "tarjeta": "tarjeta", "card": "tarjeta"}
EMAIL_DESECHABLE = {"mailinator.com", "guerrillamail.com", "tempmail.io", "10minutemail.com"}
SI = {"1", "si", "sí", "true", "s"}
NO = {"0", "no", "false", "n"}
IP_RE = re.compile(r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$")

# Columnas que solo existen DESPUÉS de que un analista revisa (riesgo R2 del caso).
COLUMNAS_FUGA = ["revisado_por_analista", "motivo_bloqueo"]

# ---------------------------------------------------------------- utilidades


def txt(s: pd.Series) -> pd.Series:
    return s.fillna("").astype(str).str.strip()


def a_bool(s: pd.Series) -> pd.Series:
    v = txt(s).str.lower()
    out = pd.Series(pd.NA, index=s.index, dtype="Int64")
    out[v.isin(SI)] = 1
    out[v.isin(NO)] = 0
    return out


def normalizar_pais(s: pd.Series) -> pd.Series:
    v = txt(s).str.lower()
    return v.map(PAISES).fillna(v.str.upper().replace("", pd.NA))


def parsear_fecha(s: pd.Series) -> pd.Series:
    """Fechas sin hora en tres formatos: AAAA-MM-DD, DD/MM/AAAA, DD-MM-AAAA."""
    v = txt(s)
    out = pd.to_datetime(v, format="%Y-%m-%d", errors="coerce")
    out = out.fillna(pd.to_datetime(v, format="%d/%m/%Y", errors="coerce"))
    out = out.fillna(pd.to_datetime(v, format="%d-%m-%Y", errors="coerce"))
    return out.dt.date


def parsear_timestamp(s: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Devuelve (timestamp UTC, marca de zona inferida).

    Regla de limpieza L-TS: 'Z' es UTC; '-04:00'/'-03:00' trae su desfase y se
    convierte a UTC; los formatos sin zona ('AAAA-MM-DD HH:MM:SS' y
    'DD/MM/AAAA HH:MM') se interpretan como hora de Chile y se marcan
    (zona_inferida=1). Evidencia: los reintentos del mismo pago aparecen
    escritos en ambos formatos con 40-80 s de diferencia solo si se asume
    hora de Chile para los que no traen zona.
    """
    v = txt(s)
    utc = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns, UTC]")
    inferida = pd.Series(0, index=s.index, dtype="int64")

    m_z = v.str.match(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
    utc[m_z] = pd.to_datetime(v[m_z], format="%Y-%m-%dT%H:%M:%SZ", utc=True)

    m_off = v.str.match(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d[+-]\d\d:\d\d$")
    utc[m_off] = pd.to_datetime(v[m_off], format="%Y-%m-%d %H:%M:%S%z", utc=True)

    for patron, fmt in [(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d$", "%Y-%m-%d %H:%M:%S"),
                        (r"^\d\d/\d\d/\d{4} \d\d:\d\d$", "%d/%m/%Y %H:%M")]:
        m = v.str.match(patron)
        local = pd.to_datetime(v[m], format=fmt)
        utc[m] = local.dt.tz_localize(ZONA_CL, ambiguous="NaT", nonexistent="shift_forward").dt.tz_convert("UTC")
        inferida[m] = 1
    return utc, inferida


def parsear_monto(monto: pd.Series, moneda: pd.Series) -> pd.DataFrame:
    """Regla L-MONTO. Devuelve valor numérico, moneda resuelta y marca de inferencia.

    - '$' y espacios se eliminan.
    - Coma decimal ('45,54') -> punto.
    - 'N.NNN' (tres dígitos tras el punto) es separador de miles en CLP.
    - 'N.NN' (dos dígitos) es decimal y solo ocurre en USD.
    - Moneda vacía: decimales o entero < 1.000 -> USD; si no, CLP (moneda_inferida=1).
      En la muestra no hay ningún monto CLP entero entre 1 y 999, así que el corte es limpio.
    """
    m = txt(monto).str.replace("$", "", regex=False).str.replace(" ", "", regex=False)
    mon = txt(moneda).str.upper()
    valor = pd.Series(np.nan, index=m.index)
    tiene_miles = m.str.match(r"^-?\d{1,3}(\.\d{3})+$")
    tiene_dec_punto = m.str.match(r"^-?\d+\.\d{1,2}$")
    tiene_dec_coma = m.str.match(r"^-?\d+,\d{1,2}$")
    entero = m.str.match(r"^-?\d+$")

    # Moneda resuelta
    res = mon.where(mon.isin(["CLP", "USD"]), "")
    inferida = res == ""
    res = res.mask(inferida & (tiene_dec_punto | tiene_dec_coma), "USD")
    res = res.mask(inferida & tiene_miles, "CLP")
    ent_val = pd.to_numeric(m.where(entero), errors="coerce")
    res = res.mask(inferida & entero & (ent_val.abs() < 1000), "USD")
    res = res.mask(inferida & entero & (ent_val.abs() >= 1000), "CLP")

    # Valor numérico
    valor[entero] = ent_val[entero]
    valor[tiene_dec_coma] = pd.to_numeric(m[tiene_dec_coma].str.replace(",", "."), errors="coerce")
    valor[tiene_dec_punto] = pd.to_numeric(m[tiene_dec_punto], errors="coerce")
    # 'N.NNN' en CLP = miles; en USD sería un decimal de 3 cifras (no ocurre) -> se trata igual que miles
    valor[tiene_miles] = pd.to_numeric(m[tiene_miles].str.replace(".", "", regex=False), errors="coerce")

    usd = np.where(res == "USD", valor, valor / CLP_POR_USD)
    return pd.DataFrame({"monto_original": valor, "moneda": res.replace("", pd.NA),
                         "moneda_inferida": inferida.astype(int), "monto_usd": np.round(usd, 4)})


def ip_valida(s: pd.Series) -> pd.Series:
    def ok(x: str) -> bool:
        mm = IP_RE.match(x)
        if not mm:
            return False
        octs = [int(g) for g in mm.groups()]
        return all(0 <= o <= 255 for o in octs) and x != "0.0.0.0"
    return txt(s).map(ok)


def perfil(df: pd.DataFrame, clave: str | None) -> dict:
    vacios = (df.isna() | df.astype(str).eq("")).sum()
    return {
        "filas": int(len(df)),
        "columnas": int(df.shape[1]),
        "tipos": {c: str(t) for c, t in df.dtypes.items()},
        "nulos_por_columna": {c: int(v) for c, v in vacios.items() if v > 0},
        "nulos_total": int(vacios.sum()),
        "filas_duplicadas_exactas": int(df.duplicated().sum()),
        "claves_duplicadas": int(df[clave].duplicated().sum()) if clave else None,
    }

# ---------------------------------------------------------------- limpieza por archivo


def limpiar_usuarios(u: pd.DataFrame, log: list) -> pd.DataFrame:
    n0 = len(u)
    u = u.drop_duplicates()
    log.append(("usuarios", "L-U1 filas duplicadas exactas", n0 - len(u), "descartar",
                "son la misma fila exportada dos veces; no aportan información"))
    u = u.drop_duplicates("usuario_id", keep="first")
    out = pd.DataFrame({"usuario_id": txt(u.usuario_id)})
    out["fecha_registro"] = parsear_fecha(u.fecha_registro)
    log.append(("usuarios", "L-U2 fecha_registro en 3 formatos", int(len(u)), "corregir",
                "se normaliza a ISO AAAA-MM-DD; los tres formatos son inequívocos"))
    out["pais"] = normalizar_pais(u.pais)
    log.append(("usuarios", "L-U3 país escrito de 6+ formas (Chile, chile , CL...)",
                int((txt(u.pais) != out["pais"]).sum()), "corregir", "se lleva a ISO-3166 alfa-2"))
    seg = txt(u.segmento).str.lower().map(SEGMENTOS)
    log.append(("usuarios", "L-U4 segmento con sinónimos (individuo, pyme, empresa...)",
                int((txt(u.segmento).str.lower() != seg).sum()), "corregir",
                "se agrupa en persona / comercio_pequeno / comercio_grande"))
    out["segmento"] = seg
    kyc = pd.to_numeric(txt(u.nivel_kyc), errors="coerce")
    fuera = kyc.notna() & ~kyc.between(0, 3)
    log.append(("usuarios", "L-U5 nivel_kyc = -1 (fuera de rango 0-3) o vacío", int(fuera.sum() + kyc.isna().sum()),
                "marcar", "queda NULL; el modelo trata el faltante como señal propia, no se inventa un nivel"))
    out["nivel_kyc"] = kyc.mask(fuera).astype("Int64")
    out["verificado"] = a_bool(u.verificado)
    log.append(("usuarios", "L-U6 verificado como 1/0/si/no/vacío", int(len(u)), "corregir",
                "se lleva a booleano; vacío queda NULL"))
    edad = pd.to_numeric(txt(u.edad_cuenta_dias), errors="coerce")
    log.append(("usuarios", "L-U7 edad_cuenta_dias negativa", int((edad < 0).sum()), "marcar",
                "una cuenta no puede tener edad negativa; queda NULL"))
    out["edad_cuenta_dias"] = edad.mask(edad < 0).astype("Int64")
    out["transacciones_previas"] = pd.to_numeric(txt(u.transacciones_previas), errors="coerce").astype("Int64")
    dom = txt(u.email_dominio).str.lower()
    out["email_dominio"] = dom.replace("", pd.NA)
    out["email_desechable"] = dom.isin(EMAIL_DESECHABLE).astype(int)
    out["telefono_verificado"] = a_bool(u.telefono_verificado)
    return out.reset_index(drop=True)


def limpiar_dispositivos(d: pd.DataFrame, log: list) -> pd.DataFrame:
    out = pd.DataFrame({"dispositivo_id": txt(d.dispositivo_id)})
    tipo = txt(d.tipo).str.lower()
    log.append(("dispositivos", "L-D1 tipo en mayúsculas/minúsculas mezcladas", int((txt(d.tipo) != tipo).sum()),
                "corregir", "se normaliza a minúsculas: android, ios, web, pos"))
    out["tipo"] = tipo
    so = txt(d.sistema_operativo)
    out["sistema_operativo"] = so.replace("", pd.NA)
    so_l = so.str.lower()
    incons = ((tipo == "ios") & so_l.str.contains("android|linux|windows")) | \
             ((tipo == "android") & so_l.str.contains("ios|mac os"))
    log.append(("dispositivos", "L-D2 sistema operativo contradice el tipo (ios con Android)", int(incons.sum()),
                "marcar", "no se corrige: es una señal de huella falsificada; se guarda so_inconsistente=1"))
    out["so_inconsistente"] = incons.astype(int)
    utc, inf = parsear_timestamp(d.primera_vez)
    out["primera_vez_utc"] = utc
    out["usuarios_distintos"] = pd.to_numeric(txt(d.usuarios_distintos), errors="coerce").astype("Int64")
    out["emulador"] = a_bool(d.emulador)
    log.append(("dispositivos", "L-D3 emulador vacío en 70% de filas", int((txt(d.emulador) == "").sum()), "marcar",
                "vacío = no informado por el tag; queda NULL, no se asume 0"))
    out["pais_declarado"] = normalizar_pais(d.pais_declarado)
    return out


def limpiar_lista_negra(ln: pd.DataFrame, log: list) -> pd.DataFrame:
    out = pd.DataFrame({"entrada_id": txt(ln.entrada_id)})
    tipo = txt(ln.tipo).str.lower().map(TIPOS_LN)
    log.append(("lista_negra", "L-L1 tipo en inglés/español y mayúsculas (device, merchant, IP...)",
                int((txt(ln.tipo) != tipo).sum()), "corregir", "4 tipos canónicos: ip, dispositivo, comercio, tarjeta"))
    out["tipo"] = tipo
    out["valor"] = txt(ln.valor)
    log.append(("lista_negra", "L-L2 valor con espacios alrededor", int((ln.valor != txt(ln.valor)).sum()),
                "corregir", "sin el strip la búsqueda exacta de la regla dura falla"))
    out["fecha_alta"] = parsear_fecha(ln.fecha_alta)
    out["motivo"] = txt(ln.motivo).replace("", "sin_motivo")
    out["agregado_por"] = txt(ln.agregado_por).replace("", pd.NA)
    vig = a_bool(ln.vigente)
    log.append(("lista_negra", "L-L3 vigente vacío", int(vig.isna().sum()), "corregir",
                "una entrada se desactiva escribiendo 0; vacío = nunca desactivada -> vigente=1 (vigente_inferido=1)"))
    out["vigente_inferido"] = vig.isna().astype(int)
    out["vigente"] = vig.fillna(1).astype(int)
    antes = len(out)
    out = out.sort_values("fecha_alta").drop_duplicates(["tipo", "valor"], keep="last")
    log.append(("lista_negra", "L-L4 mismo (tipo, valor) dos veces (CM40825)", antes - len(out), "descartar",
                "se conserva la entrada más reciente"))
    return out.sort_values("entrada_id").reset_index(drop=True)


def limpiar_transacciones(t: pd.DataFrame, log: list) -> pd.DataFrame:
    n0 = len(t)
    t = t.drop_duplicates()
    log.append(("transacciones", "L-T1 duplicado del sistema (mismo transaccion_id y fila idéntica)", n0 - len(t),
                "descartar", "es la misma transacción registrada dos veces; contarla dos veces infla la velocidad"))
    t = t.drop_duplicates("transaccion_id", keep="first").reset_index(drop=True)

    out = pd.DataFrame({"transaccion_id": txt(t.transaccion_id), "usuario_id": txt(t.usuario_id),
                        "comercio_id": txt(t.comercio_id).replace("", pd.NA),
                        "dispositivo_id": txt(t.dispositivo_id).replace("", pd.NA)})
    utc, inf = parsear_timestamp(t.timestamp)
    out["ts_utc"] = utc
    out["zona_inferida"] = inf
    log.append(("transacciones", "L-T2 timestamps en UTC, con desfase y sin zona (4 formatos)", int(inf.sum()),
                "corregir", "todo a UTC; los sin zona se asumen hora de Chile y se marcan zona_inferida=1"))

    mm = parsear_monto(t.monto, t.moneda)
    out = pd.concat([out, mm], axis=1)
    log.append(("transacciones", "L-T3 monto con '$', miles con punto, coma decimal", int(len(t)), "corregir",
                "se parsea según formato y moneda; todo se expresa también en USD (950 CLP/USD)"))
    log.append(("transacciones", "L-T4 moneda vacía", int(mm.moneda_inferida.sum()), "corregir",
                "se infiere por formato: decimales o < 1.000 -> USD; si no, CLP (moneda_inferida=1)"))

    out["canal"] = txt(t.canal).str.lower().map(CANALES)
    out["mcc"] = txt(t.mcc)
    out["pais_transaccion"] = normalizar_pais(t.pais_transaccion)
    lat = pd.to_numeric(txt(t.latitud), errors="coerce")
    lon = pd.to_numeric(txt(t.longitud), errors="coerce")
    cero = (lat == 0) & (lon == 0)
    log.append(("transacciones", "L-T5 coordenadas (0,0) en el Golfo de Guinea", int(cero.sum()), "marcar",
                "es un valor por defecto del SDK, no una ubicación; lat/lon quedan NULL"))
    out["latitud"] = lat.mask(cero)
    out["longitud"] = lon.mask(cero)
    out["coordenadas_validas"] = (out.latitud.notna() & out.longitud.notna()).astype(int)
    ipv = ip_valida(t.ip)
    log.append(("transacciones", "L-T6 IP inválida ('-', 'n/a', '0.0.0.0', '999.1.1.1', vacía)", int((~ipv).sum()),
                "marcar", "la IP queda NULL y ip_valida=0; una IP ilegible es en sí una señal"))
    out["ip"] = txt(t.ip).where(ipv)
    out["ip_valida"] = ipv.astype(int)
    out["tarjeta_enmascarada"] = txt(t.tarjeta_enmascarada).replace("", pd.NA)
    out["resultado_autorizacion"] = txt(t.resultado_autorizacion).str.lower()
    out["intentos_previos_1h"] = pd.to_numeric(txt(t.intentos_previos_1h), errors="coerce").astype("Int64")
    out["revisado_por_analista"] = a_bool(t.revisado_por_analista).fillna(0).astype(int)
    out["motivo_bloqueo"] = txt(t.motivo_bloqueo).replace("", pd.NA)
    out["es_fraude"] = a_bool(t.es_fraude)
    log.append(("transacciones", "L-T7 es_fraude como 1/0/si/SI/no/vacío", int(out.es_fraude.isna().sum()), "marcar",
                "vacío = nadie revisó, NO significa legítima: queda NULL y no entra al entrenamiento"))

    # Montos fuera de rango
    neg = out.monto_original < 0
    cero_m = out.monto_original == 0
    sin_monto = out.monto_original.isna()
    log.append(("transacciones", "L-T8 monto negativo", int(neg.sum()), "descartar",
                "es una reversa/devolución, no una compra que haya que autorizar"))
    log.append(("transacciones", "L-T9 monto cero", int(cero_m.sum()), "descartar",
                "no hay compra que evaluar; un cobro de $0 no llega al servicio de fraude"))
    out = out[~(neg | cero_m | sin_monto)]
    sin_ts = out.ts_utc.isna()
    log.append(("transacciones", "L-T10 timestamp ilegible o inexistente (cambio de hora)", int(sin_ts.sum()),
                "descartar", "sin hora no se puede calcular velocidad ni ordenar en el tiempo"))
    out = out[~sin_ts].copy()

    # Reintentos legítimos: mismo usuario+comercio+monto, ID distinto, < 120 s
    out = out.sort_values(["usuario_id", "ts_utc", "transaccion_id"]).reset_index(drop=True)
    g = out.groupby("usuario_id")
    dt = (out.ts_utc - g.ts_utc.shift()).dt.total_seconds()
    mismo = (out.comercio_id.fillna("") == g.comercio_id.shift().fillna("")) & \
            (out.monto_original == g.monto_original.shift())
    out["es_reintento"] = ((dt <= 120) & mismo).astype(int)
    log.append(("transacciones", "L-T11 reintento del cliente (ID nuevo, mismo pago, < 120 s)",
                int(out.es_reintento.sum()), "marcar",
                "NO se borra: es un evento real que el core vio; cuenta para la velocidad (RF10)"))
    return out

# ---------------------------------------------------------------- variables del modelo


def contar_ventana(df: pd.DataFrame, clave: str, segundos: int) -> pd.Series:
    """Cuántas transacciones previas (estrictamente antes) de la misma clave en la ventana."""
    res = pd.Series(0, index=df.index, dtype="int64")
    sub = df[df[clave].notna()].sort_values("ts_utc")
    for _, grp in sub.groupby(clave):
        ts = grp.ts_utc.astype("int64").to_numpy() // 10**9
        izq = np.searchsorted(ts, ts - segundos, side="left")
        res.loc[grp.index] = np.arange(len(ts)) - izq
    return res


def integrar_y_variables(t, u, d, ln, log):
    tx = t.copy()
    tx["usuario_conocido"] = tx.usuario_id.isin(u.usuario_id).astype(int)
    log.append(("integracion", "I-1 transacciones cuyo usuario_id no existe en usuarios.csv",
                int((tx.usuario_conocido == 0).sum()), "marcar",
                "se conservan (el pago ocurrió); las variables de usuario quedan NULL y usuario_conocido=0"))
    sin_disp = tx.dispositivo_id.isna()
    huerf_disp = tx.dispositivo_id.notna() & ~tx.dispositivo_id.isin(d.dispositivo_id)
    log.append(("integracion", "I-2 transacciones sin dispositivo_id", int(sin_disp.sum()), "marcar",
                "típico de POS y API; dispositivo_presente=0"))
    log.append(("integracion", "I-3 dispositivo_id sin pareja en dispositivos.csv", int(huerf_disp.sum()), "marcar",
                "ninguno en la muestra"))
    usados = set(tx.dispositivo_id.dropna())
    log.append(("integracion", "I-4 dispositivos sin ninguna transacción", int((~d.dispositivo_id.isin(usados)).sum()),
                "conservar", "se cargan igual: el dominio los consulta para evaluar transacciones nuevas"))

    vig = ln[ln.vigente == 1]
    sets = {tp: set(vig[vig.tipo == tp].valor) for tp in ["ip", "dispositivo", "comercio", "tarjeta"]}
    tx["en_lista_negra"] = (tx.ip.isin(sets["ip"]) | tx.dispositivo_id.isin(sets["dispositivo"]) |
                            tx.comercio_id.isin(sets["comercio"]) |
                            tx.tarjeta_enmascarada.isin(sets["tarjeta"])).astype(int)
    log.append(("integracion", "I-5 transacciones que tocan una entrada vigente de la lista negra",
                int(tx.en_lista_negra.sum()), "marcar", "alimenta la regla dura RF4/RF8"))

    # Velocidad (RF10): se calcula sobre TODO el historial limpio, no solo el etiquetado
    tx["tx_usuario_10min"] = contar_ventana(tx, "usuario_id", 600)
    tx["tx_usuario_24h"] = contar_ventana(tx, "usuario_id", 86400)
    tx["tx_dispositivo_1h"] = contar_ventana(tx, "dispositivo_id", 3600)
    tx["hora_local"] = tx.ts_utc.dt.tz_convert(ZONA_CL).dt.hour

    uu = u.set_index("usuario_id")
    dd = d.set_index("dispositivo_id")
    m = tx.join(uu[["pais", "segmento", "nivel_kyc", "verificado", "edad_cuenta_dias", "transacciones_previas",
                    "email_desechable", "telefono_verificado"]].add_prefix("u_"), on="usuario_id")
    m = m.join(dd[["tipo", "usuarios_distintos", "emulador", "so_inconsistente"]].add_prefix("d_"), on="dispositivo_id")
    return tx, m


# Contrato de entrada de POST /predict (mismo orden que servicios/ia/app/features.py)
COLUMNAS_PAYLOAD = [
    "transaccion_id", "monto_usd", "hora_local", "canal", "mcc", "pais_transaccion", "intentos_previos_1h",
    "tx_usuario_10min", "tx_usuario_24h", "tx_dispositivo_1h", "ip_valida", "coordenadas_validas",
    "en_lista_negra", "usuario_conocido", "u_pais", "u_segmento", "u_nivel_kyc", "u_verificado",
    "u_edad_cuenta_dias", "u_transacciones_previas", "u_email_desechable", "u_telefono_verificado",
    "d_tipo", "d_usuarios_distintos", "d_emulador", "d_so_inconsistente",
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--crudos", default=str(Path(__file__).parent / "crudos"))
    ap.add_argument("--salida", default=str(Path(__file__).parent / "salida"))
    ap.add_argument("--fraccion-prueba", type=float, default=0.25)
    a = ap.parse_args()
    crudos, salida = Path(a.crudos), Path(a.salida)
    salida.mkdir(parents=True, exist_ok=True)

    leer = lambda n: pd.read_csv(crudos / f"{n}.csv", dtype=str, keep_default_na=False)
    raw = {n: leer(n) for n in ["usuarios", "dispositivos", "transacciones", "lista_negra"]}
    claves = {"usuarios": "usuario_id", "dispositivos": "dispositivo_id",
              "transacciones": "transaccion_id", "lista_negra": "entrada_id"}
    reporte = {"antes": {n: perfil(df, claves[n]) for n, df in raw.items()}}

    log: list = []
    u = limpiar_usuarios(raw["usuarios"], log)
    d = limpiar_dispositivos(raw["dispositivos"], log)
    ln = limpiar_lista_negra(raw["lista_negra"], log)
    t = limpiar_transacciones(raw["transacciones"], log)
    t, m = integrar_y_variables(t, u, d, ln, log)

    # ---- dataset del modelo: solo filas con etiqueta confirmada; sin columnas de fuga
    lab = m[m.es_fraude.notna()].sort_values("ts_utc").reset_index(drop=True)
    corte = int(len(lab) * (1 - a.fraccion_prueba))
    lab["conjunto"] = np.where(np.arange(len(lab)) < corte, "entrenamiento", "prueba")
    fecha_corte = lab.ts_utc.iloc[corte]
    ds = lab[COLUMNAS_PAYLOAD + ["es_fraude", "conjunto", "ts_utc"]].copy()
    ds["es_fraude"] = ds.es_fraude.astype(int)

    # ---- salidas para el servicio de carga
    t_out = t.drop(columns=[]).copy()
    for c in ["ts_utc"]:
        t_out[c] = t_out[c].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    d_out = d.copy()
    d_out["primera_vez_utc"] = d_out.primera_vez_utc.dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    ds_out = ds.copy()
    ds_out["ts_utc"] = ds_out.ts_utc.dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    u.to_csv(salida / "usuarios.csv", index=False)
    d_out.to_csv(salida / "dispositivos.csv", index=False)
    ln.to_csv(salida / "lista_negra.csv", index=False)
    t_out.sort_values("transaccion_id").to_csv(salida / "transacciones.csv", index=False)
    ds_out.to_csv(salida / "dataset_modelo.csv", index=False)

    tratados = {"usuarios": u, "dispositivos": d, "transacciones": t, "lista_negra": ln}
    reporte["despues"] = {n: perfil(df.astype(object).where(df.notna(), ""), claves[n]) for n, df in tratados.items()}
    reporte["reglas"] = [{"archivo": a_, "regla": r, "filas_afectadas": int(n), "decision": dcs, "por_que": p}
                         for a_, r, n, dcs, p in log]
    reporte["modelo"] = {
        "filas_etiquetadas": int(len(lab)),
        "fraudes": int(lab.es_fraude.astype(int).sum()),
        "tasa_fraude_etiquetadas": round(float(lab.es_fraude.astype(int).mean()), 4),
        "tasa_fraude_muestra_completa": round(float(t.es_fraude.fillna(0).astype(int).sum() / len(t)), 4),
        "filas_sin_etiqueta_excluidas": int(t.es_fraude.isna().sum()),
        "columnas_excluidas_por_fuga": COLUMNAS_FUGA + ["resultado_autorizacion"],
        "split": "temporal: 75% más antiguo entrena, 25% más reciente prueba (fijo, RF11)",
        "fecha_corte_utc": str(fecha_corte),
        "entrenamiento": {"filas": int((lab.conjunto == "entrenamiento").sum()),
                          "fraudes": int(lab[lab.conjunto == "entrenamiento"].es_fraude.astype(int).sum())},
        "prueba": {"filas": int((lab.conjunto == "prueba").sum()),
                   "fraudes": int(lab[lab.conjunto == "prueba"].es_fraude.astype(int).sum())},
    }
    (salida / "perfilado.json").write_text(json.dumps(reporte, indent=2, ensure_ascii=False, default=str))

    # resumen legible
    print(f"{'archivo':<14}{'filas antes':>12}{'filas después':>15}{'dup antes':>11}{'nulos antes':>13}{'nulos después':>15}")
    for n in raw:
        a_, b_ = reporte["antes"][n], reporte["despues"][n]
        print(f"{n:<14}{a_['filas']:>12}{b_['filas']:>15}{a_['filas_duplicadas_exactas']:>11}"
              f"{a_['nulos_total']:>13}{b_['nulos_total']:>15}")
    print("\nReglas aplicadas:")
    for r in reporte["reglas"]:
        print(f"  [{r['decision']:<9}] {r['archivo']:<13} {r['regla']}: {r['filas_afectadas']}")
    print("\nDataset del modelo:", json.dumps(reporte["modelo"], ensure_ascii=False))


if __name__ == "__main__":
    main()
