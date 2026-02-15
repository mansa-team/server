import os
import sys
import json
import time
import math
from typing import Optional, Dict, Any

from datetime import datetime, timedelta
from dotenv import load_dotenv
from time import sleep

import requests
import pandas as pd
import numpy as np

from sqlalchemy import create_engine, text, QueuePool

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
        'KEY.SYSTEM': os.getenv('PROMETHEUS_KEY.SYSTEM'),
        'KEY': os.getenv('PROMETHEUS_PRIVATE.KEY'),
        'GEMINI_API.KEY': os.getenv('GEMINI_API.KEY'),
    }
    
    SCRAPER = {
        'ENABLED': os.getenv('SCRAPER_ENABLED'),
        'SCHEDULER': os.getenv('SCRAPER_SCHEDULER'),
        'JSON': os.getenv('JSON_EXPORT'),
        'MYSQL': os.getenv('MYSQL_EXPORT'),
        'MAX_WORKERS': os.getenv('MAX_WORKERS'),
    }

    AUTH = {
        'ENABLED': os.getenv('AUTH_ENABLED'),
        'HOST': os.getenv('AUTH_HOST'),
        'PORT': os.getenv('AUTH_PORT'),
        'JEW_TOKEN': os.getenv('JEW_TOKEN'),
    }
dbEngine = create_engine(
    f"mysql+pymysql://{Config.MYSQL['USER']}:{Config.MYSQL['PASSWORD']}@{Config.MYSQL['HOST']}/{Config.MYSQL['DATABASE']}",
    poolclass=QueuePool,
    pool_size=20,
    max_overflow=40,
    pool_pre_ping=True,
    echo=False,
    connect_args={'charset': 'utf8mb4'}
)