"""Configuración de la API: rutas de los artefactos y reglas del negocio."""
import os
from pathlib import Path

RAIZ_API = Path(__file__).resolve().parents[1]
ARTEFACTOS = Path(os.getenv("ARTEFACTOS_DIR", RAIZ_API / "artefactos"))
RUTA_MODELO = ARTEFACTOS / "modelo.joblib"
RUTA_PANEL = ARTEFACTOS / "panel.csv"
RUTA_META = ARTEFACTOS / "metadatos.json"

API_VERSION = "2.0.0"

# Reglas del negocio
INTERVALO_KM = 5000            # la Compañía hace preventivo cada 5.000 km
DIAS_MAX_SIN_DATOS = 7         # más días sin GPS => vehículo inactivo ("Sin GPS desde ...")
ALERTA_ROJA_DIAS = 7           # preventivo en 7 días o menos
ALERTA_AMARILLA_DIAS = 14      # preventivo entre 8 y 14 días
MAX_DIAS = 365                 # tope para la fecha estimada
DIAS_KM_RECIENTE = 28          # ventana del km/día descriptivo
NO_CONTRATO = ("Traslado",)    # zonas que no son un contrato

# Nombre para mostrar de cada contrato (solo códigos anonimizados)
ETIQUETAS_CONTRATO = {"Contrato D": "Contrato D (piloto)"}
