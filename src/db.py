import os
from urllib.parse import urlparse
import pg8000.native
import pg8000.dbapi
from dotenv import load_dotenv

load_dotenv()

def _parse_db_url():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise ValueError("DATABASE_URL not found in environment variables or .env file.")
    return urlparse(db_url)

def get_native_conn():
    """Returns a fast pg8000.native connection for SQL execution and COPY streams."""
    u = _parse_db_url()
    return pg8000.native.Connection(
        user=u.username,
        password=u.password,
        host=u.hostname,
        port=u.port or 5432,
        database=u.path.lstrip("/"),
        ssl_context=True,
    )

def get_dbapi_conn():
    """Returns a DB-API 2.0 connection compatible with pandas.read_sql()."""
    u = _parse_db_url()
    return pg8000.dbapi.connect(
        user=u.username,
        password=u.password,
        host=u.hostname,
        port=u.port or 5432,
        database=u.path.lstrip("/"),
        ssl_context=True,
    )
