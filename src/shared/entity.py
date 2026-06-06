"""
Entity resolution--matches incoming company names to existing records.

Two-pass approach: normalize legal suffixes first (handles 90% of cases),
then fuzzy string match as fallback.
"""

from difflib import SequenceMatcher

from sqlalchemy.orm import Session

from src.models.schema import Company

# common legal suffixes that don't help distinguish companies
SUFFIXES = frozenset({
    "corp", "corporation", "inc", "incorporated", "llc", "ltd",
    "limited", "systems", "platforms", "technologies", "company",
    "co", "group", "holdings",
})

FUZZY_THRESHOLD = 0.80


def normalize_name(name: str) -> str:
    """Strip legal suffixes and normalize whitespace."""
    tokens = name.lower().split()
    cleaned = [t for t in tokens if t.rstrip(".,") not in SUFFIXES]
    return " ".join(cleaned).strip()


def resolve_company(db: Session, name: str, domain: str) -> Company | None:
    """Find existing company matching this name/domain, or return None."""

    # pass 1: exact domain match (fast path)
    company = db.query(Company).filter_by(domain=domain).first()
    if company:
        return company

    # pass 2: normalized name--catches "Acme Corp" vs "Acme Corporation"
    normalized = normalize_name(name)
    if not normalized:
        return None

    # full scan--add pg_trgm index for >10K companies
    existing = db.query(Company).all()
    for candidate in existing:
        if normalize_name(candidate.name) == normalized:
            return candidate

    # pass 3: fuzzy--tried Levenshtein first, SequenceMatcher handles multi-word names better
    # e.g., "JPMorgan Chase" vs "JP Morgan"
    for candidate in existing:
        ratio = SequenceMatcher(
            None, normalized, normalize_name(candidate.name)
        ).ratio()
        if ratio > FUZZY_THRESHOLD:
            return candidate

    return None
