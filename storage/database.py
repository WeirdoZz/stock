from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
from config.settings import settings
from storage.models import Base

engine = create_engine(
    f"sqlite:///{settings.db_path}",
    connect_args={"check_same_thread": False},
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,
    pool_pre_ping=True,
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_conn, _):
    """Enable WAL mode and tune SQLite for concurrent read performance."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")      # concurrent reads during writes
    cursor.execute("PRAGMA synchronous=NORMAL")    # durable on OS crash, faster than FULL
    cursor.execute("PRAGMA cache_size=-32000")     # 32 MB page cache
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


@contextmanager
def get_session() -> Session:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
