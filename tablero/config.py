"""Configuración del tablero de mantenimiento preventivo de flota.

El tablero no calcula nada: todos los datos y la estimación salen de la API (ver api/ en este repositorio).
La dirección de la API se define con la variable de entorno API_URL, así no hay que tocar el código
cuando cambia la máquina donde corre (EC2, Docker local, etc.).
"""
import os

# ---- API -----------------------------------------------------------------------------------------
API_URL = os.getenv("API_URL", "http://3.18.4.17:8001").rstrip("/")
API_TIMEOUT = float(os.getenv("API_TIMEOUT", "10"))      # segundos de espera por respuesta

# ---- Consultas -----------------------------------------------------------------------------------
DIAS_HISTORIAL = 120      # días que se piden a /historial (gráfica y tabla)
SEMANAS_USO = 26          # semanas que se piden a /uso-semanal
MAX_DIAS_PROYECCION = 60  # tope de días que se dibujan de la proyección en la gráfica

# ---- Paleta (la del equipo) ----------------------------------------------------------------------
AZUL_PRIMARIO = "#164479"
AZUL_SECUNDARIO = "#2B79BA"
AMARILLO = "#F8AA00"
ROJO = "#E7344C"
VERDE = "#65B32E"
