"""Tablero de mantenimiento preventivo de flota (Dash). Todos los datos salen de la API.

Local (desde la carpeta tablero/):   python app.py      ->  http://127.0.0.1:8050
Producción / Docker:                 gunicorn app:server --bind 0.0.0.0:$PORT
La API se define con la variable de entorno API_URL (ver config.py).
"""
import os
from datetime import date, timedelta

import plotly.graph_objects as go
from dash import ALL, Dash, Input, Output, State, callback, ctx, dash_table, dcc, html, no_update
from dash.exceptions import PreventUpdate

import api
import config as cfg

app = Dash(__name__, title="Mantenimiento preventivo de flota", update_title=None)
server = app.server                       # objeto WSGI que usa gunicorn
app.index_string = app.index_string.replace("<html>", '<html lang="es">')

FUENTE = '"Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif'
NACIONAL = "nacional"


# ------------------------------------------------------------------ formato (es-CO: 1.234,5 · dd/mm/aaaa)
def num(x, dec=0):
    if x is None:
        return "—"
    return f"{x:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def fecha(iso):
    return "—" if not iso else date.fromisoformat(iso[:10]).strftime("%d/%m/%Y")


def corta(iso):
    return date.fromisoformat(iso[:10]).strftime("%d/%m")


def codigo(contrato):
    return (contrato or "—").replace("Contrato ", "")


def chip(texto):
    """Etiqueta con el endpoint que alimenta cada bloque (sirve para mostrar la integración con la API)."""
    return html.Span(texto, className="chip")


# ------------------------------------------------------------------ piezas del diseño
def tarjeta(titulo, valor, sub=None, clase=""):
    return html.Div([html.Span(titulo, className="tarjeta-titulo"),
                     html.Span(valor, className=f"tarjeta-valor {clase}"),
                     html.Span(sub or "", className="tarjeta-sub")], className="tarjeta")


def kpis(resumen):
    if resumen is None:
        return [tarjeta("Vehículos activos", "—"), tarjeta("Preventivo en ≤ 7 días", "—"),
                tarjeta("Preventivo en 8–14 días", "—"), tarjeta("Km/día prom. (28 días)", "—")]
    return [
        tarjeta("Vehículos activos", num(resumen["vehiculos_activos"]), f"de {num(resumen['vehiculos'])} en el contrato"
                if resumen["contrato"] else f"de {num(resumen['vehiculos'])} en la flota"),
        tarjeta("Preventivo en ≤ 7 días", num(resumen["preventivo_0_7_dias"]), "incluye vencidos", "rojo"),
        tarjeta("Preventivo en 8–14 días", num(resumen["preventivo_8_14_dias"]), None, "amarillo"),
        tarjeta("Km/día prom. (28 días)", num(resumen["km_dia_promedio_28"]), "vehículos activos"),
    ]


def tabla_flota(flota, seleccionado):
    cabecera = html.Thead(html.Tr([html.Th(t) for t in
                                   ("Vehículo", "Contrato", "Km/día", "Próximo", "Restan", "Fecha", "Alerta")]))
    filas = []
    for e in flota:
        sin_gps = e["alerta"] == "sin_datos"
        filas.append(html.Tr(className=("seleccionada " if e["vehiculo"] == seleccionado else "") + ("apagada" if sin_gps else ""),
                             children=[
            html.Td(html.Button(e["vehiculo"], id={"type": "fila", "vehiculo": e["vehiculo"]}, n_clicks=0,
                                className="fila-boton", title="Ver el detalle de este vehículo")),
            html.Td(codigo(e["contrato"])),
            html.Td(num(e["km_dia_pronosticado"]), className="der"),
            html.Td(num(e["proximo_servicio_km"]), className="der"),
            html.Td(num(e["km_restantes"]), className="der"),
            html.Td("—" if sin_gps else fecha(e["fecha_estimada"]), className="der"),
            html.Td(html.Span("Sin GPS" if sin_gps else e["alerta_texto"], className=f"pill pill-{e['alerta']}",
                              title=e["alerta_texto"])),
        ]))
    if not filas:
        return html.P("No hay vehículos para mostrar.", className="texto-suave")
    return html.Div(html.Table([cabecera, html.Tbody(filas)], className="tabla-flota"), className="tabla-contenedor")


def figura_vacia(texto):
    fig = go.Figure()
    fig.update_layout(template="simple_white", xaxis={"visible": False}, yaxis={"visible": False},
                      margin={"l": 10, "r": 10, "t": 10, "b": 10},
                      annotations=[{"text": texto, "showarrow": False, "font": {"size": 15, "color": "#55636F"}}])
    return fig


def figura_km(h):
    """Km por día del vehículo + proyección hasta la fecha estimada del próximo preventivo."""
    dias = h["dias"]
    x = [d["fecha"] for d in dias]
    y = [d["km"] for d in dias]
    p = h["proyeccion"]
    fig = go.Figure()
    fig.add_bar(x=x, y=y, name="Km diarios", marker_color=cfg.AZUL_SECUNDARIO,
                hovertemplate="%{x|%d/%m/%Y}<br>%{y:,.1f} km<extra></extra>")
    ultimo = date.fromisoformat(x[-1])
    est = date.fromisoformat(p["fecha_estimada"])
    n_proy = max(min((est - ultimo).days, cfg.MAX_DIAS_PROYECCION), 0)
    fin = ultimo + timedelta(days=n_proy)
    if n_proy:
        px = [(ultimo + timedelta(days=i)).isoformat() for i in range(1, n_proy + 1)]
        fig.add_bar(x=px, y=[p["km_dia_pronosticado"]] * n_proy, name="Proyección (km/día)",
                    marker_color="rgba(43,121,186,0.22)", marker_line_color=cfg.AZUL_SECUNDARIO, marker_line_width=1,
                    hovertemplate="%{x|%d/%m/%Y}<br>%{y:,.1f} km/día (proyectado)<extra></extra>")
    # línea vertical en la fecha estimada
    en_rango = est <= fin
    xl = est.isoformat() if en_rango else fin.isoformat()
    fig.add_shape(type="line", x0=xl, x1=xl, y0=0, y1=1, yref="paper", line={"color": cfg.ROJO, "width": 2})
    etiqueta = f"{num(p['proximo_servicio_km'])} km · {corta(p['fecha_estimada'])}"
    if not en_rango:
        etiqueta += " (fuera del rango)"
    fig.add_annotation(x=xl, y=1, yref="paper", text=etiqueta, showarrow=False, xanchor="right", yanchor="bottom",
                       font={"color": "#A01B30", "size": 12})
    fig.update_layout(template="simple_white", barmode="overlay", bargap=0.15, font={"family": FUENTE, "size": 13},
                      separators=",.", margin={"l": 50, "r": 20, "t": 30, "b": 40}, legend={"orientation": "h", "y": -0.2},
                      xaxis={"range": [x[0], (fin + timedelta(days=2)).isoformat()], "tickformat": "%d/%m"},
                      yaxis={"title": "km por día", "gridcolor": "#E3E8EE", "tickformat": ",d"})
    return fig


def figura_uso(filas):
    """Km totales por semana del contrato (o de toda la flota)."""
    if not filas:
        return figura_vacia("Sin datos de uso semanal")
    por_semana = {}
    for f in filas:
        por_semana[f["semana"]] = por_semana.get(f["semana"], 0) + f["km"]
    semanas = sorted(por_semana)
    fig = go.Figure(go.Bar(x=semanas, y=[por_semana[s] for s in semanas], marker_color=cfg.AZUL_PRIMARIO,
                           hovertemplate="Semana del %{x|%d/%m/%Y}<br>%{y:,.0f} km<extra></extra>"))
    fig.update_layout(template="simple_white", font={"family": FUENTE, "size": 13}, bargap=0.2, separators=",.",
                      margin={"l": 60, "r": 10, "t": 10, "b": 40},
                      xaxis={"title": "semana (lunes)", "tickformat": "%d/%m"},
                      yaxis={"title": "km totales", "gridcolor": "#E3E8EE", "tickformat": ",d"})
    return fig


def cajas(fecha_txt="—", km_dia="—", restan="—"):
    def una(etiqueta, valor, clase=""):
        return html.Div([html.Span(etiqueta, className="caja-etiqueta"), html.Span(valor, className=f"caja-valor {clase}")],
                        className="caja-resultado")
    return [una("Fecha estimada", fecha_txt, "grande"), una("Km/día", km_dia), una("Km restantes", restan)]


def aviso_api(error):
    return html.Div([html.Strong("No se pudo cargar la información. "), str(error)], className="banner-error", role="alert")


COLUMNAS_HISTORIAL = [
    {"name": "Carro", "id": "carro"},
    {"name": "Fecha", "id": "fecha"},
    {"name": "Ubicación (contrato)", "id": "ubicacion"},
    {"name": "Km recorridos", "id": "km"},
]


# ------------------------------------------------------------------ diseño (maqueta de la Entrega 1 + vista por contrato)
def layout():
    """Se evalúa en cada carga de página: si la API cambió o estaba apagada, basta con recargar."""
    opciones = [{"label": "Nacional (todos los contratos)", "value": NACIONAL}]
    try:
        opciones += [{"label": c["etiqueta"], "value": c["contrato"]} for c in api.contratos()]
        salud = api.health()
        subtitulo = f"La Compañía · Plataforma de seguimiento GPS · datos al {fecha(salud['fecha_datos'])}"
        pie = (f"Datos anonimizados de la plataforma GPS · versión de datos (DVC): {salud['version_datos'][:8]} · "
               f"Modelo: {salud['modelo']} · API v{salud['version_api']}")
    except api.ErrorAPI:
        subtitulo, pie = "La Compañía · Plataforma de seguimiento GPS", "Datos anonimizados de la plataforma GPS"

    return html.Div(className="pagina", children=[
        dcc.Store(id="store-flota", data=[]),

        html.Header(className="encabezado", children=[
            html.Div([html.H1("Mantenimiento preventivo de flota"), html.P(subtitulo, className="subtitulo")]),
            html.Div(className="selector-contrato", children=[
                html.Label("Vista", htmlFor="dd-contrato", className="etiqueta-clara"),
                dcc.Dropdown(id="dd-contrato", options=opciones, value=NACIONAL, clearable=False, searchable=False),
            ]),
        ]),

        html.Div(id="banner"),
        html.Div(id="kpis", className="kpis", children=kpis(None)),

        # Fila principal (como el diseño de referencia): flota a la izquierda, consulta al modelo a la derecha
        html.Div(className="fila-principal", children=[
            html.Section(className="seccion", children=[
                html.Div(className="seccion-cabecera", children=[html.H2("Próximos preventivos"), chip("GET /flota")]),
                html.Div(id="tabla-flota"),
            ]),
            html.Div(className="panel-modelo", children=[
                html.Div(className="seccion-cabecera", children=[html.Span("Consulta al modelo", className="panel-titulo"),
                                                                  chip("POST /predict")]),
                html.Div(className="controles-consulta", children=[
                    html.Div(className="campo-con-etiqueta", children=[
                        html.Label("Buscar placa", htmlFor="dd-vehiculo", className="etiqueta"),
                        dcc.Dropdown(id="dd-vehiculo", options=[], value=None, clearable=False, searchable=True,
                                     placeholder="Ej.: VH-07", className="dd-placa"),
                    ]),
                    html.Div(className="campo-con-etiqueta", children=[
                        html.Label("Km del último preventivo (opcional)", htmlFor="km-preventivo", className="etiqueta"),
                        dcc.Input(id="km-preventivo", type="number", min=0, placeholder="Ej.: 150000",
                                  className="campo-km", debounce=False),
                    ]),
                ]),
                html.Button("Consulta tu próximo mantenimiento", id="btn-consulta", n_clicks=0, className="boton-principal"),
                html.Div(id="cajas-resultado", className="cajas-resultado", children=cajas(), **{"aria-live": "polite"}),
                html.Div(id="resultado-consulta", className="resultado-consulta", **{"aria-live": "polite"}),
                html.Div(className="sub-bloque", children=[
                    html.Div(className="seccion-cabecera", children=[
                        html.H3(id="titulo-grafico", children="Km diarios y proyección"), chip("GET /historial")]),
                    dcc.Graph(id="grafico-km", config={"displayModeBar": False}, style={"height": "280px"},
                              figure=figura_vacia("Selecciona un vehículo")),
                ]),
            ]),
        ]),

        # Debajo: detalle del vehículo
        html.Section(className="seccion", children=[
            html.Div(className="seccion-cabecera", children=[html.H2("Detalle del vehículo"),
                                                              html.Span(id="subtitulo-vehiculo", className="texto-suave")]),
            html.Div(id="aviso-vehiculo"),
            html.Div(id="tarjetas", className="tarjetas"),
        ]),

        # Historial del vehículo + uso semanal de la flota
        html.Div(className="fila-inferior", children=[
            html.Section(className="seccion", children=[
                html.H2("Historial del vehículo"),
                dash_table.DataTable(
                    id="tabla-historial", columns=COLUMNAS_HISTORIAL, data=[], page_size=10, style_as_list_view=True,
                    style_table={"overflowX": "auto"},
                    style_header={"fontWeight": "600", "borderBottom": f"2px solid {cfg.AZUL_PRIMARIO}",
                                  "backgroundColor": "white", "color": cfg.AZUL_PRIMARIO, "fontFamily": FUENTE},
                    style_cell={"padding": "10px 12px", "fontFamily": FUENTE, "fontSize": "15px", "color": "#1B2733",
                                "textAlign": "left"},
                    style_cell_conditional=[{"if": {"column_id": "km"}, "textAlign": "right"}],
                ),
            ]),
            html.Section(className="seccion", children=[
                html.Div(className="seccion-cabecera", children=[html.H2("Uso semanal"), chip("GET /uso-semanal")]),
                dcc.Graph(id="grafico-uso", config={"displayModeBar": False}, style={"height": "340px"},
                          figure=figura_vacia("Cargando…")),
            ]),
        ]),

        html.Footer(pie, className="pie"),
    ])


app.layout = layout


# ------------------------------------------------------------------ callbacks
@callback(Output("store-flota", "data"), Output("kpis", "children"), Output("grafico-uso", "figure"),
          Output("dd-vehiculo", "options"), Output("dd-vehiculo", "value"), Output("banner", "children"),
          Input("dd-contrato", "value"), State("dd-vehiculo", "value"))
def cargar_vista(contrato, actual):
    """Cambia el contrato (o Nacional): actualiza indicadores, tabla, uso semanal y lista de placas."""
    c = None if contrato in (None, NACIONAL) else contrato
    try:
        resumen, flota, uso = api.resumen(c), api.flota(c), api.uso_semanal(c)
    except api.ErrorAPI as e:
        return [], kpis(None), figura_vacia("Sin conexión con la API"), [], None, aviso_api(e)
    placas = sorted(e["vehiculo"] for e in flota)
    vehiculo = actual if actual in placas else (flota[0]["vehiculo"] if flota else None)
    return flota, kpis(resumen), figura_uso(uso), [{"label": p, "value": p} for p in placas], vehiculo, None


@callback(Output("tabla-flota", "children"), Input("store-flota", "data"), Input("dd-vehiculo", "value"))
def pintar_tabla(flota, seleccionado):
    return tabla_flota(flota or [], seleccionado)


@callback(Output("dd-vehiculo", "value", allow_duplicate=True),
          Input({"type": "fila", "vehiculo": ALL}, "n_clicks"), prevent_initial_call=True)
def elegir_desde_tabla(_clicks):
    """Clic en una fila de la tabla = elegir ese vehículo en el buscador."""
    if not ctx.triggered or not ctx.triggered[0]["value"]:
        raise PreventUpdate            # la tabla se acaba de volver a dibujar, no hubo clic
    return ctx.triggered_id["vehiculo"]


@callback(Output("tarjetas", "children"), Output("subtitulo-vehiculo", "children"), Output("aviso-vehiculo", "children"),
          Output("grafico-km", "figure"), Output("tabla-historial", "data"), Output("titulo-grafico", "children"),
          Input("dd-vehiculo", "value"), State("store-flota", "data"))
def cargar_vehiculo(vehiculo, flota):
    if not vehiculo:
        return [], "", None, figura_vacia("Selecciona un vehículo"), [], "Km diarios y proyección"
    e = next((x for x in (flota or []) if x["vehiculo"] == vehiculo), None)
    try:
        h = api.historial(vehiculo)
        e = e or api.predecir(vehiculo)
    except api.ErrorAPI as err:
        return [], vehiculo, aviso_api(err), figura_vacia("Sin datos para este vehículo"), [], f"Km diarios de {vehiculo}"

    aviso = None
    if not e["activo"]:
        aviso = html.Div(f"Este vehículo no reporta GPS desde el {fecha(e['ultimo_dato_gps'])} "
                         f"({e['dias_sin_datos']} días): los datos pueden estar desactualizados.", className="aviso")
    tarjetas = [
        tarjeta("Contrato actual", codigo(e["contrato"])),
        tarjeta("Odómetro", f"{num(e['odometro_km'])} km"),
        tarjeta("Último dato del GPS", fecha(e["ultimo_dato_gps"]),
                "hoy" if e["dias_sin_datos"] == 0 else f"hace {e['dias_sin_datos']} días"),
        tarjeta("Km/día (últimos 28 días)", num(e["km_dia_ultimos_28"], 1)),
        tarjeta("Próximo servicio", f"{num(e['proximo_servicio_km'])} km"),
        tarjeta("Km restantes", f"{num(e['km_restantes'])} km", "base supuesta" if e["base_supuesta"] else None),
    ]
    filas = [{"carro": vehiculo, "fecha": fecha(d["fecha"]), "ubicacion": d["contrato"] or "—",
              "km": "Sin dato" if d["km"] is None else num(d["km"], 1)} for d in reversed(h["dias"])]
    return (tarjetas, f"{vehiculo} · {codigo(e['contrato'])}", aviso, figura_km(h), filas,
            f"Km diarios de {vehiculo} y proyección")


@callback(Output("cajas-resultado", "children"), Output("resultado-consulta", "children"), Output("km-preventivo", "value"),
          Input("btn-consulta", "n_clicks"), Input("dd-vehiculo", "value"), State("km-preventivo", "value"))
def consultar(_clicks, vehiculo, km_prev):
    """Botón 'Consulta tu próximo mantenimiento': llama a POST /predict y muestra la fecha estimada."""
    if ctx.triggered_id != "btn-consulta":                       # cambió el vehículo: limpiar respuesta y km escrito
        return cajas(), None, None
    if not vehiculo:
        return cajas(), html.P("Elige primero un vehículo.", className="mensaje-error"), no_update
    if km_prev is not None and km_prev < 0:
        return (cajas(), html.P("El kilometraje del último preventivo no puede ser negativo.", className="mensaje-error"),
                no_update)
    try:
        e = api.predecir(vehiculo, km_prev)
    except api.ErrorAPI as err:
        return cajas(), html.P(str(err), className="mensaje-error", role="alert"), no_update

    notas = []
    if e["base_supuesta"]:
        notas.append("Se supone que el último preventivo fue en el múltiplo de 5.000 km más reciente. "
                     "Escribe el km real del último preventivo para afinar la fecha.")
    if not e["activo"]:
        notas.append(f"Sin GPS desde el {fecha(e['ultimo_dato_gps'])}: la estimación puede no ser confiable.")
    if e["alerta"] == "vencido":
        notas.append("El kilometraje del próximo servicio ya se superó: el preventivo está vencido.")
    detalle = [
        html.Div(className="fila-rango", children=[
            html.Span(e["alerta_texto"], className=f"pill pill-{e['alerta']}"),
            html.Span(f"Rango probable: {corta(e['fecha_min'])} – {corta(e['fecha_max'])}", className="texto-fuerte"),
        ]),
        html.P(f"Km/día pronosticado: {num(e['km_dia_pronosticado'], 1)} (error típico del modelo en este vehículo: "
               f"±{num(e['error_km_dia'], 1)} km/día).", className="texto-suave"),
    ] + [html.P(n, className="aviso") for n in notas]
    return cajas(fecha(e["fecha_estimada"]), num(e["km_dia_pronosticado"]), num(e["km_restantes"])), detalle, no_update


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8050")), debug=False)
