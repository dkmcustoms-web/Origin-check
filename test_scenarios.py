"""Sanity checks voor OriginValidator — laat alle hoofd-scenario's zien."""

from dkm_origin import OriginValidator

v = OriginValidator()


def show(title, result):
    print(f"\n--- {title} ---")
    print(f"  valid={result.valid}  severity={result.severity.value}  code={result.code}")
    print(f"  → {result.message}")


# 1. Het scenario uit Luc's vraag: REX naar USA
show(
    "REX C100 → USA (zoals in Luc's voorbeeld)",
    v.validate_proof(destination_country="US", proof_type="C100", value_eur=15000),
)

# 2. REX voor Japan boven 6.000 EUR met REX-nummer
show(
    "REX → Japan, 15.000 EUR, met REX-nr",
    v.validate_proof(
        destination_country="JP",
        proof_type="STATEMENT_OF_ORIGIN_REX",
        value_eur=15000,
        rex_number="BEREXBE123456789",
    ),
)

# 3. REX voor Japan zonder REX-nummer
show(
    "REX → Japan, 15.000 EUR, ZONDER REX-nr",
    v.validate_proof(
        destination_country="JP",
        proof_type="STATEMENT_OF_ORIGIN_REX",
        value_eur=15000,
    ),
)

# 4. EUR.1 voor Zwitserland - klassieke happy path
show(
    "EUR.1 → Zwitserland",
    v.validate_proof(destination_country="CH", proof_type="EUR1"),
)

# 5. Oorsprongsverklaring op factuur > 6.000 EUR zonder vergunning
show(
    "Factuurverklaring → Noorwegen, 12.000 EUR, geen toegelaten exporteur",
    v.validate_proof(
        destination_country="NO",
        proof_type="INVOICE_DECLARATION",
        value_eur=12000,
        authorised_exporter=False,
    ),
)

# 6. Idem maar mét toegelaten exporteur
show(
    "Factuurverklaring → Noorwegen, 12.000 EUR, toegelaten exporteur",
    v.validate_proof(
        destination_country="NO",
        proof_type="INVOICE_DECLARATION",
        value_eur=12000,
        authorised_exporter=True,
    ),
)

# 7. EUR.1 voor Turkije zonder specificatie — meerdere overeenkomsten
show(
    "EUR.1 → Turkije zonder agreement_id",
    v.validate_proof(destination_country="TR", proof_type="EUR1"),
)

# 8. A.TR voor Turkije douane-unie
show(
    "A.TR → Turkije (TR_CU)",
    v.validate_proof(destination_country="TR", proof_type="ATR", agreement_id="TR_CU"),
)

# 9. EUR.1 voor Turkije EGKS - oké
show(
    "EUR.1 → Turkije EGKS (TR_EGKS)",
    v.validate_proof(destination_country="TR", proof_type="EUR1", agreement_id="TR_EGKS"),
)

# 10. Ghanese REX-nummer (mag niet)
show(
    "REX → Ghana met GHREX-nummer",
    v.validate_proof(
        destination_country="GH",
        proof_type="STATEMENT_OF_ORIGIN_REX",
        value_eur=10000,
        rex_number="GHREX123",
    ),
)

# 11. Israel met bijzondere vermelding Y864 waarschuwing
show(
    "EUR.1 → Israël (toont special_marking warning)",
    v.validate_proof(destination_country="IL", proof_type="EUR1"),
)

# 12. Summary voor bestemming
print("\n--- Summary Japan ---")
print(v.summarise_for_destination("JP"))

print("\n--- Summary USA ---")
print(v.summarise_for_destination("US"))

print("\n--- Summary Turkije ---")
print(v.summarise_for_destination("TR"))
