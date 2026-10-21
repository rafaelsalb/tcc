from sqlalchemy import create_engine

from config import POSTGRES_DSN


# pool_pre_ping survives the docker Postgres container restarting between
# requests; without it the pooled connections go stale and raise.
engine = create_engine(POSTGRES_DSN, echo=False, pool_pre_ping=True)
