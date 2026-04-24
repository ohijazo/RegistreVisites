import json
from pathlib import Path
from functools import lru_cache

from app.config import settings

SUPPORTED_LANGS = ["ca", "es", "fr", "en"]
DEFAULT_LANG = "ca"


def _load(lang: str) -> dict:
    path = Path(f"translations/{lang}.json")
    if not path.exists():
        path = Path(f"translations/{DEFAULT_LANG}.json")
    return json.loads(path.read_text(encoding="utf-8"))


if settings.ENV == "production":
    load_translations = lru_cache(maxsize=4)(_load)
else:
    load_translations = _load


def t(lang: str, key: str, **kwargs) -> str:
    """Retorna la traducció i aplica format si cal."""
    translations = load_translations(lang)
    text = translations.get(key, key)
    return text.format(**kwargs) if kwargs else text
