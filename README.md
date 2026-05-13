# DKM Origin Check

Gestructureerde dataset + validatie-library voor preferentiële oorsprong, op
basis van het AADA-overzicht **OEO – D.D 15.316** (bijwerking 30 april 2026).

Twee use cases:
1. **Q&A app** — antwoorden over oorsprongsregels per bestemming
2. **Export declaration check** — automatische validatie in jullie aangifte-flow

## Wat zit erin

```
dkm_origin_app/
├── data/
│   └── preferential_agreements.json   ← single source of truth, machine-readable
├── dkm_origin/
│   ├── __init__.py
│   └── validator.py                   ← validator + lookup library
├── app.py                             ← Streamlit demo (Q&A + validatie)
├── test_scenarios.py                  ← test-scenario's (geen pytest nodig)
└── requirements.txt
```

## Het dataset-bestand

`preferential_agreements.json` bevat alle ~50 preferentiële akkoorden, douane-unies
en uitzonderingen, gestructureerd per land/regio met:
- ISO-2 codes (voor join met EUCDM-data)
- type overeenkomst (reciprocal / non_reciprocal / customs_union)
- toegelaten oorsprongsbewijzen (EUR.1, REX-attest, factuurverklaring, A.TR, etc.)
- TARIC document-codes (N865, N864, U165, N018, ...)
- drawback ja/nee
- PEM-status (R / C / R/T)
- cumulatie-types (bilateraal / diagonaal / volledig / uitgebreid / regionaal)
- geldigheidsduur (4 / 10 / 12 maanden)
- retroactieve termijn (1 / 2 / 3 jaar)
- inwerkingtredings-datum
- wettelijke basis (PB-referenties)
- bijzondere markeringen (REVISED RULES, TRANSITIONAL RULES, Y864 voor Israel, ...)

## Use case 1 — Q&A app

Voor medewerkers die snel willen weten wat te doen voor een bepaalde bestemming.
De Streamlit-app (`app.py`) doet dit deterministisch zonder LLM. Voor échte
natural-language Q&A (bv. *"Mag ik nog drawback toepassen op textiel uit Marokko
onder de nieuwe regels?"*) kan de JSON als grounded context naar de Claude API
gestuurd worden — past in jullie bestaande `dkm-customs-utils` patroon.

## Use case 2 — Export declaration check

Het concrete voorbeeld uit jullie vraag:

```python
from dkm_origin import OriginValidator

v = OriginValidator()

# Iemand claimt REX (TARIC C100/U165) voor zending naar USA → moet failen
r = v.validate_proof(
    destination_country="US",
    proof_type="C100",          # TARIC code wordt automatisch vertaald
    value_eur=15000,
)
assert not r.valid
print(r.code)     # NO_AGREEMENT
print(r.message)  # "Geen preferentiële overeenkomst tussen EU en US..."
```

Andere checks die ingebouwd zitten:
- `NO_AGREEMENT` — bestemming heeft geen preferentiële akkoord
- `PROOF_NOT_ACCEPTED` — bv. A.TR claimen voor Japan
- `AUTHORISED_EXPORTER_REQUIRED` — factuurverklaring > 6.000 EUR zonder vergunning
- `REX_REQUIRED` — REX-attest > 6.000 EUR zonder REX-nummer
- `WRONG_REX_FORMAT` — bv. GHREX-nummer voor Ghana (mag niet)
- `MULTIPLE_AGREEMENTS` — bv. Turkije zonder specificatie EGKS/agri/CU
- `OK_WITH_WARNINGS` — bv. Israel met verplichte Y864 vermelding

Integratie-suggesties:
- **EUCDM aangifte-validatie**: roep `validate_proof()` aan vóór `EUCDECLARATION`
  ingediend wordt. Map TARIC document-codes uit `EUCDOCUMENT` direct via
  `TARIC_CODE_TO_PROOF`.
- **REST-endpoint**: wrap de validator in FastAPI of een Streamlit-internal API.
- **dkm-customs-utils**: het pakket `dkm_origin` is een natuurlijke uitbreiding —
  enkele exports (`OriginValidator`, `ValidationResult`, `Severity`).

## Installeren

```bash
pip install -r requirements.txt
python test_scenarios.py     # bevestig dat alles draait
streamlit run app.py         # demo
```

## Deployment

### Railway (prototype / testing — aanbevolen om mee te starten)

Snelste pad om de app live te krijgen voor feedback van collega's.

**Stappen:**

1. Maak een GitHub-repo aan (private of public — er staat géén bedrijfsdata in
   deze codebase):
   ```bash
   git init
   git add .
   git commit -m "Initial commit — DKM Origin Check"
   git branch -M main
   git remote add origin git@github.com:<jouw-org>/dkm-origin-check.git
   git push -u origin main
   ```

2. Ga naar [railway.app](https://railway.app) → **New Project** →
   **Deploy from GitHub repo** → kies je repo.

3. Railway detecteert automatisch:
   - `requirements.txt` → installeert dependencies via Nixpacks
   - `runtime.txt` → gebruikt Python 3.11
   - `Procfile` / `railway.toml` → start de app op `$PORT`

4. Wacht 1-2 minuten op de build. Je krijgt een URL zoals
   `https://dkm-origin-check-production.up.railway.app`.

5. Onder **Settings → Networking**: klik **Generate Domain** als er niet
   automatisch eentje is, of voeg een custom domain toe.

**Belangrijke Railway-instellingen:**

- **Region**: kies `europe-west4` (Amsterdam) voor laagste latency vanuit Antwerpen
- **Healthcheck path**: `/_stcore/health` (al geconfigureerd in `railway.toml`)
- **Auto-deploy on push**: aan laten — elke `git push` naar `main` redeployt
- **Environment variables**: niets nodig voor deze app (geen secrets, geen DB)

**Kosten:**
- Free trial: $5 credit (genoeg voor enkele dagen testen)
- Hobby plan: $5/maand voor permanente uptime
- App verbruikt ~256 MB RAM en is meeste van de tijd idle → ruim binnen budget

**Troubleshooting:**
- Build failt op `oracledb` of Oracle Client: niet relevant hier (de app heeft
  géén Oracle-dependency). Check je `requirements.txt`.
- App start maar je krijgt "Application failed to respond": Railway gebruikt
  `$PORT` envvar — Streamlit moet daarop luisteren. `Procfile` regelt dit.
- "Connection error" in Streamlit: de `enableCORS = false` en
  `enableXsrfProtection = false` settings in `.streamlit/config.toml` zijn nodig
  omdat Railway de app achter een reverse proxy serveert.

### Streamlit Community Cloud (alternatief, gratis)

Direct vanaf GitHub, geen Procfile nodig. Beperking: alleen public repos op de
free tier, en de Streamlit-branding is iets prominenter.

### Azure App Service (productie binnen DKM)

Wanneer de app klaar is voor productie, migreer naar jullie bestaande pipeline:
GitHub → GitHub Actions → Azure App Service in `dkm-int-apps-rg`. Geen Oracle
nodig dus VNet integratie optioneel. Public deploy is veilig (geen bedrijfsdata
in de dataset).

## Onderhoud

Het AADA-document wordt periodiek bijgewerkt (zie versie-veld in JSON). Bij elke
update:
1. download de nieuwste PDF van [financien.belgium.be](https://financien.belgium.be)
2. extract met `pdftotext -layout <pdf> <txt>`
3. update de getroffen entries in `preferential_agreements.json`
4. update `metadata.version` + `metadata.extracted_at`
5. run `python test_scenarios.py` om regressies te detecteren

Voor automatisatie zou je een GitHub Action kunnen toevoegen die maandelijks
checkt of er een nieuwe versie online staat.

## Disclaimer

Dit is geen officiële AADA-publicatie. Voor authentieke teksten: EUR-LEX. Voor
actuele tarieven en preferentie-status: TARBEL.
