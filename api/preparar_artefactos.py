"""Genera los artefactos de la API (modelo + panel + metadatos) a partir de los datos versionados con DVC.

Uso (desde la raíz del repo, con `dvc pull` hecho):
    python api/preparar_artefactos.py                      # modelo provisional (Gradient Boosting)
    python api/preparar_artefactos.py --run-id <RUN_ID>    # modelo escogido, tomado de MLflow

Con --run-id el modelo se descarga del servidor MLflow (variables MLFLOW_TRACKING_USERNAME y
MLFLOW_TRACKING_PASSWORD). Así la API sirve exactamente el modelo registrado en el experimento.

Salidas (api/artefactos/): modelo.joblib, panel.csv, metadatos.json
         api/requirements.txt (versiones exactas con las que se generó el modelo)
"""
import argparse
import json
import platform
import re
import sys
from datetime import datetime
from importlib import metadata
from pathlib import Path

import joblib
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))
import modelos_comunes as mc  # noqa: E402  (mismas variables y pipeline que los notebooks)

ARTEFACTOS = RAIZ / "api" / "artefactos"
REQUISITOS = RAIZ / "api" / "requirements.txt"
COLUMNAS_PANEL = ["vehiculo", "fecha", "contrato", "km", "odo_fin_dia", "con_registro", "dato_faltante",
                  "apta_modelo"]


def verificar_anonimizado(km: pd.DataFrame) -> None:
    """El repositorio es público: aborta si los datos no parecen anonimizados."""
    malos_v = [v for v in km["vehiculo"].unique() if not re.fullmatch(r"VH-\d{2}", str(v))]
    malos_c = [c for c in km["contrato"].dropna().unique() if not re.fullmatch(r"Contrato [A-Z]|Traslado", str(c))]
    if malos_v or malos_c:
        sys.exit(f"ERROR: datos sin anonimizar (vehículos {malos_v[:3]}, contratos {malos_c[:3]}). No se genera nada.")


def version(paquete):
    try:
        return metadata.version(paquete)
    except metadata.PackageNotFoundError:
        return None


def cargar_modelo(run_id, train):
    if run_id:
        import mlflow
        mc.configurar_mlflow()
        pipeline = mlflow.sklearn.load_model(f"runs:/{run_id}/model")
        run = mlflow.get_run(run_id)
        nombre = f"{run.data.tags.get('modelo', 'modelo')} ({run.info.run_name})"
        return pipeline, nombre, f"MLflow run {run_id}"
    from sklearn.ensemble import GradientBoostingRegressor
    Xtr, ytr = mc.separar_xy(train)
    pipeline = mc.construir_pipeline(GradientBoostingRegressor(random_state=42)).fit(Xtr, ytr)
    return pipeline, "GradientBoostingRegressor (provisional)", "provisional: entrenado por este script"


def main(run_id):
    if not mc.RUTA_CSV.exists():
        sys.exit(f"No existe {mc.RUTA_CSV}. Ejecuta primero `dvc pull`.")
    km = pd.read_csv(mc.RUTA_CSV, parse_dates=["fecha"])
    verificar_anonimizado(km)
    train, test = mc.cargar_datos()

    pipeline, nombre, origen = cargar_modelo(run_id, train)

    # Error en prueba (por vehículo): da el rango de fechas que muestra el tablero
    Xte, yte = mc.separar_xy(test)
    err = (yte - pipeline.predict(Xte)).abs()
    base = (yte - test["km_media28"]).abs().mean()

    ARTEFACTOS.mkdir(parents=True, exist_ok=True)
    joblib.dump({"pipeline": pipeline, "features": mc.FEATURES, "numericas": mc.NUMERICAS,
                 "objetivo": mc.OBJETIVO}, ARTEFACTOS / "modelo.joblib")

    panel = km[COLUMNAS_PANEL + [c for c in mc.FEATURES if c not in COLUMNAS_PANEL]].sort_values(["vehiculo", "fecha"])
    panel.round(3).to_csv(ARTEFACTOS / "panel.csv", index=False)

    meta = {
        "modelo": nombre,
        "origen": origen,
        "objetivo": mc.OBJETIVO,
        "version_datos": mc.version_datos(),
        "fecha_max_datos": str(km["fecha"].max().date()),
        "mae_global": round(float(err.mean()), 2),
        "mae_linea_base": round(float(base), 2),
        "mejora_vs_linea_base_pct": round(100 * (base - err.mean()) / base, 1),
        "mae_por_vehiculo": {v: round(float(e.mean()), 2) for v, e in err.groupby(test["vehiculo"].to_numpy())},
        "n_train": len(train), "n_test": len(test),
        "python": platform.python_version(),
        "versiones": {p: version(p) for p in ("scikit-learn", "pandas", "numpy", "joblib")},
        "generado": datetime.now().isoformat(timespec="seconds"),
    }
    (ARTEFACTOS / "metadatos.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    v = meta["versiones"]
    REQUISITOS.write_text(
        "# Generado por api/preparar_artefactos.py: mismas versiones con las que se creó el modelo\n"
        "fastapi==0.115.12\nuvicorn==0.34.2\n"
        f"scikit-learn=={v['scikit-learn']}\npandas=={v['pandas']}\nnumpy=={v['numpy']}\njoblib=={v['joblib']}\n",
        encoding="utf-8")

    print(f"Modelo: {nombre} | origen: {origen}")
    print(f"MAE prueba {meta['mae_global']} km/día vs línea base {meta['mae_linea_base']} "
          f"({meta['mejora_vs_linea_base_pct']}% de mejora) | datos {meta['version_datos'][:8]} al {meta['fecha_max_datos']}")
    print(f"Artefactos en {ARTEFACTOS} | Python {meta['python']} | requirements: {REQUISITOS.name}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--run-id", help="ID de la corrida de MLflow con el modelo escogido")
    main(p.parse_args().run_id)
