"""Entrena el modelo mínimo de Guardián Centinela y aplica la compuerta de calidad.

    python servicios/ia/entrenar.py --dataset datos/salida/dataset_modelo.csv --salida servicios/ia/modelo

Sale con código 1 (y el pipeline NO construye la imagen) si la métrica sobre el
conjunto de prueba fijo queda bajo el umbral (RF11). El umbral se fija con la
variable UMBRAL_PR_AUC (por defecto 0.70).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import average_precision_score, confusion_matrix, roc_auc_score

sys.path.insert(0, str(Path(__file__).parent))
from app.features import NOMBRES, vectorizar  # noqa: E402

VERSION_BASE = "1.0.0"
PARAMS = dict(n_estimators=200, max_depth=3, learning_rate=0.08, subsample=0.9, colsample_bytree=0.8,
              min_child_weight=2, reg_lambda=1.0, objective="binary:logistic", eval_metric="aucpr",
              tree_method="hist", random_state=42, n_jobs=1)
UMBRAL_REVISAR, UMBRAL_BLOQUEAR = 0.50, 0.85  # umbrales v1 de referencia (los vigentes viven en la base)


def metricas(y, p, umbral):
    pred = (p >= umbral).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    return {"umbral": umbral, "tp": int(tp), "fp": int(fp), "fn": int(fn), "tn": int(tn),
            "recall_fraude": round(tp / (tp + fn), 4) if tp + fn else None,
            "precision": round(tp / (tp + fp), 4) if tp + fp else None,
            "falsos_positivos_sobre_bloqueos": round(fp / (tp + fp), 4) if tp + fp else None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="datos/salida/dataset_modelo.csv")
    ap.add_argument("--salida", default=str(Path(__file__).parent / "modelo"))
    a = ap.parse_args()
    umbral_gate = float(os.getenv("UMBRAL_PR_AUC", "0.70"))

    df = pd.read_csv(a.dataset, dtype={"mcc": str})
    X = np.array([vectorizar(r) for r in df.to_dict("records")], dtype=float)
    y = df.es_fraude.to_numpy()
    tr, te = (df.conjunto == "entrenamiento").to_numpy(), (df.conjunto == "prueba").to_numpy()

    peso = (y[tr] == 0).sum() / max((y[tr] == 1).sum(), 1)
    modelo = xgb.XGBClassifier(**PARAMS, scale_pos_weight=float(peso))
    modelo.fit(X[tr], y[tr])
    p = modelo.predict_proba(X[te])[:, 1]

    pr_auc = float(average_precision_score(y[te], p))
    roc = float(roc_auc_score(y[te], p))
    base = float(y[te].mean())
    imp = modelo.get_booster().get_score(importance_type="gain")
    importancia = sorted(((NOMBRES[int(k[1:])], round(v, 3)) for k, v in imp.items()), key=lambda x: -x[1])[:10]

    sha = os.getenv("GIT_SHA", "local")[:7]
    meta = {
        "version_modelo": f"{VERSION_BASE}+{sha}",
        "algoritmo": "XGBoost (gradient boosted trees) · explicación por TreeSHAP nativo (pred_contribs)",
        "entrenado_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "commit": os.getenv("GIT_SHA", "local"),
        "variables": NOMBRES,
        "parametros": {**PARAMS, "scale_pos_weight": round(float(peso), 3)},
        "datos": {"entrenamiento_filas": int(tr.sum()), "entrenamiento_fraudes": int(y[tr].sum()),
                  "prueba_filas": int(te.sum()), "prueba_fraudes": int(y[te].sum())},
        "metricas_prueba": {
            "pr_auc": round(pr_auc, 4), "roc_auc": round(roc, 4), "pr_auc_azar": round(base, 4),
            "en_umbral_revisar": metricas(y[te], p, UMBRAL_REVISAR),
            "en_umbral_bloquear": metricas(y[te], p, UMBRAL_BLOQUEAR),
        },
        "compuerta": {"metrica": "pr_auc", "umbral": umbral_gate, "aprobada": pr_auc >= umbral_gate},
        "importancia_top10_gain": importancia,
        "advertencia": ("Probabilidades sobre la muestra etiquetada (11% fraude). En producción la tasa es 0,012%; "
                        "los umbrales de decisión se recalibran en modo sombra (riesgo R3)."),
    }
    print(json.dumps(meta["metricas_prueba"], indent=2, ensure_ascii=False))
    print("Top variables:", importancia[:6])

    if pr_auc < umbral_gate:
        print(f"COMPUERTA FALLIDA: PR-AUC {pr_auc:.3f} < {umbral_gate}. No se publica el modelo.", file=sys.stderr)
        sys.exit(1)

    out = Path(a.salida)
    out.mkdir(parents=True, exist_ok=True)
    modelo.get_booster().save_model(out / "modelo.json")
    (out / "metadata.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    print(f"OK: modelo {meta['version_modelo']} guardado en {out} (PR-AUC {pr_auc:.3f} >= {umbral_gate})")


if __name__ == "__main__":
    main()
