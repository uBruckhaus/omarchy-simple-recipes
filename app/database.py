import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATA_DIR = Path(os.environ.get("RECIPES_DATA_DIR", str(Path.home() / ".local/share/simple-recipes/data")))
DATA_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
engine = create_engine(f"sqlite:///{DATA_DIR / 'rezepte.db'}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)

class Base(DeclarativeBase):
    pass

