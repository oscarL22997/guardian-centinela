"""Prueba del servicio de carga: correrlo dos veces no duplica filas (requiere DATABASE_URL y DIR_DATOS)."""
import os
import sys
from pathlib import Path

import psycopg
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import carga  # noqa: E402

pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="sin base de datos")


def conteos():
    with psycopg.connect(os.environ["DATABASE_URL"]) as c:
        return {t: c.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
                for t in ["usuarios", "dispositivos", "lista_negra", "transacciones", "umbrales"]}


def test_carga_idempotente():
    carga.main()
    primera = conteos()
    carga.main()
    assert conteos() == primera
    assert primera["transacciones"] > 20000 and primera["umbrales"] >= 1
