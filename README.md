# Predicción de la fecha del próximo mantenimiento preventivo en la flota

Proyecto del curso **Despliegue de Soluciones Analíticas (MIAD – Universidad de los Andes)**.

Es un componente del proyecto de grado *"Predicción de fallas en flotas con Machine Learning para planificar el mantenimiento preventivo"*. El objetivo es estimar, para cada camioneta de la flota de la Compañía, **cuándo alcanzará el kilometraje de su próximo mantenimiento preventivo**, de modo que el responsable de flota pueda programar con anticipación el taller, los repuestos y las reparaciones pendientes.

La solución final incluye un modelo supervisado, una API para servir las predicciones y un tablero, desplegados en contenedores Docker.

## Estado del proyecto

| Entrega | Contenido | Estado |
|---|---|---|
| 1 | Problema, pregunta de negocio, datos, exploración (EDA), maqueta | Entregada, pendiente de retroalimentación |
| 2 | Preprocesamiento, modelos, experimentos en MLflow, tablero | En desarrollo |
| 3 | API, empaquetado y despliegue en Docker | Pendiente |

## Estructura del repositorio

```
├── data/
│   ├── Daily Movement Report Anonimizado.csv.dvc   # datos crudos (metadatos DVC)
│   └── processed.dvc                               # datos procesados (metadatos DVC)
├── notebooks/
│   └── EDA Daily Movement Report.ipynb             # análisis exploratorio (Entrega 1)
├── src/
│   └── pipeline_preprocesamiento.py                # viajes GPS -> tabla km por vehículo-día
├── .dvc/config                                     # configuración del remoto DVC
├── requirements.txt
└── README.md
```

## Datos

- **Fuente:** reporte diario de movimientos de la plataforma GPS del contrato piloto (5 camionetas, mayo–octubre de 2026, 9.589 viajes).
- **Anonimización:** vehículos como `VH-01` a `VH-05` y conductores como `Conductor 01` a `Conductor 20`. Sin placas ni datos personales.
- **Versionamiento:** los datos se gestionan con **DVC** y se almacenan en un remoto de **Google Drive**. En Git solo se versionan los archivos `.dvc`.

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

## Obtener los datos (DVC + Google Drive)

Los datos están en un remoto de Google Drive. Para acceder, pide al equipo que agregue tu cuenta de Google y te comparta el secreto del cliente OAuth (por un canal privado; nunca se sube al repositorio).

```powershell
dvc remote modify --local gdrive gdrive_client_secret "SECRETO"
dvc pull
```

La primera vez se abre el navegador para autorizar el acceso. Si aparece el error `invalid_grant` (la autorización vence cada 7 días), borra la carpeta `pydrive2fs` del caché de tu usuario y repite `dvc pull`.

Para publicar una nueva versión de los datos: `dvc add <ruta>`, `dvc push` y commit del archivo `.dvc`.

## Preprocesamiento

`src/pipeline_preprocesamiento.py` transforma los viajes del GPS en una tabla con un registro por vehículo y día (`data/processed/km_diario.csv`), que es la que usa el modelo. Las reglas de limpieza, las variables y los parámetros están documentados al inicio del script.

```powershell
python src/pipeline_preprocesamiento.py
dvc add data/processed
dvc push
```