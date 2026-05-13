"""
DKM Origin Check — Streamlit demo (v2)

Schema v2: export en import zijn nu gescheiden per akkoord.
"""

from __future__ import annotations

import streamlit as st

from dkm_origin import OriginValidator, Severity, resolve_country, is_eu_member, display_name

st.set_page_config(
    page_title="DKM Origin Check",
    page_icon="🛃",
    layout="wide",
)

DKM_BLUE = "#3cceff"
DKM_ORANGE = "#f35e40"

st.markdown(
    f"""
    <style>
    .stApp h1 {{ color: {DKM_ORANGE}; }}
    div[data-testid="stMetricValue"] {{ color: {DKM_BLUE}; }}
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def get_validator() -> OriginValidator:
    return OriginValidator()


validator = get_validator()

st.title("🛃 DKM Origin Check")
st.caption(
    "Op basis van AADA — OEO D.D. 15.316 (bijwerking 30 april 2026). "
    "Informatief; verifieer steeds tegen EUR-LEX en TARBEL."
)

tab_lookup, tab_validate, tab_browse = st.tabs(
    ["🔎 Lookup per bestemming", "✅ Aangifte-validatie", "📚 Browse alle akkoorden"]
)


def render_direction_section(agreement: dict, direction: str, country_label: str) -> None:
    section = agreement.get(direction, {})
    proofs = section.get("proof_types", [])

    if direction == "export":
        header = f"📤 **Export — EU → {country_label}**"
    else:
        header = f"📥 **Import — {country_label} → EU**"
    st.markdown(header)

    if not proofs:
        st.caption("_Geen preferentiële oorsprongsbewijzen voor deze richting._")
        if section.get("notes"):
            for n in section["notes"]:
                st.info(f"ℹ️ {n}")
        return

    for p in proofs:
        line = f"- **{p['name']}**"
        if p.get("taric_code"):
            line += f" _(TARIC: `{p['taric_code']}`)_"
        if p.get("threshold_eur"):
            threshold_str = f"{p['threshold_eur']:,}".replace(",", ".")
            line += f"  · drempel **{threshold_str} EUR**"
        if p.get("requires_above_threshold"):
            req_label = {
                "rex_number": "REX-nummer",
                "authorised_exporter": "toegelaten exporteur",
                "local_exporter_id": "lokaal exporteur-nummer",
            }.get(p["requires_above_threshold"], p["requires_above_threshold"])
            line += f"  · vereist **{req_label}**"
        st.markdown(line)
        if p.get("note"):
            st.caption(f"  ↳ {p['note']}")

    meta_cols = st.columns(2)
    meta_cols[0].caption(f"Geldigheid: **{section.get('validity_months', '?')} maanden**")
    meta_cols[1].caption(f"Retroactief: **{section.get('retroactive_years', '?')} jaar**")

    if section.get("notes"):
        for n in section["notes"]:
            st.info(f"ℹ️ {n}")


with tab_lookup:
    st.subheader("Welke regels gelden voor mijn bestemming?")

    country_input = st.text_input(
        "Bestemmingsland",
        placeholder="Typ landnaam of ISO-code (bv. 'Canada', 'Japan', 'VS', 'CH')",
        help="Werkt op NL/EN naam, ISO-2, ISO-3, en aliassen zoals VS, UK, VAE",
        key="lookup_country",
    )

    iso = None
    if country_input:
        match = resolve_country(country_input)
        if match.matched:
            st.caption(f"✓ Herkend als: **{match.name_nl}** ({match.iso2})")
            iso = match.iso2
        else:
            if match.suggestions:
                st.caption(f"⚠️ Niet herkend. Bedoel je: {', '.join(match.suggestions)}?")
            else:
                st.caption(f"⚠️ Land '{country_input}' niet herkend.")

    if iso:
        agreements = validator.get_agreements_for(iso)
        if not agreements:
            if is_eu_member(iso):
                st.info(
                    f"ℹ️ **{display_name(iso)}** ({iso}) is een EU-lidstaat — intra-Unie verkeer. "
                    f"Preferentiële oorsprongsbewijzen zijn niet van toepassing."
                )
            else:
                st.error(
                    f"❌ Geen preferentiële overeenkomst tussen EU en **{display_name(iso)}** ({iso}). "
                    f"Voor export hierheen: enkel niet-preferentieel CvO (KvK) mogelijk."
                )
        else:
            for a in agreements:
                with st.container(border=True):
                    cols = st.columns([3, 1, 1, 1])
                    cols[0].markdown(f"### {a['country_name_nl']}")
                    drawback = a.get("drawback_allowed")
                    cols[1].metric(
                        "Drawback",
                        "Ja" if drawback else ("Nee" if drawback is False else "n.v.t."),
                    )
                    cols[2].metric("PEM-status", a.get("pem_status", "—"))
                    cols[3].metric("Akkoord-ID", a["id"])

                    if a.get("agreement_type"):
                        st.caption(
                            f"Type: **{a['agreement_type']}**"
                            + (" · 🛃 douane-unie" if a.get("is_customs_union") else "")
                            + (f" · in werking sinds {a['in_force_since']}" if a.get("in_force_since") else "")
                        )

                    col_exp, col_imp = st.columns(2)
                    with col_exp:
                        render_direction_section(a, "export", a["country_name_nl"])
                    with col_imp:
                        render_direction_section(a, "import", a["country_name_nl"])

                    st.markdown("---")
                    st.markdown(f"**Cumulatie:** {', '.join(a.get('cumulation', [])) or 'geen'}")
                    if a.get("special_marking"):
                        st.warning(f"⚠️ Bijzondere vermelding: {a['special_marking']}")
                    if a.get("notes"):
                        for n in a["notes"]:
                            st.info(f"ℹ️ {n}")
                    if a.get("legal_basis"):
                        with st.expander("Wettelijke basis"):
                            for lb in a["legal_basis"]:
                                st.markdown(f"- {lb}")


with tab_validate:
    st.subheader("Aangifte-validatie")
    st.caption(
        "Simuleert wat een aangever invult: richting + land + bewijs + waarde. "
        "Pass/fail met uitleg. Te integreren via REST in jullie aangifte-flow."
    )

    direction = st.radio(
        "Richting",
        options=["export", "import"],
        format_func=lambda x: "📤 Export (EU → land)" if x == "export" else "📥 Import (land → EU)",
        horizontal=True,
        key="validate_direction",
    )

    col1, col2 = st.columns(2)
    with col1:
        country_input = st.text_input(
            "Bestemmingsland (export) / Oorsprongsland (import)",
            value="Canada",
            placeholder="bv. Canada, Japan, USA, VS, CH",
            help="NL of EN naam, ISO-2, ISO-3, of alias (VS, VK)",
            key="validate_country",
        )
        if country_input:
            m = resolve_country(country_input)
            if m.matched:
                dest_resolved = m.iso2
                st.caption(f"✓ Herkend als: **{m.name_nl}** ({m.iso2})")
            else:
                dest_resolved = country_input
                if m.suggestions:
                    st.caption(f"⚠️ Niet herkend. Bedoel je: {', '.join(m.suggestions)}?")
                else:
                    st.caption("⚠️ Niet herkend.")
        else:
            dest_resolved = ""

        proof = st.selectbox(
            "Oorsprongsbewijs / document",
            options=[
                "EUR1",
                "EUR_MED",
                "INVOICE_DECLARATION",
                "INVOICE_DECLARATION_EUR_MED",
                "STATEMENT_OF_ORIGIN_REX",
                "STATEMENT_OF_ORIGIN_LOCAL",
                "IMPORTERS_KNOWLEDGE",
                "ATR",
                "T2_T2L",
                "EUR1_CMR",
                "—— of via TARIC ——",
                "N865 (= EUR.1)",
                "N864 (= factuurverklaring)",
                "N954 (= EUR-MED)",
                "N018 (= A.TR)",
                "U045 (= REX/GSP)",
            ],
        )
    with col2:
        value = st.number_input("Zending-waarde (EUR)", min_value=0.0, value=15000.0, step=1000.0)
        rex = st.text_input("REX-nummer (indien van toepassing)", placeholder="BEREXBE...")
        local_id = st.text_input(
            "Lokaal exporteur-nummer (voor import)",
            placeholder="bv. Canadees BN, JP Corporate Nr, NZ Customs Client Code",
            help="Voor import-richting bij moderne FTAs",
        )
        auth_exp = st.checkbox("Toegelaten exporteur (vergunning aanwezig)")
        agr_id = st.text_input(
            "Agreement ID (optioneel)",
            placeholder="bv. TR_CU voor Turkije douane-unie",
            help="Enkel nodig bij landen met meerdere akkoorden",
        )

    if st.button("Valideer", type="primary"):
        if proof.startswith("——"):
            st.warning("Kies een echt bewijs-type, niet de header.")
        else:
            proof_code = proof.split()[0]
            result = validator.validate_proof(
                destination_country=dest_resolved,
                proof_type=proof_code,
                direction=direction,
                value_eur=value if value > 0 else None,
                agreement_id=agr_id or None,
                authorised_exporter=auth_exp,
                rex_number=rex or None,
                local_exporter_id=local_id or None,
            )
            if result.severity == Severity.OK:
                st.success(f"✅ {result.message}")
            elif result.severity == Severity.WARNING:
                st.warning(f"⚠️ {result.message}")
            else:
                st.error(f"❌ {result.message}")

            with st.expander("Volledige response (JSON voor API-integratie)"):
                st.json(result.to_dict())

    st.divider()
    st.markdown("**Test-scenario's:**")
    st.markdown(
        """
        - `export` + `Canada` + `INVOICE_DECLARATION` + 15.000 EUR → ❌ niet aanvaard (enkel REX-attest)
        - `export` + `Canada` + `STATEMENT_OF_ORIGIN_REX` + 15.000 EUR + REX-nr → ✅ ok
        - `export` + `USA` + om het even wat → ❌ geen akkoord
        - `export` + `Japan` + `STATEMENT_OF_ORIGIN_REX` + 15.000 EUR → ❌ REX-nr vereist
        - `import` + `Japan` + `IMPORTERS_KNOWLEDGE` → ✅ ok (mag bij JP→EU)
        - `import` + `Canada` + `STATEMENT_OF_ORIGIN_LOCAL` + BN → ✅ ok
        - `export` + `CH` + `EUR1` → ✅ ok (klassieke PEM)
        """
    )


with tab_browse:
    st.subheader("Overzicht van alle akkoorden")
    import pandas as pd

    rows = []
    for a in validator._data["agreements"]:
        iso = a.get("country_iso")
        if isinstance(iso, list):
            iso_str = ", ".join(iso)
        elif iso is None:
            iso_str = "(meerdere)"
        else:
            iso_str = iso
        exp_proofs = [p["id"] for p in a.get("export", {}).get("proof_types", [])]
        imp_proofs = [p["id"] for p in a.get("import", {}).get("proof_types", [])]
        rows.append({
            "ID": a["id"],
            "Bestemming": iso_str,
            "Naam": a["country_name_nl"],
            "Zone": a.get("zone", ""),
            "Type": a.get("agreement_type", ""),
            "Export bewijzen": ", ".join(exp_proofs) or "—",
            "Import bewijzen": ", ".join(imp_proofs) or "—",
            "PEM": a.get("pem_status", "—"),
            "Drawback": a.get("drawback_allowed"),
            "In werking": a.get("in_force_since", ""),
        })
    df = pd.DataFrame(rows)
    zone_filter = st.multiselect("Filter zone", options=sorted(df["Zone"].unique()))
    if zone_filter:
        df = df[df["Zone"].isin(zone_filter)]
    st.dataframe(df, use_container_width=True, height=500)
    st.download_button(
        "📥 Download als CSV",
        df.to_csv(index=False).encode("utf-8"),
        file_name="dkm_preferential_agreements_v2.csv",
        mime="text/csv",
    )
