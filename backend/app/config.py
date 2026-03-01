from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Database (SQLite por padrão para facilitar desenvolvimento)
    DATABASE_URL: str = "sqlite:///./gestao_contas.db"

    # JWT
    SECRET_KEY: str = "sua-chave-secreta-aqui-mude-em-producao"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 horas

    # App
    APP_NAME: str = "Gestão de Contas"
    DEBUG: bool = True

    # Upload
    MAX_UPLOAD_SIZE: int = 10 * 1024 * 1024  # 10MB
    UPLOAD_DIR: str = "/tmp/uploads"

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
