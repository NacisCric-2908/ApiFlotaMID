# Cambios

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/). El proyecto usa [versionado semántico](https://semver.org/lang/es/).

## [0.1.0] - 2026-11-22 (en desarrollo, sin publicar)

Primera versión del **MID de Flota** (clúster Rodar).

### Agregado

- `GET /recomendaciones/vehiculo?lat&lng&tipo`: los 3 mejores vehículos a 500 m o menos (disponibles, batería de al menos 25 %, fuera de zonas prohibidas), ordenados por `puntaje = distancia - batería × 2`. Lista vacía con `motivo` si no hay candidatos; `503` si Viajes y zonas no responde.
- `GET /flota/alertas`: una alerta por cada condición (batería menor a 15 %, zona prohibida, más de 2 h sin actualizar), con prioridad, ordenadas por prioridad y antigüedad. Si Viajes y zonas no responde, degrada con la advertencia `zonas_no_verificadas`.
- `GET /health` público y rechazo con `401` de toda petición sin la cabecera `X-Gateway-Secret` del gateway.
- Arquitectura hexagonal: núcleo sin dependencias de FastAPI ni httpx, puertos y adaptadores.
- Adaptadores HTTP con tiempo máximo de espera, reintentos limitados con backoff y un único tipo de error; token del gateway (OAuth2 *client credentials*) con caché, renovación y una sola solicitud simultánea; paginación del CRUD de Flota.
- Contrato OpenAPI 3.1 con alcances (propuestos) y errores declarados, y `operationId` claros para generar clientes.
- Simulador del CRUD de Flota, de Viajes y zonas y del token del gateway, con los datos semilla acordados.
- Docker y Docker Compose para todo; dependencias con uv.
- 148 pruebas sin red (reglas, adaptadores, API y punta a punta contra el simulador).
- Guía de integración para quienes consumen el MID.

### Verificado

- Contra el CRUD real de Flota 1.0.0 (con MongoDB): mismos vehículos y mismo orden que con el simulador; con el CRUD apagado responde `503` (`flota-crud`).

### Limitaciones conocidas

Ver [PENDIENTES.md](PENDIENTES.md). En particular: **no se ha probado contra Viajes y zonas real ni contra el token real del gateway** (aún no existen); el clima no se usa en la recomendación.
