from functools import lru_cache

from mireacrm_common.config import ServiceSettings
from pydantic_settings import SettingsConfigDict


class Settings(ServiceSettings):
    model_config = SettingsConfigDict(env_prefix="BILLING_", env_file=".env", extra="ignore")

    service_name: str = "billing-service"
    postgres_dsn: str = "postgresql+asyncpg://billing_user:billing_pass@localhost:5432/billing_db"
    http_port: int = 8006
    grpc_port: int = 9006

    booking_addr: str = "localhost:9003"
    client_addr: str = "localhost:9005"


@lru_cache
def get_settings() -> Settings:
    return Settings()
