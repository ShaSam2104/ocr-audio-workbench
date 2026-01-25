"""SQLAlchemy database configuration."""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import DATABASE_URL

# Create SQLAlchemy engine
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
    echo=False,  # Set to True for debugging
)

# Enable FTS5 for SQLite
if "sqlite" in DATABASE_URL:
    @event.listens_for(engine, "connect")
    def enable_fts5(dbapi_conn, connection_record):
        """Enable FTS5 extension and foreign keys for SQLite."""
        cursor = dbapi_conn.cursor()
        # Enable foreign keys
        cursor.execute("PRAGMA foreign_keys=ON")
        # Load FTS5 extension (most SQLite builds have this compiled in)
        try:
            cursor.execute("PRAGMA compile_options")
            options = cursor.fetchall()
            # FTS5 is usually available, but we can optionally load it
        except Exception as e:
            print(f"Warning: Could not verify FTS5 support: {e}")
        cursor.close()

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for all models
Base = declarative_base()


def get_db():
    """Dependency for getting database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables in the database."""
    Base.metadata.create_all(bind=engine)
