"""Configuración central del tablero de mantenimiento de flota."""
from pathlib import Path

BASE = Path(__file__).resolve().parent      # .../tablero
RAIZ = BASE.parent                          # raíz del repositorio

# ---- Artefactos que usa el tablero en ejecución (van en Git; ya anonimizados) ----
ARTEFACTOS = BASE / "artefactos"
RUTA_PANEL = ARTEFACTOS / "panel_diario.csv"
RUTA_HISTORIAL = ARTEFACTOS / "historial_diario.csv"
RUTA_MODELO = ARTEFACTOS / "modelo_ridge.joblib"
RUTA_META = ARTEFACTOS / "metadatos.json"

# ---- Entradas versionadas con DVC (solo las usa preparar_artefactos.py) ----
RUTA_KM_DIARIO = RAIZ / "data" / "processed" / "km_diario.csv"
RUTA_VIAJES = RAIZ / "data" / "processed" / "viajes_limpios.csv"
RUTA_PROCESSED_DVC = RAIZ / "data" / "processed.dvc"

# ---- Contexto (anonimizado según la tabla de anonimización del equipo) ----
CONTRATO = "Contrato D"            # confirmar con el equipo
REGION = "Llanos Orientales"
DESCRIPCION_VEHICULO = "Nissan Frontier 2024"

# ---- Reglas de negocio ----
INTERVALO_KM = 5000                # un preventivo cada 5.000 km (guías del proyecto)
# Odómetro del último preventivo de cada vehículo, cuando se tenga el consolidado de mantenimiento.
# Ejemplo: {"VH-01": 45000.0}. Si un vehículo no está aquí, se asume que el último preventivo fue en el
# múltiplo de INTERVALO_KM más reciente (supuesto provisional que se muestra en el tablero).
ODO_ULTIMO_PREVENTIVO: dict[str, float] = {}
UMBRAL_USO_BAJO_KM_DIA = 50        # por debajo de esto se avisa que la estimación es menos confiable
DIAS_MAX_SIN_DATOS = 7             # más días sin datos que esto -> aviso de datos desactualizados
MAX_DIAS_RANGO = 365               # tope para el extremo superior del rango de fechas

# ---- Modelo (debe coincidir con src/modelos_comunes.py) ----
OBJETIVO = "km_media_prox28"       # km/día promedio de los próximos 28 días
NUMERICAS = [
    "km_lag1", "km_lag2", "km_lag7",
    "km_media7", "km_media14", "km_media28", "km_std7", "km_media_dia_semana",
    "dia_semana", "fin_de_semana", "mes",
]
CATEGORICAS = ["vehiculo"]
FEATURES = NUMERICAS + CATEGORICAS
ALPHA = 0.01                       # Ridge con el menor CV MAE en MLflow (ridge_alpha_0.01)
