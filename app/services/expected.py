"""Vinculació automàtica de visites previstes amb registres reals.

Quan un visitant es registra al quiosc, busquem si hi ha una visita
prevista per a avui que coincideixi (nom + empresa) i, si n'hi ha
exactament una, hi posem visit_id i status='arrived'.

L'estratègia evita falsos positius: si hi ha múltiples possibles
coincidències o cap, no toquem res — el recepcionista pot vincular
manualment via el botó del llistat.
"""
import unicodedata
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ExpectedVisit, Visit


def _normalize_tokens(s: str) -> set[str]:
    """Conjunt de tokens normalitzats: minúscules, sense accents, longitud ≥ 2."""
    if not s:
        return set()
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return {t for t in s.replace(",", " ").split() if len(t) >= 2}


def _normalize_company(s: str) -> str:
    """Empresa normalitzada: minúscules, sense accents, espais col·lapsats."""
    if not s:
        return ""
    s = unicodedata.normalize("NFD", s.lower().strip())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.split())


async def auto_link_expected_visit(
    visit: Visit, db: AsyncSession
) -> ExpectedVisit | None:
    """Cerca i vincula una visita prevista pendent del dia que coincideixi
    amb la visita acabada de crear. Retorna l'ExpectedVisit vinculat o None.

    Criteri d'auto-vincle:
      - expected_date == avui (UTC) AND status == 'pending' AND visit_id IS NULL
      - Tots els tokens del visitor_name de la prevista apareixen al
        first_name + last_name de la visita real (normalitzats).
      - Si la prevista té visitor_company, ha de coincidir amb la de la
        visita (normalitzada). Si no en té, només es valida pel nom.
      - Exactament 1 candidat passa el filtre. 0 o ≥2 → no vincula
        (evita falsos positius en cas d'homonímia).
    """
    today = datetime.now(timezone.utc).date()
    result = await db.execute(
        select(ExpectedVisit).where(
            ExpectedVisit.expected_date == today,
            ExpectedVisit.status == "pending",
            ExpectedVisit.visit_id.is_(None),
        )
    )
    candidates = result.scalars().all()
    if not candidates:
        return None

    visit_tokens = _normalize_tokens(f"{visit.first_name} {visit.last_name}")
    visit_company = _normalize_company(visit.company)

    matches: list[ExpectedVisit] = []
    for exp in candidates:
        exp_tokens = _normalize_tokens(exp.visitor_name)
        if not exp_tokens or not exp_tokens.issubset(visit_tokens):
            continue
        if exp.visitor_company:
            if _normalize_company(exp.visitor_company) != visit_company:
                continue
        matches.append(exp)

    if len(matches) != 1:
        return None

    matched = matches[0]
    matched.visit_id = visit.id
    matched.status = "arrived"
    return matched


async def find_matching_visit_for_expected(
    expected: ExpectedVisit, db: AsyncSession
) -> Visit | None:
    """Sentit invers de l'auto-vincle: donada una visita prevista, busca
    una visita real registrada avui que hi coincideixi. Útil quan
    l'admin clica "Marcar arribada" manualment.
    """
    today = datetime.now(timezone.utc).date()
    today_start = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc)
    tomorrow_start = today_start + timedelta(days=1)

    result = await db.execute(
        select(Visit).where(
            Visit.checked_in_at >= today_start,
            Visit.checked_in_at < tomorrow_start,
        )
    )
    visits = result.scalars().all()
    if not visits:
        return None

    exp_tokens = _normalize_tokens(expected.visitor_name)
    if not exp_tokens:
        return None
    exp_company = (
        _normalize_company(expected.visitor_company)
        if expected.visitor_company else None
    )

    matches: list[Visit] = []
    for v in visits:
        v_tokens = _normalize_tokens(f"{v.first_name} {v.last_name}")
        if not exp_tokens.issubset(v_tokens):
            continue
        if exp_company and _normalize_company(v.company) != exp_company:
            continue
        matches.append(v)

    if len(matches) != 1:
        return None
    return matches[0]
