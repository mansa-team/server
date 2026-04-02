import os
import socket
from typing import Dict, Any
from pydantic import Field, AliasChoices
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine, QueuePool
from sqlalchemy.orm import sessionmaker, scoped_session

def applyIPv4Force():
    _old_getaddrinfo = socket.getaddrinfo
    def _new_getaddrinfo(*args, **kwargs):
        res = _old_getaddrinfo(*args, **kwargs)
        return [r for r in res if r[0] == socket.AF_INET]
    socket.getaddrinfo = _new_getaddrinfo

applyIPv4Force()

class MysqlSettings(BaseSettings):
    USER: str = Field(validation_alias=AliasChoices('MYSQL_USER'))
    PASSWORD: str = Field(validation_alias=AliasChoices('MYSQL_PASSWORD'))
    HOST: str = Field(validation_alias=AliasChoices('MYSQL_HOST'))
    DATABASE: str = Field(validation_alias=AliasChoices('MYSQL_DATABASE'))
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

    def __getitem__(self, item):
        return getattr(self, item)

class StocksApiSettings(BaseSettings):
    ENABLED: bool = Field(validation_alias=AliasChoices('STOCKSAPI_ENABLED'))
    HOST: str = Field(validation_alias=AliasChoices('STOCKSAPI_HOST'))
    PORT: int = Field(validation_alias=AliasChoices('STOCKSAPI_PORT'))
    KEY_SYSTEM: bool = Field(validation_alias=AliasChoices('STOCKSAPI_KEY.SYSTEM'))
    KEY: str = Field(validation_alias=AliasChoices('STOCKSAPI_PRIVATE.KEY'))
    DEFAULT_QUOTA: int = Field(validation_alias=AliasChoices('STOCKSAPI_DEFAULT.QUOTA'))
    QUOTA_RESETDAYS: int = Field(validation_alias=AliasChoices('STOCKSAPI_QUOTA.RESETDAYS'))
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

    def __getitem__(self, item):
        mapping = {
            'KEY.SYSTEM': 'KEY_SYSTEM',
            'DEFAULT.QUOTA': 'DEFAULT_QUOTA',
            'QUOTA.RESETDAYS': 'QUOTA_RESETDAYS'
        }
        return getattr(self, mapping.get(item, item))

class PrometheusSettings(BaseSettings):
    ENABLED: bool = Field(validation_alias=AliasChoices('PROMETHEUS_ENABLED'))
    HOST: str = Field(validation_alias=AliasChoices('PROMETHEUS_HOST'))
    PORT: int = Field(validation_alias=AliasChoices('PROMETHEUS_PORT'))
    GEMINI_API_KEY: str = Field(validation_alias=AliasChoices('GEMINI_API.KEY'))
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

    def __getitem__(self, item):
        mapping = {
            'GEMINI_API.KEY': 'GEMINI_API_KEY'
        }
        return getattr(self, mapping.get(item, item))

class ScraperSettings(BaseSettings):
    ENABLED: bool = Field(validation_alias=AliasChoices('SCRAPER_ENABLED'))
    SCHEDULER: str = Field(validation_alias=AliasChoices('SCRAPER_SCHEDULER'))
    JSON: bool = Field(validation_alias=AliasChoices('JSON_EXPORT'))
    MYSQL: bool = Field(validation_alias=AliasChoices('MYSQL_EXPORT'))
    MAX_WORKERS: int = Field(validation_alias=AliasChoices('MAX_WORKERS'))
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

    def __getitem__(self, item):
        return getattr(self, item)

class UserSettings(BaseSettings):
    ENABLED: bool = Field(validation_alias=AliasChoices('USER_ENABLED'))
    HOST: str = Field(validation_alias=AliasChoices('USER_HOST'))
    PORT: int = Field(validation_alias=AliasChoices('USER_PORT'))
    JWT_SECRET_KEY: str = Field(validation_alias=AliasChoices('JWT_SECRET_KEY'))
    GOOGLE_CLIENT_ID: str = Field(validation_alias=AliasChoices('GOOGLE_CLIENT.ID'))
    GOOGLE_CLIENT_SECRET: str = Field(validation_alias=AliasChoices('GOOGLE_CLIENT.SECRET'))
    GOOGLE_REDIRECT_URI: str = Field(validation_alias=AliasChoices('GOOGLE_REDIRECT.URI'))
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

    def __getitem__(self, item):
        mapping = {
            'GOOGLE_CLIENT.ID': 'GOOGLE_CLIENT_ID',
            'GOOGLE_CLIENT.SECRET': 'GOOGLE_CLIENT_SECRET',
            'GOOGLE_REDIRECT.URI': 'GOOGLE_REDIRECT_URI'
        }
        return getattr(self, mapping.get(item, item))

class Config:
    DEBUG_MODE: bool = os.getenv('DEBUG_MODE', 'FALSE').upper() == 'TRUE'
    MYSQL = MysqlSettings()
    STOCKS_API = StocksApiSettings()
    PROMETHEUS = PrometheusSettings()
    SCRAPER = ScraperSettings()
    USER = UserSettings()

LOCALHOST_ADDRESSES = ['localhost', '127.0.0.1', '0.0.0.0', 'None', None]

engine = create_engine(
    f"mysql+pymysql://{Config.MYSQL['USER']}:{Config.MYSQL['PASSWORD']}@{Config.MYSQL['HOST']}/{Config.MYSQL['DATABASE']}",

    poolclass=QueuePool,
    pool_size=20,
    max_overflow=40,
    pool_pre_ping=True,
    echo=False,
    connect_args={'charset': 'utf8mb4'}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
ScopedSession = scoped_session(SessionLocal)

def getSession():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()