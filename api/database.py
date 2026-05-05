"""
database.py — Connection pool management for ShopPrime API.
Uses psycopg2 with a ThreadedConnectionPool backed by Neon PostgreSQL.
"""

import os
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

# ThreadedConnectionPool: min 2, max 10 connections
_pool: pool.ThreadedConnectionPool = None


def get_pool() -> pool.ThreadedConnectionPool:
    global _pool
    if _pool is None:
        _pool = pool.ThreadedConnectionPool(
            minconn=2,
            maxconn=10,
            dsn=DATABASE_URL,
        )
    return _pool


@contextmanager
def get_conn():
    """Yield a connection from the pool; auto-return on exit."""
    connection = get_pool().getconn()
    try:
        yield connection
    except Exception:
        connection.rollback()
        raise
    finally:
        get_pool().putconn(connection)


@contextmanager
def get_cursor(commit: bool = True):
    """Yield a RealDictCursor; commit or rollback on exit."""
    with get_conn() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        try:
            yield cursor
            if commit:
                conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()


def close_pool():
    global _pool
    if _pool:
        _pool.closeall()
        _pool = None
