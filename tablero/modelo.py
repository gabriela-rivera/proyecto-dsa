"""Predicción de la fecha del próximo mantenimiento.

Hoy el tablero carga el modelo directamente. Cuando exista la API (Entrega 3), basta con reemplazar el
cuerpo de `estimar()` por una llamada HTTP a la API; el resto del tablero no cambia.
"""
import math
from functools import lru_cache

import joblib
import pandas as pd

import config as cfg
from datos import cargar


@lru_cache(maxsize=1)
def _cargar_modelo():
    obj = joblib.load(cfg.RUTA_MODELO)
    return obj["pipeline"], obj["features"]


def km_faltantes(vehiculo, odometro):
    """Km que faltan para el siguiente preventivo."""
    ultimo = cfg.ODO_ULTIMO_PREVENTIVO.get(vehiculo)
    if ultimo is not None:
        return max(ultimo + cfg.INTERVALO_KM - odometro, 0.0)
    # Supuesto provisional: el último preventivo fue en el múltiplo de INTERVALO_KM más reciente
    return cfg.INTERVALO_KM - (odometro % cfg.INTERVALO_KM)


def _fecha_en(base, km_pendientes, km_dia):
    dias = min(math.ceil(km_pendientes / km_dia), cfg.MAX_DIAS_RANGO)
    return dias, base + pd.Timedelta(days=dias)


def precargar():
    """Carga el modelo al iniciar el servidor para que la primera consulta no se demore."""
    _cargar_modelo()


def estimar(vehiculo):
    """Devuelve la fecha estimada del próximo preventivo y la información para explicarla."""
    panel, _, meta = cargar()
    pipeline, features = _cargar_modelo()

    del_vehiculo = panel[panel["vehiculo"] == vehiculo]
    candidatas = del_vehiculo[del_vehiculo["apta_modelo"]]
    if candidatas.empty:
        raise ValueError(f"No hay datos suficientes para estimar el vehículo {vehiculo}.")
    fila = candidatas.iloc[[-1]]                      # último día con variables completas (entrada del modelo)
    fecha_features = fila["fecha"].iloc[0]

    ultimo = del_vehiculo[~del_vehiculo["dato_faltante"]].iloc[-1]   # último día con datos reales del GPS
    fecha_ref = ultimo["fecha"]                       # la fecha estimada se cuenta desde aquí
    odometro = float(ultimo["odo_fin_dia"])

    X = fila[features].copy()
    X[cfg.NUMERICAS] = X[cfg.NUMERICAS].astype(float)
    km_dia = float(max(pipeline.predict(X)[0], 1.0))  # km/día pronosticados (promedio de 28 días)

    faltan = km_faltantes(vehiculo, odometro)
    dias, fecha = _fecha_en(fecha_ref, faltan, km_dia)

    # Rango probable: km/día pronosticado ± error típico del modelo en prueba
    mae = meta["mae_por_vehiculo_km_dia"].get(vehiculo, meta["mae_global_km_dia"])
    dias_min, fecha_min = _fecha_en(fecha_ref, faltan, km_dia + mae)
    dias_max, fecha_max = _fecha_en(fecha_ref, faltan, max(km_dia - mae, 1.0))

    return {
        "vehiculo": vehiculo,
        "fecha_referencia": fecha_ref,
        "fecha_variables": fecha_features,
        "odometro": odometro,
        "km_dia": km_dia,
        "km_faltantes": faltan,
        "dias": dias,
        "fecha": fecha,
        "fecha_min": fecha_min,
        "fecha_max": fecha_max,
        "dias_max_topado": dias_max >= cfg.MAX_DIAS_RANGO,
        "error_km_dia": mae,
        "uso_bajo": km_dia < cfg.UMBRAL_USO_BAJO_KM_DIA,
        "dias_sin_datos": int((panel["fecha"].max() - fecha_ref).days),
        "base_supuesta": vehiculo not in cfg.ODO_ULTIMO_PREVENTIVO,
    }
