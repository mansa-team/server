from sqlalchemy.orm import declarative_base

from main.models.user import User
from main.models.stocksapi_key import StocksAPIKey

Base = declarative_base()

__all__ = ['Base', 'User', 'StocksAPIKey']
