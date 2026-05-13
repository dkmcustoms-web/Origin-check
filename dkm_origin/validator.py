"""
DKM Origin Validator
====================

Validation library voor preferentiële oorsprong in export-aangiften.

Gebouwd op basis van het AADA-overzicht "OEO – D.D 15.316 – Overzicht van
Preferentiële Overeenkomsten en Douane-Unies" (bijwerking 30 april 2026).

Use cases:
    - Q&A over oorsprongsregels per bestemmingsland
    - Validatie van oorsprongsbewijzen in export-aangiften
      (bv. is REX-nummer aanvaardbaar voor bestemming X?)
    - Integratie in dkm-customs-utils en export declaration check

Voorbeeld:
    from dkm_origin import OriginValidator

    v = OriginValidator()
    result = v.validate_proof(
        destination_country="US",
        proof_type="STATEMENT_OF_ORIGIN_REX",
        value_eur=15000,
    )
    if not result.valid:
        print(result.message)
        # → "Geen preferentiële overeenkomst tussen EU en US (Verenigde Staten).
        #    REX-nummer is hier niet van toepassing."
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


from .countries import resolve_country, display_name, is_eu_member, CountryMatch


DATA_PATH = Path(__file__).parent.parent / "data" / "preferential_agreements.json"

# Mapping van TARIC document codes naar interne proof type IDs.
# Te gebruiken om vanuit een EUCDM-aangifte direct te valideren.
TARIC_CODE_TO_PROOF = {
    "N865": "EUR1",
    "N954": "EUR_MED",
    "N864": "INVOICE_DECLARATION",
    "N953": "INVOICE_DECLARATION_EUR_MED",
    "U165": "STATEMENT_OF_ORIGIN_REX",
    "N018": "ATR",
    # Alias - some systems use C100 historically for EUR.1
    "C100": "EUR1",
}


class Severity(str, Enum):
    OK = "ok"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class ValidationResult:
    """Resultaat van een validatie."""

    valid: bool
    severity: Severity
    code: str
    message: str
    destination: str | None = None
    proof_type: str | None = None
    agreement_id: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "severity": self.severity.value,
            "code": self.code,
            "message": self.message,
            "destination": self.destination,
            "proof_type": self.proof_type,
            "agreement_id": self.agreement_id,
            "details": self.details,
        }


class OriginValidator:
    """Validator voor preferentiële oorsprongsbewijzen.

    Initialiseert in O(1) door data eenmalig in te laden uit JSON.
    Thread-safe voor lezen.
    """

    def __init__(self, data_path: Path | str | None = None) -> None:
        path = Path(data_path) if data_path else DATA_PATH
        with open(path, "r", encoding="utf-8") as f:
            self._data = json.load(f)
        self._build_indexes()

    def _build_indexes(self) -> None:
        """Bouwt lookup-indexen voor snelle queries."""
        self.agreements_by_id: dict[str, dict] = {}
        self.agreements_by_country: dict[str, list[dict]] = {}

        for agr in self._data["agreements"]:
            self.agreements_by_id[agr["id"]] = agr
            iso = agr.get("country_iso")
            if iso is None:
                continue
            iso_codes = iso if isinstance(iso, list) else [iso]
            for code in iso_codes:
                self.agreements_by_country.setdefault(code.upper(), []).append(agr)

        # GSP countries (special — flat in metadata)
        gsp = self.agreements_by_id.get("GSP")
        if gsp:
            for category, codes in gsp.get("gsp_categories", {}).items():
                for code in codes:
                    if code.upper() not in self.agreements_by_country:
                        self.agreements_by_country.setdefault(code.upper(), []).append(gsp)

        self.proof_types: dict[str, dict] = self._data["proof_types"]

    # -------------------------------------------------------------------
    # Lookup API
    # -------------------------------------------------------------------

    def get_agreements_for(self, country: str) -> list[dict]:
        """Alle overeenkomsten van toepassing voor een bestemmingsland.

        Accepteert ISO-2, ISO-3, NL/EN naam of alias.
        """
        match = resolve_country(country)
        if not match.matched:
            return []
        return self.agreements_by_country.get(match.iso2, [])

    def has_preferential_agreement(self, country: str) -> bool:
        return bool(self.get_agreements_for(country))

    def list_destinations(self) -> list[str]:
        return sorted(self.agreements_by_country.keys())

    def get_proof_type_info(self, proof_type: str) -> dict | None:
        """Info over een oorsprongsbewijs-type (zoals EUR.1 of REX-attest)."""
        return self.proof_types.get(proof_type)

    def resolve_proof_from_taric(self, taric_code: str) -> str | None:
        """Vertaalt een TARIC document-code naar een interne proof type."""
        return TARIC_CODE_TO_PROOF.get(taric_code.upper())

    # -------------------------------------------------------------------
    # Validation API
    # -------------------------------------------------------------------

    def validate_proof(
        self,
        destination_country: str,
        proof_type: str,
        value_eur: float | None = None,
        agreement_id: str | None = None,
        authorised_exporter: bool = False,
        rex_number: str | None = None,
    ) -> ValidationResult:
        """Valideert of een oorsprongsbewijs aanvaardbaar is voor de bestemming.

        Args:
            destination_country: ISO-2 code OF landnaam OF alias
                                 (bv. "US", "USA", "Verenigde Staten", "VS")
            proof_type: interne proof type key OF TARIC document code
            value_eur: zending-waarde in EUR (voor REX-drempel / 6.000 EUR check)
            agreement_id: optioneel — kies specifieke overeenkomst bij meerdere
                          (bv. TR_EGKS vs TR_AGRI vs TR_CU)
            authorised_exporter: heeft de exporteur een toegelaten-exporteur vergunning?
            rex_number: indien proof_type een REX-variant is, het opgegeven REX-nummer

        Returns:
            ValidationResult met severity OK/WARNING/ERROR + uitleg
        """
        # Stap 0: resolve het bestemmingsland (accepteert ISO-2, ISO-3, NL/EN naam, aliassen)
        match = resolve_country(destination_country)
        if not match.matched:
            suggestion_text = ""
            if match.suggestions:
                suggestion_text = f" Bedoelde je: {', '.join(match.suggestions)}?"
            return ValidationResult(
                valid=False,
                severity=Severity.ERROR,
                code="UNKNOWN_COUNTRY",
                message=f"Bestemmingsland {destination_country!r} niet herkend.{suggestion_text}",
                destination=destination_country,
                proof_type=proof_type,
                details={"suggestions": match.suggestions},
            )
        dest = match.iso2

        # Stap 0b: EU-lidstaat? Dan is een preferentieel oorsprongsbewijs niet relevant.
        if is_eu_member(dest):
            return ValidationResult(
                valid=False,
                severity=Severity.ERROR,
                code="EU_INTRA",
                message=(
                    f"{match.name_nl} ({dest}) is een EU-lidstaat — dit is intra-Unie "
                    f"verkeer en geen export. Preferentiële oorsprongsbewijzen zijn hier "
                    f"niet van toepassing."
                ),
                destination=dest,
                proof_type=proof_type,
            )

        # Stap 1: vertaal eventuele TARIC code
        if proof_type.upper() in TARIC_CODE_TO_PROOF:
            proof_type = TARIC_CODE_TO_PROOF[proof_type.upper()]

        if proof_type not in self.proof_types:
            return ValidationResult(
                valid=False,
                severity=Severity.ERROR,
                code="UNKNOWN_PROOF_TYPE",
                message=f"Onbekend oorsprongsbewijs-type: {proof_type!r}",
                destination=dest,
                proof_type=proof_type,
            )

        # Stap 2: heeft de bestemming een preferentiële overeenkomst?
        agreements = self.agreements_by_country.get(dest, [])
        if not agreements:
            return ValidationResult(
                valid=False,
                severity=Severity.ERROR,
                code="NO_AGREEMENT",
                message=(
                    f"Geen preferentiële overeenkomst tussen EU en {match.name_nl} ({dest}). "
                    f"Oorsprongsbewijs {proof_type!r} is hier niet van toepassing. "
                    f"Eventueel kan een niet-preferentieel certificaat van oorsprong "
                    f"(KvK) nodig zijn voor de bestemming."
                ),
                destination=dest,
                proof_type=proof_type,
            )

        # Stap 3: kies overeenkomst (bij meerdere)
        if agreement_id:
            chosen = self.agreements_by_id.get(agreement_id)
            if not chosen or chosen not in agreements:
                return ValidationResult(
                    valid=False,
                    severity=Severity.ERROR,
                    code="AGREEMENT_NOT_APPLICABLE",
                    message=f"Overeenkomst {agreement_id!r} niet van toepassing voor {dest}",
                    destination=dest,
                )
        else:
            # Filter: alleen overeenkomsten die het opgegeven proof_type accepteren
            candidates = [a for a in agreements if proof_type in a.get("proof_types", [])]
            if not candidates:
                # Geen overeenkomst accepteert dit proof - return PROOF_NOT_ACCEPTED
                # via de generieke fallback hieronder
                candidates = agreements

            # Voorkeur: specifieke (single-country) overeenkomst boven regio-groep
            specific = [a for a in candidates if isinstance(a.get("country_iso"), str)]
            if len(specific) == 1:
                chosen = specific[0]
            elif len(candidates) == 1:
                chosen = candidates[0]
            else:
                # Echt meerdere, gebruiker moet kiezen
                return ValidationResult(
                    valid=False,
                    severity=Severity.WARNING,
                    code="MULTIPLE_AGREEMENTS",
                    message=(
                        f"Meerdere overeenkomsten gevonden voor {dest}: "
                        f"{[a['id'] for a in candidates]}. "
                        f"Specificeer agreement_id (bv. voor Turkije: TR_CU voor douane-unie, "
                        f"TR_EGKS voor staalproducten, TR_AGRI voor landbouw)."
                    ),
                    destination=dest,
                    proof_type=proof_type,
                    details={"agreements": [a["id"] for a in candidates]},
                )

        # Stap 4: is het opgegeven proof_type aanvaardbaar binnen die overeenkomst?
        valid_proofs = chosen.get("proof_types", [])
        if proof_type not in valid_proofs:
            return ValidationResult(
                valid=False,
                severity=Severity.ERROR,
                code="PROOF_NOT_ACCEPTED",
                message=(
                    f"Oorsprongsbewijs {proof_type!r} is NIET aanvaard onder de "
                    f"overeenkomst met {dest}. Aanvaardbare bewijzen: {valid_proofs}"
                ),
                destination=dest,
                proof_type=proof_type,
                agreement_id=chosen["id"],
                details={"accepted_proof_types": valid_proofs},
            )

        # Stap 5: drempel-waarde / REX / toegelaten exporteur checks
        threshold = self.proof_types[proof_type].get("threshold_eur", 6000)
        # OCT heeft eigen drempel
        if chosen.get("threshold_eur"):
            threshold = chosen["threshold_eur"]

        if proof_type == "INVOICE_DECLARATION":
            if value_eur is not None and value_eur > threshold and not authorised_exporter:
                return ValidationResult(
                    valid=False,
                    severity=Severity.ERROR,
                    code="AUTHORISED_EXPORTER_REQUIRED",
                    message=(
                        f"Oorsprongsverklaring op factuur boven {threshold} EUR "
                        f"vereist een vergunning toegelaten exporteur. "
                        f"Zending-waarde: {value_eur} EUR."
                    ),
                    destination=dest,
                    proof_type=proof_type,
                    agreement_id=chosen["id"],
                )

        if proof_type == "STATEMENT_OF_ORIGIN_REX":
            if value_eur is not None and value_eur > threshold and not rex_number:
                return ValidationResult(
                    valid=False,
                    severity=Severity.ERROR,
                    code="REX_REQUIRED",
                    message=(
                        f"Attest van oorsprong boven {threshold} EUR vereist een "
                        f"REX-registratienummer (geregistreerd exporteurs-systeem). "
                        f"Zending-waarde: {value_eur} EUR."
                    ),
                    destination=dest,
                    proof_type=proof_type,
                    agreement_id=chosen["id"],
                )
            # Speciale gevallen: GH wil GEEN REX van EU, SG/CL/NZ/CA hebben land-specifieke nrs
            if chosen["id"] == "GH" and rex_number and rex_number.upper().startswith("GHREX"):
                return ValidationResult(
                    valid=False,
                    severity=Severity.ERROR,
                    code="WRONG_REX_FORMAT",
                    message=(
                        "Ghanese REX-nummers (GHREX...) mogen NIET gebruikt worden. "
                        "Ghana is geen SAP-land; gebruik Ghanees registratienummer."
                    ),
                    destination=dest,
                    proof_type=proof_type,
                    agreement_id=chosen["id"],
                )

        # Stap 6: success — toon eventuele waarschuwingen / bijzonderheden
        warnings: list[str] = []
        if chosen.get("special_marking"):
            warnings.append(f"Bijzondere vermelding vereist: {chosen['special_marking']}")
        if chosen.get("in_force_status") == "provisional":
            warnings.append("Overeenkomst is in voorlopige toepassing — verifieer dagelijks via TARBEL.")

        if warnings:
            return ValidationResult(
                valid=True,
                severity=Severity.WARNING,
                code="OK_WITH_WARNINGS",
                message=f"Geldig onder overeenkomst {chosen['id']}, maar let op: " + " | ".join(warnings),
                destination=dest,
                proof_type=proof_type,
                agreement_id=chosen["id"],
                details={"warnings": warnings, "agreement": chosen},
            )

        return ValidationResult(
            valid=True,
            severity=Severity.OK,
            code="OK",
            message=(
                f"Oorsprongsbewijs {proof_type} is geldig voor export naar {dest} "
                f"onder overeenkomst {chosen['id']} "
                f"({self.proof_types[proof_type]['name']})."
            ),
            destination=dest,
            proof_type=proof_type,
            agreement_id=chosen["id"],
            details={"agreement": chosen},
        )

    # -------------------------------------------------------------------
    # Q&A helpers (voor LLM grounding / Streamlit)
    # -------------------------------------------------------------------

    def summarise_for_destination(self, country: str) -> str:
        """Tekst-samenvatting voor mens of LLM-context.

        Accepteert ISO-2, ISO-3, NL/EN naam of alias.
        """
        match = resolve_country(country)
        if not match.matched:
            hint = ""
            if match.suggestions:
                hint = f" Bedoelde je: {', '.join(match.suggestions)}?"
            return f"Bestemmingsland {country!r} niet herkend.{hint}"
        agreements = self.agreements_by_country.get(match.iso2, [])
        if not agreements:
            return (
                f"Geen preferentiële overeenkomst tussen EU en {match.name_nl} ({match.iso2}). "
                f"Voor export hierheen geldt enkel een niet-preferentieel certificaat "
                f"van oorsprong (via Kamer van Koophandel), indien gevraagd door de invoerder."
            )
        parts = []
        for a in agreements:
            proofs = a.get("proof_types", [])
            proof_names = [self.proof_types[p]["name"] for p in proofs if p in self.proof_types]
            parts.append(
                f"• {a['country_name_nl']} ({a['id']}): "
                f"oorsprongsbewijzen = {', '.join(proof_names)}; "
                f"geldigheid = {a.get('validity_months', '?')} maanden; "
                f"drawback = {a.get('drawback_allowed', 'n/a')}; "
                f"cumulatie = {a.get('cumulation', [])}; "
                f"PEM-status = {a.get('pem_status', 'n/a')}."
            )
        return "\n".join(parts)
