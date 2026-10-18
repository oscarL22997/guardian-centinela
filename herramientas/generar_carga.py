"""Genera carga contra el sistema y mide latencia (IE2, IE8).

    python herramientas/generar_carga.py --url http://localhost:8080 --n 600 --concurrencia 10

Solo usa la biblioteca estándar. Mientras corre, en otra terminal:  docker stats
"""
import argparse
import json
import random
import statistics
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

MCC = ["5411", "5812", "5912", "5541", "6011", "7995", "4814"]


def una(url, usuarios, pref):
    u = random.choice(usuarios)
    cuerpo = {"usuario_id": u["usuario_id"], "dispositivo_id": u.get("dispositivo_id"),
              "monto": random.choice([3500, 12000, 24700, 89000, 250000]), "moneda": "CLP",
              "canal": random.choice(["app", "web", "pos"]), "mcc": random.choice(MCC),
              "pais_transaccion": random.choice(["CL"] * 8 + ["AR", "NG"]), "intentos_previos_1h": random.choice([0, 0, 1, 3])}
    req = urllib.request.Request(url + pref + "/evaluar", data=json.dumps(cuerpo).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            b = json.loads(r.read())
            return (time.perf_counter() - t0) * 1000, r.status, b.get("replica_ia"), b.get("origen")
    except Exception as e:  # noqa: BLE001
        return (time.perf_counter() - t0) * 1000, getattr(e, "code", 0), None, "error"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8080")
    ap.add_argument("--n", type=int, default=600)
    ap.add_argument("--concurrencia", type=int, default=10)
    ap.add_argument("--prefijo", default="/api/dominio", help="ruta del dominio detrás del gateway")
    a = ap.parse_args()
    usuarios = json.loads(urllib.request.urlopen(a.url + a.prefijo + "/usuarios?limit=50").read())
    t0 = time.time()
    with ThreadPoolExecutor(a.concurrencia) as ex:
        res = list(ex.map(lambda _: una(a.url, usuarios, a.prefijo), range(a.n)))
    dur = time.time() - t0
    lat = sorted(r[0] for r in res if r[1] == 200)
    q = lambda p: lat[min(len(lat) - 1, int(p * len(lat)))]  # noqa: E731
    replicas, origenes = {}, {}
    for _, _, rep, ori in res:
        replicas[rep] = replicas.get(rep, 0) + 1
        origenes[ori] = origenes.get(ori, 0) + 1
    print(f"peticiones={a.n} ok={len(lat)} duración={dur:.1f}s rendimiento={a.n / dur:.1f} req/s "
          f"({a.n / dur * 60:.0f} req/min)")
    if lat:
        print(f"latencia ms: p50={q(.5):.1f} p95={q(.95):.1f} p99={q(.99):.1f} máx={lat[-1]:.1f} "
              f"media={statistics.mean(lat):.1f}")
    print("réplicas de IA que respondieron:", replicas)
    print("origen de la decisión:", origenes)


if __name__ == "__main__":
    main()
