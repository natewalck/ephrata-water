# ephrata-water

Water safety data for Ephrata Borough, PA — fetched from official sources, explained in
plain language, and published as a static dashboard for non-technical readers.

**Live dashboard: <https://natewalck.github.io/ephrata-water/>**

Ephrata Borough's tap water comes from the **Ephrata Area Joint Authority** (EAJA,
PWSID `PA7360045`), a community system serving ~24,500 people from Cocalico Creek and
groundwater wells. This site is generated from public regulatory data; it is not an
official publication of EAJA, EPA, or PA DEP.

## How it works

```
pipeline/fetch/   one module per source (sdwis, echo, ...), each fails independently
pipeline/interpret.py   coded records -> plain-language statuses and sentences
pipeline/rtk.py         parses lab PDFs from Right-to-Know requests; parsed JSON is committed
pipeline/build.py       writes site/data/water.json
site/             static frontend (no framework, no build step)
```

`publish.yml` runs weekly (and on merge): it fetches fresh data at build time and deploys
`site/` to GitHub Pages. **No fetched data is committed to the repo** — `main` is code plus
the parsed output of Right-to-Know requests (`pipeline/refdata/rtk_*.json`), which cannot
be fetched from anywhere.
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
| Right-to-Know request to Ephrata Borough | Lab certificates and PA DEP submissions for a sampling window (bacteria, PFAS, disinfection byproducts, nitrate, pesticides, general chemistry) |
| EAJA annual water quality reports | Multi-year detected-contaminant trends (planned) |
| [Water Quality Portal](https://www.waterqualitydata.us/) | Cocalico Creek source-water context (planned) |

## Adding a Right-to-Know response

```sh
pdftotext -layout response.pdf - | uv run python -m pipeline.rtk > pipeline/refdata/rtk_YYYY-MM.json
```

Then point `RTK_FILE` and `RTK_WINDOW` in `pipeline/build.py` at it. Do not commit the PDF:
responses include the requester's home address. Check `uv run pytest` and the parsed
analyte counts against the PDF before merging; the parser is regex over `pdftotext`
output and a new lab report layout can drop rows silently.

## Development

```sh
uv sync
uv run pytest                      # parser/interpreter tests, offline
uv run python -m pipeline.build    # fetch + write site/data/water.json
python -m http.server -d site 8000 # view locally
```
