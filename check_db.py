import psycopg
from app.config import settings

with psycopg.connect(settings.database_url) as conn:
    print(conn.execute("select version()").fetchone())