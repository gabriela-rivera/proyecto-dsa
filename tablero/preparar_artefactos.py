"""Genera los artefactos que usa el tablero a partir de los datos versionados con DVC.

Uso (desde la raíz del repo, con los datos ya descargados con `dvc pull`):
    python tablero/preparar_artefactos.py

Entradas : data/processed/km_diario.csv y data/processed/viajes_limpios.csv  (DVC)
Salidas  : tablero/artefactos/panel_diario.csv, historial_diario.csv, modelo_ridge.joblib, metadatos.json
           tablero/requirements.txt   (versiones exactas con las que se entrenó el modelo)

Por qué existe: Render no puede ejecutar `dvc pull` (el remoto de Google Drive pide autorización
interactiva), así que el tablero lleva su propia copia ligera de los datos ya anonimizados.
La fuente de verdad sigue siendo DVC: si cambian los datos, se vuelve a correr este script.
"""
import json
import re
import sys
from importlib import metadata

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

import config as cfg


def verificar_anonimizado(vehiculos, conductores):
    """Aborta si los datos no parecen anonimizados (el repositorio es público)."""
    malos_v = [v for v in vehiculos if not re.fullmatch(r"VH-\d{2}", str(v))]
    malos_c = [c for c in conductores if not re.fullmatch(r"Conductor \d+|Sin conductor", str(c))]
    if malos_v or malos_c:
        sys.exit("ERROR: los datos no parecen anonimizados (vehículos o conductores con formato inesperado). "
                 "No se genera nada. Revisa data/processed antes de continuar.")


def construir_pipeline(estimador):
    pre = ColumnTransformer([
        ("num", Pipeline([("imp", SimpleImputer(strategy="median")),
                          ("sc", StandardScaler())]), cfg.NUMERICAS),
        ("cat", OneHotEncoder(handle_unknown="ignore"), cfg.CATEGORICAS),
    ])
    return Pipeline([("pre", pre), ("modelo", estimador)])


def separar_xy(df):
    X = df[cfg.FEATURES].copy()
    X[cfg.NUMERICAS] = X[cfg.NUMERICAS].astype(float)
    return X, df[cfg.OBJETIVO].astype(float)


def version_datos():
    try:
        return re.search(r"md5:\s*([0-9a-f]+)", cfg.RUTA_PROCESSED_DVC.read_text()).group(1)
    except Exception:
        return "desconocida"


def version(paquete, respaldo=None):
    try:
        return metadata.version(paquete)
    except metadata.PackageNotFoundError:
        return respaldo


def main():
    for ruta in (cfg.RUTA_KM_DIARIO, cfg.RUTA_VIAJES):
        if not ruta.exists():
            sys.exit(f"No existe {ruta}. Ejecuta primero `dvc pull` (o el pipeline de preprocesamiento).")

    km = pd.read_csv(cfg.RUTA_KM_DIARIO, parse_dates=["fecha"])
    viajes = pd.read_csv(cfg.RUTA_VIAJES, parse_dates=["fecha"])
    verificar_anonimizado(km["vehiculo"].unique(), viajes["conductor"].dropna().unique())

    # ---------------- Modelo ----------------
    etiquetadas = km[km["apta_modelo"].astype(bool) & km[cfg.OBJETIVO].notna()].copy()
    train = etiquetadas[etiquetadas["particion"] == "train"]
    test = etiquetadas[etiquetadas["particion"] == "test"]

    # 1) Error en prueba por vehículo (sirve para el rango de fechas que muestra el tablero)
    Xtr, ytr = separar_xy(train)
    Xte, yte = separar_xy(test)
    prueba = construir_pipeline(Ridge(alpha=cfg.ALPHA)).fit(Xtr, ytr)
    err = (yte - prueba.predict(Xte)).abs()
    mae_global = float(err.mean())
    mae_veh = {v: float(e.mean()) for v, e in err.groupby(test["vehiculo"].to_numpy())}

    # 2) Modelo final: se reentrena con todas las filas etiquetadas (train + test)
    Xall, yall = separar_xy(etiquetadas)
    final = construir_pipeline(Ridge(alpha=cfg.ALPHA)).fit(Xall, yall)

    cfg.ARTEFACTOS.mkdir(parents=True, exist_ok=True)
    joblib.dump({"pipeline": final, "features": cfg.FEATURES}, cfg.RUTA_MODELO)

    # ---------------- Panel diario (variables por vehículo-día) ----------------
    cols = ["vehiculo", "fecha", "km", "viajes", "odo_fin_dia", "dato_faltante", "apta_modelo", cfg.OBJETIVO]
    cols += [c for c in cfg.NUMERICAS if c not in cols]
    panel = km[cols].sort_values(["vehiculo", "fecha"]).copy()
    numericas = panel.select_dtypes("number").columns
    panel[numericas] = panel[numericas].round(3)
    panel.to_csv(cfg.RUTA_PANEL, index=False)

    # ---------------- Historial diario (para la tabla del tablero) ----------------
    def conductor_principal(s):
        s = s.dropna()
        return s.mode().iat[0] if not s.empty else "Sin dato"

    hist = (viajes.groupby(["vehiculo", "fecha"])
                  .agg(viajes=("distancia_km", "size"), km=("distancia_km", "sum"),
                       conductor=("conductor", conductor_principal))
                  .reset_index().round({"km": 1}))
    hist.to_csv(cfg.RUTA_HISTORIAL, index=False)

    # ---------------- Metadatos ----------------
    meta = {
        "version_datos": version_datos(),
        "modelo": f"Ridge(alpha={cfg.ALPHA})",
        "objetivo": cfg.OBJETIVO,
        "n_entrenamiento_final": int(len(etiquetadas)),
        "fecha_corte_prueba": str(test["fecha"].min().date()) if len(test) else None,
        "mae_global_km_dia": round(mae_global, 2),
        "mae_por_vehiculo_km_dia": {k: round(v, 2) for k, v in mae_veh.items()},
        "scikit_learn": version("scikit-learn"),
        "fecha_max_datos": str(km["fecha"].max().date()),
    }
    cfg.RUTA_META.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    # ---------------- requirements.txt del tablero (versiones exactas del entrenamiento) ----------------
    respaldo = {"dash": "4.5.0", "gunicorn": "26.2.0"}
    lineas = []
    for pkg in ("dash", "gunicorn", "pandas", "numpy", "scikit-learn", "joblib"):
        v = version(pkg, respaldo.get(pkg))
        lineas.append(f"{pkg}=={v}" if v else pkg)
    (cfg.BASE / "requirements.txt").write_text("\n".join(lineas) + "\n", encoding="utf-8")

    print("Artefactos generados en", cfg.ARTEFACTOS)
    print(f"  Modelo final: {meta['modelo']} | filas de entrenamiento: {meta['n_entrenamiento_final']}")
    print(f"  Error en prueba (km/día): global {mae_global:.2f} | por vehículo {meta['mae_por_vehiculo_km_dia']}")
    print(f"  Versión de datos (DVC): {meta['version_datos']}")
    print("  requirements.txt actualizado:", ", ".join(lineas))


if __name__ == "__main__":
    main()
