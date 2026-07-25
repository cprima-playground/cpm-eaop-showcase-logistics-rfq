from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MCP_", extra="ignore")

    host: str = "127.0.0.1"
    port: int = 8000
    public_url: AnyHttpUrl = AnyHttpUrl("http://localhost:8091/mcp")
    issuer_url: AnyHttpUrl = AnyHttpUrl("http://localhost:8081/realms/rfq")
    introspection_endpoint: AnyHttpUrl = AnyHttpUrl(
        "http://localhost:8081/realms/rfq/protocol/openid-connect/token/introspect"
    )
    introspection_client_id: str | None = None
    introspection_client_secret: str | None = Field(default=None, repr=False)
    ca_cert: str | None = None
    required_scope: str | None = None
    expected_audience: str | None = None
    log_level: str = "INFO"
    allowed_origins: str = "http://localhost:6274,http://127.0.0.1:6274"
