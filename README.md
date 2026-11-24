# Predicción de la fecha del próximo mantenimiento preventivo en la flota

Proyecto del curso **Despliegue de Soluciones Analíticas (MIAD – Universidad de los Andes)**.

Es un componente del proyecto de grado *"Predicción de fallas en flotas con Machine Learning para planificar el mantenimiento preventivo"*. El objetivo es estimar, para cada camioneta de la flota de la Compañía, **cuándo alcanzará el kilometraje de su próximo mantenimiento preventivo**, de modo que el responsable de flota pueda programar con anticipación el taller, los repuestos y las reparaciones pendientes.

La solución final incluye un modelo supervisado, una API para servir las predicciones y un tablero, desplegados en contenedores Docker.

## Prototipo desplegado

| Componente | Dirección |
|---|---|
| Tablero | http://3.18.4.17:8050 |
| API (documentación interactiva) | http://3.18.4.17:8001/docs |

La API y el tablero corren en contenedores Docker (`docker compose up -d --build`) en una instancia EC2 de AWS. El modelo en producción es un SVR (`svr_8`), registrado en MLflow.

## Documentación

- **Manual de usuario** del tablero: [PDF](docs/downloads/Manual_de_usuario.pdf) · [web](docs/web/manual_usuario.md)
- **Manual de instalación** (tablero, API y modelo): [PDF](docs/downloads/Manual_de_instalacion.pdf) · [web](docs/web/manual_instalacion.md)

## Estructura del repositorio

```
├── api/                  # API FastAPI: app/, pruebas, Dockerfile y artefactos/ (modelo final y datos anonimizados)
├── tablero/              # tablero Dash que consulta la API, con su Dockerfile
├── docker-compose.yml    # levanta la API (8001) y el tablero (8050)
├── src/
│   ├── pipeline_anonimizar_reporte.py   # reporte GPS crudo -> reporte anonimizado
│   ├── pipeline_preprocesamiento.py     # viajes -> tabla km por vehículo-día con contrato
│   └── modelos_comunes.py               # variables, pipeline de sklearn y registro en MLflow
├── notebooks/            # EDA y experimentos 01–07 (Ridge, Lasso, ElasticNet, RF, GB, XGBoost, SVR); 08 exporta el modelo
├── data/                 # metadatos DVC de los datos (los datos están en el remoto)
├── docs/                 # manuales (downloads/ en PDF, web/ en Markdown)
└── requirements.txt
```

## Datos

- **Fuente:** reporte diario de movimientos de la plataforma de seguimiento GPS de la Compañía: 11 camionetas de dos contratos, diciembre de 2023 a noviembre de 2026 (184.741 viajes).
- **Anonimización:** `src/pipeline_anonimizar_reporte.py` reemplaza placas por `VH-01`…`VH-11`, conductores por `Conductor NN` y ubicaciones por la letra del contrato. Las tablas de correspondencia quedan fuera del repositorio (`data/raw/`).
- **Versionamiento:** DVC con remoto en **Amazon S3** (Google Drive como respaldo). Versiones etiquetadas en Git: `datos-v1` (Entrega 2) y `datos-v2` (Entrega 3).

## Configuración del entorno

Requiere **Python 3.11 o 3.12**. Las versiones más recientes (3.13+) aún no son compatibles con todas las dependencias.

```powershell
git clone https://github.com/gabriela-rivera/proyecto-dsa.git
cd proyecto-dsa
python -m venv .venv                 # o: py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1         # Windows
# source .venv/bin/activate          # macOS / Linux
pip install -r requirements.txt
```

Si PowerShell bloquea la activación del entorno:
```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

## Obtener los datos (DVC + S3)

El remoto de datos es privado. Cada integrante tiene llaves de acceso propias al bucket (se entregan por un canal privado; nunca se suben al repositorio):

```powershell
dvc remote modify --local s3 access_key_id 'ACCESS_KEY'
dvc remote modify --local s3 secret_access_key 'SECRET_KEY'
dvc pull
```

Para publicar una nueva versión de los datos: `dvc add <ruta>`, `dvc push` y commit del archivo `.dvc`.

## Flujo de trabajo

| Paso | Qué se hace | Dónde |
|---|---|---|
| 1. Anonimización | Reporte GPS crudo → reporte anonimizado (versionado con DVC) | `src/pipeline_anonimizar_reporte.py` |
| 2. Preprocesamiento | Viajes → tabla de km por vehículo y día, con contrato y variables del modelo | `src/pipeline_preprocesamiento.py` |
| 3. Exploración | Análisis de los datos v1 (Entrega 1) y comparación con los datos v2 | `notebooks/EDA*.ipynb` |
| 4. Modelos | Línea base, Ridge, Lasso, ElasticNet, Random Forest, Gradient Boosting, XGBoost y SVR, registrados en MLflow | `notebooks/01` a `07` |
| 5. Modelo final | Se escoge por validación cruzada (`svr_8`) y se exporta a la API desde MLflow | `api/preparar_artefactos.py --run-id <RUN_ID>` |
| 6. Despliegue | API y tablero en contenedores Docker | `docker compose up -d --build` |

```powershell
python src/pipeline_anonimizar_reporte.py      # requiere los archivos privados de data/raw/
python src/pipeline_preprocesamiento.py
dvc add "data/Daily Movement Report Anonimizado.csv" data/processed
dvc push
```

Los experimentos se registran en un servidor MLflow con autenticación (variables `MLFLOW_TRACKING_URI`, `MLFLOW_TRACKING_USERNAME` y `MLFLOW_TRACKING_PASSWORD`). La configuración común de los modelos está en `src/modelos_comunes.py`.

La instalación de la API y el tablero, en la nube o en local, está en el [manual de instalación](docs/web/manual_instalacion.md).
