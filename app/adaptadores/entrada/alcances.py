"""Alcances (scopes) del MID de Flota, declarados en el contrato OpenAPI.

La validación del token y de los alcances la hace el API Gateway; este servicio solo confía en la cabecera
secreta del gateway. Estas dependencias existen para que el contrato los documente (`security` por operación) y
no rechazan nada por sí mismas. Los nombres son una propuesta: se acuerdan con el líder del gateway.
"""

from fastapi.openapi.models import OAuthFlowClientCredentials, OAuthFlows
from fastapi.security import APIKeyHeader, OAuth2

RECOMENDACIONES_LEER = "recomendaciones:leer"
ALERTAS_LEER = "alertas:leer"

oauth2 = OAuth2(
    scheme_name="OAuth2Gateway",
    flows=OAuthFlows(
        clientCredentials=OAuthFlowClientCredentials(
            tokenUrl="/token",
            scopes={
                RECOMENDACIONES_LEER: "Pedir recomendaciones de vehículos",
                ALERTAS_LEER: "Consultar las alertas operativas de la flota",
            },
        )
    ),
    auto_error=False,
)

cabecera_gateway = APIKeyHeader(name="X-Gateway-Secret", scheme_name="GatewaySecret", auto_error=False)
