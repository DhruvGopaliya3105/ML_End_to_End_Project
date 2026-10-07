import logging
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError

from src.config import SQLITE_DB_PATH


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


# Absolute path, so the SQLite file is always the one next to the project
# root. It used to be "sqlite:///./sanjeevani_clinic.db" (relative), which
# created a *different*, empty database whenever the server was started from
# another directory - a very confusing "my data disappeared" bug.
SQLITE_URL = f"sqlite:///{SQLITE_DB_PATH}"


def _sqlite_engine():
    SQLITE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(
        SQLITE_URL,
        connect_args={"check_same_thread": False}
    )


def _explain_mysql_failure(error: BaseException) -> str:
    """Turn a raw driver error into an actionable hint.

    Without this, a MySQL problem shows up only as an unexplained silently
    empty app, because the connection falls back to SQLite.
    """

    text_error = str(error)
    lowered = text_error.lower()

    if "cryptography" in lowered and (
        "sha2" in lowered or "sha256" in lowered
    ):
        return (
            "MySQL 8 uses caching_sha2_password authentication, which PyMySQL "
            "can only handle if the 'cryptography' package is installed. "
            "Run: pip install cryptography  (it is now listed in "
            "requirements.txt, so 'pip install -r requirements.txt' fixes it too)"
        )

    # 1044 = "Access denied for user ... to database 'x'"
    #        -> the database is missing, or this user has no rights on it
    if "to database" in lowered or "(1044" in text_error:
        return (
            f"The database '{DB_NAME}' is missing, or user '{DB_USER}' has no "
            "privileges on it. Run your MySQL setup script to create it (or fix "
            "DB_NAME / DB_USER in your .env file)."
        )

    # 1049 = "Unknown database"
    if "unknown database" in lowered or "(1049" in text_error:
        return (
            f"The database '{DB_NAME}' does not exist on this MySQL server. "
            "Run your MySQL setup script to create it, or fix DB_NAME in .env."
        )

    # 1045 = "Access denied for user ... (using password: YES)"
    if "(1045" in text_error or (
        "access denied" in lowered and "using password" in lowered
    ):
        return (
            "MySQL rejected the username or password. Check DB_USER and "
            "DB_PASSWORD in your .env file."
        )

    if "access denied" in lowered:
        return (
            "MySQL denied access. Check DB_USER and DB_PASSWORD in your .env "
            "file."
        )

    if "connection refused" in lowered or "(2003" in text_error:
        return (
            "Nothing is listening on that MySQL host/port. Is the MySQL "
            "service started? Check DB_HOST and DB_PORT in your .env file."
        )

    if "(1698" in text_error or "auth_socket" in lowered:
        return (
            "This MySQL user authenticates via the operating-system socket "
            "(auth_socket), which the app cannot use. Create a password-based "
            "user, e.g. "
            "CREATE USER 'sanjeevani'@'localhost' IDENTIFIED BY 'yourpass';"
        )

    if "can't connect to mysql server" in lowered or "(2002" in text_error:
        return (
            "Could not reach the MySQL server. Make sure the MySQL service "
            "is running and DB_HOST/DB_PORT are correct."
        )

    return text_error[:200]


def _get_engine():
    """Auto-detect available database: try MySQL first, fall back to SQLite.

    The fallback is intentional (it lets the project run with zero setup), but
    it is now reported loudly instead of being silent: ``DATABASE_BACKEND`` and
    ``DATABASE_LABEL`` below expose which database is really in use, the log
    line is a WARNING, and ``/health`` reports it.
    """

    global DATABASE_BACKEND, DATABASE_LABEL, MYSQL_FALLBACK_REASON

    if USE_SQLITE:
        logger.info("Using SQLite database (USE_SQLITE=true) -> %s", SQLITE_DB_PATH)
        DATABASE_BACKEND = "sqlite"
        DATABASE_LABEL = f"SQLite ({SQLITE_DB_PATH})"
        return _sqlite_engine()

    # ---- Try MySQL if credentials are present ----
    if not all([DB_USER, DB_PASSWORD, DB_HOST, DB_NAME]):

        MYSQL_FALLBACK_REASON = (
            "MySQL settings are incomplete in .env "
            "(DB_USER / DB_PASSWORD / DB_HOST / DB_NAME)."
        )

        logger.warning(
            "%s Falling back to SQLite -> %s",
            MYSQL_FALLBACK_REASON,
            SQLITE_DB_PATH,
        )

        DATABASE_BACKEND = "sqlite"
        DATABASE_LABEL = f"SQLite ({SQLITE_DB_PATH})"
        return _sqlite_engine()

    try:
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
            MYSQL_FALLBACK_REASON = (
                f"MySQL connection failed ({DB_HOST}:{DB_PORT}/{DB_NAME}) -- "
                f"{_explain_mysql_failure(e)}"
            )
            logger.warning(
                "%s -- Falling back to SQLite -> %s",
                MYSQL_FALLBACK_REASON,
                SQLITE_DB_PATH,
            )
            DATABASE_BACKEND = "sqlite"
            DATABASE_LABEL = f"SQLite ({SQLITE_DB_PATH})"
            return _sqlite_engine()
        finally:
            test_engine.dispose()

    except Exception as e:  # noqa: BLE001 - bad URL / missing driver etc.
        MYSQL_FALLBACK_REASON = (
            f"MySQL connection failed ({DB_HOST}:{DB_PORT}/{DB_NAME}) -- "
            f"{_explain_mysql_failure(e)}"
        )
        logger.warning(
            "%s -- Falling back to SQLite -> %s",
            MYSQL_FALLBACK_REASON,
            SQLITE_DB_PATH,
        )
        DATABASE_BACKEND = "sqlite"
        DATABASE_LABEL = f"SQLite ({SQLITE_DB_PATH})"
        return _sqlite_engine()

    logger.info(
        "MySQL database connection successful to %s:%s/%s",
        DB_HOST, DB_PORT, DB_NAME
    )
    DATABASE_BACKEND = "mysql"
    DATABASE_LABEL = f"MySQL ({DB_HOST}:{DB_PORT}/{DB_NAME})"
    return create_engine(mysql_url, pool_pre_ping=True)


# Filled in by _get_engine()
DATABASE_BACKEND = "unknown"
DATABASE_LABEL = "unknown"
MYSQL_FALLBACK_REASON = None


# SQLAlchemy engine with auto-detection
engine = _get_engine()


# Database session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)


def get_db():
    """FastAPI dependency that yields a database session."""
    db = SessionLocal()

    try:
        yield db

    finally:
        db.close()
