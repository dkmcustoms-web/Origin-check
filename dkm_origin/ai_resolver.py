"""
AI-fallback country resolver
============================

Wanneer de lokale resolver (`countries.resolve_country()`) een input niet
herkent, valt deze module terug op Claude Haiku om de ISO-2 code op te
zoeken. Werkt voor élke taal en alle creatieve omschrijvingen.

Patroon: lokaal eerst (gratis), AI alleen als fallback (paar cents/maand
bij gebruik).

Vereist een ANTHROPIC_API_KEY environment variable. Als die ontbreekt
gedraagt de module zich als de gewone lokale resolver.
"""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache

from .countries import CountryMatch, COUNTRIES, resolve_country as _local_resolve


# Set van alle bekende ISO-2 codes (om Haiku's antwoord te valideren)
KNOWN_ISO2: set[str] = set(COUNTRIES.keys())


SYSTEM_PROMPT = """Je bent een land-resolver. De gebruiker geeft een land-aanduiding \
in eender welke taal of formulering. Geef ALLEEN de ISO-3166-1 alpha-2 code terug \
(twee hoofdletters, bv. JP voor Japan, FR voor Frankrijk).

Regels:
- Twijfel je over het land? Antwoord met UNKNOWN.
- Is de input geen land maar iets anders? Antwoord met UNKNOWN.
- Geef NOOIT uitleg, NOOIT meerdere codes, NOOIT iets anders dan twee hoofdletters of UNKNOWN.

Voorbeelden:
- "프랑스" → FR
- "the country with the Eiffel Tower" → FR
- "Frankreich" → FR
- "frankrijk" → FR
- "Verenigde Staten van Amerika" → US
- "VSA" → US
- "een appel" → UNKNOWN"""


def _call_haiku(query: str, api_key: str) -> str | None:
    """Roep Haiku aan en parse het antwoord. Return ISO-2 of None."""
    try:
        # Lazy import: Anthropic SDK alleen importeren als nodig
        import anthropic
    except ImportError:
        return None

    client = anthropic.Anthropic(api_key=api_key)
    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=10,  # heel laag — antwoord is 2 chars of "UNKNOWN"
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": query}],
        )
        text = "".join(
            block.text for block in response.content if hasattr(block, "text")
        ).strip().upper()
    except Exception:
        return None

    # Strikte validatie: exact 2 hoofdletters
    if re.fullmatch(r"[A-Z]{2}", text) and text in KNOWN_ISO2:
        return text
    return None


@lru_cache(maxsize=512)
def _cached_haiku_lookup(query: str) -> str | None:
    """Cache de Haiku-antwoorden per process. Save tokens bij herhaling."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    return _call_haiku(query, api_key)


def resolve_country_with_ai(user_input: str) -> CountryMatch:
    """Lokale resolver eerst; valt terug op Haiku bij mismatch.

    Identieke API als `countries.resolve_country()`, plus method="ai" wanneer
    Haiku het oplost.
    """
    # Stap 1: probeer lokaal (gratis en instant)
    local = _local_resolve(user_input)
    if local.matched:
        return local

    # Stap 2: alleen AI-call als lokaal echt niets vond
    if not user_input or not user_input.strip():
        return local

    iso2 = _cached_haiku_lookup(user_input.strip())
    if iso2:
        return CountryMatch(
            iso2=iso2,
            name_nl=COUNTRIES[iso2][1],
            matched=True,
            method="ai",
            suggestions=[],
        )

    # Geen lokale match én Haiku gaf UNKNOWN of geen API-key → de lokale suggesties teruggeven
    return local


def is_ai_available() -> bool:
    """True als de API-key gezet is én de SDK beschikbaar."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
        return True
    except ImportError:
        return False
