import os
import socket
from dotenv import load_dotenv
from sqlalchemy import create_engine, QueuePool
from sqlalchemy.orm import sessionmaker, scoped_session

def applyIPv4Force():
    _old_getaddrinfo = socket.getaddrinfo
    def _new_getaddrinfo(*args, **kwargs):
        res = _old_getaddrinfo(*args, **kwargs)
        return [r for r in res if r[0] == socket.AF_INET]
    socket.getaddrinfo = _new_getaddrinfo

applyIPv4Force()
load_dotenv()

LOCALHOST_ADDRESSES = ['localhost', '127.0.0.1', '0.0.0.0', 'None', None]
class Config:
    DEBUG_MODE = os.getenv('DEBUG_MODE')

    MYSQL = {
        'USER': os.getenv('MYSQL_USER'),
        'PASSWORD': os.getenv('MYSQL_PASSWORD'),
        'HOST': os.getenv('MYSQL_HOST'),
        'DATABASE': os.getenv('MYSQL_DATABASE'),
    }
    
    STOCKS_API = {
        'ENABLED': os.getenv('STOCKSAPI_ENABLED'),
        'HOST': os.getenv('STOCKSAPI_HOST'),
        'PORT': os.getenv('STOCKSAPI_PORT'),
        'KEY.SYSTEM': os.getenv('STOCKSAPI_KEY.SYSTEM'),
        'KEY': os.getenv('STOCKSAPI_PRIVATE.KEY'),
        'DEFAULT.QUOTA': os.getenv('STOCKSAPI_DEFAULT.QUOTA'),
        'QUOTA.RESETDAYS': os.getenv('STOCKSAPI_QUOTA.RESETDAYS'),
    }

    PROMETHEUS = {
        'ENABLED': os.getenv('PROMETHEUS_ENABLED'),
        'HOST': os.getenv('PROMETHEUS_HOST'),
        'PORT': os.getenv('PROMETHEUS_PORT'),
        'GEMINI_API.KEY': os.getenv('GEMINI_API.KEY'),
    }
    
    SCRAPER = {
        'ENABLED': os.getenv('SCRAPER_ENABLED'),
        'SCHEDULER': os.getenv('SCRAPER_SCHEDULER'),
        'JSON': os.getenv('JSON_EXPORT'),
        'MYSQL': os.getenv('MYSQL_EXPORT'),
        'MAX_WORKERS': os.getenv('MAX_WORKERS'),
    }

    USER = {
        'ENABLED': os.getenv('USER_ENABLED'),
        'HOST': os.getenv('USER_HOST'),
        'PORT': os.getenv('USER_PORT'),
        'JWT_SECRET_KEY': os.getenv('JWT_SECRET_KEY'),
        'GOOGLE_CLIENT.ID': os.getenv('GOOGLE_CLIENT.ID'),
        'GOOGLE_CLIENT.SECRET': os.getenv('GOOGLE_CLIENT.SECRET'),
        'GOOGLE_REDIRECT.URI': os.getenv('GOOGLE_REDIRECT.URI'),
    }

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