# matplan

Personal meal planner: high protein, low kcal, high volume, with current grocery prices from stores in Kungälv and Ytterby. Spec: gopnikzxc/Testproject1#1.

## Get started

```
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/matplan gui                               # interactive terminal GUI (see below)
.venv/bin/matplan plan                              # plan the coming days in 3-day blocks
.venv/bin/matplan byt 1 kolhydrater Potatis         # swap an ingredient in block 1 (without an ingredient: next in turn)
.venv/bin/matplan refresh                           # sync the store's whole food range + current prices
.venv/bin/matplan sök tonfisk                       # search the synced range (brand, pack, price, kcal, protein)
.venv/bin/matplan lista                             # shopping list: whole packages, kr/kg, single store vs split
.venv/bin/matplan export [folder]                   # save plan.md and inkopslista.md for your phone
.venv/bin/matplan produkter Kycklingfilé            # fetched products with ids
.venv/bin/matplan lås Kycklingfilé "City Gross Ytterby" <id>   # always use that product there
.venv/bin/matplan bunkra [--ta X | --ta-bort X]    # stock-up suggestions; --ta adds one to the shopping list
.venv/bin/matplan köpt [--butik B | --delad]        # add the shopping list to inventory; the plan becomes active
.venv/bin/matplan lagat [--block N]                 # subtract a cooked batch from inventory
.venv/bin/matplan lager [ingredient grams]          # show inventory or set an amount
.venv/bin/matplan plan --ny                         # drop the bought plan and plan again
.venv/bin/matplan installningar                     # list settings
.venv/bin/matplan installningar jag.kcal_mal 1800   # change a setting
.venv/bin/pytest
```

The database is stored at `~/.local/share/matplan/matplan.db`. Set `MATPLAN_DB` to use a different file.

## Terminal GUI

`matplan gui` opens a Textual app with tabs for Plan, Inköpslista, Lager, Bunkring, Priser and Inställningar. Everything comes from the same commands as the CLI. The bottom line shows cost against the budget, each person's kcal and protein, and the cheapest store.

| Key | Does |
|---|---|
| `b` | Swaps the selected ingredient in a block's lunch and dinner. Totals and the list update right away |
| `k` | Bought: puts the shopping list (and accepted stock-ups) into inventory |
| `l` | Cooked: subtracts the selected block's batch from inventory |
| `t` | Accepts the selected stock-up suggestion (Bunkring tab) |
| `r` | Refreshes prices in the background |
| `e` | Exports plan.md and inkopslista.md |
| `n` | New plan, dropping the bought plan and any swaps |
| `q` | Quit |

Settings and inventory amounts are changed in the input box at the bottom of their tabs, for example `veckobudget 1300` or `Havregryn 750`.

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
| `rea_procent` / `rea_veckor` | 25 / 8 | A price is a deal when it is at least this many percent below the median of the last weeks |
| `frys_kg` / `torr_kg` | 10 / 2 | Storage space for stock-up in the freezer and the dry store. What's already in stock counts against it |
| `butik_citygross` / `butik_willys` | 1 / 0 | Which stores are fetched and planned against. A store that's off is skipped by `refresh`, and its saved prices are ignored |

Planning uses inventory first: whatever is already at home costs 0 kr, and the shopping list only covers what's missing. Once you've run `köpt`, that plan stays in place until it ends or you run `plan --ny`.

## The store's range

`refresh` syncs City Gross's whole food range for your store, about 7,400 products, in pages of 2000. Non-food, sweets, snacks, ice cream, buns, biscuits, spices, sauces and butter are left out. Each product stores brand, name, pack size, barcode, category, price, kr/kg and nutrition per 100 g from the store's data (other explicit bases are scaled to 100). Products that disappear are marked as no longer sold. Prices are saved as history per product. `matplan sök` searches by whole words in brand, name and description.

## Deals

Every refresh is saved as price history, one price per day. With at least 3 days of history in the window, a product is a deal when it is `rea_procent` below the median. Before that, the store's own offer flag decides, and that flag also covers multi-buy offers. Deals are marked "(rea)" in the plan, the shopping list and the export.

A fresh protein deal (eggs, dairy, fresh meat) that gives more protein per krona than a frozen or dry item in stock goes first. That stock item then costs its normal price in the plan instead of 0 kr, because it keeps. The plan says when this happens.

## Stock-up

`matplan bunkra` suggests extra purchases. An item qualifies when it is a protein source, keeps (frozen or dry), is on a deal right now, and gives more protein per krona than the average of your protein sources. The best protein per krona gets space first. Quantities come in whole packages, within the space left in the freezer or dry store. A suggestion you accept with `--ta` goes in a separate section of the shopping list, outside the budget, and `köpt` puts it into inventory.

## Stores

| Store | Status | Notes |
|---|---|---|
| City Gross Ytterby | ✅ | Store number 3240, looked up from siteId 31 via the web shop's GraphQL. Search returns Ytterby's own range and prices |
| Willys Kungälv | ✅ (off by default; `matplan installningar butik_willys 1` turns it on) | Store 2104 (Komarken). The store is selected in the session with a CSRF token and `store/activate`. Results have no category, so the module filters with the search's category facet |

`refresh` searches with each ingredient's Swedish search terms. A product counts only if its name contains the search words as whole words and the store's category fits, which keeps out cat food, ready meals and pickled cucumber. Eggs are compared per egg and converted to kr/kg at 60 g per egg. Products sold by weight count as loose weight. Products can also be excluded by word, which drops for example a frozen smoothie listed among the berries. Responses are cached for 6 hours under `~/.cache/matplan/http`. A full refresh against both stores takes just over a minute, because requests are spaced out.

## Nutrition values

`refresh` also fetches nutrition values for ingredients that don't have any stored yet:
- **Livsmedelsverket's food database** (CC BY 4.0), by food number.
- **Open Food Facts** (ODbL), by barcode, for branded products Livsmedelsverket doesn't have: Keso 1.5% and Arla Greek yoghurt 0%.

Once fetched, values are kept in the database, and the plan names its sources. Until then, the catalog's hand-entered values are used.

## Status

Done: #2–#7 and #9–#15, which is the whole spec in #1

ICA Maxi (#8) is shelved because ICA blocks automated access.
