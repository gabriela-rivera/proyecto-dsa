"""Lógica de la API: km/día con el modelo y, con ellos, la fecha del próximo preventivo.

El modelo se carga de un joblib con las llaves "pipeline", "features" y "numericas". Cambiar de modelo
(Gradient Boosting, Random Forest, XGBoost…) es reemplazar ese archivo con api/preparar_artefactos.py.
"""
import json
import math
from datetime import date
from functools import lru_cache

import joblib
import pandas as pd

from app import config as cfg


# --------------------------------------------------------------------------- carga
@lru_cache(maxsize=1)
def cargar_modelo():
    obj = joblib.load(cfg.RUTA_MODELO)
    return obj["pipeline"], obj["features"], obj["numericas"]


@lru_cache(maxsize=1)
def cargar_datos():
    panel = pd.read_csv(cfg.RUTA_PANEL, parse_dates=["fecha"]).sort_values(["vehiculo", "fecha"])
    meta = json.loads(cfg.RUTA_META.read_text(encoding="utf-8"))
    return panel.reset_index(drop=True), meta


def fecha_datos() -> date:
    panel, _ = cargar_datos()
    return panel["fecha"].max().date()


# --------------------------------------------------------------------------- contratos
def normalizar_contrato(valor: str | None) -> str | None:
    """Acepta "D", "contrato d" o "Contrato D" y devuelve "Contrato D"."""
    if valor is None or not str(valor).strip():
        return None
    v = str(valor).strip()
    v = v[len("contrato"):].strip() if v.lower().startswith("contrato") else v
    return f"Contrato {v.upper()}"


@lru_cache(maxsize=1)
def contrato_actual() -> dict:
    """Contrato de cada vehículo = el del último día con datos GPS que no fue traslado."""
    panel, _ = cargar_datos()
    con = panel[panel["con_registro"] & ~panel["contrato"].isin(cfg.NO_CONTRATO)]
    return con.groupby("vehiculo")["contrato"].last().to_dict()


def vehiculos(contrato: str | None = None) -> list[str]:
    actual = contrato_actual()
    return sorted(v for v, c in actual.items() if contrato is None or c == contrato)


def contratos() -> list[dict]:
    salida = []
    for c in sorted(set(contrato_actual().values())):
        estados = [estado_vehiculo(v) for v in vehiculos(c)]
        salida.append({"contrato": c, "etiqueta": cfg.ETIQUETAS_CONTRATO.get(c, c),
                       "vehiculos": len(estados), "activos": sum(e["activo"] for e in estados)})
    return salida


# --------------------------------------------------------------------------- reglas
def km_faltantes(odometro: float, km_ultimo_preventivo: float | None = None) -> tuple[float, float]:
    """(km que faltan, km del próximo servicio)."""
    if km_ultimo_preventivo is not None:
        proximo = km_ultimo_preventivo + cfg.INTERVALO_KM
        return max(proximo - odometro, 0.0), proximo
    # Supuesto: el último preventivo fue en el múltiplo de 5.000 km más reciente
    proximo = (math.floor(odometro / cfg.INTERVALO_KM) + 1) * cfg.INTERVALO_KM
    return proximo - odometro, float(proximo)


def alerta(dias: int, faltan: float, dias_sin_datos: int, ultimo_dato: date) -> tuple[str, str]:
    if dias_sin_datos > cfg.DIAS_MAX_SIN_DATOS:
        return "sin_datos", f"Sin GPS desde {ultimo_dato:%d/%m}"
    if faltan <= 0:
        return "vencido", "Vencido"
    if dias <= cfg.ALERTA_ROJA_DIAS:
        return "0_7_dias", "≤ 7 días"
    if dias <= cfg.ALERTA_AMARILLA_DIAS:
        return "8_14_dias", "8–14 días"
    return "mas_14_dias", "> 14 días"


def _dias_para(km_pendientes: float, km_dia: float) -> int:
    return min(math.ceil(km_pendientes / max(km_dia, 1.0)), cfg.MAX_DIAS)


# --------------------------------------------------------------------------- estimación
def estado_vehiculo(vehiculo: str, km_ultimo_preventivo: float | None = None) -> dict:
    """Fecha estimada del próximo preventivo de un vehículo y los datos para explicarla."""
    panel, meta = cargar_datos()
    pipeline, features, numericas = cargar_modelo()

    g = panel[panel["vehiculo"] == vehiculo]
    if g.empty:
        raise KeyError(vehiculo)
    con_datos = g[g["con_registro"]]
    candidatas = g[g["apta_modelo"]]
    if con_datos.empty or candidatas.empty:
        raise ValueError(f"No hay datos suficientes para estimar el vehículo {vehiculo}.")

    ultimo = con_datos.iloc[-1]
    ultimo_dato = ultimo["fecha"].date()
    odometro = float(g["odo_fin_dia"].dropna().iloc[-1])
    dias_sin_datos = (fecha_datos() - ultimo_dato).days

    X = candidatas.iloc[[-1]][features].copy()
    X[numericas] = X[numericas].astype(float)
    km_dia = float(max(pipeline.predict(X)[0], 1.0))      # promedio de km/día de los próximos 28 días

    faltan, proximo = km_faltantes(odometro, km_ultimo_preventivo)
    dias = _dias_para(faltan, km_dia)
    fecha = ultimo["fecha"] + pd.Timedelta(days=dias)

    mae = meta["mae_por_vehiculo"].get(vehiculo, meta["mae_global"])
    dias_min = _dias_para(faltan, km_dia + mae)
    dias_max = _dias_para(faltan, km_dia - mae) if km_dia - mae >= 1 else cfg.MAX_DIAS

    reciente = g[g["fecha"] > pd.Timestamp(fecha_datos()) - pd.Timedelta(days=cfg.DIAS_KM_RECIENTE)]
    km_dia_28 = reciente["km"].mean()
    codigo, texto = alerta(dias, faltan, dias_sin_datos, ultimo_dato)

    return {
        "vehiculo": vehiculo,
        "contrato": contrato_actual().get(vehiculo),
        "activo": dias_sin_datos <= cfg.DIAS_MAX_SIN_DATOS,
        "ultimo_dato_gps": ultimo_dato,
        "dias_sin_datos": dias_sin_datos,
        "odometro_km": round(odometro, 1),
        "km_dia_pronosticado": round(km_dia, 1),
        "km_dia_ultimos_28": None if pd.isna(km_dia_28) else round(float(km_dia_28), 1),
        "proximo_servicio_km": round(proximo),
        "km_restantes": round(faltan, 1),
        "base_supuesta": km_ultimo_preventivo is None,
        "dias": dias,
        "fecha_estimada": fecha.date(),
        "fecha_min": (ultimo["fecha"] + pd.Timedelta(days=dias_min)).date(),
        "fecha_max": (ultimo["fecha"] + pd.Timedelta(days=dias_max)).date(),
        "error_km_dia": round(mae, 1),
        "alerta": codigo,
        "alerta_texto": texto,
    }


def flota(contrato: str | None = None) -> list[dict]:
    estados = [estado_vehiculo(v) for v in vehiculos(contrato)]
    # Primero los activos por fecha más próxima; al final los que no tienen GPS reciente
    return sorted(estados, key=lambda e: (not e["activo"], e["dias"], e["vehiculo"]))


def resumen(contrato: str | None = None) -> dict:
    estados = flota(contrato)
    activos = [e for e in estados if e["activo"]]
    km28 = [e["km_dia_ultimos_28"] for e in activos if e["km_dia_ultimos_28"] is not None]
    return {
        "contrato": contrato,
        "fecha_datos": fecha_datos(),
        "vehiculos": len(estados),
        "vehiculos_activos": len(activos),
        "preventivo_0_7_dias": sum(e["alerta"] in ("0_7_dias", "vencido") for e in activos),
        "preventivo_8_14_dias": sum(e["alerta"] == "8_14_dias" for e in activos),
        "km_dia_promedio_28": round(sum(km28) / len(km28), 1) if km28 else None,
    }


def historial(vehiculo: str, dias: int) -> dict:
    panel, _ = cargar_datos()
    g = panel[panel["vehiculo"] == vehiculo]
    if g.empty:
        raise KeyError(vehiculo)
    desde = pd.Timestamp(fecha_datos()) - pd.Timedelta(days=dias - 1)
    g = g[g["fecha"] >= desde]
    e = estado_vehiculo(vehiculo)
    return {
        "vehiculo": vehiculo,
        "dias": [{"fecha": f.date(), "km": None if pd.isna(k) else round(float(k), 1), "contrato": c}
                 for f, k, c in zip(g["fecha"], g["km"], g["contrato"])],
        "proyeccion": {k: e[k] for k in ("km_dia_pronosticado", "proximo_servicio_km", "km_restantes",
                                          "fecha_estimada")},
    }


def uso_semanal(contrato: str | None, semanas: int) -> list[dict]:
    panel, _ = cargar_datos()
    p = panel[panel["vehiculo"].isin(vehiculos(contrato)) & panel["km"].notna()].copy()
    p["semana"] = p["fecha"] - pd.to_timedelta(p["fecha"].dt.day_of_week, unit="D")   # lunes de la semana
    desde = p["semana"].max() - pd.Timedelta(weeks=semanas - 1)
    s = p[p["semana"] >= desde].groupby(["semana", "vehiculo"])["km"].sum().reset_index()
    return [{"semana": r.semana.date(), "vehiculo": r.vehiculo, "km": round(float(r.km), 1)}
            for r in s.itertuples()]
