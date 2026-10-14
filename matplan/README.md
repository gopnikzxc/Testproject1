# matplan

Personal meal planner: high protein, low kcal, high volume, with current grocery prices from stores in Kungälv and Ytterby. Spec: gopnikzxc/Testproject1#1.

## Get started

```
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/matplan plan                              # plan the coming days in 3-day blocks
.venv/bin/matplan refresh                           # fetch current prices from the stores
.venv/bin/matplan installningar                     # list settings
.venv/bin/matplan installningar jag.kcal_mal 1800   # change a setting
.venv/bin/pytest
```

The database is stored at `~/.local/share/matplan/matplan.db`. Set `MATPLAN_DB` to use a different file.

## Settings

| Key | Default | Meaning |
|---|---|---|
| `jag.kcal_mal` / `jag.protein_mal` | 2000 / 180 | Your kcal ceiling and protein floor per day |
| `fru.kcal_mal` / `fru.protein_mal` | 1700 / 110 | Your wife's targets |
| `frukost` | 1 | Breakfast on (1) or off (0) |
| `antal_mellanmal` | 2 | Snacks per day |
| `plandagar` | 7 | How many days ahead to plan |
| `vikt_protein` / `vikt_volym` / `vikt_kostnad` | 1 / 1 / 1 | How much protein density (g/100 kcal), volume (g/kcal) and low cost (kr/g protein) count when picking meals |

## Status

#2, #3 and #4 are done. For #6, the price pipeline is in place: the store interface, `refresh` with cache and spacing, whole-word matching to the cheapest kr/kg, price history and price age. No store module is connected yet, so the plan uses placeholder prices. Nutrition values are still hand-entered (#5).
