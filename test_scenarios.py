"""Sanity checks v2 — toont alle hoofd-scenario's met richting-onderscheid."""

from dkm_origin import OriginValidator

v = OriginValidator()


def show(title, result):
    print(f"\n--- {title} ---")
    print(f"  {result.severity.value:8s}  {result.code}")
    print(f"  → {result.message}")


# ═══════════════════════════════════════════════════════════════
# DE ORIGINELE BUG: Canada toonde N864 voor export
# ═══════════════════════════════════════════════════════════════

show(
    "[BUG-FIX] EXPORT EU→Canada met factuurverklaring (moet falen)",
    v.validate_proof(
        destination_country="Canada", proof_type="INVOICE_DECLARATION",
        direction="export", value_eur=15000, authorised_exporter=True,
    ),
)

show(
    "[BUG-FIX] EXPORT EU→Canada met N864 (TARIC, moet falen)",
    v.validate_proof(
        destination_country="Canada", proof_type="N864",
        direction="export", value_eur=15000, authorised_exporter=True,
    ),
)

show(
    "[OK] EXPORT EU→Canada met REX-attest + REX-nr",
    v.validate_proof(
        destination_country="Canada", proof_type="STATEMENT_OF_ORIGIN_REX",
        direction="export", value_eur=15000, rex_number="BEREXBE0123456789",
    ),
)

show(
    "[OK] IMPORT Canada→EU met lokaal exporteur-nr",
    v.validate_proof(
        destination_country="Canada", proof_type="STATEMENT_OF_ORIGIN_LOCAL",
        direction="import", value_eur=15000, local_exporter_id="123456789RM0001",
    ),
)

# Klassieke PEM symmetrie
show(
    "[OK] EXPORT EU→Zwitserland met EUR.1",
    v.validate_proof(destination_country="Zwitserland", proof_type="EUR1", direction="export"),
)
show(
    "[OK] IMPORT Zwitserland→EU met EUR.1",
    v.validate_proof(destination_country="Zwitserland", proof_type="EUR1", direction="import"),
)

# Importer's Knowledge
show(
    "[OK] IMPORT Japan→EU met Importer's Knowledge",
    v.validate_proof(destination_country="Japan", proof_type="IMPORTERS_KNOWLEDGE", direction="import"),
)
show(
    "[ERR] EXPORT EU→Zwitserland met Importer's Knowledge (mag niet bij PEM)",
    v.validate_proof(destination_country="Zwitserland", proof_type="IMPORTERS_KNOWLEDGE", direction="export"),
)

# Drempel-checks
show(
    "[ERR] EXPORT EU→Noorwegen factuurverklaring >6k zonder vergunning",
    v.validate_proof(
        destination_country="Noorwegen", proof_type="INVOICE_DECLARATION",
        direction="export", value_eur=12000, authorised_exporter=False,
    ),
)
show(
    "[OK] EXPORT EU→Noorwegen factuurverklaring >6k MET vergunning",
    v.validate_proof(
        destination_country="Noorwegen", proof_type="INVOICE_DECLARATION",
        direction="export", value_eur=12000, authorised_exporter=True,
    ),
)
show(
    "[ERR] EXPORT EU→Japan REX-attest >6k zonder REX-nr",
    v.validate_proof(
        destination_country="Japan", proof_type="STATEMENT_OF_ORIGIN_REX",
        direction="export", value_eur=15000,
    ),
)

# Land-resolutie
show(
    "[ERR] EU-lidstaat (Frankrijk)",
    v.validate_proof(destination_country="Frankrijk", proof_type="EUR1", direction="export"),
)
show(
    "[ERR] Geen akkoord (USA / VS)",
    v.validate_proof(destination_country="VS", proof_type="EUR1", direction="export"),
)

# Summaries
print("\n\n═══ SUMMARY Canada (beide richtingen) ═══")
print(v.summarise_for_destination("Canada"))

print("\n═══ SUMMARY Japan (beide richtingen) ═══")
print(v.summarise_for_destination("Japan"))

print("\n═══ SUMMARY Zwitserland (alleen export) ═══")
print(v.summarise_for_destination("Zwitserland", direction="export"))
