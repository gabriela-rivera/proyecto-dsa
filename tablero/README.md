# Tablero de mantenimiento de flota (Dash)

Tablero que sigue la maqueta de la Entrega 1: buscar una placa, ver el detalle del vehículo, su historial de viajes y
consultar al modelo la fecha estimada del próximo mantenimiento preventivo.

## Archivos

| Archivo | Para qué sirve |
|---|---|
| `app.py` | Diseño del tablero y callbacks (punto de entrada; expone `server` para gunicorn) |
| `modelo.py` | Carga el modelo y calcula la fecha estimada. Aquí se cambiará por una llamada a la API en la Entrega 3 |
| `datos.py` | Lectura de los artefactos y consultas por vehículo |
| `config.py` | Parámetros: contrato, intervalo de 5.000 km, variables del modelo, rutas |
| `preparar_artefactos.py` | Genera `artefactos/` a partir de los datos de DVC y entrena el modelo final |
| `assets/estilos.css` | Estilos |
| `artefactos/` | Datos anonimizados ya procesados + modelo (`.joblib`) + metadatos. Es lo único que lee el tablero |
| `requirements.txt` | Dependencias del tablero (las escribe `preparar_artefactos.py`) |

## Ejecutar en local (desde la raíz del repo)

```powershell
dvc pull                                    # trae data/processed
python tablero/preparar_artefactos.py       # genera tablero/artefactos y tablero/requirements.txt
python tablero/app.py                       # abre http://127.0.0.1:8050
```

## Cómo funciona la estimación

1. El modelo (Ridge, alpha = 0,01) pronostica los **km/día promedio de los próximos 28 días** del vehículo.
2. Se calculan los **km que faltan** para el siguiente preventivo (intervalo de 5.000 km).
3. `fecha estimada = último día con datos + km faltantes / km por día pronosticados`.
4. El **rango probable** usa el error típico del modelo en prueba para ese vehículo.

Supuesto provisional: sin el consolidado de mantenimiento, se asume que el último preventivo fue en el múltiplo de 5.000 km
más reciente. Cuando se tenga, se cargan los odómetros reales en `ODO_ULTIMO_PREVENTIVO` de `config.py`.

## Despliegue en Render

- Root Directory: `tablero`
- Build Command: `pip install -r requirements.txt`
- Start Command: `gunicorn app:server --bind 0.0.0.0:$PORT --workers 1 --timeout 120`
- Variable de entorno: `PYTHON_VERSION` con la misma versión de Python con la que se generaron los artefactos
