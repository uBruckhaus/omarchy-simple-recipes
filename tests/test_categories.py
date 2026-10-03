from types import SimpleNamespace
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.database import Base
from app.models import Category
from app.main import DEFAULT_CATEGORIES, category_for, ensure_categories

def recipe(title, tags="[]", ingredients="[]"):
    return SimpleNamespace(title=title, tags=tags, ingredients=ingredients)

def test_categories_from_title_and_ingredients():
    assert category_for(recipe("Spaghetti Carbonara")) == "Pasta"
    assert category_for(recipe("Margherita Pizza")) == "Pizza"
    assert category_for(recipe("Abendessen", ingredients='["500 g Lachs"]')) == "Fisch"
    assert category_for(recipe("Überraschung")) == "Sonstiges"

def test_deleted_default_category_is_not_recreated():
    engine=create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        ensure_categories(db)
        assert set(db.scalars(select(Category.name))) == set(DEFAULT_CATEGORIES)
        db.delete(db.scalar(select(Category).where(Category.name == "Pasta")))
        db.commit()
        ensure_categories(db)
        names=set(db.scalars(select(Category.name)))
        assert "Pasta" not in names
        assert "Sonstiges" in names
