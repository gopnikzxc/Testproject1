# matplan

Personal meal planner: high protein, low kcal, high volume, with current grocery prices from stores in Kungälv and Ytterby. Spec: gopnikzxc/Testproject1#1.

## Get started

```
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/matplan plan                              # plan the coming days in 3-day blocks
.venv/bin/matplan refresh                           # fetch current prices from the stores
.venv/bin/matplan lista                             # shopping list: whole packages, kr/kg, single store vs split
.venv/bin/matplan export [folder]                   # save plan.md and inkopslista.md for your phone
.venv/bin/matplan produkter Kycklingfilé            # fetched products with ids
.venv/bin/matplan lås Kycklingfilé "City Gross Ytterby" <id>   # always use that product there
.venv/bin/matplan köpt [--butik B | --delad]        # add the shopping list to inventory; the plan becomes active
.venv/bin/matplan lagat [--block N]                 # subtract a cooked batch from inventory
.venv/bin/matplan lager [ingredient grams]          # show inventory or set an amount
.venv/bin/matplan plan --ny                         # drop the bought plan and plan again
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
| `veckobudget` / `manadsbudget` | 1250 / 5000 | Ceilings for planned food. A month counts as 4 weeks, and no day may cost more than the stricter of the two |

Planning uses inventory first: whatever is already at home costs 0 kr, and the shopping list only covers what's missing. Once you've run `köpt`, that plan stays in place until it ends or you run `plan --ny`.

## Stores

| Store | Status | Notes |
|---|---|---|
| City Gross Ytterby | ✅ | Store number 3240, looked up from siteId 31 via the web shop's GraphQL. Search returns Ytterby's own range and prices |
| ICA Maxi Kungälv | coming in #8 | |
| Willys Kungälv | coming in #12 | |

`refresh` searches with each ingredient's Swedish search terms. A product counts only if its name contains the search words as whole words and the store's category fits, which keeps out cat food, ready meals and pickled cucumber. Eggs are compared per egg and converted to kr/kg at 60 g per egg. Products sold by weight count as loose weight. Responses are cached for 6 hours under `~/.cache/matplan/http`.

## Nutrition values

`refresh` also fetches nutrition values for ingredients that don't have any stored yet:
- **Livsmedelsverket's food database** (CC BY 4.0), by food number.
- **Open Food Facts** (ODbL), by barcode, for branded products Livsmedelsverket doesn't have: Keso 1.5% and Arla Greek yoghurt 0%.

Once fetched, values are kept in the database, and the plan names its sources. Until then, the catalog's hand-entered values are used.

## Status

Done:
- #2, #3, #4, #5, #6, #7, #9, #10, #11
- the split-trip comparison from #8

Left:
- #8: the ICA Maxi module.
- #12: Willys.
