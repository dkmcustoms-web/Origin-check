"""
DKM Origin Validator (v2)
=========================

Validation library voor preferentiële oorsprong in export- én import-aangiften.

Gebouwd op basis van het AADA-overzicht "OEO – D.D 15.316 – Overzicht van
Preferentiële Overeenkomsten en Douane-Unies" (bijwerking 30 april 2026).

v2-wijzigingen t.o.v. v1:
- Datamodel splitst per akkoord een `export` (EU → bestemmingsland) en
  `import` (bestemmingsland → EU) sectie. Voor moderne FTAs (CETA, JP-EPA,
  EU-SG, EU-VN, EU-NZ, EU-Chili, TCA, Mercosur) verschillen die.
- `validate_proof()` heeft nu een `direction` parameter ("export" of "import").
- TARIC-codes zijn per akkoord+richting, niet meer globaal. Enkel ingevuld
  waar met zekerheid bekend; anders enkel naam.

Voorbeeld:
    from dkm_origin import OriginValidator

    v = OriginValidator()
    result = v.validate_proof(
        destination_country="Canada",
        proof_type="INVOICE_DECLARATION",
        direction="export",
        value_eur=15000,
    )
    # → PROOF_NOT_ACCEPTED: voor EU→CA is enkel REX-attest geldig
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from .countries import resolve_country, display_name, is_eu_member, CountryMatch


DATA_PATH = Path(__file__).parent.parent / "data" / "preferential_agreements.json"

Direction = Literal["export", "import"]

# Mapping van TARIC document codes naar interne proof type IDs.
# Enkel codes die we met zekerheid kennen.
TARIC_CODE_TO_PROOF = {
    "N865": "EUR1",
    "N954": "EUR_MED",
    "N864": "INVOICE_DECLARATION",
    "N953": "INVOICE_DECLARATION_EUR_MED",
    "N018": "ATR",
    "U045": "STATEMENT_OF_ORIGIN_REX",
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
    direction: Direction | None = None
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
            "direction": self.direction,
            "proof_type": self.proof_type,
            "agreement_id": self.agreement_id,
            "details": self.details,
        }


class OriginValidator:
    """Validator voor preferentiële oorsprongsbewijzen, schema v2."""

    def __init__(self, data_path: Path | str | None = None) -> None:
        path = Path(data_path) if data_path else DATA_PATH
        with open(path, "r", encoding="utf-8") as f:
            self._data = json.load(f)
        self._build_indexes()

    def _build_indexes(self) -> None:
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

        # GSP countries (special — bewaar de lijst voor lookups)
        gsp = self.agreements_by_id.get("GSP")
        if gsp:
            categories = gsp.get("gsp_categories")
            if categories:
                for category, codes in categories.items():
                    for code in codes:
                        if code.upper() not in self.agreements_by_country:
                            self.agreements_by_country.setdefault(code.upper(), []).append(gsp)

        self.proof_type_registry: dict[str, dict] = self._data.get("proof_type_registry", {})

    # -------------------------------------------------------------------
    # Lookup API
    # -------------------------------------------------------------------

    def get_agreements_for(self, country: str) -> list[dict]:
        """Alle overeenkomsten van toepassing voor een bestemmingsland."""
        match = resolve_country(country)
        if not match.matched:
            return []
        return self.agreements_by_country.get(match.iso2, [])

    def has_preferential_agreement(self, country: str) -> bool:
        return bool(self.get_agreements_for(country))

    def list_destinations(self) -> list[str]:
        return sorted(self.agreements_by_country.keys())

    def get_proof_type_info(self, proof_type: str) -> dict | None:
        return self.proof_type_registry.get(proof_type)

    def resolve_proof_from_taric(self, taric_code: str) -> str | None:
        return TARIC_CODE_TO_PROOF.get(taric_code.upper())

    def get_proofs_for_direction(self, agreement: dict, direction: Direction) -> list[dict]:
        """Geeft de lijst van toegestane bewijs-types voor een richting."""
        section = agreement.get(direction, {})
        return section.get("proof_types", [])

    # -------------------------------------------------------------------
    # Validation API
    # -------------------------------------------------------------------

    def validate_proof(
        self,
        destination_country: str,
        proof_type: str,
        direction: Direction = "export",
        value_eur: float | None = None,
        agreement_id: str | None = None,
        authorised_exporter: bool = False,
        rex_number: str | None = None,
        local_exporter_id: str | None = None,
    ) -> ValidationResult:
        """Valideert of een oorsprongsbewijs aanvaardbaar is.

        Args:
            destination_country: ISO-2 / ISO-3 / NL-naam / EN-naam / alias
            proof_type: interne proof type key OF TARIC document code
            direction: "export" (EU → land) of "import" (land → EU)
            value_eur: zending-waarde voor drempel-checks
            agreement_id: optioneel — bij meerdere akkoorden voor één land
            authorised_exporter: heeft de exporteur een vergunning?
            rex_number: REX-registratienummer (indien aanwezig)
            local_exporter_id: lokaal exporteur-nummer (Canadees BN, JP Corporate Nr, etc.)
        """
        if direction not in ("export", "import"):
            return ValidationResult(
                valid=False, severity=Severity.ERROR, code="INVALID_DIRECTION",
                message=f"direction moet 'export' of 'import' zijn, niet {direction!r}",
                direction=direction,
            )

        # Stap 0: land resolven
        match = resolve_country(destination_country)
        if not match.matched:
            sugg = f" Bedoelde je: {', '.join(match.suggestions)}?" if match.suggestions else ""
            return ValidationResult(
                valid=False, severity=Severity.ERROR, code="UNKNOWN_COUNTRY",
                message=f"Bestemmingsland {destination_country!r} niet herkend.{sugg}",
                destination=destination_country, direction=direction, proof_type=proof_type,
                details={"suggestions": match.suggestions},
            )
        dest = match.iso2

        if is_eu_member(dest):
            return ValidationResult(
                valid=False, severity=Severity.ERROR, code="EU_INTRA",
                message=(
                    f"{match.name_nl} ({dest}) is een EU-lidstaat — dit is intra-Unie "
                    f"verkeer. Preferentiële oorsprongsbewijzen zijn niet van toepassing."
                ),
                destination=dest, direction=direction, proof_type=proof_type,
            )

        # Stap 1: TARIC code → interne proof type
        original_proof = proof_type
        if proof_type.upper() in TARIC_CODE_TO_PROOF:
            proof_type = TARIC_CODE_TO_PROOF[proof_type.upper()]

        if proof_type not in self.proof_type_registry:
            return ValidationResult(
                valid=False, severity=Severity.ERROR, code="UNKNOWN_PROOF_TYPE",
                message=f"Onbekend oorsprongsbewijs-type: {original_proof!r}",
                destination=dest, direction=direction, proof_type=proof_type,
            )

        # Stap 2: heeft land een akkoord?
        agreements = self.agreements_by_country.get(dest, [])
        if not agreements:
            return ValidationResult(
                valid=False, severity=Severity.ERROR, code="NO_AGREEMENT",
                message=(
                    f"Geen preferentiële overeenkomst tussen EU en {match.name_nl} ({dest}). "
                    f"Oorsprongsbewijs {proof_type!r} is hier niet van toepassing. "
                    f"Eventueel kan een niet-preferentieel certificaat van oorsprong "
                    f"(KvK) nodig zijn."
                ),
                destination=dest, direction=direction, proof_type=proof_type,
            )

        # Stap 3: kies akkoord
        if agreement_id:
            chosen = self.agreements_by_id.get(agreement_id)
            if not chosen or chosen not in agreements:
                return ValidationResult(
                    valid=False, severity=Severity.ERROR, code="AGREEMENT_NOT_APPLICABLE",
                    message=f"Overeenkomst {agreement_id!r} niet van toepassing voor {dest}",
                    destination=dest, direction=direction,
                )
        else:
            candidates = [
                a for a in agreements
                if any(p["id"] == proof_type for p in self.get_proofs_for_direction(a, direction))
            ]
            if not candidates:
                candidates = agreements
            specific = [a for a in candidates if isinstance(a.get("country_iso"), str)]
            if len(specific) == 1:
                chosen = specific[0]
            elif len(candidates) == 1:
                chosen = candidates[0]
            else:
                return ValidationResult(
                    valid=False, severity=Severity.WARNING, code="MULTIPLE_AGREEMENTS",
                    message=(
                        f"Meerdere overeenkomsten voor {dest}: "
                        f"{[a['id'] for a in candidates]}. Specificeer agreement_id."
                    ),
                    destination=dest, direction=direction, proof_type=proof_type,
                    details={"agreements": [a["id"] for a in candidates]},
                )

        # Stap 4: is het bewijs aanvaard voor deze richting?
        section_proofs = self.get_proofs_for_direction(chosen, direction)
        if not section_proofs:
            return ValidationResult(
                valid=False, severity=Severity.ERROR, code="NO_PROOFS_FOR_DIRECTION",
                message=(
                    f"Geen preferentiële oorsprongsbewijzen voorzien voor richting "
                    f"{direction!r} onder akkoord {chosen['id']} ({chosen['country_name_nl']}). "
                    f"Bijvoorbeeld GSP is eenzijdig (enkel import in EU)."
                ),
                destination=dest, direction=direction, agreement_id=chosen["id"],
            )

        matching = [p for p in section_proofs if p["id"] == proof_type]
        if not matching:
            accepted = [p["id"] for p in section_proofs]
            return ValidationResult(
                valid=False, severity=Severity.ERROR, code="PROOF_NOT_ACCEPTED",
                message=(
                    f"Bewijs {proof_type!r} is NIET aanvaard voor {direction} "
                    f"onder akkoord {chosen['id']} ({chosen['country_name_nl']}). "
                    f"Aanvaard: {accepted}"
                ),
                destination=dest, direction=direction, proof_type=proof_type,
                agreement_id=chosen["id"],
                details={"accepted_proof_types": accepted},
            )
        proof_def = matching[0]

        # Stap 5: drempel- en vereisten-check
        threshold = proof_def.get("threshold_eur")
        requires = proof_def.get("requires_above_threshold")

        if value_eur is not None and threshold and value_eur > threshold:
            if requires == "authorised_exporter" and not authorised_exporter:
                return ValidationResult(
                    valid=False, severity=Severity.ERROR, code="AUTHORISED_EXPORTER_REQUIRED",
                    message=(
                        f"{proof_def['name']} boven {threshold} EUR vereist een vergunning "
                        f"toegelaten exporteur. Zending: {value_eur} EUR."
                    ),
                    destination=dest, direction=direction, proof_type=proof_type,
                    agreement_id=chosen["id"],
                )
            if requires == "rex_number" and not rex_number:
                return ValidationResult(
                    valid=False, severity=Severity.ERROR, code="REX_REQUIRED",
                    message=(
                        f"{proof_def['name']} boven {threshold} EUR vereist een REX-nummer. "
                        f"Zending: {value_eur} EUR."
                    ),
                    destination=dest, direction=direction, proof_type=proof_type,
                    agreement_id=chosen["id"],
                )
            if requires == "local_exporter_id" and not local_exporter_id:
                return ValidationResult(
                    valid=False, severity=Severity.ERROR, code="LOCAL_EXPORTER_ID_REQUIRED",
                    message=(
                        f"{proof_def['name']} vereist een lokaal exporteur-nummer "
                        f"(bv. {proof_def.get('note', 'lokaal registratienummer')})."
                    ),
                    destination=dest, direction=direction, proof_type=proof_type,
                    agreement_id=chosen["id"],
                )

        # Speciale check: Ghanese REX-nummers (mogen NIET)
        if chosen["id"] == "GH" and rex_number and rex_number.upper().startswith("GHREX"):
            return ValidationResult(
                valid=False, severity=Severity.ERROR, code="WRONG_REX_FORMAT",
                message=(
                    "Ghanese REX-nummers (GHREX...) zijn NIET toegestaan. "
                    "Ghana is geen SAP-land; gebruik een Ghanees registratienummer."
                ),
                destination=dest, direction=direction, proof_type=proof_type,
                agreement_id=chosen["id"],
            )

        # Stap 6: success — toon waarschuwingen waar van toepassing
        warnings: list[str] = []
        if chosen.get("special_marking"):
            warnings.append(f"Bijzondere vermelding: {chosen['special_marking']}")
        if chosen.get("in_force_status") == "provisional":
            warnings.append("Akkoord is in voorlopige toepassing — verifieer via TARBEL.")
        if proof_def.get("note"):
            warnings.append(proof_def["note"])

        direction_label = "EU → " + match.name_nl if direction == "export" else match.name_nl + " → EU"

        if warnings:
            return ValidationResult(
                valid=True, severity=Severity.WARNING, code="OK_WITH_WARNINGS",
                message=f"Geldig voor {direction_label} onder akkoord {chosen['id']}. Let op: " + " | ".join(warnings),
                destination=dest, direction=direction, proof_type=proof_type,
                agreement_id=chosen["id"],
                details={"warnings": warnings, "agreement": chosen, "proof_def": proof_def},
            )

        return ValidationResult(
            valid=True, severity=Severity.OK, code="OK",
            message=(
                f"{proof_def['name']} is geldig voor {direction_label} "
                f"onder akkoord {chosen['id']}."
            ),
            destination=dest, direction=direction, proof_type=proof_type,
            agreement_id=chosen["id"],
            details={"agreement": chosen, "proof_def": proof_def},
        )

    # -------------------------------------------------------------------
    # Q&A helpers
    # -------------------------------------------------------------------

    def summarise_for_destination(self, country: str, direction: Direction | None = None) -> str:
        """Tekst-samenvatting voor een bestemmingsland.

        Als direction is opgegeven, alleen die richting; anders beide.
        """
        match = resolve_country(country)
        if not match.matched:
            hint = f" Bedoelde je: {', '.join(match.suggestions)}?" if match.suggestions else ""
            return f"Bestemmingsland {country!r} niet herkend.{hint}"
        if is_eu_member(match.iso2):
            return f"{match.name_nl} ({match.iso2}) is een EU-lidstaat (intra-Unie)."
        agreements = self.agreements_by_country.get(match.iso2, [])
        if not agreements:
            return (
                f"Geen preferentiële overeenkomst tussen EU en {match.name_nl} ({match.iso2}). "
                f"Niet-preferentieel CvO (KvK) eventueel mogelijk."
            )

        directions = [direction] if direction else ["export", "import"]
        parts: list[str] = []
        for a in agreements:
            for d in directions:
                proofs = self.get_proofs_for_direction(a, d)
                if not proofs:
                    continue
                d_label = "EU → " + match.name_nl if d == "export" else match.name_nl + " → EU"
                proof_strs = []
                for p in proofs:
                    s = p["name"]
                    if p.get("taric_code"):
                        s += f" (TARIC {p['taric_code']})"
                    if p.get("threshold_eur"):
                        s += f" — drempel {p['threshold_eur']} EUR"
                    if p.get("requires_above_threshold"):
                        s += f", vereist {p['requires_above_threshold']}"
                    proof_strs.append(s)
                parts.append(f"  {d_label} (akkoord {a['id']}): " + " | ".join(proof_strs))
        return "\n".join(parts)
