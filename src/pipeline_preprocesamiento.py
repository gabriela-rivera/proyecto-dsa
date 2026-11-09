"""
Preprocesamiento del Daily Movement Report anonimizado para el modelo de km por día.

Entrada : data/Daily Movement Report Anonimizado.csv   (un registro por viaje)
Salidas : data/processed/viajes_limpios.csv          (un registro por viaje, limpio)
          data/processed/km_diario.csv               (un registro por vehículo y día, con variables para el modelo)

Paso a  modelo (km_diario.csv):
    - Objetivos: km (km del día) y km_media_prox14 / km_media_prox28 (promedio de km/día de los próximos 14 / 28 días).
    - Variables: km_lag1, km_lag2, km_lag7, km_media7, km_media14, km_media28, km_std7,
                 km_media_dia_semana, dia_semana, fin_de_semana, mes, vehiculo.
    - Filas: apta_modelo == True (y objetivo no vacío). Partición: columna 'particion' (train / test).

Uso (desde la raíz del repo):
    python src/pipeline_preprocesamiento.py
"""
from pathlib import Path
import argparse

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
ENTRADA = RAIZ / "data" / "Daily Movement Report Anonimizado.csv"
SALIDA = RAIZ / "data" / "processed"

# Parámetros del preprocesamiento (documentados en el reporte)
DIAS_HUECO_GPS = 7          # >= 7 días seguidos sin viajes se consideran falta de datos (GPS/indisponibilidad), no 0 km
UMBRAL_SALTO_ODO_KM = 1.0   # diferencia entre odómetro final de un viaje e inicial del siguiente
FECHA_CORTE_TEST = "2026-09-15"  # partición temporal: entrenamiento < corte <= prueba
VENTANAS = (7, 14, 28)
REZAGOS = (1, 2, 7)
HORIZONTES = (14, 28)       # objetivos km_media_prox14 y km_media_prox28


# --------------------------------------------------------------------------- viajes
def cargar(ruta: Path) -> pd.DataFrame:
    return pd.read_csv(ruta, encoding="utf-8-sig")


def limpiar_viajes(df: pd.DataFrame) -> pd.DataFrame:
    """Limpieza a nivel de viaje (mismos criterios del EDA de la Entrega 1)."""
    df = df.drop_duplicates().copy()

    df["salida_dt"] = pd.to_datetime(df["DepartureDate"] + " " + df["DepartureTime"], format="%d/%m/%Y %H:%M:%S")
    df["llegada_dt"] = pd.to_datetime(df["ArrivalDate"] + " " + df["ArrivalTime"], format="%d/%m/%Y %H:%M:%S")

    for orig, nuevo in {"DrivingTime": "min_conduccion", "StandingTime": "min_detenido",
                        "Duration": "min_duracion"}.items():
        df[nuevo] = pd.to_timedelta(df[orig], errors="coerce").dt.total_seconds() / 60

    def a_numero(s):
        return pd.to_numeric(s.astype(str).str.replace(",", "", regex=False), errors="coerce")

    df["odo_inicio"] = a_numero(df["StartOdoMeter"])
    df["odo_fin"] = a_numero(df["EndOdoMeter"])
    df["distancia_km"] = a_numero(df["Distance"])
    df["vel_max_kmh"] = a_numero(df["MaxSpeed"])
    df["vel_prom_kmh"] = a_numero(df["AvgSpeed"])
    df["combustible_l"] = a_numero(df["TotalFuelUsedMeasured"])

    df["vehiculo"] = df["AssetHostID"]
    df["conductor"] = df["AssetName2"]
    df["fecha"] = df["salida_dt"].dt.normalize()

    cols = ["vehiculo", "conductor", "fecha", "salida_dt", "llegada_dt", "distancia_km", "odo_inicio", "odo_fin",
            "min_conduccion", "min_detenido", "min_duracion", "vel_max_kmh", "vel_prom_kmh", "combustible_l"]
    df = df[cols].sort_values(["vehiculo", "salida_dt"]).reset_index(drop=True)

    # Salto de odómetro entre viajes consecutivos: km que el GPS no registró como viaje
    df["salto_odo_km"] = df["odo_inicio"] - df.groupby("vehiculo")["odo_fin"].shift()
    df.loc[df["salto_odo_km"].abs() < UMBRAL_SALTO_ODO_KM, "salto_odo_km"] = 0.0
    return df


# --------------------------------------------------------------------------- diario
def agregar_diario(v: pd.DataFrame) -> pd.DataFrame:
    """Un registro por vehículo y día calendario, incluidos los días sin viajes."""
    d = (v.groupby(["vehiculo", "fecha"])
           .agg(km=("distancia_km", "sum"), viajes=("distancia_km", "size"),
                min_conduccion=("min_conduccion", "sum"), min_detenido=("min_detenido", "sum"),
                combustible_l=("combustible_l", "sum"), vel_max_kmh=("vel_max_kmh", "max"),
                conductores=("conductor", "nunique"), odo_fin_dia=("odo_fin", "max"),
                salto_odo_km=("salto_odo_km", lambda s: s.fillna(0).clip(lower=0).sum()))
           .reset_index())

    calendario = pd.date_range(v["fecha"].min(), v["fecha"].max(), freq="D")
    completo = []
    for veh, sub in d.groupby("vehiculo"):
        s = sub.set_index("fecha").reindex(calendario)
        s.index.name = "fecha"
        s["vehiculo"] = veh
        s["con_registro"] = s["viajes"].notna()

        # Rachas de días sin registro: las cortas son 0 km (vehículo quieto); las largas o al final, faltantes
        sin = ~s["con_registro"]
        racha_id = (sin != sin.shift()).cumsum()
        largo_racha = sin.groupby(racha_id).transform("size").where(sin, 0)
        ultimo_dia_con_datos = s.index[s["con_registro"]].max()
        faltante = sin & ((largo_racha >= DIAS_HUECO_GPS) | (s.index > ultimo_dia_con_datos))
        s["dato_faltante"] = faltante

        for c in ["km", "viajes", "min_conduccion", "min_detenido", "combustible_l", "conductores", "salto_odo_km"]:
            s.loc[sin & ~faltante, c] = 0.0
        s["odo_fin_dia"] = s["odo_fin_dia"].ffill()
        completo.append(s.reset_index())
    return pd.concat(completo, ignore_index=True)


# --------------------------------------------------------------------------- variables
def crear_variables(d: pd.DataFrame) -> pd.DataFrame:
    """Variables de calendario, rezagos y medias móviles (solo con información de días anteriores)."""
    d = d.sort_values(["vehiculo", "fecha"]).copy()
    d["dia_semana"] = d["fecha"].dt.dayofweek
    d["fin_de_semana"] = (d["dia_semana"] >= 5).astype(int)
    d["mes"] = d["fecha"].dt.month

    g = d.groupby("vehiculo")["km"]
    for k in REZAGOS:
        d[f"km_lag{k}"] = g.shift(k)
    for w in VENTANAS:
        d[f"km_media{w}"] = g.transform(lambda s: s.shift(1).rolling(w, min_periods=max(3, w // 4)).mean())
    d["km_std7"] = g.transform(lambda s: s.shift(1).rolling(7, min_periods=3).std())
    d["km_media_dia_semana"] = (d.groupby(["vehiculo", "dia_semana"])["km"]
                                  .transform(lambda s: s.shift(1).expanding(min_periods=2).mean()))

    # Objetivos "directos" para estimar la fecha: promedio de km/día de los próximos N días (t+1 .. t+N).
    # Se exige al menos el 75% de días con dato; si no, queda vacío.
    for h in HORIZONTES:
        d[f"km_media_prox{h}"] = g.transform(
            lambda s, h=h: s[::-1].rolling(h, min_periods=int(h * 0.75)).mean()[::-1].shift(-1))

    d["particion"] = np.where(d["fecha"] < pd.Timestamp(FECHA_CORTE_TEST), "train", "test")
    # Filas utilizables por el modelo: con objetivo conocido y con historia suficiente
    d["apta_modelo"] = (~d["dato_faltante"]) & d["km"].notna() & d[["km_lag1", "km_lag7", "km_media28"]].notna().all(axis=1)
    return d


def main(entrada: Path, salida: Path) -> None:
    salida.mkdir(parents=True, exist_ok=True)
    viajes = limpiar_viajes(cargar(entrada))
    diario = crear_variables(agregar_diario(viajes))

    viajes.to_csv(salida / "viajes_limpios.csv", index=False)
    diario.to_csv(salida / "km_diario.csv", index=False)

    print(f"Viajes limpios: {len(viajes):,}")
    print(f"Vehículo-día: {len(diario):,} | faltantes: {int(diario['dato_faltante'].sum())} "
          f"| aptas para el modelo: {int(diario['apta_modelo'].sum())} "
          f"(train {int((diario['apta_modelo'] & (diario['particion'] == 'train')).sum())}, "
          f"test {int((diario['apta_modelo'] & (diario['particion'] == 'test')).sum())})")
    for h in HORIZONTES:
        ok = diario["apta_modelo"] & diario[f"km_media_prox{h}"].notna()
        print(f"Objetivo km_media_prox{h}: train {int((ok & (diario['particion'] == 'train')).sum())}, "
              f"test {int((ok & (diario['particion'] == 'test')).sum())}")
    print(diario.groupby("vehiculo").agg(dias=("fecha", "size"), faltantes=("dato_faltante", "sum"),
                                          km_dia=("km", "mean")).round(1).to_string())


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--entrada", type=Path, default=ENTRADA)
    p.add_argument("--salida", type=Path, default=SALIDA)
    a = p.parse_args()
    main(a.entrada, a.salida)
