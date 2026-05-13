"""
DKM Origin Check — Streamlit demo

Twee use cases in één app:
1. "Vraag het na" — Q&A over preferentiële oorsprongsregels per bestemming
2. "Export declaration check" — valideer claim van oorsprongsbewijs in een aangifte

Te integreren in dkm-int-hub als één van de tegels.
Past op Streamlit Cloud (geen Oracle nodig) of Azure App Service.
"""

from __future__ import annotations

import streamlit as st

from dkm_origin import OriginValidator, Severity, all_countries_for_dropdown, resolve_country

st.set_page_config(
    page_title="DKM Origin Check",
    page_icon="🛃",
    layout="wide",
)

# DKM branding
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
    ["🔎 Lookup per bestemming", "✅ Aangifte-validatie", "📚 Browse alle overeenkomsten"]
)

# ──────────────────────────────────────────────────────────────────
# Tab 1: lookup per bestemming
# ──────────────────────────────────────────────────────────────────
with tab_lookup:
    st.subheader("Welke regels gelden voor mijn bestemming?")

    country_input = st.text_input(
        "Bestemmingsland",
        placeholder="Typ landnaam of ISO-code (bv. 'Japan', 'Verenigde Staten', 'VS', 'CH')",
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
            from dkm_origin import is_eu_member, display_name
            if is_eu_member(iso):
                st.info(
                    f"ℹ️ **{display_name(iso)}** ({iso}) is een EU-lidstaat. "
                    f"Dit is intra-Unie verkeer — preferentiële oorsprongsbewijzen "
                    f"zijn hier niet van toepassing."
                )
            else:
                st.error(
                    f"❌ Geen preferentiële overeenkomst tussen EU en **{display_name(iso)}** ({iso}). "
                    f"Voor export hierheen: enkel niet-preferentieel certificaat van "
                    f"oorsprong (KvK) mogelijk, indien gevraagd door invoerder."
                )
        else:
            for a in agreements:
                with st.container(border=True):
                    cols = st.columns([2, 1, 1, 1])
                    cols[0].markdown(f"**{a['country_name_nl']}**")
                    cols[1].metric("Geldigheid", f"{a.get('validity_months', '?')} mnd")
                    cols[2].metric(
                        "Drawback",
                        "Ja" if a.get("drawback_allowed") else ("Nee" if a.get("drawback_allowed") is False else "n.v.t."),
                    )
                    cols[3].metric("PEM-status", a.get("pem_status", "n.v.t."))

                    proofs = a.get("proof_types", [])
                    st.markdown("**Aanvaarde oorsprongsbewijzen:**")
                    for p in proofs:
                        info = validator.get_proof_type_info(p) or {}
                        taric = info.get("taric_doc_code", "—")
                        st.markdown(f"- `{p}` — {info.get('name', p)} _(TARIC: {taric})_")

                    st.markdown(f"**Cumulatie:** {', '.join(a.get('cumulation', [])) or 'geen'}")
                    st.markdown(f"**Retroactief opstellen:** {a.get('retroactive_years', '?')} jaar")

                    if a.get("special_marking"):
                        st.warning(f"⚠️ Bijzondere vermelding: {a['special_marking']}")
                    if a.get("notes"):
                        for n in a["notes"]:
                            st.info(f"ℹ️ {n}")
                    if a.get("legal_basis"):
                        with st.expander("Wettelijke basis"):
                            for lb in a["legal_basis"]:
                                st.markdown(f"- {lb}")

# ──────────────────────────────────────────────────────────────────
# Tab 2: aangifte-validatie
# ──────────────────────────────────────────────────────────────────
with tab_validate:
    st.subheader("Export declaration check")
    st.caption(
        "Simuleert wat een aangever invult: bestemming + document-code + waarde. "
        "Geeft een PASS/FAIL terug met uitleg. "
        "Te integreren in jullie bestaande export-flow (bv. via REST-call)."
    )

    col1, col2 = st.columns(2)
    with col1:
        country_input = st.text_input(
            "Bestemmingsland",
            value="Verenigde Staten",
            placeholder="bv. Japan, USA, Verenigde Staten, VS, CH",
            help="NL of EN naam, ISO-2 (US, JP), ISO-3 (USA, JPN), of alias (VS, VK)",
            key="validate_country",
        )
        if country_input:
            m = resolve_country(country_input)
            if m.matched:
                dest_resolved = m.iso2
                st.caption(f"✓ Herkend als: **{m.name_nl}** ({m.iso2})")
            else:
                dest_resolved = country_input  # raw doorgeven — validator geeft UNKNOWN_COUNTRY
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
                "STATEMENT_OF_ORIGIN_REX",
                "IMPORTERS_KNOWLEDGE",
                "ATR",
                "T2_T2L",
                "C100 (TARIC code → EUR.1)",
                "U165 (TARIC code → REX-attest)",
                "N864 (TARIC code → factuurverklaring)",
            ],
        )
    with col2:
        value = st.number_input("Zending-waarde (EUR)", min_value=0.0, value=15000.0, step=1000.0)
        rex = st.text_input("REX-nummer (indien van toepassing)", placeholder="BEREXBE...")
        auth_exp = st.checkbox("Toegelaten exporteur (vergunning aanwezig)")
        agr_id = st.text_input(
            "Agreement ID (optioneel)",
            placeholder="bv. TR_CU voor Turkije douane-unie",
            help="Enkel nodig bij landen met meerdere overeenkomsten (TR, AD)",
        )

    if st.button("Valideer", type="primary"):
        # Strip TARIC-toelichting indien aanwezig
        proof_code = proof.split()[0]
        result = validator.validate_proof(
            destination_country=dest_resolved,
            proof_type=proof_code,
            value_eur=value if value > 0 else None,
            agreement_id=agr_id or None,
            authorised_exporter=auth_exp,
            rex_number=rex or None,
        )
        if result.severity == Severity.OK:
            st.success(f"✅ {result.message}")
        elif result.severity == Severity.WARNING:
            st.warning(f"⚠️ {result.message}")
        else:
            st.error(f"❌ {result.message}")

        with st.expander("Volledige response (JSON-shape voor API-integratie)"):
            st.json(result.to_dict())

    st.divider()
    st.markdown("**Voorbeeld scenario's om te testen:**")
    st.markdown(
        """
        - `C100` + `US` + 15.000 EUR → ❌ geen akkoord
        - `STATEMENT_OF_ORIGIN_REX` + `JP` + 15.000 EUR + REX-nr → ✅ ok
        - `STATEMENT_OF_ORIGIN_REX` + `JP` + 15.000 EUR (geen REX) → ❌ REX vereist
        - `INVOICE_DECLARATION` + `CH` + 12.000 EUR + géén toegelaten exp → ❌ vergunning vereist
        - `EUR1` + `TR` (zonder agreement_id) → ⚠️ welke Turkije-overeenkomst?
        - `ATR` + `TR` + agreement_id `TR_CU` → ✅ ok
        """
    )

# ──────────────────────────────────────────────────────────────────
# Tab 3: browse alle overeenkomsten
# ──────────────────────────────────────────────────────────────────
with tab_browse:
    st.subheader("Overzicht van alle overeenkomsten")
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
        rows.append(
            {
                "ID": a["id"],
                "Bestemming(en)": iso_str,
                "Naam": a["country_name_nl"],
                "Zone": a["zone"],
                "Type": a.get("agreement_type", ""),
                "PEM": a.get("pem_status", "—"),
                "Drawback": a.get("drawback_allowed"),
                "Geldigheid (mnd)": a.get("validity_months"),
                "In werking": a.get("in_force_since", ""),
            }
        )
    df = pd.DataFrame(rows)
    zone_filter = st.multiselect("Filter zone", options=sorted(df["Zone"].unique()))
    if zone_filter:
        df = df[df["Zone"].isin(zone_filter)]
    st.dataframe(df, use_container_width=True, height=500)
    st.download_button(
        "📥 Download dataset als CSV",
        df.to_csv(index=False).encode("utf-8"),
        file_name="dkm_preferential_agreements.csv",
        mime="text/csv",
    )
