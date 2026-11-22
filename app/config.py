from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.dominio.reglas import ReglasAlertas, ReglasRecomendacion


class Settings(BaseSettings):
    """Configuración leída de variables de entorno. Sin valores por defecto para lo sensible (secretos y URLs)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Del gateway hacia este MID
    gateway_secret: str

    # Del MID hacia el CRUD de Flota (entre servicios): el CRUD exige su propia cabecera secreta
    flota_crud_url: str
    flota_crud_secret: str

    # Del MID hacia Viajes y zonas: siempre por el gateway, con el token de este MID (OAuth2 client credentials)
    gateway_url: str
    gateway_token_url: str | None = None  # por defecto: gateway_url + /token
    client_id: str
    client_secret: str
    token_scope: str = "zonas:leer"
    zonas_ruta: str = "/viajes/zonas/verificar"

    # Reglas de negocio (valores del enunciado)
    radio_busqueda_m: float = 500
    bateria_minima: int = 25
    max_recomendaciones: int = 3
    bateria_alerta: int = 15
    bateria_alerta_alta: int = 10
    horas_sin_actualizar: float = 2
    estados_alerta: str = "disponible"

    # Llamadas a otros servicios
    externos_timeout_s: float = 3.0  # espera máxima por intento
    externos_reintentos: int = 2  # reintentos tras el primer intento
    externos_backoff_s: float = 0.2  # espera inicial entre intentos; se duplica cada vez
    concurrencia_zonas: int = 10
    max_paginas: int = 10  # páginas máximas al leer el CRUD de Flota (100 vehículos por página)

    log_level: str = "info"

    @property
    def url_token(self) -> str:
        return self.gateway_token_url or f"{self.gateway_url.rstrip('/')}/token"

    def reglas_recomendacion(self) -> ReglasRecomendacion:
        return ReglasRecomendacion(
            radio_m=self.radio_busqueda_m,
            bateria_minima=self.bateria_minima,
            max_resultados=self.max_recomendaciones,
            concurrencia_zonas=self.concurrencia_zonas,
        )

    def reglas_alertas(self) -> ReglasAlertas:
        estados = frozenset(e.strip() for e in self.estados_alerta.split(",") if e.strip())
        return ReglasAlertas(
            bateria_alerta=self.bateria_alerta,
            bateria_alerta_alta=self.bateria_alerta_alta,
            horas_sin_actualizar=self.horas_sin_actualizar,
            estados=estados,
            concurrencia_zonas=self.concurrencia_zonas,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
