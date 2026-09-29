import os
import logging

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError


logger = logging.getLogger(__name__)

# .env file load karega
load_dotenv()


# .env se database ki values read karega
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT") or "3306"
DB_NAME = os.getenv("DB_NAME")
USE_SQLITE = os.getenv("USE_SQLITE", "false").lower() == "true"


def _get_engine():
    """Auto-detect available database: Try MySQL first, fallback to SQLite"""
    
    if USE_SQLITE:
        logger.info("Using SQLite database (USE_SQLITE=true)")
        return create_engine(
            "sqlite:///./sanjeevani_clinic.db",
            connect_args={"check_same_thread": False}
        )
    
    # Try MySQL first
    mysql_url = URL.create(
        drivername="mysql+pymysql",
        username=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=int(DB_PORT),
        database=DB_NAME
    )

    test_engine = create_engine(mysql_url, pool_pre_ping=True)
    try:
        with test_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except OperationalError as e:
        logger.warning(
            f"MySQL connection failed ({DB_HOST}:{DB_PORT}): {str(e)[:80]}... "
            "Falling back to SQLite"
        )
        return create_engine(
            "sqlite:///./sanjeevani_clinic.db",
            connect_args={"check_same_thread": False}
        )
    finally:
        test_engine.dispose()

    logger.info(f"MySQL database connection successful to {DB_HOST}:{DB_PORT}/{DB_NAME}")
    return create_engine(mysql_url, pool_pre_ping=True)


# SQLAlchemy engine with auto-detection
engine = _get_engine()


# Database session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)


# FastAPI endpoints ke liye database session
def get_db():
    db = SessionLocal()

    try:
        yield db

    finally:
        db.close()
