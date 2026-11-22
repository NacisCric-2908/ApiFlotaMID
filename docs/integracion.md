# Guía de integración: API Flota MID (recomendaciones y alertas)

Para quien consume el MID de Flota: la aplicación que le muestra vehículos cercanos al usuario, el panel del equipo operativo y el líder del gateway. El contrato formal está en [`openapi.json`](openapi.json). Esta guía explica cómo usarlo bien. Es un **servicio independiente en la nube**: no hay nada que instalar, clonar ni levantar; se consume por el gateway con un token.

## 0. Datos de conexión

> **Pendiente del líder del gateway:** completar esta tabla cuando el gateway esté desplegado. El resto de la guía no cambia.

| Dato | Valor |
| --- | --- |
| URL base del gateway | _por completar_ |
| Pedir un token | `POST {gateway}/token` (OAuth2 *client credentials*; forma exacta que publique el gateway) |
| Prefijo de Flota | `/flota` |
| `client_id` y secreto de quien consume | _por completar (los entrega el líder del gateway)_ |
| Alcances del MID de Flota | `recomendaciones:leer`, `alertas:leer` (propuestos; se acuerdan con el líder del gateway) |
| Ambiente de pruebas | _por completar_ (el mismo gateway, con los 30 vehículos semilla de Flota) |

## 1. Qué hace y quién lo usa

| Endpoint | Para qué | Lo usa |
| --- | --- | --- |
| `GET /flota/recomendaciones/vehiculo` | Los 3 mejores vehículos cerca de un punto | La aplicación del usuario (y la demostración) |
| `GET /flota/alertas` | Vehículos que requieren atención del equipo operativo | El panel de operaciones |

El MID **no guarda datos propios**: combina el CRUD de Flota (los vehículos) con las zonas de Viajes y zonas. Por eso puede responder `503` cuando alguno de los dos no está disponible.

## 2. Cómo se llega al servicio

Toda llamada pasa por el **API Gateway**. El servicio no es accesible directamente y rechaza con `401` cualquier petición que no traiga la cabecera `X-Gateway-Secret` correcta (la agrega el gateway al reenviar; **los consumidores no la envían ni la conocen**).

Rutas que debe configurar el gateway (líder del gateway: **las dos reglas de prefijo son distintas**, por cómo está definido el contrato del enunciado):

| Ruta pública del gateway | Se reenvía al MID como | Alcance |
| --- | --- | --- |
| `GET /flota/recomendaciones/vehiculo` | `GET /recomendaciones/vehiculo` (**se quita** el prefijo `/flota`) | `recomendaciones:leer` |
| `GET /flota/alertas` | `GET /flota/alertas` (**no se quita** el prefijo: la ruta del MID ya empieza por `/flota`) | `alertas:leer` |
| `GET /flota/health` | `GET /health` (sin token) | ninguno |

Reglas del gateway por este servicio: agregar `X-Gateway-Secret` (el valor de `GATEWAY_SECRET` configurado en el MID), descartar la que traiga el cliente, validar token y alcances antes de reenviar, dejar pasar los errores sin cambiarlos y responder `503` con el formato de error común si el MID no responde. **Esperas:** las dos consultas tardan en el peor caso ~10 s (consultan al CRUD y a Viajes y zonas, con 3 s por intento y hasta 2 reintentos); configure al menos 15 s.

## 3. Autenticación y alcances

El gateway emite el token (ruta `/token`, credenciales por quien consume) y valida token y alcances **antes** de reenviar. El MID no los vuelve a validar; solo los declara en el contrato.

| Alcance | Permite |
| --- | --- |
| `recomendaciones:leer` | `GET /recomendaciones/vehiculo` |
| `alertas:leer` | `GET /flota/alertas` |

`GET /health` es público.

## 4. Convenciones

- **JSON.** Fechas en ISO 8601 UTC (`2026-11-22T18:04:51.122454Z`).
- **Coordenadas:** GeoJSON, en orden **`[longitud, latitud]`**. Los parámetros de consulta usan `lat` y `lng` por separado.
- **Errores:** siempre `{ "codigo": "...", "mensaje": "...", "detalle": {} }`. Programe contra `codigo`, no contra `mensaje`. Los datos inválidos responden `400` (no `422`). Catálogo en la sección 7.

## 5. Referencia de endpoints

### `GET /flota/recomendaciones/vehiculo`

| Parámetro | Obligatorio | Descripción |
| --- | --- | --- |
| `lat` | sí | Latitud del usuario (-90 a 90) |
| `lng` | sí | Longitud del usuario (-180 a 180) |
| `tipo` | no | `scooter` o `bicicleta`: solo vehículos de ese tipo |

```bash
curl "$GATEWAY/flota/recomendaciones/vehiculo?lat=4.711&lng=-74.0721&tipo=bicicleta" -H "Authorization: Bearer $TOKEN"
```

```json
{
  "recomendaciones": [
    {
      "vehiculoId": "veh-0014",
      "tipo": "bicicleta",
      "distanciaMetros": 149.8,
      "bateriaPct": 81,
      "puntaje": -12.2,
      "ubicacion": { "type": "Point", "coordinates": [-74.07345, 4.711] },
      "localidad": "Suba"
    }
  ],
  "total": 1
}
```

(Se acortó a un vehículo; la respuesta trae hasta 3, del mejor al peor `puntaje`.)

- **Reglas, en orden:** (1) vehículos `disponible` a 500 m o menos; (2) se descartan los de batería menor a 25 %; (3) se descartan los que están en una zona prohibida; (4) se ordena por `puntaje = distanciaMetros - bateriaPct * 2` (menor es mejor) y se devuelven los 3 mejores.
- **Sin candidatos:** responde **`200`** con la lista vacía y un `motivo`: `{ "recomendaciones": [], "total": 0, "motivo": "sin_vehiculos_cercanos" }`. El motivo es `sin_vehiculos_cercanos` (no hay vehículos disponibles con batería suficiente a 500 m) o `todos_en_zona_prohibida`. `motivo` solo aparece cuando la lista está vacía.
- **Si Viajes y zonas no responde: `503`.** No se recomienda un vehículo sin validar las zonas.
- **La recomendación no reserva el vehículo.** Otro viaje puede tomarlo antes: la reserva ocurre al iniciar el viaje, y ahí un `409` significa «ya lo tomaron».

Respuestas: `200`, `400`, `401`, `503`.

### `GET /flota/alertas`

Sin parámetros. Un vehículo `disponible` genera **una alerta por cada condición** que cumple (uno con batería baja y en zona prohibida aparece dos veces):

| `tipoAlerta` | Cuándo | `prioridad` |
| --- | --- | --- |
| `bateria_baja` | batería menor a 15 % | `alta` si es menor a 10 %; `media` si no |
| `zona_prohibida` | está en una zona prohibida | `alta` |
| `sin_actualizar` | su ubicación no se actualiza hace más de 2 horas | `media` |

La lista sale **ordenada por prioridad y luego por tiempo sin actualizar** (la más antigua primero). Solo se evalúan los vehículos `disponible`: uno en viaje no se puede recoger y su ubicación no se actualiza durante el trayecto; uno en mantenimiento ya está en manos del equipo operativo.

```json
{
  "alertas": [
    {
      "vehiculoId": "veh-0016",
      "tipoAlerta": "zona_prohibida",
      "prioridad": "alta",
      "detalle": "Está en una zona prohibida",
      "tipo": "bicicleta",
      "estado": "disponible",
      "bateriaPct": 59,
      "ubicacion": { "type": "Point", "coordinates": [-74.07165, 4.711] },
      "localidad": "Suba",
      "actualizadoEn": "2026-11-22T18:04:51.122454Z",
      "minutosSinActualizar": 15
    }
  ],
  "total": 1,
  "advertencias": []
}
```

- **Si Viajes y zonas no responde, NO falla** (a diferencia de la recomendación): devuelve las alertas de batería e inactividad y la advertencia `"advertencias": ["zonas_no_verificadas"]`, para que el panel avise que faltan las de zona prohibida. Un resultado parcial le sirve más a un operador que un error.
- Si el CRUD de Flota no responde: `503`.

Respuestas: `200`, `401`, `503`.

### `GET /flota/health`

`{"estado": "ok"}`. Público, sin token. Solo indica que el servicio está vivo.

## 6. Valores de las reglas

| Regla | Valor |
| --- | --- |
| Radio de búsqueda | 500 m |
| Batería mínima para recomendar | 25 % |
| Cantidad de recomendaciones | 3 |
| Alerta por batería | menor a 15 % (alta si es menor a 10 %) |
| Alerta por inactividad | más de 2 horas sin actualizar la ubicación |
| Estados que generan alertas | solo `disponible` |

Son configurables en el servidor (no por quien consume). Si cambian, cambia lo que devuelve el servicio, no el contrato.

## 7. Catálogo de errores

| HTTP | `codigo` | Cuándo | `detalle` |
| --- | --- | --- | --- |
| 400 | `solicitud_invalida` | Parámetros inválidos o faltantes | `{ "errores": [ { "campo": "lat", "mensaje": "..." } ] }` |
| 401 | `gateway_no_autorizado` | Falta o es incorrecta la cabecera secreta (no pasó por el gateway) | `{}` |
| 404 / 405 | `no_encontrado` / `metodo_no_permitido` | Ruta o método inexistente | `{}` |
| 503 | `servicio_no_disponible` | No responde un servicio del que depende el MID | `{ "servicio": "viajes-zonas", "motivo": "ConnectError" }` |
| otro | `error_http` | Cualquier otro error HTTP sin código propio (poco común) | `{}` |
| 500 | `error_interno` | Falla inesperada | `{}` |

En `503`, `detalle.servicio` dice cuál servicio falló: `viajes-zonas` (Viajes y zonas), `flota-crud` (CRUD de Flota) o `gateway-token` (no se pudo obtener el token del gateway: credenciales mal configuradas en el MID). `detalle.motivo` es corto (`ConnectError`, `ReadTimeout`, `http_503`, `http_401`...).

```json
{ "codigo": "servicio_no_disponible",
  "mensaje": "No se pudo consultar Viajes y zonas: sin validar las zonas no se recomienda ningún vehículo.",
  "detalle": { "servicio": "viajes-zonas", "motivo": "ConnectError" } }
```

## 8. Recetas

**Mostrar los vehículos cercanos al usuario** (aplicación del usuario):

1. Pida `GET /flota/recomendaciones/vehiculo` con la ubicación del usuario.
2. Si `recomendaciones` trae vehículos, muéstrelos en orden (el primero es el mejor).
3. Si viene vacía, use `motivo` para el mensaje: `sin_vehiculos_cercanos` («no hay vehículos cerca») o `todos_en_zona_prohibida`.
4. Si responde `503`, no muestre vehículos: diga que el servicio no está disponible e intente de nuevo en unos segundos. **No** reintente en un ciclo cerrado.
5. Cuando el usuario elija uno, siga con *iniciar viaje* (MID de Viajes) usando el `vehiculoId`. Allí se reserva; un `409` significa que otro viaje lo tomó, y conviene volver a pedir recomendaciones.

**Panel del equipo operativo:** pida `GET /flota/alertas` cada cierto tiempo (por ejemplo cada minuto), muestre las de prioridad `alta` primero y, si `advertencias` trae `zonas_no_verificadas`, avise que la lista está incompleta.

## 9. Probar su integración

El MID se consume como un servicio: no hay que instalar, clonar ni levantar nada.

1. **Simulando sus respuestas**, para las pruebas unitarias. Respuestas reales para copiar:

| Situación | Estado HTTP | Cuerpo |
| --- | --- | --- |
| Hay vehículos | 200 | el JSON de la sección 5 |
| Sin candidatos | 200 | `{"recomendaciones":[],"total":0,"motivo":"sin_vehiculos_cercanos"}` |
| Viajes y zonas caído | 503 | el JSON de la sección 7 |
| Parámetro inválido | 400 | `{"codigo":"solicitud_invalida","mensaje":"Los datos enviados no son válidos.","detalle":{"errores":[{"campo":"lat","mensaje":"Input should be less than or equal to 90"}]}}` |
| Alertas con zonas no verificadas | 200 | `{"alertas":[...],"total":5,"advertencias":["zonas_no_verificadas"]}` |

2. **Contra el ambiente de pruebas** (sección 0), con su token. Con los datos semilla de Flota, desde el punto `lat=4.7110&lng=-74.0721` el resultado esperado es: `veh-0014` (150 m, 81 %), `veh-0022` (112 m, 61 %) y `veh-0008` (180 m, 73 %). `veh-0016`, el más cercano, queda fuera por estar en la zona prohibida. Las alertas esperadas, en orden: `veh-0016` (`zona_prohibida`, alta), `veh-0015` (`bateria_baja`, alta), `veh-0021` y `veh-0008` (`sin_actualizar`, media), `veh-0019` y `veh-0009` (`bateria_baja`, media).

Ejemplo en Python (httpx):

```python
import httpx


async def mejores_vehiculos(http: httpx.AsyncClient, lat: float, lng: float, tipo: str | None = None) -> list[dict]:
    """Hasta 3 vehículos recomendados (lista vacía si no hay), del mejor al peor."""
    params = {"lat": lat, "lng": lng, **({"tipo": tipo} if tipo else {})}
    r = await http.get("/flota/recomendaciones/vehiculo", params=params)
    r.raise_for_status()  # 400 y 503 lanzan httpx.HTTPStatusError: trátelos como «no disponible», sin reintentar en ciclo
    return r.json()["recomendaciones"]


async def alertas_urgentes(http: httpx.AsyncClient) -> tuple[list[dict], list[str]]:
    """Las alertas de prioridad alta y las advertencias (p. ej. ['zonas_no_verificadas'])."""
    r = await http.get("/flota/alertas")
    r.raise_for_status()
    cuerpo = r.json()
    return [a for a in cuerpo["alertas"] if a["prioridad"] == "alta"], cuerpo["advertencias"]


# Uso: cliente con la URL del gateway, el token y un tiempo de espera corto
# async with httpx.AsyncClient(base_url=GATEWAY, timeout=15.0, headers={"Authorization": f"Bearer {token}"}) as http:
#     vehiculos = await mejores_vehiculos(http, 4.7110, -74.0721)
```

## 10. Versiones del contrato

La API usa **versionado semántico**; la versión está en `info.version` de [openapi.json](openapi.json). Agregar campos opcionales sube la versión menor y no rompe a nadie. Quitar o renombrar un campo, o cambiar un código de error o una regla, sube la versión mayor y se avisa antes de publicarla.
