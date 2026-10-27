# Predicción de la fecha del próximo mantenimiento preventivo en la flota 

Proyecto del curso **Despliegue de Soluciones Analíticas (MIAD – Universidad de los Andes)**.

Es un componente del proyecto de grado *"Predicción de fallas en flotas con Machine Learning para planificar el mantenimiento preventivo"*. El objetivo es estimar, para cada camioneta de la flota de la Compañía, **cuándo alcanzará el kilometraje de su próximo mantenimiento preventivo**, de modo que el responsable de flota pueda programar con anticipación el taller, los repuestos y las reparaciones pendientes.

La solución final incluye un modelo supervisado, una API para servir las predicciones y un tablero, desplegados en contenedores Docker.

## Estado del proyecto

| Entrega | Contenido | Estado |
|---|---|---|
| 1 | Problema, pregunta de negocio, datos, exploración (EDA), maqueta | Entregada, pendiente de retroalimentación
| 2 | Modelos, experimentos en MLflow, tablero | Pendiente
| 3 | API, empaquetado y despliegue en Docker | Pendiente

## Estructura del repositorio

```
├── data/
│   └── Daily Movement Report Anonimizado.csv.dvc   # metadatos DVC (el CSV está en el remoto)
├── notebooks/
│   └── EDA_Daily_Movement_Report.ipynb             # análisis exploratorio
├── .dvc/config                                     # configuración del remoto DVC
├── requirements.txt
└── README.md
```

## Datos

- **Fuente:** reporte diario de movimientos de la plataforma GPS del contrato piloto (5 camionetas, mayo–octubre de 2026, 9.589 viajes).
- **Anonimización:** vehículos como `VH-01` a `VH-05` y conductores como `Conductor 01` a `Conductor 20`. Sin placas ni datos personales.
- **Versionamiento:** los datos se gestionan con **DVC** y se almacenan en un remoto de **Google Drive**. En Git solo se versionan los archivos `.dvc`.

## Configuración del entorno

```powershell
git clone https://github.com/gabriela-rivera/proyecto-dsa.git
cd proyecto-dsa
python -m venv .venv
.\.venv\Scripts\Activate.ps1        # Windows
# source .venv/bin/activate         # macOS / Linux
pip install -r requirements.txt
```

## Obtener los datos (DVC + Google Drive)

1. Pide al equipo que agregue tu cuenta de Google como **usuario de prueba** de la app y como **editor** de la carpeta de Drive.
2. Configura el secreto del cliente OAuth. Lo entrega el equipo por un canal privado 
   ```powershell
   dvc remote modify --local gdrive gdrive_client_secret "SECRETO"
   ```
3. Descarga los datos:
   ```powershell
   dvc pull
   ```

Para publicar una nueva versión de los datos:
```powershell
dvc add "data/<archivo>.csv"
dvc push
git add "data/<archivo>.csv.dvc"
git commit -m "Actualizar datos"
git push
```