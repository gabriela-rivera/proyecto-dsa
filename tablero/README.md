# Tablero de mantenimiento preventivo de flota

Tablero en **Dash** que sigue la maqueta de la Entrega 1 y la amplía con la vista por contrato. No calcula nada:
todos los datos y la estimación de la fecha salen de la **API** (`api/` en este repositorio).

## Qué muestra y de dónde sale cada parte

| Parte del tablero | Endpoint de la API |
|---|---|
| Selector de vista (Nacional / contrato) | `GET /contratos` |
| Indicadores superiores | `GET /resumen?contrato=` |
| Próximos preventivos (tabla de la flota) | `GET /flota?contrato=` |
| Uso semanal | `GET /uso-semanal?contrato=&semanas=26` |
| Buscador de placa + bloque sombreado "Consulta al modelo" | `POST /predict` |
| Detalle del vehículo | `GET /flota` (datos del vehículo elegido) |
| Uso reciente y proyección; historial | `GET /historial/{vehiculo}?dias=120` |
| Pie de página (versión de datos y modelo) | `GET /health` |

"Nacional" es llamar a los mismos endpoints sin el parámetro `contrato`.

## Configuración

| Variable de entorno | Valor por defecto | Para qué sirve |
|---|---|---|
| `API_URL` | `http://3.18.4.17:8001` | Dirección de la API. Si cambia la máquina, solo se cambia esta variable. |
| `API_TIMEOUT` | `10` | Segundos de espera por cada respuesta de la API. |
| `PORT` | `8050` | Puerto del tablero al ejecutarlo con `python app.py`. |

## Ejecutar en local

Desde la carpeta `tablero/`, con el entorno virtual activo:

```powershell
pip install -r requirements.txt
$env:API_URL = "http://3.18.4.17:8001"     # opcional si la API está en la dirección por defecto
python app.py                              # http://127.0.0.1:8050
```

Si la API está apagada o `API_URL` está mal, el tablero no se cae: muestra un aviso con el motivo.

## Estructura

```
tablero/
├── app.py            # diseño y callbacks
├── api.py            # cliente de la API (una función por endpoint, errores legibles)
├── config.py         # API_URL, tiempos, paleta
├── assets/estilos.css
└── requirements.txt
```

## Alcance y limitaciones

- La tabla de historial muestra fecha, contrato (ubicación) y km por día. La maqueta incluía además viajes y
  encargado, que la API no entrega.
- La fecha estimada supone que el último preventivo se hizo en el múltiplo de 5.000 km más reciente, salvo que se
  escriba el km real del último preventivo en la consulta.
- Los vehículos sin GPS reciente (más de 7 días) se marcan como "Sin GPS" y no muestran fecha estimada en la tabla.
