from sqlalchemy import select
from .models import Category

CATEGORY_RULES = {
    "Pasta": ("pasta", "nudel", "spaghetti", "penne", "tagliatelle", "lasagne", "gnocchi", "ravioli", "macaroni", "fettuccine", "rigatoni", "tortellini", "orzo", "carbonara", "bolognese", "arrabbiata", "pesto"),
    "Pizza": ("pizza", "calzone", "flammkuchen"),
    "Suppe": ("suppe", "soup", "eintopf", "stew", "brühe", "broth", "chowder", "ramen", "goulash", "minestrone"),
    "Salat": ("salat", "salad", "bowl", "coleslaw", "dressing"),
    "Backen": ("brot", "brötchen", "kuchen", "muffin", "muffins", "backen", "bread", "cake", "cookie", "cookies", "biscuit", "biscuits", "pie", "tart", "waffle", "waffel", "teig", "dough", "pancake", "pancakes", "brownie", "brownies", "gebäck", "pastry"),
    "Dessert": ("dessert", "nachtisch", "creme", "eis", "tiramisu", "pudding", "süß", "sweet", "ice cream", "mousse", "parfait", "schokolade", "chocolate", "sorbet"),
    "Frühstück": ("frühstück", "breakfast", "porridge", "müsli", "omelett", "omelette", "egg", "eggs", "rührei", "spiegelei", "brunch"),
    "Fleisch": ("hähnchen", "huhn", "chicken", "rind", "beef", "schwein", "pork", "steak", "hackfleisch", "meat", "bacon", "speck", "turkey", "pute", "lamb", "lamm", "sausage", "wurst", "schnitzel", "gulasch", "braten", "filet", "ribs", "rippchen", "burger", "patty", "veal", "kalb"),
    "Fisch": ("fisch", "fish", "lachs", "salmon", "thunfisch", "tuna", "garnele", "shrimp", "prawn", "seafood", "meeresfrüchte", "cod", "kabeljau", "forelle", "trout", "dorade", "zander", "crab", "krabbe", "calamari"),
    "Vegetarisch": ("vegetarisch", "vegetarian", "vegan", "veggie", "tofu", "gemüse", "vegetable", "vegetables", "aubergine", "eggplant", "zucchini", "pilz", "pilze", "mushroom", "mushrooms", "linsen", "lentil", "kichererbse", "kichererbsen", "chickpea", "falafel", "parmigiana", "spinat", "spinach", "avocado", "curry"),
}
DEFAULT_CATEGORIES = list(CATEGORY_RULES) + ["Sonstiges"]
CATEGORY_ICONS = {
    "Pasta":"🍝", "Pizza":"🍕", "Suppe":"🥣", "Salat":"🥗", "Backen":"🥐",
    "Dessert":"🍰", "Frühstück":"🍳", "Fleisch":"🥩", "Fisch":"🐠",
    "Vegetarisch":"🌱", "Sonstiges":"🗂️",
}

def fallback_category_icon(name):
    lowered=name.lower()
    choices=(("🔥",("grill","bbq")),("🍹",("getränk","drink","cocktail")),
             ("🍪",("keks","cookie")),("🍞",("brot","bread")),
             ("🍗",("huhn","hähnchen","chicken")),("🍚",("reis","rice")),
             ("🫙",("mittag","abend","gericht")),("🍎",("gesund","obst","frucht")))
    return next((icon for icon, words in choices if any(word in lowered for word in words)),"🏷️")

def category_icons(db):
    return {category.name:category.icon or CATEGORY_ICONS.get(category.name,"🏷️")
            for category in db.scalars(select(Category).order_by(Category.name))}

def category_for(recipe, force: bool = False):
    if not force and getattr(recipe, "category", ""): return recipe.category
    title = (getattr(recipe, "title", "") or "").lower()
    for cat, words in CATEGORY_RULES.items():
        if any(word in title for word in words): return cat
    ingredients = (getattr(recipe, "ingredients", "") or "").lower()
    for cat, words in CATEGORY_RULES.items():
        if any(word in ingredients for word in words): return cat
    tags = (getattr(recipe, "tags", "") or "").lower()
    for cat, words in CATEGORY_RULES.items():
        if any(word in tags for word in words): return cat
    return "Sonstiges"

def ensure_categories(db):
    existing=set(db.scalars(select(Category.name)).all())
    # Seed the complete set only for a new database. Afterwards deleted default
    # categories must stay deleted; only the required fallback is recreated.
    required = DEFAULT_CATEGORIES if not existing else ["Sonstiges"]
    for name in required:
        if name not in existing: db.add(Category(name=name,icon=CATEGORY_ICONS.get(name,"🏷️")))
    for category in db.scalars(select(Category)):
        if category.icon in ("", "🏷️"):
            category.icon=CATEGORY_ICONS.get(category.name,fallback_category_icon(category.name))
    db.commit()

