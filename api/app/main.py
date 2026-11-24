"""API de predicción de la fecha del próximo mantenimiento preventivo de la flota.

Ejecutar en local (desde la carpeta api/):
    uvicorn app.main:app --reload --port 8001
Documentación interactiva: http://localhost:8001/docs
"""
from contextlib import asynccontextmanager
from datetime import date

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from app import config as cfg
from app import prediccion as pr


@asynccontextmanager
async def lifespan(_: FastAPI):
    pr.cargar_modelo()      # carga el modelo y los datos una sola vez al arrancar
    pr.cargar_datos()
    yield


app = FastAPI(
    title="API · Próximo mantenimiento preventivo de la flota",
    description=("Estima el km/día de cada vehículo para los próximos 28 días y, con él, la fecha del "
                 "próximo preventivo (cada 5.000 km). Datos anonimizados de la plataforma GPS."),
    version=cfg.API_VERSION,
    lifespan=lifespan,
)


# --------------------------------------------------------------------------- esquemas
class Salud(BaseModel):
    estado: str
    version_api: str
    modelo: str
    origen_modelo: str
    version_datos: str
    fecha_datos: date


class Contrato(BaseModel):
    contrato: str
    etiqueta: str
    vehiculos: int
    activos: int


class Resumen(BaseModel):
    contrato: str | None = Field(description="None = vista nacional")
    fecha_datos: date
    vehiculos: int
    vehiculos_activos: int
    preventivo_0_7_dias: int
    preventivo_8_14_dias: int
    km_dia_promedio_28: float | None


class Estimacion(BaseModel):
    vehiculo: str
    contrato: str | None
    activo: bool
    ultimo_dato_gps: date
    dias_sin_datos: int
    odometro_km: float
    km_dia_pronosticado: float
    km_dia_ultimos_28: float | None
    proximo_servicio_km: int
    km_restantes: float
    base_supuesta: bool = Field(description="True si se supuso el último preventivo en el múltiplo de 5.000 km")
    dias: int
    fecha_estimada: date
    fecha_min: date
    fecha_max: date
    error_km_dia: float
    alerta: str = Field(description="0_7_dias | 8_14_dias | mas_14_dias | vencido | sin_datos")
    alerta_texto: str


class SolicitudPrediccion(BaseModel):
    vehiculo: str = Field(examples=["VH-07"])
    km_ultimo_preventivo: float | None = Field(default=None, ge=0, examples=[150000])


class DiaKm(BaseModel):
    fecha: date
    km: float | None
    contrato: str | None


class Proyeccion(BaseModel):
    km_dia_pronosticado: float
    proximo_servicio_km: int
    km_restantes: float
    fecha_estimada: date


class Historial(BaseModel):
    vehiculo: str
    dias: list[DiaKm]
    proyeccion: Proyeccion


class UsoSemanal(BaseModel):
    semana: date = Field(description="Lunes de la semana")
    vehiculo: str
    km: float


# --------------------------------------------------------------------------- utilidades
def _contrato(valor: str | None) -> str | None:
    c = pr.normalizar_contrato(valor)
    if c is not None and c not in set(pr.contrato_actual().values()):
        raise HTTPException(404, f"No existe el contrato {valor}.")
    return c


def _vehiculo(valor: str) -> str:
    v = valor.strip().upper()
    if v not in pr.vehiculos():
        raise HTTPException(404, f"No existe el vehículo {valor}.")
    return v


# --------------------------------------------------------------------------- rutas
@app.get("/", include_in_schema=False)
@app.get("/health", response_model=Salud, tags=["estado"])
def health():
    _, meta = pr.cargar_datos()
    return Salud(estado="ok", version_api=cfg.API_VERSION, modelo=meta["modelo"],
                 origen_modelo=meta["origen"], version_datos=meta["version_datos"],
                 fecha_datos=pr.fecha_datos())


@app.get("/contratos", response_model=list[Contrato], tags=["flota"])
def contratos():
    return pr.contratos()


@app.get("/vehiculos", response_model=list[str], tags=["flota"])
def vehiculos(contrato: str | None = Query(None, examples=["D"])):
    return pr.vehiculos(_contrato(contrato))


@app.get("/resumen", response_model=Resumen, tags=["flota"])
def resumen(contrato: str | None = Query(None, description="Sin contrato = vista nacional", examples=["D"])):
    return pr.resumen(_contrato(contrato))


@app.get("/flota", response_model=list[Estimacion], tags=["flota"])
def flota(contrato: str | None = Query(None, description="Sin contrato = vista nacional", examples=["D"])):
    return pr.flota(_contrato(contrato))


@app.post("/predict", response_model=Estimacion, tags=["predicción"])
def predict(solicitud: SolicitudPrediccion):
    vehiculo = _vehiculo(solicitud.vehiculo)
    try:
        return pr.estado_vehiculo(vehiculo, solicitud.km_ultimo_preventivo)
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.get("/historial/{vehiculo}", response_model=Historial, tags=["descriptivo"])
def historial(vehiculo: str, dias: int = Query(60, ge=7, le=400)):
    return pr.historial(_vehiculo(vehiculo), dias)


@app.get("/uso-semanal", response_model=list[UsoSemanal], tags=["descriptivo"])
def uso_semanal(contrato: str | None = Query(None, examples=["B"]), semanas: int = Query(26, ge=1, le=156)):
    return pr.uso_semanal(_contrato(contrato), semanas)
