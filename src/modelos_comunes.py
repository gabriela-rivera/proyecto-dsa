"""Funciones comunes para los notebooks de modelos (Ridge, Lasso, ElasticNet).

Objetivo: predecir km/dia (promedio de los proximos 28 dias) por vehiculo y,
con eso, estimar dias = km faltantes / km/dia predicho.
"""
import os
import re
from pathlib import Path

import matplotlib.pyplot as plt
import mlflow
import mlflow.sklearn
import numpy as np
import pandas as pd
from mlflow.models import infer_signature
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.model_selection import TimeSeriesSplit, cross_val_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

# ----------------------------- Configuracion -----------------------------
RAIZ = Path(__file__).resolve().parents[1]
RUTA_CSV = RAIZ / "data" / "processed" / "km_diario.csv"
RUTA_DVC = RAIZ / "data" / "processed.dvc"

# Se puede sobreescribir con la variable de entorno MLFLOW_TRACKING_URI
TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://34.229.81.56:5000")
EXPERIMENTO = "modelo_km_dia"
OBJETIVO = "km_media_prox28"
AUTOR = "Alejandro Acosta"
FECHA_CORTE = "2026-09-15"

# Supuesto para traducir error de km/dia a error de fecha (dias):
# faltan KM_FALTANTES km para el proximo preventivo. Ajustar con el equipo.
KM_FALTANTES = 500

NUMERICAS = [
    "km_lag1", "km_lag2", "km_lag7",
    "km_media7", "km_media14", "km_media28", "km_std7", "km_media_dia_semana",
    "dia_semana", "fin_de_semana", "mes",
]
CATEGORICAS = ["vehiculo"]
FEATURES = NUMERICAS + CATEGORICAS

# Validacion temporal dentro del train (gap evita solapar ventanas del objetivo)
CV_SPLITS = 3
CV_GAP = 35  # ~7 dias * 5 vehiculos


# ------------------------------- Datos ----------------------------------
def cargar_datos():
    """Devuelve (train, test) filtrados por apta_modelo y objetivo no vacio."""
    df = pd.read_csv(RUTA_CSV, parse_dates=["fecha"])
    df = df[df["apta_modelo"].astype(bool) & df[OBJETIVO].notna()]
    df = df.sort_values(["fecha", "vehiculo"]).reset_index(drop=True)
    train = df[df["particion"] == "train"].reset_index(drop=True)
    test = df[df["particion"] == "test"].reset_index(drop=True)
    return train, test


def separar_xy(df):
    X = df[FEATURES].copy()
    X[NUMERICAS] = X[NUMERICAS].astype(float)
    return X, df[OBJETIVO].astype(float)


def version_datos():
    """Hash md5 de data/processed.dvc (identifica la version de los datos)."""
    try:
        texto = RUTA_DVC.read_text()
        return re.search(r"md5:\s*([0-9a-f]+)", texto).group(1)
    except Exception:
        return "desconocida"


# ------------------------------ Modelo ----------------------------------
def construir_pipeline(estimador):
    pre = ColumnTransformer([
        ("num", Pipeline([("imp", SimpleImputer(strategy="median")),
                          ("sc", StandardScaler())]), NUMERICAS),
        ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAS),
    ])
    return Pipeline([("pre", pre), ("modelo", estimador)])


def mae_fecha_dias(y_real, y_pred, km_faltantes=KM_FALTANTES):
    """Error absoluto medio de la fecha (dias) para un caso con km_faltantes."""
    dias_real = km_faltantes / np.clip(np.asarray(y_real, float), 1, None)
    dias_pred = km_faltantes / np.clip(np.asarray(y_pred, float), 1, None)
    return float(np.mean(np.abs(dias_real - dias_pred)))


def calcular_metricas(y_real, y_pred):
    return {
        "mae": float(mean_absolute_error(y_real, y_pred)),
        "rmse": float(np.sqrt(mean_squared_error(y_real, y_pred))),
        "mae_fecha_dias": mae_fecha_dias(y_real, y_pred),
    }


# ------------------------------- MLflow ---------------------------------
def configurar_mlflow():
    mlflow.set_tracking_uri(TRACKING_URI)
    mlflow.set_experiment(EXPERIMENTO)
    print("MLflow:", TRACKING_URI, "| experimento:", EXPERIMENTO)


def _grafica(test, y_pred, titulo):
    fig, ax = plt.subplots(1, 2, figsize=(12, 4))
    y = test[OBJETIVO].values
    ax[0].scatter(y, y_pred, alpha=0.6)
    lim = [min(y.min(), np.min(y_pred)), max(y.max(), np.max(y_pred))]
    ax[0].plot(lim, lim, "r--")
    ax[0].set(xlabel="Real (km/dia)", ylabel="Predicho (km/dia)", title="Real vs predicho")
    d = pd.DataFrame({"fecha": test["fecha"], "real": y, "pred": y_pred})
    d = d.groupby("fecha").mean()
    ax[1].plot(d.index, d["real"], label="real")
    ax[1].plot(d.index, d["pred"], label="predicho")
    ax[1].set(title="Promedio diario (todos los vehiculos)", ylabel="km/dia")
    ax[1].legend()
    ax[1].tick_params(axis="x", rotation=30)
    fig.suptitle(titulo)
    fig.tight_layout()
    return fig


def correr_baseline(test):
    """Baseline: promedio movil de 28 dias (km_media28) como prediccion."""
    y = test[OBJETIVO].values
    pred = test["km_media28"].values
    m = calcular_metricas(y, pred)
    with mlflow.start_run(run_name="baseline_promedio_movil_28d"):
        mlflow.set_tags({"modelo": "baseline", "autor": AUTOR, "objetivo": OBJETIVO,
                         "version_datos": version_datos()})
        mlflow.log_params({"metodo": "promedio_movil_28d", "objetivo": OBJETIVO,
                           "n_test": len(test), "km_faltantes_supuesto": KM_FALTANTES})
        mlflow.log_metrics({"mae": m["mae"], "rmse": m["rmse"],
                            "mae_fecha_dias": m["mae_fecha_dias"],
                            "mejora_mae_pct": 0.0, "mejora_fecha_pct": 0.0})
        mlflow.log_figure(_grafica(test, pred, "Baseline 28d"), "real_vs_predicho.png")
        plt.close("all")
    print(f"Baseline -> MAE {m['mae']:.2f} km/dia | MAE fecha {m['mae_fecha_dias']:.2f} dias")
    return m


def correr_modelo(nombre, run_name, estimador, params, train, test, base):
    """Entrena, evalua y registra una corrida en MLflow. `base` = metricas del baseline."""
    Xtr, ytr = separar_xy(train)
    Xte, yte = separar_xy(test)
    pipe = construir_pipeline(estimador)

    cv = TimeSeriesSplit(n_splits=CV_SPLITS, gap=CV_GAP)
    cv_mae = -cross_val_score(pipe, Xtr, ytr, cv=cv,
                              scoring="neg_mean_absolute_error").mean()

    pipe.fit(Xtr, ytr)
    pred = pipe.predict(Xte)
    m = calcular_metricas(yte, pred)
    m["cv_mae"] = float(cv_mae)
    m["mejora_mae_pct"] = 100 * (base["mae"] - m["mae"]) / base["mae"]
    m["mejora_fecha_pct"] = 100 * (base["mae_fecha_dias"] - m["mae_fecha_dias"]) / base["mae_fecha_dias"]

    with mlflow.start_run(run_name=run_name) as run:
        mlflow.set_tags({"modelo": nombre, "autor": AUTOR, "objetivo": OBJETIVO,
                         "version_datos": version_datos()})
        mlflow.log_params({**params, "objetivo": OBJETIVO, "n_train": len(train),
                           "n_test": len(test), "corte_train_test": FECHA_CORTE,
                           "cv": f"TimeSeriesSplit(n_splits={CV_SPLITS}, gap={CV_GAP})",
                           "km_faltantes_supuesto": KM_FALTANTES})
        mlflow.log_metrics(m)
        mlflow.log_figure(_grafica(test, pred, run_name), "real_vs_predicho.png")
        plt.close("all")
        firma = infer_signature(Xtr, pipe.predict(Xtr))
        mlflow.sklearn.log_model(pipe, name="model", signature=firma,
                                 input_example=Xtr.head(3))
        run_id = run.info.run_id

    print(f"{run_name:<28} MAE {m['mae']:.2f} | CV {m['cv_mae']:.2f} | "
          f"mejora {m['mejora_mae_pct']:.1f}% | fecha {m['mae_fecha_dias']:.2f} d")
    return {"run_name": run_name, "run_id": run_id, **params, **m}
