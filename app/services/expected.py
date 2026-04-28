"""Vinculació automàtica de visites previstes amb registres reals.

Quan un visitant es registra al quiosc, busquem si hi ha una visita
prevista per a avui que coincideixi pel nom. La política és:

  1. Filtrar candidats del dia pendents pel nom (subset de tokens
     normalitzats: minúscules, sense accents, sense paraules curtes).
  2. Si hi ha exactament 1 candidat amb nom coincident → vincular
     (encara que les empreses no quadrin: el nom complet és prou
     identificador en el cas habitual).
  3. Si hi ha múltiples candidats amb el mateix nom → exigir que
     l'empresa coincideixi (normalitzada) per desempatar.
  4. Si encara hi ha múltiples o cap → no vincular (estat segur).

Aquesta política tolera variacions menors d'empresa (un visitant
treballant per a Otis es registra com a empresa pròpia) sense crear
falsos positius en cas d'homònims, on encara cal coincidència
estricta d'empresa.
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


def _select_unique_match(
    candidates: list[ExpectedVisit],
    visit_tokens: set[str],
    visit_company_norm: str,
) -> ExpectedVisit | None:
    """Aplica la política de match: nom primer, empresa com a desempat.

    Retorna el candidat vinculable o None si no és segur vincular.
    """
    # Pas 1: filtrar pels que tenen el nom coincident (subset de tokens)
    name_matches = [
        e for e in candidates
        if (toks := _normalize_tokens(
            f"{e.visitor_first_name} {e.visitor_last_name or ''}"
        )) and toks.issubset(visit_tokens)
    ]
    if len(name_matches) == 1:
        return name_matches[0]
    if len(name_matches) <= 1:
        return None

    # Pas 2: empat — restringir per empresa coincident (només si la prevista
    # en té; si està buida, no es considera coincident en aquest pas).
    company_matches = [
        e for e in name_matches
        if e.visitor_company
        and _normalize_company(e.visitor_company) == visit_company_norm
    ]
    if len(company_matches) == 1:
        return company_matches[0]
    return None


async def auto_link_expected_visit(
    visit: Visit, db: AsyncSession
) -> ExpectedVisit | None:
    """Cerca i vincula una visita prevista pendent del dia que coincideixi
    amb la visita acabada de crear. Retorna l'ExpectedVisit vinculat o None.

    Vegeu el docstring del mòdul per al criteri exacte.
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

    matched = _select_unique_match(candidates, visit_tokens, visit_company)
    if matched is None:
        return None
    matched.visit_id = visit.id
    matched.status = "arrived"
    return matched


async def find_matching_visit_for_expected(
    expected: ExpectedVisit, db: AsyncSession
) -> Visit | None:
    """Sentit invers de l'auto-vincle: donada una visita prevista, busca
    una visita real registrada avui que hi coincideixi (mateixa política
    que `auto_link_expected_visit`: nom primer, empresa com a desempat).
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

    exp_tokens = _normalize_tokens(
        f"{expected.visitor_first_name} {expected.visitor_last_name or ''}"
    )
    if not exp_tokens:
        return None
    exp_company_norm = (
        _normalize_company(expected.visitor_company)
        if expected.visitor_company else ""
    )

    # Pas 1: filtrar visites pel nom (tokens de la prevista ⊆ tokens de la visita)
    name_matches = [
        v for v in visits
        if exp_tokens.issubset(_normalize_tokens(f"{v.first_name} {v.last_name}"))
    ]
    if len(name_matches) == 1:
        return name_matches[0]
    if len(name_matches) <= 1:
        return None

    # Pas 2: empat — desempatar per empresa coincident només si la prevista
    # té empresa explícita
    if not exp_company_norm:
        return None
    company_matches = [
        v for v in name_matches
        if _normalize_company(v.company) == exp_company_norm
    ]
    if len(company_matches) == 1:
        return company_matches[0]
    return None
