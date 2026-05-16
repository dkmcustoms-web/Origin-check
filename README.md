# DKM Origin Check (v2)

Gestructureerde dataset + validatie-library voor preferentiële oorsprong, op
basis van het AADA-overzicht **OEO – D.D 15.316** (bijwerking 30 april 2026).

Twee use cases:
1. **Q&A app** — antwoorden over oorsprongsregels per bestemming
2. **Aangifte-validatie** — automatische validatie voor export én import

## Wat is er nieuw in v2

Het v1-datamodel had één gedeelde `proof_types` lijst per akkoord. Dat klopt
voor klassieke PEM-akkoorden (EUR.1 voor beide richtingen), maar voor moderne
FTAs zoals CETA en EU-Japan verschillen export en import wezenlijk:

- **EU → Canada**: enkel REX-attest (geen factuurverklaring/N864!)
- **Canada → EU**: oorsprongsverklaring met Canadees Business Number

In v2 heeft elk akkoord twee aparte secties: `export` (EU → land) en `import`
(land → EU). De validator heeft een nieuwe `direction` parameter.

TARIC-codes worden nu enkel ingevuld waar ze met zekerheid bekend zijn:
- `N865` = EUR.1
- `N864` = oorsprongsverklaring op factuur (PEM-context)
- `N954` = EUR-MED
- `N953` = factuurverklaring EUR-MED
- `N018` = A.TR (Turkije douane-unie)
- `U045` = REX-attest (GSP)

Voor moderne FTAs (CETA, JP-EPA, TCA, EU-SG, EU-VN, EU-NZ, EU-Chili, Mercosur)
laten we de TARIC-code leeg omdat er geen eenduidige per-akkoord-code bestaat.

## Wat zit erin

```
dkm_origin_app/
├── data/
│   └── preferential_agreements.json   ← schema v2, export/import gesplitst
├── dkm_origin/
│   ├── __init__.py
│   ├── countries.py                   ← landnaam/ISO resolver
│   └── validator.py                   ← validator met direction-parameter
├── migrate_to_v2.py                   ← migratie van v1 naar v2 (documentatie)
├── app.py                             ← Streamlit demo
├── test_scenarios.py
├── requirements.txt
├── Procfile + railway.toml + runtime.txt   ← Railway config
└── .streamlit/config.toml
```

## API gebruik

```python
from dkm_origin import OriginValidator

v = OriginValidator()

# EU → Canada export: REX-attest met REX-nummer
result = v.validate_proof(
    destination_country="Canada",  # ook "CA", "CAN" werkt
    proof_type="STATEMENT_OF_ORIGIN_REX",
    direction="export",
    value_eur=15000,
    rex_number="BEREXBE0123456789",
)
# → severity=warning, code=OK_WITH_WARNINGS, "REX-nummer verplicht boven 6.000 EUR"

# EU → Canada export met factuurverklaring: WORDT GEWEIGERD
result = v.validate_proof(
    destination_country="Canada",
    proof_type="N864",  # TARIC code wordt vertaald naar INVOICE_DECLARATION
    direction="export",
    value_eur=15000,
)
# → severity=error, code=PROOF_NOT_ACCEPTED,
#   "INVOICE_DECLARATION is NIET aanvaard voor export onder akkoord CA.
#    Aanvaard: ['STATEMENT_OF_ORIGIN_REX']"

# Canada → EU import: lokaal exporteur-nummer (Canadees Business Number)
result = v.validate_proof(
    destination_country="Canada",
    proof_type="STATEMENT_OF_ORIGIN_LOCAL",
    direction="import",
    local_exporter_id="123456789RM0001",
)
```

## Error codes

| Code | Betekenis |
|---|---|
| `OK` | Bewijs is geldig |
| `OK_WITH_WARNINGS` | Geldig, maar let op (bv. Y864 voor Israel, REX-vereiste boven drempel) |
| `NO_AGREEMENT` | Land heeft geen preferentieel akkoord met EU (bv. USA, China) |
| `EU_INTRA` | Land is EU-lidstaat (intra-Unie verkeer, niet preferentieel) |
| `UNKNOWN_COUNTRY` | Landnaam niet herkend |
| `UNKNOWN_PROOF_TYPE` | Bewijs-type niet herkend |
| `PROOF_NOT_ACCEPTED` | Bewijs niet toegelaten voor deze richting onder dit akkoord |
| `NO_PROOFS_FOR_DIRECTION` | Bv. GSP heeft geen export-richting (eenzijdig) |
| `AUTHORISED_EXPORTER_REQUIRED` | Factuurverklaring >6.000 EUR zonder vergunning |
| `REX_REQUIRED` | REX-attest >drempel zonder REX-nummer |
| `LOCAL_EXPORTER_ID_REQUIRED` | Moderne FTA-import zonder lokaal nummer |
| `WRONG_REX_FORMAT` | Bv. GHREX-nummer voor Ghana (mag niet) |
| `MULTIPLE_AGREEMENTS` | Bv. Turkije zonder TR_EGKS/TR_CU/TR_AGRI specificatie |

## Installeren

```bash
pip install -r requirements.txt
python test_scenarios.py     # bevestig dat alles werkt
streamlit run app.py         # demo
```

## Deployment

### Railway (prototype / testing)

1. Push naar GitHub (private of public — geen bedrijfsdata in de codebase)
2. railway.app → New Project → Deploy from GitHub repo
3. Railway detecteert `requirements.txt`, `runtime.txt`, en `Procfile` automatisch
4. Pin de region op `europe-west4` (Amsterdam) voor laagste latency
5. Auto-deploy on push laten staan voor snelle iteratie

### Streamlit Community Cloud (alternatief)

Direct vanaf GitHub, geen Procfile nodig. Beperking: alleen public repos.

### Azure App Service (productie binnen DKM)

GitHub → GitHub Actions → Azure App Service in `dkm-int-apps-rg`. Geen Oracle
nodig, dus VNet integratie optioneel.

## AI-fallback voor landherkenning (optioneel)

De app gebruikt eerst een lokale resolver met ~120 landen + NL/EN namen + ISO
codes + aliassen + fuzzy matching. Dat dekt 95% van de gebruikers-input gratis
en instant.

Voor de 5% randgevallen (input in Duits, Frans, Japans, Koreaans, omschrijvingen
zoals "land van Eiffeltoren", ongebruikelijke typo's) is er een AI-fallback met
**Claude Haiku 4.5**.

### Inschakelen

Zet de environment variable `ANTHROPIC_API_KEY`:

**Lokaal:**
```bash
export ANTHROPIC_API_KEY=sk-ant-...
streamlit run app.py
```

**Railway:**
1. Open je service in Railway dashboard
2. **Variables** tab → **+ New Variable**
3. Naam: `ANTHROPIC_API_KEY`, waarde: je API-key van console.anthropic.com
4. Railway redeployt automatisch

**Azure App Service:**
Configuration → Application Settings → New application setting.

### Gedrag

- **Met API-key**: banner toont "🤖 AI-fallback voor landherkenning actief".
  Als de lokale resolver faalt op een onbekende input, valt de app terug op
  Haiku. Bij succes verschijnt een badge `🤖 (AI)` naast het herkende land.
- **Zonder API-key**: banner toont "ℹ️ AI-fallback uit". De app werkt
  volledig zoals voorheen met enkel de lokale resolver.

### Kosten en performantie

- Lokaal resolved: gratis, sub-millisecond
- AI-resolved: ~$0.0002 per call met Haiku 4.5 (200ms latency typical)
- Resultaten zijn in-process gecached (LRU, 512 entries) — herhalingen kosten niks
- Geschatte maandelijkse kost bij intensief gebruik: <$1

### Privacy

Bij AI-fallback wordt enkel de ingevulde landnaam naar de Anthropic API
gestuurd. **Geen bedrijfsdata, geen zending-waarden, geen REX-nummers**.
De prompt is restrictief: Haiku mag enkel een ISO-2 code teruggeven of
"UNKNOWN", en het antwoord wordt gevalideerd voor het in de app komt.

## Onderhoud

Het AADA-document wordt periodiek bijgewerkt. Bij elke update:
1. Download de nieuwste PDF van financien.belgium.be
2. Update de getroffen entries in `preferential_agreements.json`
3. Update `metadata.version` + `metadata.extracted_at`
4. Run `python test_scenarios.py` om regressies te detecteren

## Disclaimer

Dit is geen officiële AADA-publicatie. Voor authentieke teksten: EUR-LEX.
Voor actuele preferentie-status: TARBEL.
