# ephrata-water

Water safety data for Ephrata Borough, PA — fetched from official sources, explained in
plain language, and published as a static dashboard for non-technical readers.

Ephrata Borough's tap water comes from the **Ephrata Area Joint Authority** (EAJA,
PWSID `PA7360045`), a community system serving ~24,500 people from Cocalico Creek and
groundwater wells. This site is generated from public regulatory data; it is not an
official publication of EAJA, EPA, or PA DEP.

## How it works

```
pipeline/fetch/   one module per source (sdwis, echo, ...), each fails independently
pipeline/interpret.py   coded records -> plain-language statuses and sentences
pipeline/build.py       writes site/data/water.json
site/             static frontend (no framework, no build step)
```

`publish.yml` runs weekly (and on merge): it fetches fresh data at build time and deploys
`site/` to GitHub Pages. **No data is committed to the repo** — `main` is code only.
A source being down degrades its panel with an "unavailable" note instead of failing
the deploy; if *no* source produced usable data the build exits non-zero and the
previously published site stays up.

Setup notes: repo Settings → Pages → Source must be **GitHub Actions** (otherwise
`deploy-pages` 404s confusingly), and GitHub disables cron workflows after ~60 days
without repo activity — re-enable from the Actions tab if the weekly refresh email
says it was turned off.

Reference data in `pipeline/refdata/sdwa_ref_codes.csv` is a trimmed vendored copy of
EPA ECHO's `SDWA_REF_CODE_VALUES.csv` (violation/contaminant/rule code descriptions).

## Data sources

| Source | What we use it for |
| --- | --- |
| [EPA Envirofacts SDWIS](https://www.epa.gov/enviro/envirofacts-data-service-api) | System inventory, violations, lead/copper summaries |
| [EPA ECHO SDW services](https://echo.epa.gov/tools/web-services) | Current compliance status, quarterly history |
| PA DEP Drinking Water Reporting System | Sample results (planned) |
| [EPA UCMR5](https://www.epa.gov/dwucmr) | PFAS occurrence results (planned) |
| EAJA annual water quality reports | Multi-year detected-contaminant trends (planned) |
| [Water Quality Portal](https://www.waterqualitydata.us/) | Cocalico Creek source-water context (planned) |

## Development

```sh
uv sync
uv run pytest                      # parser/interpreter tests, offline
uv run python -m pipeline.build    # fetch + write site/data/water.json
python -m http.server -d site 8000 # view locally
```
