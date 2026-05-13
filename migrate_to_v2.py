"""
Migratie van het oude JSON-schema naar het nieuwe schema met expliciete
export/import-secties per akkoord.

Aanleiding: de oude `proof_types` lijst was symmetrisch en aggregeerde EU→X
en X→EU, wat voor moderne FTAs (CETA, JP-EPA, etc.) leidde tot foute output.
De PDF heeft expliciet aparte modaliteiten per richting; die brengen we nu
boven naar gestructureerde velden.

TARIC-codes worden enkel ingevuld waar ze met zekerheid bekend zijn:
- N865 = EUR.1
- N864 = oorsprongsverklaring op factuur (PEM-context)
- N954 = EUR-MED
- N953 = oorsprongsverklaring EUR-MED
- N018 = A.TR (Turkije douane-unie)
- U045 = oorsprongsverklaring REX (GSP-context)

Voor moderne FTAs (CETA, JP-EPA, EU-SG, EU-VN, EU-NZ, EU-Chili, TCA,
Mercosur) is er geen eenduidige TARIC-code per akkoord; daar laten we de
code leeg en tonen we enkel de naam.
"""

import json
from pathlib import Path

OLD = Path(__file__).parent / "data" / "preferential_agreements.json"
NEW = Path(__file__).parent / "data" / "preferential_agreements.json"


# Bewijs-types die we hergebruiken (referentie-data)
PROOF_NAMES = {
    "EUR1": "Certificaat inzake goederenverkeer EUR.1",
    "EUR_MED": "Certificaat EUR-MED",
    "INVOICE_DECLARATION": "Oorsprongsverklaring op factuur of ander handelsdocument",
    "INVOICE_DECLARATION_EUR_MED": "Oorsprongsverklaring EUR-MED op factuur",
    "STATEMENT_OF_ORIGIN_REX": "Attest van oorsprong (met REX-nummer)",
    "STATEMENT_OF_ORIGIN_LOCAL": "Attest van oorsprong (met lokaal registratienummer)",
    "STATEMENT_OF_ORIGIN_MERCOSUR_CERT": "Certificaat van oorsprong (Mercosur Bijlage 3-D)",
    "IMPORTERS_KNOWLEDGE": "Aan de importeur bekende informatie (Importer's Knowledge)",
    "ATR": "A.TR certificaat (vrij verkeer, géén oorsprong)",
    "T2_T2L": "T2 / T2L (vrij verkeer binnen douane-unie)",
    "EUR1_CMR": "EUR.1-CMR (Kameroense variant)",
}


# Per akkoord-id: hoe ziet de export-richting (EU → land) en import-richting
# (land → EU) eruit volgens de PDF? Alleen waar het verschilt van een
# symmetrische default of waar bijzonderheden gelden.
#
# Velden: list of {id, taric_code?, threshold_eur?, requires?, note?}
# requires kan zijn: "authorised_exporter", "rex_number", "local_exporter_id"

EXPORT_IMPORT_OVERRIDES: dict[str, dict] = {
    # ── CETA — moderne FTA: REX-attest verplicht in beide richtingen
    "CA": {
        "export": {
            "proof_types": [
                {"id": "STATEMENT_OF_ORIGIN_REX",
                 "threshold_eur": 6000,
                 "requires_above_threshold": "rex_number",
                 "note": "REX-nummer verplicht boven 6.000 EUR"},
            ],
            "notes": ["Drawback niet meer toegestaan vanaf 21/09/2020"],
        },
        "import": {
            "proof_types": [
                {"id": "STATEMENT_OF_ORIGIN_LOCAL",
                 "requires_above_threshold": "local_exporter_id",
                 "note": "Canadees Business Number verplicht, ongeacht waarde"},
            ],
        },
    },
    # ── TCA UK
    "GB": {
        "export": {
            "proof_types": [
                {"id": "STATEMENT_OF_ORIGIN_REX",
                 "threshold_eur": 6000,
                 "requires_above_threshold": "rex_number",
                 "note": "REX-nummer verplicht boven 6.000 EUR"},
            ],
        },
        "import": {
            "proof_types": [
                {"id": "STATEMENT_OF_ORIGIN_LOCAL",
                 "requires_above_threshold": "local_exporter_id",
                 "note": "Brits EORI-nummer (GB...) verplicht ongeacht waarde"},
                {"id": "IMPORTERS_KNOWLEDGE",
                 "note": "Mag ipv attest"},
            ],
        },
    },
    # ── EU-Japan EPA
    "JP": {
        "export": {
            "proof_types": [
                {"id": "STATEMENT_OF_ORIGIN_REX",
                 "threshold_eur": 6000,
                 "requires_above_threshold": "rex_number",
                 "note": "REX-nummer verplicht boven 6.000 EUR"},
            ],
        },
        "import": {
            "proof_types": [
                {"id": "STATEMENT_OF_ORIGIN_LOCAL",
                 "note": "Japans Corporate Number"},
                {"id": "IMPORTERS_KNOWLEDGE",
                 "note": "Mag ipv attest"},
            ],
        },
    },
    # ── EU-Singapore
    "SG": {
        "export": {
            "proof_types": [
                {"id": "STATEMENT_OF_ORIGIN_REX",
                 "threshold_eur": 6000,
                 "requires_above_threshold": "rex_number",
                 "note": "REX-nummer verplicht boven 6.000 EUR (sinds 1/1/2023)"},
            ],
        },
        "import": {
            "proof_types": [
                {"id": "STATEMENT_OF_ORIGIN_LOCAL",
                 "requires_above_threshold": "local_exporter_id",
                 "note": "Unique Entity Number, ongeacht waarde"},
            ],
        },
    },
    # ── EU-Vietnam
    "VN": {
        "export": {
            "proof_types": [
                {"id": "STATEMENT_OF_ORIGIN_REX",
                 "threshold_eur": 6000,
                 "requires_above_threshold": "rex_number",
                 "note": "REX-nummer verplicht boven 6.000 EUR"},
            ],
        },
        "import": {
            "proof_types": [
                {"id": "EUR1", "taric_code": "N865"},
                {"id": "INVOICE_DECLARATION", "taric_code": "N864", "threshold_eur": 6000,
                 "requires_above_threshold": "authorised_exporter"},
            ],
            "notes": ["Vietnam zit niet meer in SAP/GSP sinds 1/1/2023"],
        },
    },
    # ── EU-Nieuw-Zeeland
    "NZ": {
        "export": {
            "proof_types": [
                {"id": "STATEMENT_OF_ORIGIN_REX",
                 "threshold_eur": 6000,
                 "requires_above_threshold": "rex_number",
                 "note": "REX-nummer verplicht boven 6.000 EUR"},
            ],
        },
        "import": {
            "proof_types": [
                {"id": "STATEMENT_OF_ORIGIN_LOCAL",
                 "requires_above_threshold": "local_exporter_id",
                 "note": "NZ Customs Client Code (8 cijfers + 1 letter, bv. 12345678A)"},
                {"id": "IMPORTERS_KNOWLEDGE", "note": "Mag ipv attest"},
            ],
        },
    },
    # ── EU-Chili interim
    "CL": {
        "export": {
            "proof_types": [
                {"id": "STATEMENT_OF_ORIGIN_REX",
                 "threshold_eur": 6000,
                 "requires_above_threshold": "rex_number"},
            ],
        },
        "import": {
            "proof_types": [
                {"id": "STATEMENT_OF_ORIGIN_LOCAL",
                 "requires_above_threshold": "local_exporter_id",
                 "note": "RUT-nummer (Rol Único Tributario), ongeacht waarde"},
            ],
        },
    },
    # ── Mercosur (voorlopige toepassing 1 mei 2026)
    "MERCOSUR": {
        "export": {
            "proof_types": [
                {"id": "STATEMENT_OF_ORIGIN_REX",
                 "threshold_eur": 6000,
                 "requires_above_threshold": "rex_number",
                 "note": "Volgens Bijlage 3-C"},
            ],
        },
        "import": {
            "proof_types": [
                {"id": "STATEMENT_OF_ORIGIN_LOCAL",
                 "note": "Nationaal registratienummer (AR/BR/UY)"},
                {"id": "STATEMENT_OF_ORIGIN_MERCOSUR_CERT",
                 "note": "Volgens Bijlage 3-D (AR/BR/PY/UY)"},
            ],
        },
    },
    # ── OZA (ESA): EU→OZA gebruikt REX-systeem, OZA→EU per land verschillend
    "ESA": {
        "export": {
            "proof_types": [
                {"id": "STATEMENT_OF_ORIGIN_REX",
                 "threshold_eur": 6000,
                 "requires_above_threshold": "rex_number",
                 "note": "REX-nummer verplicht boven 6.000 EUR"},
            ],
        },
        "import": {
            "proof_types": [
                {"id": "EUR1", "taric_code": "N865"},
                {"id": "INVOICE_DECLARATION", "taric_code": "N864", "threshold_eur": 6000,
                 "requires_above_threshold": "authorised_exporter"},
                {"id": "STATEMENT_OF_ORIGIN_REX",
                 "note": "Per land: ZW vanaf 1/7/2021, MG vanaf 1/1/2023, SC vanaf 1/7/2023"},
            ],
        },
    },
    # ── Ghana: EU→GH REX-attest, GH→EU is bijzonder (geen REX, eigen Ghanees nr)
    "GH": {
        "export": {
            "proof_types": [
                {"id": "STATEMENT_OF_ORIGIN_REX",
                 "threshold_eur": 6000,
                 "requires_above_threshold": "rex_number",
                 "note": "REX-nummer verplicht boven 6.000 EUR"},
            ],
        },
        "import": {
            "proof_types": [
                {"id": "STATEMENT_OF_ORIGIN_LOCAL",
                 "note": "Vanaf 20/8/2023: Ghanees registratienummer (GEEN REX). "
                         "EUR.1's en factuurverklaringen NIET meer aanvaard."},
            ],
        },
    },
    # ── Ivoorkust: REX in beide richtingen sinds 2/12/2022
    "CI": {
        "export": {
            "proof_types": [
                {"id": "INVOICE_DECLARATION", "taric_code": "N864", "threshold_eur": 6000,
                 "requires_above_threshold": "rex_number",
                 "note": "REX-nummer verplicht boven 6.000 EUR"},
            ],
        },
        "import": {
            "proof_types": [
                {"id": "INVOICE_DECLARATION", "taric_code": "N864", "threshold_eur": 6000,
                 "note": "REX-nummer verplicht boven 6.000 EUR (sinds 2/12/2022)"},
            ],
        },
    },
    # ── Kameroen (CEMAC): EU→CM gebruikt EUR.1-CMR variant
    "CM": {
        "export": {
            "proof_types": [
                {"id": "EUR1_CMR", "note": "Kameroense variant op EUR.1"},
                {"id": "INVOICE_DECLARATION", "taric_code": "N864", "threshold_eur": 6000,
                 "requires_above_threshold": "authorised_exporter"},
            ],
            "notes": ["Geen cumulatie bij EU-export naar Kameroen"],
        },
        "import": {
            "proof_types": [
                {"id": "EUR1", "taric_code": "N865", "note": "Volgens MAR-ACS"},
                {"id": "INVOICE_DECLARATION", "taric_code": "N864", "threshold_eur": 6000},
            ],
        },
    },
    # ── LGO (OCT): REX-attest met hogere drempel (10.000 EUR)
    "OCT": {
        "export": {
            "proof_types": [
                {"id": "STATEMENT_OF_ORIGIN_REX",
                 "threshold_eur": 10000,
                 "requires_above_threshold": "rex_number",
                 "note": "REX-registratie verplicht boven 10.000 EUR"},
            ],
        },
        "import": {
            "proof_types": [
                {"id": "STATEMENT_OF_ORIGIN_REX",
                 "threshold_eur": 10000,
                 "requires_above_threshold": "rex_number"},
            ],
        },
    },
    # ── GSP/SAP: eenzijdig, alleen X→EU is relevant
    "GSP": {
        "export": {
            "proof_types": [],
            "notes": [
                "SAP/GSP is een EENZIJDIGE preferentie: enkel invoer in EU. "
                "Voor EU-uitvoer naar deze landen gelden geen SAP-preferenties."
            ],
        },
        "import": {
            "proof_types": [
                {"id": "STATEMENT_OF_ORIGIN_REX", "taric_code": "U045",
                 "requires_above_threshold": "rex_number"},
            ],
        },
    },
    # ── Turkije industriële douane-unie: A.TR (geen oorsprong, vrij verkeer)
    "TR_CU": {
        "export": {
            "proof_types": [
                {"id": "ATR", "taric_code": "N018",
                 "note": "A.TR bewijst vrij verkeer, NIET oorsprong"},
            ],
        },
        "import": {
            "proof_types": [
                {"id": "ATR", "taric_code": "N018"},
            ],
        },
    },
    # ── San Marino douane-unie
    "SM": {
        "export": {
            "proof_types": [
                {"id": "T2_T2L", "note": "Geen oorsprongsbewijs vereist; vrij verkeer"},
            ],
        },
        "import": {
            "proof_types": [
                {"id": "T2_T2L"},
            ],
        },
    },
    # ── Andorra industrieel douane-unie
    "AD_INDUSTRIAL": {
        "export": {
            "proof_types": [
                {"id": "T2_T2L", "note": "Geen oorsprongsbewijs vereist; vrij verkeer"},
            ],
        },
        "import": {
            "proof_types": [
                {"id": "T2_T2L"},
            ],
        },
    },
}


def build_proof_entry(proof_id: str, taric_code: str | None = None, **kwargs) -> dict:
    """Bouw een proof-entry met naam + optioneel TARIC-code en extra velden."""
    entry = {
        "id": proof_id,
        "name": PROOF_NAMES.get(proof_id, proof_id),
    }
    if taric_code:
        entry["taric_code"] = taric_code
    entry.update(kwargs)
    return entry


def default_pem_proofs() -> list[dict]:
    """Standaard PEM-akkoord: EUR.1 + factuurverklaring, symmetrisch."""
    return [
        build_proof_entry("EUR1", taric_code="N865"),
        build_proof_entry("INVOICE_DECLARATION", taric_code="N864",
                          threshold_eur=6000, requires_above_threshold="authorised_exporter"),
    ]


def default_pem_proofs_eur_med() -> list[dict]:
    """Voor PEM-landen met EUR-MED optie (oude regels-zijde)."""
    return [
        build_proof_entry("EUR1", taric_code="N865"),
        build_proof_entry("EUR_MED", taric_code="N954"),
        build_proof_entry("INVOICE_DECLARATION", taric_code="N864",
                          threshold_eur=6000, requires_above_threshold="authorised_exporter"),
        build_proof_entry("INVOICE_DECLARATION_EUR_MED", taric_code="N953",
                          threshold_eur=6000, requires_above_threshold="authorised_exporter"),
    ]


# Akkoorden die enkel EUR.1 hebben (geen factuurverklaring)
EUR1_ONLY = {"SY"}

# Akkoorden met EUR-MED optie (oude PEM-regels nog van toepassing aan één kant)
EUR_MED_AGREEMENTS = {"DZ"}


def migrate():
    with open(OLD, "r", encoding="utf-8") as f:
        data = json.load(f)

    new_agreements = []
    for agr in data["agreements"]:
        agr_id = agr["id"]

        # Bouw export en import secties
        if agr_id in EXPORT_IMPORT_OVERRIDES:
            override = EXPORT_IMPORT_OVERRIDES[agr_id]
            export_section = {
                "proof_types": [
                    build_proof_entry(p.pop("id"), p.pop("taric_code", None), **p)
                    for p in [dict(x) for x in override.get("export", {}).get("proof_types", [])]
                ],
                "validity_months": agr.get("validity_months"),
                "retroactive_years": agr.get("retroactive_years_eu_import") or agr.get("retroactive_years"),
                "notes": override.get("export", {}).get("notes", []),
            }
            import_section = {
                "proof_types": [
                    build_proof_entry(p.pop("id"), p.pop("taric_code", None), **p)
                    for p in [dict(x) for x in override.get("import", {}).get("proof_types", [])]
                ],
                "validity_months": agr.get("validity_months"),
                "retroactive_years": agr.get("retroactive_years"),
                "notes": override.get("import", {}).get("notes", []),
            }
        else:
            # Symmetrische default
            if agr_id in EUR1_ONLY:
                proofs = [build_proof_entry("EUR1", taric_code="N865")]
            elif agr_id in EUR_MED_AGREEMENTS:
                proofs = default_pem_proofs_eur_med()
            else:
                proofs = default_pem_proofs()

            export_section = {
                "proof_types": [dict(p) for p in proofs],
                "validity_months": agr.get("validity_months"),
                "retroactive_years": agr.get("retroactive_years_eu_import") or agr.get("retroactive_years"),
                "notes": [],
            }
            import_section = {
                "proof_types": [dict(p) for p in proofs],
                "validity_months": agr.get("validity_months"),
                "retroactive_years": agr.get("retroactive_years"),
                "notes": [],
            }

        # Bouw nieuwe agreement (behoud alles, voeg export/import toe, verwijder oude `proof_types`)
        new_agr = {
            "id": agr["id"],
            "country_iso": agr.get("country_iso"),
            "country_name_nl": agr.get("country_name_nl"),
            "country_name_en": agr.get("country_name_en"),
            "zone": agr.get("zone"),
            "subzone": agr.get("subzone"),
            "agreement_type": agr.get("agreement_type"),
            "is_customs_union": agr.get("is_customs_union", False),
            "pem_status": agr.get("pem_status"),
            "pem_status_since": agr.get("pem_status_since"),
            "drawback_allowed": agr.get("drawback_allowed"),
            "drawback_note": agr.get("drawback_note"),
            "cumulation": agr.get("cumulation", []),
            "in_force_since": agr.get("in_force_since"),
            "in_force_status": agr.get("in_force_status"),
            "scope": agr.get("scope"),
            "hs_chapters": agr.get("hs_chapters"),
            "legal_basis": agr.get("legal_basis", []),
            "special_marking": agr.get("special_marking"),
            "notes": agr.get("notes", []),
            "export": export_section,
            "import": import_section,
        }
        # Schoonmaken: weghalen wat None is
        new_agr = {k: v for k, v in new_agr.items() if v is not None}
        new_agreements.append(new_agr)

    new_data = {
        "metadata": {
            **data["metadata"],
            "schema_version": "2.0",
            "schema_note": (
                "v2 splitst per akkoord een 'export' (EU → bestemmingsland) en 'import' "
                "(bestemmingsland → EU) sectie. Elk bevat een lijst van proof_types met "
                "naam, optionele TARIC-code, eventuele drempel en bijzondere vereisten."
            ),
        },
        "proof_type_registry": {
            pid: {"name": name} for pid, name in PROOF_NAMES.items()
        },
        "agreements": new_agreements,
    }

    with open(NEW, "w", encoding="utf-8") as f:
        json.dump(new_data, f, indent=2, ensure_ascii=False)

    print(f"Migrated {len(new_agreements)} agreements to schema v2")
    print(f"Output: {NEW}")


if __name__ == "__main__":
    migrate()
