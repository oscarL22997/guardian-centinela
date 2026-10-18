"""Pruebas del tratamiento: las tablas tratadas no tienen duplicados ni nulos en columnas clave."""
from pathlib import Path

import pandas as pd
import pytest

SALIDA = Path(__file__).resolve().parents[1] / "salida"


@pytest.fixture(scope="module")
def t():
    return {n: pd.read_csv(SALIDA / f"{n}.csv", dtype=str)
            for n in ["usuarios", "dispositivos", "transacciones", "lista_negra", "dataset_modelo"]}


@pytest.mark.parametrize("tabla,clave", [("usuarios", "usuario_id"), ("dispositivos", "dispositivo_id"),
                                         ("transacciones", "transaccion_id"), ("lista_negra", "entrada_id"),
                                         ("dataset_modelo", "transaccion_id")])
def test_sin_duplicados_ni_nulos_en_clave(t, tabla, clave):
    assert t[tabla][clave].notna().all()
    assert not t[tabla][clave].duplicated().any()


def test_columnas_clave_de_transacciones_completas(t):
    tx = t["transacciones"]
    for c in ["usuario_id", "ts_utc", "monto_usd", "moneda", "canal", "mcc"]:
        assert tx[c].notna().all(), c
    assert (tx.monto_usd.astype(float) > 0).all()
    assert set(tx.moneda) <= {"CLP", "USD"}
    assert set(tx.canal) <= {"app", "web", "pos", "api"}


def test_lista_negra_normalizada(t):
    ln = t["lista_negra"]
    assert set(ln.tipo) == {"ip", "dispositivo", "comercio", "tarjeta"}
    assert not ln.duplicated(["tipo", "valor"]).any()
    assert (ln.valor == ln.valor.str.strip()).all()


def test_dataset_modelo_sin_fuga_y_con_etiqueta(t):
    ds = t["dataset_modelo"]
    assert "revisado_por_analista" not in ds.columns and "motivo_bloqueo" not in ds.columns
    assert ds.es_fraude.isin(["0", "1"]).all()
    assert set(ds.conjunto) == {"entrenamiento", "prueba"}
    # split temporal: toda la prueba es posterior al entrenamiento
    assert ds[ds.conjunto == "entrenamiento"].ts_utc.max() <= ds[ds.conjunto == "prueba"].ts_utc.min()
