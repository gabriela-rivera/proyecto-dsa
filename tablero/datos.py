"""Acceso a los datos del tablero (lectura de artefactos y consultas por vehículo)."""
import json
import re
from functools import lru_cache

import pandas as pd

import config as cfg


@lru_cache(maxsize=1)
def cargar():
    """Lee los artefactos una sola vez. Devuelve (panel, historial, metadatos)."""
    panel = pd.read_csv(cfg.RUTA_PANEL, parse_dates=["fecha"]).sort_values(["vehiculo", "fecha"])
    hist = pd.read_csv(cfg.RUTA_HISTORIAL, parse_dates=["fecha"])
    meta = json.loads(cfg.RUTA_META.read_text(encoding="utf-8"))
    return panel, hist, meta


def vehiculos():
    panel, _, _ = cargar()
    return sorted(panel["vehiculo"].unique())


def normalizar_placa(texto):
    """'vh 2', 'VH02', 'vh-02' -> 'VH-02'."""
    t = re.sub(r"[\s_]+", "-", str(texto).strip().upper())
    m = re.fullmatch(r"VH-?(\d{1,2})", t)
    return f"VH-{int(m.group(1)):02d}" if m else t


def periodo():
    panel, _, _ = cargar()
    return panel["fecha"].min(), panel["fecha"].max()


def detalle(vehiculo):
    panel, hist, _ = cargar()
    p = panel[panel["vehiculo"] == vehiculo]
    h = hist[hist["vehiculo"] == vehiculo]
    return {
        "odometro": float(p["odo_fin_dia"].dropna().iloc[-1]),
        "km_periodo": float(h["km"].sum()),
        "viajes": int(h["viajes"].sum()),
        "ultimo_registro": h["fecha"].max(),
        "dias_con_viajes": int(h["fecha"].nunique()),
    }


def historial(vehiculo):
    """Un registro por día con viajes, del más reciente al más antiguo."""
    _, hist, _ = cargar()
    return hist[hist["vehiculo"] == vehiculo].sort_values("fecha", ascending=False)


def serie_km(vehiculo, dias=90):
    panel, _, _ = cargar()
    p = panel[panel["vehiculo"] == vehiculo]
    return p.tail(dias)[["fecha", "km", "km_media28"]]


# ---- Formato en español ----
def fmt_num(x, dec=0):
    s = f"{x:,.{dec}f}"
    return s.replace(",", "§").replace(".", ",").replace("§", ".")


def fmt_fecha(ts):
    return pd.Timestamp(ts).strftime("%d/%m/%Y")
