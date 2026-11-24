"""Cliente de la API de mantenimiento preventivo.

Cada función corresponde a un endpoint. Todas lanzan ErrorAPI con un mensaje legible para el usuario
(API apagada, demasiado lenta, vehículo inexistente, dato inválido) en vez de dejar caer el tablero.
"""
import requests

import config as cfg


class ErrorAPI(Exception):
    """Fallo al consultar la API; el mensaje se muestra tal cual en el tablero."""


def _pedir(metodo: str, ruta: str, **kwargs):
    try:
        r = requests.request(metodo, f"{cfg.API_URL}{ruta}", timeout=cfg.API_TIMEOUT, **kwargs)
    except requests.exceptions.Timeout:
        raise ErrorAPI(f"La API no respondió en {cfg.API_TIMEOUT:g} segundos. Intenta de nuevo en un momento.")
    except requests.exceptions.RequestException:
        raise ErrorAPI("No se pudo conectar con la API. Verifica que esté encendida (máquina EC2 y contenedor) "
                       "y que la variable API_URL apunte a la dirección correcta.")
    if r.status_code >= 400:
        try:
            detalle = r.json().get("detail", "")
        except ValueError:
            detalle = ""
        if isinstance(detalle, list):                       # error de validación de la API (422)
            detalle = "; ".join(str(d.get("msg", "")) for d in detalle)
        raise ErrorAPI(detalle or f"La API respondió con el error {r.status_code}.")
    try:
        return r.json()
    except ValueError:
        raise ErrorAPI("La respuesta de la API no tiene el formato esperado.")


def _contrato(contrato):
    return {"contrato": contrato} if contrato else {}


def health():
    return _pedir("GET", "/health")


def contratos():
    return _pedir("GET", "/contratos")


def resumen(contrato=None):
    return _pedir("GET", "/resumen", params=_contrato(contrato))


def flota(contrato=None):
    return _pedir("GET", "/flota", params=_contrato(contrato))


def uso_semanal(contrato=None, semanas=cfg.SEMANAS_USO):
    return _pedir("GET", "/uso-semanal", params={**_contrato(contrato), "semanas": semanas})


def historial(vehiculo, dias=cfg.DIAS_HISTORIAL):
    return _pedir("GET", f"/historial/{vehiculo}", params={"dias": dias})


def predecir(vehiculo, km_ultimo_preventivo=None):
    cuerpo = {"vehiculo": vehiculo}
    if km_ultimo_preventivo is not None:
        cuerpo["km_ultimo_preventivo"] = km_ultimo_preventivo
    return _pedir("POST", "/predict", json=cuerpo)
