"""Pruebas de la API (se corren con los artefactos de api/artefactos). Uso, desde api/:  python -m pytest"""
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def cliente():
    with TestClient(app) as c:
        yield c


def test_health(cliente):
    r = cliente.get("/health")
    assert r.status_code == 200
    assert r.json()["estado"] == "ok"


def test_contratos_suman_toda_la_flota(cliente):
    contratos = cliente.get("/contratos").json()
    assert contratos and all(c["contrato"].startswith("Contrato ") for c in contratos)
    assert sum(c["vehiculos"] for c in contratos) == len(cliente.get("/vehiculos").json())


@pytest.mark.parametrize("valor", ["D", "d", "Contrato D", "contrato d"])
def test_contrato_acepta_varias_formas(cliente, valor):
    assert cliente.get("/vehiculos", params={"contrato": valor}).json() == \
        cliente.get("/vehiculos", params={"contrato": "Contrato D"}).json()


def test_resumen_nacional_y_por_contrato(cliente):
    nacional = cliente.get("/resumen").json()
    por_contrato = [cliente.get("/resumen", params={"contrato": c["contrato"]}).json()
                    for c in cliente.get("/contratos").json()]
    assert nacional["contrato"] is None
    assert nacional["vehiculos"] == sum(r["vehiculos"] for r in por_contrato)
    assert nacional["preventivo_8_14_dias"] == sum(r["preventivo_8_14_dias"] for r in por_contrato)


def test_flota_ordenada_y_coherente(cliente):
    flota = cliente.get("/flota").json()
    activos = [e for e in flota if e["activo"]]
    assert [e["dias"] for e in activos] == sorted(e["dias"] for e in activos)
    assert flota[:len(activos)] == activos          # los vehículos sin GPS reciente van al final
    for e in activos:
        assert e["proximo_servicio_km"] % 5000 == 0
        assert 0 < e["km_restantes"] <= 5000
        assert e["fecha_min"] <= e["fecha_estimada"] <= e["fecha_max"]


def test_vehiculo_sin_gps_reciente_queda_marcado(cliente):
    for e in cliente.get("/flota").json():
        assert (e["alerta"] == "sin_datos") == (not e["activo"])


def test_predict_con_km_del_ultimo_preventivo(cliente):
    base = cliente.post("/predict", json={"vehiculo": "vh-01"}).json()
    ultimo = base["proximo_servicio_km"] - 5000
    r = cliente.post("/predict", json={"vehiculo": "VH-01", "km_ultimo_preventivo": ultimo + 1000})
    assert r.status_code == 200
    e = r.json()
    assert e["base_supuesta"] is False
    assert e["proximo_servicio_km"] == ultimo + 6000
    assert e["km_restantes"] == pytest.approx(base["km_restantes"] + 1000, abs=0.2)


def test_predict_vencido(cliente):
    odo = cliente.post("/predict", json={"vehiculo": "VH-02"}).json()["odometro_km"]
    e = cliente.post("/predict", json={"vehiculo": "VH-02", "km_ultimo_preventivo": odo - 6000}).json()
    assert e["km_restantes"] == 0 and e["alerta"] in ("vencido", "sin_datos")


@pytest.mark.parametrize("ruta,metodo,cuerpo,codigo", [
    ("/predict", "post", {"vehiculo": "VH-99"}, 404),
    ("/predict", "post", {"vehiculo": "VH-01", "km_ultimo_preventivo": -5}, 422),
    ("/flota?contrato=Z", "get", None, 404),
    ("/historial/VH-99", "get", None, 404),
])
def test_errores(cliente, ruta, metodo, cuerpo, codigo):
    r = cliente.post(ruta, json=cuerpo) if metodo == "post" else cliente.get(ruta)
    assert r.status_code == codigo


def test_historial_y_proyeccion(cliente):
    h = cliente.get("/historial/VH-06", params={"dias": 30}).json()
    assert len(h["dias"]) == 30
    assert h["proyeccion"]["proximo_servicio_km"] % 5000 == 0


def test_uso_semanal_solo_del_contrato(cliente):
    del_b = set(cliente.get("/vehiculos", params={"contrato": "B"}).json())
    filas = cliente.get("/uso-semanal", params={"contrato": "B", "semanas": 4}).json()
    assert filas and {f["vehiculo"] for f in filas} <= del_b
    assert len({f["semana"] for f in filas}) <= 4
