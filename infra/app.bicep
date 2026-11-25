// MID de Flota en Container Apps. Lo despliega el CD (.github/workflows/cd.yml) en cada cambio a main.
// Requiere la plataforma (infra/plataforma.bicep del repositorio ApiFlota) y, para funcionar de punta a punta,
// el CRUD de Flota y el gateway desplegados (ver docs/despliegue-azure.md).
targetScope = 'resourceGroup'

@description('Debe ser el mismo prefijo que usó al crear la plataforma.')
param prefijo string = 'rodar'

param ubicacion string = resourceGroup().location

@description('Imagen completa a desplegar, p. ej. rodaracrxxxx.azurecr.io/flota-mid:abc123.')
param imagen string

@description('GATEWAY_SECRET: lo que el gateway envía en X-Gateway-Secret a este MID.')
@secure()
param gatewaySecret string

@description('Valor de GATEWAY_SECRET del CRUD de Flota (este MID se lo envía en X-Gateway-Secret).')
@secure()
param flotaCrudSecret string

@description('Secreto del cliente «mid-flota» en el servicio de tokens del gateway.')
@secure()
param clientSecret string

param clientId string = 'mid-flota'

@description('Nombre de la aplicación del CRUD de Flota en el mismo entorno.')
param nombreAppCrud string = 'flota-crud'

@description('Nombre de la aplicación del gateway en el mismo entorno.')
param nombreAppGateway string = 'rodar-gateway'

@description('Si la URL del CRUD no es la interna del entorno, indíquela completa. Normalmente vacío.')
param flotaCrudUrl string = ''

@description('Si la URL del gateway no es la del entorno (p. ej. un dominio propio), indíquela completa. Normalmente vacío.')
param gatewayUrl string = ''

param nombreApp string = 'flota-mid'

@description('0 = escala a cero (ahorra, pero la primera petición tarda). 1 = siempre encendido.')
@minValue(0)
@maxValue(2)
param replicasMinimas int = 0

var sufijo = uniqueString(resourceGroup().id)
var nombreAcr = '${prefijo}acr${sufijo}'
var nombreEntorno = '${prefijo}-entorno'

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: nombreAcr
}

resource entorno 'Microsoft.App/managedEnvironments@2024-03-01' existing = {
  name: nombreEntorno
}

// Las direcciones de las aplicaciones de un entorno son predecibles: <app>.<dominio> (públicas) y
// <app>.internal.<dominio> (internas). Así no hace falta que el CRUD y el gateway existan antes que este MID.
var dominio = entorno.properties.defaultDomain
var urlCrud = empty(flotaCrudUrl) ? 'https://${nombreAppCrud}.internal.${dominio}' : flotaCrudUrl
var urlGateway = empty(gatewayUrl) ? 'https://${nombreAppGateway}.${dominio}' : gatewayUrl

resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: nombreApp
  location: ubicacion
  properties: {
    managedEnvironmentId: entorno.id
    configuration: {
      activeRevisionsMode: 'Single'
      // Interno: solo el gateway llega al MID. No tiene URL pública.
      ingress: {
        external: false
        targetPort: 8000
        transport: 'auto'
        allowInsecure: false
      }
      registries: [
        {
          server: acr.properties.loginServer
          username: acr.listCredentials().username
          passwordSecretRef: 'acr-password'
        }
      ]
      secrets: [
        {
          name: 'acr-password'
          value: acr.listCredentials().passwords[0].value
        }
        {
          name: 'gateway-secret'
          value: gatewaySecret
        }
        {
          name: 'flota-crud-secret'
          value: flotaCrudSecret
        }
        {
          name: 'client-secret'
          value: clientSecret
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'api'
          image: imagen
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: [
            {
              name: 'GATEWAY_SECRET'
              secretRef: 'gateway-secret'
            }
            {
              name: 'FLOTA_CRUD_URL'
              value: urlCrud
            }
            {
              name: 'FLOTA_CRUD_SECRET'
              secretRef: 'flota-crud-secret'
            }
            {
              name: 'GATEWAY_URL'
              value: urlGateway
            }
            {
              name: 'CLIENT_ID'
              value: clientId
            }
            {
              name: 'CLIENT_SECRET'
              secretRef: 'client-secret'
            }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/health'
                port: 8000
              }
              initialDelaySeconds: 10
              periodSeconds: 30
              failureThreshold: 3
            }
          ]
        }
      ]
      scale: {
        minReplicas: replicasMinimas
        maxReplicas: 2
      }
    }
  }
}

output nombreApp string = app.name
output fqdnInterno string = app.properties.configuration.ingress.fqdn
output urlCrudUsada string = urlCrud
output urlGatewayUsada string = urlGateway
