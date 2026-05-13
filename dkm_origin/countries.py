"""
Country lookup voor DKM Origin
==============================

Resolves vrije tekst-invoer ("Verenigde Staten", "USA", "Japan", "VK")
naar ISO-2 codes voor gebruik in de validator.

Bevat alle landen die in de preferential_agreements dataset voorkomen,
plus veel voorkomende non-preferentiële bestemmingen voor de export-flow.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import get_close_matches


@dataclass
class CountryMatch:
    """Resultaat van een country lookup."""

    iso2: str | None
    name_nl: str | None
    matched: bool
    method: str  # "exact" | "alias" | "fuzzy" | "iso2" | "iso3" | "none"
    suggestions: list[str]


# ──────────────────────────────────────────────────────────────────────
# Master country table
#   iso2: (iso3, name_nl, name_en, aliases)
# ──────────────────────────────────────────────────────────────────────
COUNTRIES: dict[str, tuple[str, str, str, list[str]]] = {
    # EU + EER + EVA
    "CH": ("CHE", "Zwitserland", "Switzerland", []),
    "NO": ("NOR", "Noorwegen", "Norway", []),
    "IS": ("ISL", "IJsland", "Iceland", []),
    "LI": ("LIE", "Liechtenstein", "Liechtenstein", []),
    "FO": ("FRO", "Faeröer Eilanden", "Faroe Islands", ["faeroer", "faroer", "faroe"]),
    # Mediterraan
    "AD": ("AND", "Andorra", "Andorra", []),
    "DZ": ("DZA", "Algerije", "Algeria", []),
    "TN": ("TUN", "Tunesië", "Tunisia", ["tunesie"]),
    "MA": ("MAR", "Marokko", "Morocco", []),
    "EH": ("ESH", "Westelijke Sahara", "Western Sahara", ["west-sahara", "westsahara"]),
    "EG": ("EGY", "Egypte", "Egypt", []),
    "LB": ("LBN", "Libanon", "Lebanon", []),
    "SY": ("SYR", "Syrië", "Syria", ["syrie"]),
    "JO": ("JOR", "Jordanië", "Jordan", ["jordanie"]),
    "PS": ("PSE", "Palestina", "Palestine", ["palestijnse gebieden", "plo"]),
    "IL": ("ISR", "Israël", "Israel", ["israel"]),
    "TR": ("TUR", "Turkije", "Turkey", []),
    # Balkan
    "AL": ("ALB", "Albanië", "Albania", ["albanie"]),
    "BA": ("BIH", "Bosnië-Herzegovina", "Bosnia and Herzegovina", ["bosnie", "bosnie-herzegovina", "bosnia"]),
    "XK": ("XKX", "Kosovo", "Kosovo", []),
    "ME": ("MNE", "Montenegro", "Montenegro", []),
    "RS": ("SRB", "Servië", "Serbia", ["servie"]),
    "MK": ("MKD", "Noord-Macedonië", "North Macedonia", ["noord-macedonie", "macedonie", "macedonia", "fyrom"]),
    # Oostelijk Partnerschap
    "MD": ("MDA", "Moldavië", "Moldova", ["moldavie"]),
    "GE": ("GEO", "Georgië", "Georgia", ["georgie"]),
    "UA": ("UKR", "Oekraïne", "Ukraine", ["oekraine", "ukraine"]),
    # UK
    "GB": ("GBR", "Verenigd Koninkrijk", "United Kingdom",
           ["vk", "uk", "groot-brittannie", "groot-brittannië", "britain", "great britain", "engeland"]),
    # Americas
    "CO": ("COL", "Colombia", "Colombia", []),
    "PE": ("PER", "Peru", "Peru", []),
    "EC": ("ECU", "Ecuador", "Ecuador", []),
    "CA": ("CAN", "Canada", "Canada", []),
    "CL": ("CHL", "Chili", "Chile", ["chile"]),
    "HN": ("HND", "Honduras", "Honduras", []),
    "NI": ("NIC", "Nicaragua", "Nicaragua", []),
    "PA": ("PAN", "Panama", "Panama", []),
    "CR": ("CRI", "Costa Rica", "Costa Rica", []),
    "SV": ("SLV", "El Salvador", "El Salvador", []),
    "GT": ("GTM", "Guatemala", "Guatemala", []),
    "AR": ("ARG", "Argentinië", "Argentina", ["argentinie"]),
    "BR": ("BRA", "Brazilië", "Brazil", ["brazilie"]),
    "PY": ("PRY", "Paraguay", "Paraguay", []),
    "UY": ("URY", "Uruguay", "Uruguay", []),
    "MX": ("MEX", "Mexico", "Mexico", []),
    "US": ("USA", "Verenigde Staten", "United States",
           ["vs", "vsa", "usa", "amerika", "united states of america", "verenigde staten van amerika"]),
    # ACS / Africa
    "KE": ("KEN", "Kenia", "Kenya", ["kenya"]),
    "GH": ("GHA", "Ghana", "Ghana", []),
    "CI": ("CIV", "Ivoorkust", "Ivory Coast", ["cote d'ivoire", "côte d'ivoire", "ivory coast"]),
    "CM": ("CMR", "Kameroen", "Cameroon", []),
    "BW": ("BWA", "Botswana", "Botswana", []),
    "LS": ("LSO", "Lesotho", "Lesotho", []),
    "MZ": ("MOZ", "Mozambique", "Mozambique", []),
    "ZA": ("ZAF", "Zuid-Afrika", "South Africa", ["zuid afrika", "south africa", "rsa"]),
    "NA": ("NAM", "Namibië", "Namibia", ["namibie"]),
    "SZ": ("SWZ", "Eswatini", "Eswatini", ["swaziland"]),
    "ZW": ("ZWE", "Zimbabwe", "Zimbabwe", []),
    "MG": ("MDG", "Madagaskar", "Madagascar", ["madagascar"]),
    "MU": ("MUS", "Mauritius", "Mauritius", []),
    "SC": ("SYC", "Seychellen", "Seychelles", ["seychelles"]),
    "KM": ("COM", "Comoren", "Comoros", ["comoros"]),
    # ACS / Caribbean
    "AG": ("ATG", "Antigua en Barbuda", "Antigua and Barbuda", ["antigua"]),
    "BS": ("BHS", "Bahama's", "Bahamas", ["bahamas"]),
    "BB": ("BRB", "Barbados", "Barbados", []),
    "BZ": ("BLZ", "Belize", "Belize", []),
    "DM": ("DMA", "Dominica", "Dominica", []),
    "DO": ("DOM", "Dominicaanse Republiek", "Dominican Republic", ["dominicaanse republiek"]),
    "GD": ("GRD", "Grenada", "Grenada", []),
    "GY": ("GUY", "Guyana", "Guyana", []),
    "JM": ("JAM", "Jamaica", "Jamaica", []),
    "KN": ("KNA", "Saint Kitts en Nevis", "Saint Kitts and Nevis", ["saint kitts", "st. kitts"]),
    "LC": ("LCA", "Saint Lucia", "Saint Lucia", ["st. lucia"]),
    "VC": ("VCT", "Saint Vincent en de Grenadines", "Saint Vincent and the Grenadines", ["saint vincent"]),
    "SR": ("SUR", "Suriname", "Suriname", []),
    "TT": ("TTO", "Trinidad en Tobago", "Trinidad and Tobago", ["trinidad"]),
    # Pacific
    "FJ": ("FJI", "Fiji", "Fiji", []),
    "WS": ("WSM", "Samoa", "Samoa", []),
    "PG": ("PNG", "Papoea-Nieuw-Guinea", "Papua New Guinea", ["png", "papoea nieuw guinea"]),
    "SB": ("SLB", "Salomonseilanden", "Solomon Islands", ["solomon islands"]),
    # Asia
    "KR": ("KOR", "Zuid-Korea", "South Korea", ["korea", "republic of korea", "zuid korea", "south korea"]),
    "JP": ("JPN", "Japan", "Japan", []),
    "SG": ("SGP", "Singapore", "Singapore", []),
    "VN": ("VNM", "Vietnam", "Vietnam", []),
    # Oceania
    "NZ": ("NZL", "Nieuw-Zeeland", "New Zealand", ["nieuw zeeland", "new zealand"]),
    # Other / customs union
    "SM": ("SMR", "San Marino", "San Marino", []),
    # Non-preferential common destinations
    "CN": ("CHN", "China", "China", []),
    "RU": ("RUS", "Rusland", "Russia", ["russian federation"]),
    "BY": ("BLR", "Wit-Rusland", "Belarus", ["belarus", "wit rusland"]),
    "AU": ("AUS", "Australië", "Australia", ["australia", "australie"]),
    "IN": ("IND", "India", "India", []),
    "ID": ("IDN", "Indonesië", "Indonesia", ["indonesie", "indonesia"]),
    "PH": ("PHL", "Filipijnen", "Philippines", ["philippines", "philippinen"]),
    "TH": ("THA", "Thailand", "Thailand", []),
    "MY": ("MYS", "Maleisië", "Malaysia", ["maleisie", "malaysia"]),
    "AE": ("ARE", "Verenigde Arabische Emiraten", "United Arab Emirates", ["uae", "vae", "emiraten"]),
    "SA": ("SAU", "Saoedi-Arabië", "Saudi Arabia", ["saoedi arabie", "saudi arabia"]),
    "TW": ("TWN", "Taiwan", "Taiwan", []),
    "HK": ("HKG", "Hongkong", "Hong Kong", ["hong kong"]),
    "PK": ("PAK", "Pakistan", "Pakistan", []),
    "BD": ("BGD", "Bangladesh", "Bangladesh", []),
    "LK": ("LKA", "Sri Lanka", "Sri Lanka", []),
    "NG": ("NGA", "Nigeria", "Nigeria", []),
    "ET": ("ETH", "Ethiopië", "Ethiopia", ["ethiopia", "ethiopie"]),
    "TZ": ("TZA", "Tanzania", "Tanzania", []),
    "UG": ("UGA", "Oeganda", "Uganda", ["uganda"]),
    "AO": ("AGO", "Angola", "Angola", []),
    "CD": ("COD", "Congo (DRC)", "DR Congo", ["drc", "kongo", "congo-kinshasa", "democratic republic of congo"]),
    "CG": ("COG", "Congo (Brazzaville)", "Republic of the Congo", ["congo-brazzaville"]),
    "BO": ("BOL", "Bolivia", "Bolivia", []),
    "VE": ("VEN", "Venezuela", "Venezuela", []),
}

# EU-lidstaten — wel herkennen, maar geen export-akkoord (intra-Unie verkeer)
EU_MEMBER_STATES: dict[str, tuple[str, str, str, list[str]]] = {
    "AT": ("AUT", "Oostenrijk", "Austria", ["austria", "oostenrijk"]),
    "BE": ("BEL", "België", "Belgium", ["belgie", "belgium"]),
    "BG": ("BGR", "Bulgarije", "Bulgaria", ["bulgaria"]),
    "HR": ("HRV", "Kroatië", "Croatia", ["kroatie", "croatia"]),
    "CY": ("CYP", "Cyprus", "Cyprus", []),
    "CZ": ("CZE", "Tsjechië", "Czechia", ["tsjechie", "czech republic"]),
    "DK": ("DNK", "Denemarken", "Denmark", ["denmark"]),
    "EE": ("EST", "Estland", "Estonia", ["estonia"]),
    "FI": ("FIN", "Finland", "Finland", []),
    "FR": ("FRA", "Frankrijk", "France", ["france", "frankrijk"]),
    "DE": ("DEU", "Duitsland", "Germany", ["germany", "deutschland"]),
    "GR": ("GRC", "Griekenland", "Greece", ["greece", "hellas"]),
    "HU": ("HUN", "Hongarije", "Hungary", ["hungary"]),
    "IE": ("IRL", "Ierland", "Ireland", ["ireland"]),
    "IT": ("ITA", "Italië", "Italy", ["italy", "italie"]),
    "LV": ("LVA", "Letland", "Latvia", ["latvia"]),
    "LT": ("LTU", "Litouwen", "Lithuania", ["lithuania"]),
    "LU": ("LUX", "Luxemburg", "Luxembourg", ["luxembourg"]),
    "MT": ("MLT", "Malta", "Malta", []),
    "NL": ("NLD", "Nederland", "Netherlands", ["netherlands", "holland"]),
    "PL": ("POL", "Polen", "Poland", ["poland"]),
    "PT": ("PRT", "Portugal", "Portugal", []),
    "RO": ("ROU", "Roemenië", "Romania", ["romania", "roemenie"]),
    "SK": ("SVK", "Slowakije", "Slovakia", ["slovakia"]),
    "SI": ("SVN", "Slovenië", "Slovenia", ["slovenia", "slovenie"]),
    "ES": ("ESP", "Spanje", "Spain", ["spain"]),
    "SE": ("SWE", "Zweden", "Sweden", ["sweden"]),
}


def _normalize(s: str) -> str:
    """Normaliseer string voor vergelijking: lowercase, geen accenten, geen leestekens."""
    s = s.strip().lower()
    # Strip accents
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    # Collapse whitespace and punctuation
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


# Bouw lookup-index eenmalig
_LOOKUP: dict[str, str] = {}  # normalized → iso2
_ALL_NAMES: list[str] = []  # voor fuzzy matching
_EU_MEMBERS_ISO2: set[str] = set()

for iso2, (iso3, name_nl, name_en, aliases) in COUNTRIES.items():
    _LOOKUP[iso2.lower()] = iso2
    _LOOKUP[iso3.lower()] = iso2
    _LOOKUP[_normalize(name_nl)] = iso2
    _LOOKUP[_normalize(name_en)] = iso2
    _ALL_NAMES.extend([name_nl, name_en])
    for alias in aliases:
        _LOOKUP[_normalize(alias)] = iso2

for iso2, (iso3, name_nl, name_en, aliases) in EU_MEMBER_STATES.items():
    _LOOKUP[iso2.lower()] = iso2
    _LOOKUP[iso3.lower()] = iso2
    _LOOKUP[_normalize(name_nl)] = iso2
    _LOOKUP[_normalize(name_en)] = iso2
    _ALL_NAMES.extend([name_nl, name_en])
    for alias in aliases:
        _LOOKUP[_normalize(alias)] = iso2
    _EU_MEMBERS_ISO2.add(iso2)
    # Voeg EU-info ook toe aan COUNTRIES voor uniforme lookup van naam
    COUNTRIES[iso2] = (iso3, name_nl, name_en, aliases)


def is_eu_member(iso2: str) -> bool:
    """True als het land een EU-lidstaat is (intra-Unie verkeer, geen export-akkoord)."""
    return iso2.upper() in _EU_MEMBERS_ISO2


def resolve_country(user_input: str) -> CountryMatch:
    """Resolve vrije tekst naar een ISO-2 country code.

    Probeert in volgorde:
        1. ISO-2 exact (US, JP)
        2. ISO-3 exact (USA, JPN)
        3. Naam NL/EN/alias exact (genormaliseerd)
        4. Fuzzy match op alle namen (close match, threshold 0.7)

    Returns:
        CountryMatch met iso2 + match-methode + suggesties bij geen exacte match
    """
    if not user_input or not user_input.strip():
        return CountryMatch(iso2=None, name_nl=None, matched=False, method="none", suggestions=[])

    raw = user_input.strip()

    # 1+2+3: directe lookup op genormaliseerde key
    normalized = _normalize(raw)
    if normalized in _LOOKUP:
        iso2 = _LOOKUP[normalized]
        # Bepaal of het exact ISO-2, ISO-3 of naam was
        method = "exact"
        if len(raw) == 2 and raw.upper() == iso2:
            method = "iso2"
        elif len(raw) == 3 and raw.upper() == COUNTRIES[iso2][0]:
            method = "iso3"
        elif normalized == _normalize(COUNTRIES[iso2][1]) or normalized == _normalize(COUNTRIES[iso2][2]):
            method = "exact"
        else:
            method = "alias"
        return CountryMatch(
            iso2=iso2,
            name_nl=COUNTRIES[iso2][1],
            matched=True,
            method=method,
            suggestions=[],
        )

    # 4: fuzzy match op alle namen
    fuzzy = get_close_matches(raw, _ALL_NAMES, n=5, cutoff=0.6)
    if fuzzy:
        # Als de eerste match heel sterk is (>0.85), neem hem
        from difflib import SequenceMatcher

        best_ratio = SequenceMatcher(None, raw.lower(), fuzzy[0].lower()).ratio()
        if best_ratio > 0.85:
            iso2 = _LOOKUP[_normalize(fuzzy[0])]
            return CountryMatch(
                iso2=iso2,
                name_nl=COUNTRIES[iso2][1],
                matched=True,
                method="fuzzy",
                suggestions=[],
            )
        # Anders alleen suggesties
        return CountryMatch(
            iso2=None,
            name_nl=None,
            matched=False,
            method="none",
            suggestions=fuzzy[:3],
        )

    # 5: prefix-match fallback (voor partial typing zoals "verenigd" of "zuid")
    prefix_matches = [
        name for name in _ALL_NAMES if _normalize(name).startswith(normalized)
    ]
    if prefix_matches:
        return CountryMatch(
            iso2=None,
            name_nl=None,
            matched=False,
            method="none",
            suggestions=prefix_matches[:5],
        )

    return CountryMatch(iso2=None, name_nl=None, matched=False, method="none", suggestions=[])


def display_name(iso2: str) -> str:
    """Geef de NL-naam voor een ISO-2 code, of de code zelf als niet gevonden."""
    info = COUNTRIES.get(iso2.upper())
    return info[1] if info else iso2.upper()


def all_countries_for_dropdown(include_eu: bool = False) -> list[tuple[str, str]]:
    """Lijst voor selectbox: [(display_label, iso2), ...], alfabetisch.

    Default: enkel niet-EU bestemmingen (export-context).
    """
    items = []
    for iso2, (_, name_nl, _, _) in COUNTRIES.items():
        if not include_eu and iso2 in _EU_MEMBERS_ISO2:
            continue
        items.append((f"{name_nl} ({iso2})", iso2))
    return sorted(items, key=lambda x: x[0])
