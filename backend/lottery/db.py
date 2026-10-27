from functools import lru_cache
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .config import database_url

@lru_cache
def engine():
    return create_engine(database_url(), pool_pre_ping=True, pool_recycle=1800)

def session_factory():
    return sessionmaker(engine(), expire_on_commit=False)
