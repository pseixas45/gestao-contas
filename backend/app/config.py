from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import List


class Settings(BaseSettings):
    # Database (SQLite por padrão para facilitar desenvolvimento)
    # Para PostgreSQL/Supabase: postgresql+psycopg2://user:pass@host:5432/dbname
    DATABASE_URL: str = "sqlite:///./gestao_contas.db"

    # Schema do PostgreSQL (ignorado para SQLite). Usado para isolar tabelas
    # quando o banco Supabase é compartilhado com outros projetos.
    DB_SCHEMA: str = ""  # vazio = usa schema default (public)

    # JWT
    SECRET_KEY: str = "sua-chave-secreta-aqui-mude-em-producao"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 horas

    # App
    APP_NAME: str = "Gestão de Contas"
    DEBUG: bool = True

    # CORS — lista separada por vírgula (ex: "https://app.com,http://localhost:3000")
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Upload
    MAX_UPLOAD_SIZE: int = 10 * 1024 * 1024  # 10MB
    UPLOAD_DIR: str = "/tmp/uploads"

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
