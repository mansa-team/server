import os
import socket
from typing import Optional
from pydantic import Field, AliasChoices
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine, QueuePool
from sqlalchemy.orm import sessionmaker


def applyIPv4Force():
    _old_getaddrinfo = socket.getaddrinfo

    def _new_getaddrinfo(*args, **kwargs):
        res = _old_getaddrinfo(*args, **kwargs)
        return [r for r in res if r[0] == socket.AF_INET]

    socket.getaddrinfo = _new_getaddrinfo


applyIPv4Force()


class BaseMansaSettings(BaseSettings):
    pass


class MysqlSettings(BaseMansaSettings):
    USER_USER: Optional[str] = Field(default=None, validation_alias=AliasChoices("USER_MYSQL_USER"))
    USER_PASSWORD: Optional[str] = Field(default=None, validation_alias=AliasChoices("USER_MYSQL_PASSWORD"))
    USER_HOST: Optional[str] = Field(default=None, validation_alias=AliasChoices("USER_MYSQL_HOST"))
    USER_DATABASE: Optional[str] = Field(default=None, validation_alias=AliasChoices("USER_MYSQL_DATABASE"))
    USER_PORT: int = Field(default=3306, validation_alias=AliasChoices("USER_MYSQL_PORT"))

    STOCKS_USER: Optional[str] = Field(default=None, validation_alias=AliasChoices("STOCKS_MYSQL_USER"))
    STOCKS_PASSWORD: Optional[str] = Field(default=None, validation_alias=AliasChoices("STOCKS_MYSQL_PASSWORD"))
    STOCKS_HOST: Optional[str] = Field(default=None, validation_alias=AliasChoices("STOCKS_MYSQL_HOST"))
    STOCKS_DATABASE: Optional[str] = Field(default=None, validation_alias=AliasChoices("STOCKS_MYSQL_DATABASE"))
    STOCKS_PORT: int = Field(default=3306, validation_alias=AliasChoices("STOCKS_MYSQL_PORT"))
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class UserSettings(BaseMansaSettings):
    ENABLED: bool = Field(default=True, validation_alias=AliasChoices("USER_ENABLED"))
    HOST: str = Field(default="localhost", validation_alias=AliasChoices("USER_HOST"))
    PORT: int = Field(default=3200, validation_alias=AliasChoices("USER_PORT"))
    JWT_SECRET_KEY: str = Field(default=..., validation_alias=AliasChoices("JWT_SECRET_KEY"))
    SESSION_SECRET_KEY: str = Field(default=..., validation_alias=AliasChoices("SESSION_SECRET_KEY"))
    GOOGLE_CLIENT_ID: str = Field(default="", validation_alias=AliasChoices("GOOGLE_CLIENT.ID"))
    GOOGLE_CLIENT_SECRET: str = Field(default="", validation_alias=AliasChoices("GOOGLE_CLIENT.SECRET"))
    GOOGLE_REDIRECT_URI: str = Field(default="", validation_alias=AliasChoices("GOOGLE_REDIRECT.URI"))
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class StocksApiSettings(BaseMansaSettings):
    ENABLED: bool = Field(default=True, validation_alias=AliasChoices("STOCKSAPI_ENABLED"))
    HOST: str = Field(default="localhost", validation_alias=AliasChoices("STOCKSAPI_HOST"))
    PORT: int = Field(default=3200, validation_alias=AliasChoices("STOCKSAPI_PORT"))
    KEY_SYSTEM: bool = Field(default=False, validation_alias=AliasChoices("STOCKSAPI_KEY.SYSTEM"))
    KEY: str = Field(default="", validation_alias=AliasChoices("STOCKSAPI_PRIVATE.KEY"))
    DEFAULT_QUOTA: int = Field(default=100, validation_alias=AliasChoices("STOCKSAPI_DEFAULT.QUOTA"))
    QUOTA_RESETDAYS: int = Field(default=30, validation_alias=AliasChoices("STOCKSAPI_QUOTA.RESETDAYS"))
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class PrometheusSettings(BaseMansaSettings):
    ENABLED: bool = Field(default=True, validation_alias=AliasChoices("PROMETHEUS_ENABLED"))
    HOST: str = Field(default="localhost", validation_alias=AliasChoices("PROMETHEUS_HOST"))
    PORT: int = Field(default=3200, validation_alias=AliasChoices("PROMETHEUS_PORT"))
    GEMINI_API_KEY: str = Field(default="", validation_alias=AliasChoices("GEMINI_API.KEY"))
    SEARXNG_URL: str = Field(default="http://searxng:8888", validation_alias=AliasChoices("SEARXNG_URL"))
    FORGEVM_URL: str = Field(default="http://forgevm:7423", validation_alias=AliasChoices("FORGEVM_URL"))
    SANDBOX_IMAGE: str = Field(default="sandbox-python:latest", validation_alias=AliasChoices("SANDBOX_IMAGE"))
    SANDBOX_MEMORY: int = Field(default=512, validation_alias=AliasChoices("SANDBOX_MEMORY"))
    SANDBOX_CPU: int = Field(default=1, validation_alias=AliasChoices("SANDBOX_CPU"))
    SANDBOX_TTL: int = Field(default=5, validation_alias=AliasChoices("SANDBOX_TTL"))

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class ScraperSettings(BaseMansaSettings):
    ENABLED: bool = Field(default=False, validation_alias=AliasChoices("SCRAPER_ENABLED"))
    SCHEDULER: str = Field(default="", validation_alias=AliasChoices("SCRAPER_SCHEDULER"))
    JSON: bool = Field(default=False, validation_alias=AliasChoices("JSON_EXPORT"))
    MYSQL: bool = Field(default=True, validation_alias=AliasChoices("MYSQL_EXPORT"))
    MAX_WORKERS: int = Field(default=10, validation_alias=AliasChoices("MAX_WORKERS"))
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class DiscordSettings(BaseMansaSettings):
    ENABLED: bool = Field(default=False, validation_alias=AliasChoices("DISCORD_ENABLED"))
    WEBHOOK_URL: str = Field(default="", validation_alias=AliasChoices("DISCORD_WEBHOOK_URL"))
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class Config:
    DEBUG_MODE: bool = os.getenv("DEBUG_MODE", "FALSE").upper() == "TRUE"
    MYSQL = MysqlSettings()
    STOCKS_API = StocksApiSettings()
    PROMETHEUS = PrometheusSettings()
    SCRAPER = ScraperSettings()
    USER = UserSettings()
    DISCORD = DiscordSettings()


LOCALHOST_ADDRESSES = ["localhost", "127.0.0.1", "0.0.0.0", "None", "host.docker.internal", None]

engine = create_engine(
    f"mysql+pymysql://{Config.MYSQL.USER_USER}:{Config.MYSQL.USER_PASSWORD}@{Config.MYSQL.USER_HOST}/{Config.MYSQL.USER_DATABASE}",
    poolclass=QueuePool,
    pool_size=20,
    max_overflow=40,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=False,
    connect_args={"charset": "utf8mb4"},
)

stocksEngine = create_engine(
    f"mysql+pymysql://{Config.MYSQL.STOCKS_USER}:{Config.MYSQL.STOCKS_PASSWORD}@{Config.MYSQL.STOCKS_HOST}/{Config.MYSQL.STOCKS_DATABASE}",
    poolclass=QueuePool,
    pool_size=20,
    max_overflow=40,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=False,
    connect_args={"charset": "utf8mb4"},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def getSession():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
