"""Tablero de mantenimiento de flota (Dash).

Ejecución local (desde la raíz del repo):   python tablero/app.py      ->  http://127.0.0.1:8050
Render (Root Directory = tablero):          gunicorn app:server
"""
import plotly.graph_objects as go
from dash import Dash, Input, Output, State, callback, ctx, dash_table, dcc, html

import config as cfg
import datos
import modelo

app = Dash(__name__, title="Mantenimiento de flota")
server = app.server                      # objeto WSGI que usa gunicorn en Render

modelo.precargar()
VEHICULOS = datos.vehiculos()
VEH_DEFECTO = VEHICULOS[0]
_, _, META = datos.cargar()
F_INI, F_FIN = datos.periodo()

FUENTE = '"Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif'

COLUMNAS = [
    {"name": "Carro", "id": "carro"},
    {"name": "Fecha", "id": "fecha"},
    {"name": "Viajes", "id": "viajes"},
    {"name": "Ubicación", "id": "ubicacion"},
    {"name": "Encargado", "id": "encargado"},
    {"name": "Km recorridos", "id": "km"},
]


def tarjeta(titulo, valor):
    return html.Div([html.Span(titulo, className="tarjeta-titulo"),
                     html.Span(valor, className="tarjeta-valor")], className="tarjeta")


def caja_fecha(valor):
    return [html.Span("Fecha estimada", className="caja-etiqueta"),
            html.Span(valor, className="caja-valor")]


# ------------------------------------------------------------------ Diseño (sigue la maqueta)
app.layout = html.Div(className="pagina", children=[
    dcc.Store(id="store-placa"),

    html.Header(className="encabezado", children=[
        html.H1("Mantenimiento de flota"),
        html.P(f"La Compañía · {cfg.CONTRATO} · Plataforma de seguimiento GPS · "
               f"{datos.fmt_fecha(F_INI)} – {datos.fmt_fecha(F_FIN)}", className="subtitulo"),
    ]),

    # Fila superior: buscador de placa + consulta al modelo (bloque sombreado)
    html.Div(className="fila-superior", children=[
        html.Div(className="buscador", children=[
            html.Label("Buscar placa", htmlFor="input-placa", className="etiqueta"),
            html.Div(className="buscador-controles", children=[
                dcc.Input(id="input-placa", type="text", value=VEH_DEFECTO, n_submit=0,
                          placeholder="Ej.: VH-01", className="campo"),
                html.Button("Buscar", id="btn-buscar", n_clicks=0, className="boton-secundario"),
            ]),
            html.Div(id="msg-busqueda", className="mensaje-error", role="alert"),
        ]),
        html.Div(className="panel-modelo", children=[
            html.Span("Consulta al modelo", className="panel-titulo"),
            html.Div(className="panel-controles", children=[
                html.Button("Consulta tu próximo mantenimiento", id="btn-consulta", n_clicks=0,
                            className="boton-principal"),
                html.Div(id="fecha-estimada", className="caja-fecha", children=caja_fecha("—"),
                         **{"aria-live": "polite"}),
            ]),
        ]),
    ]),

    html.Div(id="resultado-detalle", className="resultado-detalle", **{"aria-live": "polite"}),

    # Detalle del vehículo
    html.Section(className="seccion", children=[
        html.Div(className="seccion-cabecera", children=[
            html.H2("Detalle del vehículo"),
            html.Span(id="subtitulo-vehiculo", className="subtitulo-vehiculo"),
        ]),
        html.Div(id="tarjetas", className="tarjetas"),
    ]),

    # Uso reciente (gráfica)
    html.Section(className="seccion", children=[
        html.H2("Uso reciente del vehículo"),
        dcc.Graph(id="grafico-km", config={"displayModeBar": False}, style={"height": "320px"}),
    ]),

    # Historial
    html.Section(className="seccion", children=[
        html.H2("Historial de viajes / mantenimiento", className="centrado"),
        dash_table.DataTable(
            id="tabla-historial", columns=COLUMNAS, data=[], page_size=10, style_as_list_view=True,
            style_table={"overflowX": "auto"},
            style_header={"fontWeight": "600", "borderBottom": "2px solid #1F4D3A", "backgroundColor": "white",
                          "color": "#1B2A22", "fontFamily": FUENTE},
            style_cell={"padding": "10px 12px", "fontFamily": FUENTE, "fontSize": "15px",
                        "color": "#1B2A22", "textAlign": "left"},
            style_cell_conditional=[{"if": {"column_id": c}, "textAlign": "right"} for c in ("viajes", "km")],
        ),
    ]),

    html.Footer(className="pie", children=[
        f"Datos: plataforma de seguimiento GPS (anonimizados) · versión de datos (DVC): "
        f"{META['version_datos'][:8]} · Modelo: {META['modelo']}"
    ]),
])


# ------------------------------------------------------------------ Callbacks
@callback(Output("store-placa", "data"), Output("input-placa", "value"), Output("msg-busqueda", "children"),
          Input("btn-buscar", "n_clicks"), Input("input-placa", "n_submit"),
          State("input-placa", "value"), State("store-placa", "data"))
def buscar(_clicks, _submit, texto, actual):
    """Valida la placa escrita. Si no existe, conserva el vehículo actual y avisa."""
    if ctx.triggered_id is None:                                   # carga inicial
        return VEH_DEFECTO, VEH_DEFECTO, ""
    placa = datos.normalizar_placa(texto or "")
    if placa in VEHICULOS:
        return placa, placa, ""
    return actual, actual, f"No encontramos la placa «{texto}». Placas disponibles: {', '.join(VEHICULOS)}."


@callback(Output("subtitulo-vehiculo", "children"), Output("tarjetas", "children"),
          Output("grafico-km", "figure"), Output("tabla-historial", "data"),
          Input("store-placa", "data"))
def actualizar_vistas(placa):
    if not placa:
        return "", [], go.Figure(), []
    d = datos.detalle(placa)
    tarjetas = [
        tarjeta("Odómetro actual", f"{datos.fmt_num(d['odometro'])} km"),
        tarjeta("Km recorridos en el periodo", f"{datos.fmt_num(d['km_periodo'])} km"),
        tarjeta("Viajes registrados", datos.fmt_num(d["viajes"])),
        tarjeta("Último registro", datos.fmt_fecha(d["ultimo_registro"])),
    ]

    s = datos.serie_km(placa)
    fig = go.Figure()
    fig.add_bar(x=s["fecha"], y=s["km"], name="Km por día", marker_color="#9DBFAB")
    fig.add_scatter(x=s["fecha"], y=s["km_media28"], name="Promedio móvil 28 días",
                    mode="lines", line={"color": "#1F4D3A", "width": 3})
    fig.update_layout(margin={"l": 40, "r": 10, "t": 10, "b": 40}, paper_bgcolor="white", plot_bgcolor="white",
                      yaxis_title="km", legend={"orientation": "h", "y": 1.12, "x": 0},
                      font={"color": "#1B2A22"}, hovermode="x unified")
    fig.update_yaxes(gridcolor="#E3E9E4")

    h = datos.historial(placa)
    filas = [{"carro": placa, "fecha": datos.fmt_fecha(r.fecha), "viajes": int(r.viajes),
              "ubicacion": cfg.REGION, "encargado": r.conductor, "km": datos.fmt_num(r.km, 1)}
             for r in h.itertuples()]
    return f"{placa} · {cfg.DESCRIPCION_VEHICULO}", tarjetas, fig, filas


@callback(Output("fecha-estimada", "children"), Output("resultado-detalle", "children"),
          Input("btn-consulta", "n_clicks"), Input("store-placa", "data"))
def consultar(_n, placa):
    """Consulta al modelo. Se borra el resultado al cambiar de vehículo."""
    if ctx.triggered_id != "btn-consulta" or not placa:
        return caja_fecha("—"), []
    try:
        r = modelo.estimar(placa)
    except ValueError as e:
        return caja_fecha("—"), html.Div(str(e), className="aviso")

    if r["km_faltantes"] <= 0:
        resumen = "El vehículo ya superó el kilometraje de su próximo preventivo."
    else:
        resumen = (f"Faltan unos {datos.fmt_num(r['km_faltantes'])} km. Con un uso pronosticado de "
                   f"{datos.fmt_num(r['km_dia'])} km/día, el preventivo llegaría en unos {r['dias']} días.")
    tope = " o más" if r["dias_max_topado"] else ""
    rango = (f"Rango probable: del {datos.fmt_fecha(r['fecha_min'])} al {datos.fmt_fecha(r['fecha_max'])}{tope} "
             f"(el modelo se equivoca en promedio {datos.fmt_num(r['error_km_dia'])} km/día en este vehículo).")

    avisos = []
    if r["uso_bajo"]:
        avisos.append("Este vehículo recorre muy pocos km por día; la estimación es menos confiable.")
    if r["dias_sin_datos"] > cfg.DIAS_MAX_SIN_DATOS:
        aviso = (f"Los últimos datos de este vehículo son de hace {r['dias_sin_datos']} días "
                 f"({datos.fmt_fecha(r['fecha_referencia'])}); la fecha se calcula desde ese día.")
        if r["fecha_variables"] < r["fecha_referencia"]:
            aviso += f" El pronóstico de uso se basa en datos hasta el {datos.fmt_fecha(r['fecha_variables'])}."
        avisos.append(aviso)
    if r["base_supuesta"]:
        avisos.append(f"Se asume un preventivo cada {datos.fmt_num(cfg.INTERVALO_KM)} km desde el último múltiplo; "
                      "falta cargar el último preventivo real.")

    detalle = [html.P(resumen), html.P(rango, className="texto-secundario")]
    detalle += [html.Div(a, className="aviso") for a in avisos]
    return caja_fecha(datos.fmt_fecha(r["fecha"])), detalle


if __name__ == "__main__":
    app.run(debug=True)
