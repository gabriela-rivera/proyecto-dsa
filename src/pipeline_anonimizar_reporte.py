"""
Anonimiza el reporte de movimiento diario de la plataforma GPS según la tabla de anonimización del proyecto.

Entradas (privadas, en data/raw/, ignoradas por Git):
    data/raw/Daily Movement Report.csv   reporte crudo tal como se descarga de la plataforma GPS
    data/raw/correspondencias.csv        placa -> VH-xx y conductor -> Conductor NN (columnas: tipo, original, codigo)
    data/raw/zonas.csv                   reglas para asignar el contrato de cada viaje
                                         (columnas: tipo, patron, contrato, desde, hasta; las fechas son opcionales)

Salida (versionada con DVC):
    data/Daily Movement Report Anonimizado.csv

Qué hace:
    - Vehículos: placa -> VH-xx (según correspondencias.csv; una placa sin código detiene el proceso).
    - Conductores: nombre y cédula -> "Conductor NN". Los nuevos reciben el siguiente número y se guardan
      en correspondencias.csv, para que los códigos se mantengan entre ejecuciones.
    - Ubicación: DepartFrom / ArriveAt (dirección o geocerca) -> contrato anonimizado (Contrato B, D…) o "Traslado".
    - Se eliminan los códigos internos de la plataforma, las coordenadas y los pasajeros.

Uso (desde la raíz del repo):
    python src/pipeline_anonimizar_reporte.py
"""
from pathlib import Path
import argparse
import re

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
CRUDO = RAIZ / "data" / "raw" / "Daily Movement Report.csv"
CORRESPONDENCIAS = RAIZ / "data" / "raw" / "correspondencias.csv"
ZONAS = RAIZ / "data" / "raw" / "zonas.csv"
SALIDA = RAIZ / "data" / "Daily Movement Report Anonimizado.csv"

COLUMNAS_A_ELIMINAR = ["AssetID", "AssetExtra2", "FleetNumber", "StartLatLong", "EndLatLong", "PassengerList"]
SIN_ZONA = "Sin identificar"


# --------------------------------------------------------------------------- reglas privadas
def cargar_correspondencias(ruta: Path) -> pd.DataFrame:
    if not ruta.exists():
        raise SystemExit(f"No se encontró {ruta}. Debe existir con las columnas: tipo, original, codigo.")
    return pd.read_csv(ruta, encoding="utf-8-sig", dtype=str)


def cargar_zonas(ruta: Path) -> list[tuple]:
    """Reglas en orden de prioridad. 'desde' / 'hasta' (aaaa-mm-dd) limitan la regla a un periodo:
    sirven cuando una misma región tuvo contratos distintos en el tiempo."""
    if not ruta.exists():
        raise SystemExit(f"No se encontró {ruta}. Debe existir con las columnas: tipo, patron, contrato, desde, hasta.")
    z = pd.read_csv(ruta, encoding="utf-8-sig", dtype=str)
    for c in ("desde", "hasta"):
        z[c] = pd.to_datetime(z[c]) if c in z else pd.NaT
    return list(z[["tipo", "patron", "contrato", "desde", "hasta"]].itertuples(index=False, name=None))


# --------------------------------------------------------------------------- anonimización
def asignar_zona(lugar: str, fecha: pd.Timestamp, reglas: list[tuple]) -> str:
    """Primero busca la geocerca o el municipio por nombre; si no, usa el departamento del código postal.
    Solo aplican las reglas vigentes en la fecha del viaje."""
    texto = str(lugar).upper()
    vigentes = [r for r in reglas if (pd.isna(r[3]) or fecha >= r[3]) and (pd.isna(r[4]) or fecha <= r[4])]
    for tipo, patron, contrato, _, _ in vigentes:
        if tipo == "texto" and re.search(patron.upper(), texto):
            return contrato
    cp = re.search(r"\b(\d{6})\b", texto)
    if cp:
        for tipo, patron, contrato, _, _ in vigentes:
            if tipo == "codigo_postal" and cp.group(1).startswith(patron):
                return contrato
    return SIN_ZONA


def codificar_conductores(df: pd.DataFrame, corr: pd.DataFrame) -> tuple[pd.Series, pd.DataFrame]:
    """Mantiene los códigos existentes y asigna el siguiente número a los conductores nuevos."""
    nombres = df["AssetName2"].fillna("Sin conductor").astype(str).str.strip()
    actuales = corr[corr["tipo"] == "conductor"]
    mapa = dict(zip(actuales["original"], actuales["codigo"]))
    siguiente = len(mapa) + 1

    orden = df.assign(_n=nombres).sort_values("_salida")["_n"].drop_duplicates()
    nuevos = []
    for n in orden:
        if n not in mapa:
            mapa[n] = f"Conductor {siguiente:02d}"
            nuevos.append({"tipo": "conductor", "original": n, "codigo": mapa[n]})
            siguiente += 1
    return nombres.map(mapa), pd.concat([corr, pd.DataFrame(nuevos)], ignore_index=True)


def anonimizar(df: pd.DataFrame, corr: pd.DataFrame, reglas) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = df.copy()
    df.columns = [c.lstrip("﻿") for c in df.columns]

    vehiculos = corr[corr["tipo"] == "vehiculo"].set_index("original")["codigo"]
    sin_codigo = sorted(set(df["AssetHostID"]) - set(vehiculos.index))
    if sin_codigo:
        raise SystemExit(f"Placas sin código en correspondencias.csv: {sin_codigo}. Agréguelas y vuelva a correr.")

    df["_salida"] = pd.to_datetime(df["DepartureDate"] + " " + df["DepartureTime"], format="%d/%m/%Y %H:%M:%S")
    df["AssetName2"], corr = codificar_conductores(df, corr)

    df["AssetHostID"] = df["AssetHostID"].map(vehiculos)
    df["AssetExtra"] = df["AssetHostID"]
    df["SiteName"] = "la Compañía"
    dia = df["_salida"].dt.normalize()
    df["DepartFrom"] = [asignar_zona(x, f, reglas) for x, f in zip(df["DepartFrom"], dia)]
    df["ArriveAt"] = [asignar_zona(x, f, reglas) for x, f in zip(df["ArriveAt"], dia)]

    df = df.drop(columns=COLUMNAS_A_ELIMINAR + ["_salida"])
    return df, corr


def main(crudo: Path, correspondencias: Path, zonas: Path, salida: Path) -> None:
    df = pd.read_csv(crudo, encoding="utf-8-sig", low_memory=False)
    corr = cargar_correspondencias(correspondencias)
    anon, corr = anonimizar(df, corr, cargar_zonas(zonas))

    assert len(anon) == len(df), "Se perdieron filas en la anonimización"
    anon.to_csv(salida, index=False, encoding="utf-8-sig")
    corr.to_csv(correspondencias, index=False, encoding="utf-8-sig")

    print(f"Viajes: {len(anon):,} | columnas: {anon.shape[1]} | vehículos: {anon['AssetHostID'].nunique()} "
          f"| conductores: {anon['AssetName2'].nunique()}")
    fechas = pd.to_datetime(anon["DepartureDate"], format="%d/%m/%Y")
    print(f"Periodo: {fechas.min():%d/%m/%Y} a {fechas.max():%d/%m/%Y}")
    print("Viajes por zona de salida:")
    print(anon["DepartFrom"].value_counts().to_string())
    print(f"Archivo anonimizado: {salida}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--crudo", type=Path, default=CRUDO)
    p.add_argument("--correspondencias", type=Path, default=CORRESPONDENCIAS)
    p.add_argument("--zonas", type=Path, default=ZONAS)
    p.add_argument("--salida", type=Path, default=SALIDA)
    a = p.parse_args()
    main(a.crudo, a.correspondencias, a.zonas, a.salida)
