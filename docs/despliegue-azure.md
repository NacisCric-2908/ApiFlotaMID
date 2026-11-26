# Despliegue en Azure del MID de Flota

La guía completa (plataforma compartida, acceso de GitHub, costos, modo demostración, solución de problemas) está en el repositorio **ApiFlota**: `docs/despliegue-azure.md`. Aquí solo lo que es propio de este MID.

## Qué se despliega

Una aplicación de Container Apps llamada **`flota-mid`**, con ingreso **interno**: no tiene URL pública, solo el gateway llega a ella. Se define en [`infra/app.bicep`](../infra/app.bicep) y la despliega [`.github/workflows/cd.yml`](../.github/workflows/cd.yml) al fusionar a `main`.

## Qué necesita configurado en el repositorio

Todo esto lo deja puesto el script `scripts/03-secretos-produccion.sh` del repositorio **ApiWategay** (y el paso 2 de la guía principal). Solo hay que revisarlo en **Settings → Secrets and variables → Actions**:

| Tipo | Nombre | Qué es |
| --- | --- | --- |
| Variable | `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, `AZURE_RESOURCE_GROUP` | Acceso a Azure por OIDC (no son secretas) |
| Secreto | `FLOTA_MID_SECRET` | `GATEWAY_SECRET` de este MID: lo que el gateway envía en `X-Gateway-Secret` |
| Secreto | `FLOTA_CRUD_SECRET` | Lo que este MID envía al CRUD de Flota (el mismo que el CRUD tiene como `GATEWAY_SECRET`) |
| Secreto | `MID_FLOTA_CLIENT_SECRET` | Contraseña del cliente `mid-flota` en el servicio de tokens: con ella este MID pide su token para llamar a Viajes y zonas por el gateway |
| Variable (opcional) | `FLOTA_CRUD_URL` | Solo si el CRUD no está en el mismo entorno de Azure. Por defecto es `https://flota-crud.internal.<dominio del entorno>` |
| Variable (opcional) | `GATEWAY_URL` | Solo si el gateway tiene dominio propio. Por defecto es `https://rodar-gateway.<dominio del entorno>` |

## Cómo se conecta, ya en Azure

```
gateway ──X-Gateway-Secret──► flota-mid ──X-Gateway-Secret (del CRUD)──► flota-crud      (interno, sin pasar por el gateway)
                                   │
                                   └──Bearer (token de «mid-flota»)──► gateway ──► Viajes y zonas   (siempre por el gateway)
```

Las direcciones internas de Container Apps son predecibles, así que **no importa el orden en que se despliegue**; sí importa que, al probar, los tres servicios ya existan.

## Despliegue manual (sin GitHub)

Para probar la plantilla sin pasar por el CD, con la imagen ya publicada en el ACR:

```bash
az deployment group create -g rg-rodar --template-file infra/app.bicep \
  --parameters imagen=<acr>.azurecr.io/flota-mid:<etiqueta> \
               gatewaySecret=… flotaCrudSecret=… clientSecret=…
```

## Probar que funciona

Con el gateway ya desplegado (la URL pública la imprime su CD):

```bash
TOKEN=$(curl -s -X POST https://<gateway>/token -d grant_type=client_credentials \
  -d client_id=administrador -d client_secret=<secreto> | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
curl -H "Authorization: Bearer $TOKEN" \
  "https://<gateway>/flota/recomendaciones/vehiculo?lat=4.711&lng=-74.0721"
```

La primera petición después de un rato sin uso puede tardar o fallar (arranque en frío); vea «Modo ahorro y modo demostración» en la guía principal.
