import os
import socket
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine, QueuePool
from sqlalchemy.orm import sessionmaker


def applyIPv4Force():
    _old_getaddrinfo = socket.getaddrinfo

    def new_getaddrinfo(*args, **kwargs):
        res = _old_getaddrinfo(*args, **kwargs)
        return [r for r in res if r[0] == socket.AF_INET]

    socket.getaddrinfo = new_getaddrinfo


applyIPv4Force()


class MysqlSettings(BaseSettings):
    USER_USER: Optional[str] = Field(default=None, validation_alias="USER_MYSQL_USER")
    USER_PASSWORD: Optional[str] = Field(default=None, validation_alias="USER_MYSQL_PASSWORD")
    USER_HOST: Optional[str] = Field(default=None, validation_alias="USER_MYSQL_HOST")
    USER_DATABASE: Optional[str] = Field(default=None, validation_alias="USER_MYSQL_DATABASE")
    USER_PORT: int = Field(default=3306, validation_alias="USER_MYSQL_PORT")

    STOCKS_USER: Optional[str] = Field(default=None, validation_alias="STOCKS_MYSQL_USER")
    STOCKS_PASSWORD: Optional[str] = Field(default=None, validation_alias="STOCKS_MYSQL_PASSWORD")
    STOCKS_HOST: Optional[str] = Field(default=None, validation_alias="STOCKS_MYSQL_HOST")
    STOCKS_DATABASE: Optional[str] = Field(default=None, validation_alias="STOCKS_MYSQL_DATABASE")
    STOCKS_PORT: int = Field(default=3306, validation_alias="STOCKS_MYSQL_PORT")
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class UserSettings(BaseSettings):
    ENABLED: bool = Field(default=True, validation_alias="USER_ENABLED")
    HOST: str = Field(default="localhost", validation_alias="USER_HOST")
    PORT: int = Field(default=3200, validation_alias="USER_PORT")
    JWT_SECRET_KEY: str = Field(default=..., validation_alias="JWT_SECRET_KEY")
    GOOGLE_CLIENT_ID: str = Field(default="", validation_alias="GOOGLE_CLIENT.ID")
    GOOGLE_CLIENT_SECRET: str = Field(default="", validation_alias="GOOGLE_CLIENT.SECRET")
    GOOGLE_REDIRECT_URI: str = Field(default="", validation_alias="GOOGLE_REDIRECT.URI")
    SERVICE_TOKEN_SECRET: str = Field(default="", validation_alias="INTROSPECT_SERVICE_SECRET")
    SERVICE_TOKEN_SECRET_PREV: str = Field(default="", validation_alias="INTROSPECT_SERVICE_SECRET_PREV")
    SERVICE_TOKEN_TTL_HOURS: int = Field(default=720, validation_alias="INTROSPECT_SERVICE_TTL_HOURS")
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class StocksApiSettings(BaseSettings):
    ENABLED: bool = Field(default=True, validation_alias="STOCKSAPI_ENABLED")
    HOST: str = Field(default="localhost", validation_alias="STOCKSAPI_HOST")
    PORT: int = Field(default=3200, validation_alias="STOCKSAPI_PORT")
    KEY_SYSTEM: bool = Field(default=False, validation_alias="STOCKSAPI_KEY.SYSTEM")
    KEY: str = Field(default="", validation_alias="STOCKSAPI_PRIVATE.KEY")
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class OrunmilaSettings(BaseSettings):
    ENABLED: bool = Field(default=True, validation_alias="ORUNMILA_ENABLED")
    HOST: str = Field(default="localhost", validation_alias="ORUNMILA_HOST")
    PORT: int = Field(default=3200, validation_alias="ORUNMILA_PORT")
    GEMINI_API_KEY: str = Field(default="", validation_alias="GEMINI_API.KEY")
    SEARXNG_URL: str = Field(default="http://searxng:8888", validation_alias="SEARXNG_URL")
    FORGEVM_URL: str = Field(default="http://forgevm:7423", validation_alias="FORGEVM_URL")
    FORGEVM_API_TOKEN: str = Field(default="", validation_alias="FORGEVM_API_TOKEN")
    SANDBOX_IMAGE: str = Field(default="sandbox-python:latest", validation_alias="SANDBOX_IMAGE")
    SANDBOX_MEMORY: int = Field(default=512, validation_alias="SANDBOX_MEMORY")
    SANDBOX_CPU: int = Field(default=1, validation_alias="SANDBOX_CPU")
    SANDBOX_TTL: int = Field(default=5, validation_alias="SANDBOX_TTL")
    WORKSPACE_MAX_UPLOAD_MB: int = Field(default=10, validation_alias="WORKSPACE_MAX_UPLOAD_MB")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class ScraperSettings(BaseSettings):
    ENABLED: bool = Field(default=False, validation_alias="SCRAPER_ENABLED")
    SCHEDULER: str = Field(default="", validation_alias="SCRAPER_SCHEDULER")
    JSON: bool = Field(default=False, validation_alias="JSON_EXPORT")
    MYSQL: bool = Field(default=True, validation_alias="MYSQL_EXPORT")
    MAX_WORKERS: int = Field(default=10, validation_alias="MAX_WORKERS")
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class DiscordSettings(BaseSettings):
    ENABLED: bool = Field(default=False, validation_alias="DISCORD_ENABLED")
    WEBHOOK_URL: str = Field(default="", validation_alias="DISCORD_WEBHOOK_URL")
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class CacheSettings(BaseSettings):
    URL: str = Field(default="mem://", validation_alias="CACHE_URL")
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class Config:
    DEBUG_MODE: bool = os.getenv("DEBUG_MODE", "FALSE").upper() == "TRUE"
    MYSQL = MysqlSettings()
    STOCKS_API = StocksApiSettings()
    ORUNMILA = OrunmilaSettings()
    SCRAPER = ScraperSettings()
    USER = UserSettings()
    DISCORD = DiscordSettings()
    CACHE = CacheSettings()


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
StocksSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=stocksEngine)


def getSession():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def getStocksSession():
    db = StocksSessionLocal()
    try:
        yield db
    finally:
        db.close()
