# Pendientes del MID de Flota

Estado: **versión 0.1.0** en `develop`, con los dos endpoints del enunciado, 148 pruebas y verificada contra el CRUD real de Flota (1.0.0). Aún no se publicó una versión en `main`. Última revisión: 2026-11-22.

**Cómo usar este archivo:** marquen `[x]` al terminar, escriban un responsable y trabajen cada punto en una rama `feature/...`.

## 1. Bloqueantes: sin esto no funciona fuera de la máquina de desarrollo

- [ ] **Subir el repositorio a GitHub** (hoy es solo local; será público) y dar acceso a los compañeros de Flota. Responsable: ______
- [ ] **Probar contra Viajes y zonas real.** Hoy solo se probó contra el simulador. Hay que confirmar tres supuestos con ese grupo (si algo difiere, solo cambia `app/adaptadores/salida/zonas_http.py` y `ZONAS_RUTA`):
  1. La ruta: el MID llama `GET {gateway}/viajes/zonas/verificar?lat&lng`.
  2. La respuesta: se usa solo `permitida` (booleano); `permitida: false` significa zona prohibida. Lo demás de `zonas` no se usa.
  3. El alcance: se pide `zonas:leer` (el de la matriz del enunciado).
  Responsable: ______
- [x] **Token real del gateway.** Verificado: el gateway (repositorio ApiWategay) emite el token con el flujo estándar OAuth2 *client credentials* (`POST /token` con formulario) y este MID lo pide y lo usa sin cambios, probado de punta a punta con el CRUD real y el gateway real en Docker (cliente `mid-flota`, alcance `zonas:leer`).
- [x] **CI/CD y despliegue escritos:** `.github/workflows/ci.yml` (pruebas y validación de Bicep por pull request), `cd.yml` (construye la imagen y despliega a Azure al fusionar a `main`, con OIDC) e `infra/app.bicep` (ingreso interno, secretos de Container Apps). Guía: [docs/despliegue-azure.md](docs/despliegue-azure.md).
- [ ] **Ejecutar el despliegue de verdad** (nada se ha corrido contra Azure): configurar Azure y GitHub una sola vez según la guía del repositorio ApiFlota (`docs/despliegue-azure.md`) y desplegar en orden ApiFlota → este MID → ApiWategay. Responsable: ______
- [ ] **Reglas de rama y flujo con pull requests** (marcar el job `pruebas` del CI como requerido). Responsable: ______
- [ ] **Datos de conexión:** completar la sección 0 de [docs/integracion.md](docs/integracion.md) cuando el gateway esté desplegado (URL pública y credenciales). Responsable: ______

## 2. Con el líder del gateway

- [ ] **Las dos rutas del MID llevan reglas de prefijo distintas** (sección 2 de la guía): `/flota/recomendaciones/vehiculo` → `/recomendaciones/vehiculo` (se quita `/flota`), pero `/flota/alertas` → `/flota/alertas` (no se quita). Es consecuencia de cómo define el enunciado las rutas del MID (`/recomendaciones/vehiculo` y `/flota/alertas`). Si el gateway prefiere una regla uniforme, se puede cambiar la ruta del MID; es un cambio pequeño pero **incompatible** del contrato.
- [ ] **Alcances.** El enunciado no define los del MID; se proponen `recomendaciones:leer` y `alertas:leer`. Acordarlos. Además, la credencial de este MID debe tener `zonas:leer` para consultar a Viajes y zonas.
- [ ] **Esperas del gateway:** al menos 15 s en las dos rutas (en el peor caso tardan ~10 s por los reintentos).

## 3. Decisiones que el enunciado no fija (el grupo debe confirmarlas)

Se tomaron estas decisiones para poder implementar; están documentadas en la guía y cubiertas por pruebas, y cambiarlas es fácil.

- [ ] **Una alerta por cada condición** que cumple un vehículo (el enunciado habla de `tipoAlerta` en singular): un vehículo con batería baja y en zona prohibida aparece dos veces. Alternativa: una alerta por vehículo con la condición más grave.
- [ ] **Solo se evalúan los vehículos `disponible`.** Uno en viaje no se puede recoger y su ubicación no se actualiza durante el trayecto; uno en mantenimiento ya está con el equipo operativo. Se cambia con `ESTADOS_ALERTA`.
- [ ] **Prioridades:** `alta` (batería menor a 10 % o zona prohibida) y `media` (el resto). El enunciado solo define cuándo es alta.
- [ ] **Alertas con Viajes y zonas caído: degradan** (devuelven las demás y la advertencia `zonas_no_verificadas`) en vez de responder 503. En la recomendación sí responde 503, como pide el enunciado.
- [ ] **Si todos los cercanos tienen poca batería**, el `motivo` es `sin_vehiculos_cercanos` (el enunciado solo prevé ese y `todos_en_zona_prohibida`).
- [ ] **Clima («recomendar de otra forma si llueve»):** no se implementó. El enunciado lo sugiere como idea para el API de tercero; hoy el clima vive en el CRUD (`GET /vehiculos/{id}/clima`). El diseño deja el puerto previsto (`ClimaPort`, marcado como pendiente en el diagrama). Decidir si hace falta y qué cambiaría en la recomendación.

## 4. Mejoras (no bloqueantes)

- [ ] **`/health` es solo de vida** (no consulta al CRUD ni a Viajes y zonas). Para el *probe* de Container Apps puede convenir un *readiness*.
- [ ] **Logs estructurados y métricas.** Hoy solo hay los registros por defecto; los 503 se registran con el servicio y el motivo.
- [ ] **Las alertas hacen una consulta a Viajes y zonas por vehículo** (con tope de 10 simultáneas). Con 30 vehículos no importa; con una flota grande conviene un endpoint por lotes en Viajes y zonas o una caché corta.
- [ ] **Lectura del CRUD limitada a 10 páginas** (1.000 vehículos por consulta; deja una advertencia en el registro si se corta). Subir `MAX_PAGINAS` si la flota crece.
- [ ] **`/docs` y `/openapi.json` son públicos** (sin la cabecera del gateway). Decidir si se exponen en producción.
- [ ] **`docker-compose.yml` trae secretos de desarrollo por defecto** (apuntan al simulador). En producción deben venir de variables de entorno.
- [ ] **Linter y formateador** (por ejemplo `ruff`) y cobertura en el pipeline.

## 5. Documentación

- [ ] Completar **«Aportes de cada integrante»** en el [README.md](README.md).
- [ ] Cuando se despliegue: publicar la guía [docs/integracion.md](docs/integracion.md) a los otros equipos y a quien use el MID (aplicación del usuario, panel de operación). Es un servicio independiente: no necesitan el repositorio.
- [ ] Cuando se estabilice: publicar la versión 1.0.0 (rama `release/1.0.0`, fusión a `main`, etiqueta `v1.0.0`) como se hizo con el CRUD.
