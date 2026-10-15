# matplan

Personal meal planner: high protein, low kcal, high volume, with current grocery prices from stores in Kungälv and Ytterby. Spec: gopnikzxc/Testproject1#1.

## Get started

```
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/matplan gui                               # interactive terminal GUI (see below)
.venv/bin/matplan plan                              # plan the coming days in 3-day blocks
.venv/bin/matplan byt 1 kolhydrater Potatis         # swap an ingredient in block 1 (without an ingredient: next in turn)
.venv/bin/matplan butik "442 50"                    # City Gross stores, nearest first (or --sök Borås)
.venv/bin/matplan butik --välj "City Gross Borås"   # choose the store to plan against
.venv/bin/matplan refresh                           # sync the store's whole food range + current prices
.venv/bin/matplan sök tonfisk                       # search the synced range (price, kcal, protein, nutrition source, slot)
.venv/bin/matplan näring                            # nutrition matches for products without the store's values
.venv/bin/matplan näring --bekräfta "Spetskål"      # confirm the suggested match (or --lmv <number>); --sök <text> searches
.venv/bin/matplan slot "Keso 1,5 %" protein         # set a group's or product id's slot by hand (--ta-bort clears it)
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

`matplan gui` opens a Textual app with tabs for Plan, Inköpslista, Lager, Bunkring, Priser, Butik and Inställningar. Everything comes from the same commands as the CLI. The bottom line shows cost against the budget, each person's kcal and protein, the chosen store and the cheapest store.

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

In the Butik tab, type a postcode (nearest first) or a name/town in the input box, then press Enter on a store to choose it. Press `r` afterwards to sync its range.

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

Planning uses inventory first: whatever is already at home costs 0 kr, and the shopping list only covers what's missing. Once you've run `köpt`, that plan stays in place until it ends or you run `plan --ny`.

## The store's range

`refresh` syncs City Gross's whole food range for your store, about 7,400 products, in pages of 2000. Non-food, sweets, snacks, ice cream, buns, biscuits, spices, sauces and butter are left out. Each product stores brand, name, pack size, barcode, category, price, kr/kg and nutrition per 100 g from the store's data (other explicit bases are scaled to 100). Products that disappear are marked as no longer sold. Prices are saved as history per product. `matplan sök` searches by whole words in brand, name and description.

## Deals

Every refresh is saved as price history, one price per day. With at least 3 days of history in the window, a product is a deal when it is `rea_procent` below the median. Before that, the store's own offer flag decides, and that flag also covers multi-buy offers. Deals are marked "(rea)" in the plan, the shopping list and the export.

A fresh protein deal (eggs, dairy, fresh meat) that gives more protein per krona than a frozen or dry item in stock goes first. That stock item then costs its normal price in the plan instead of 0 kr, because it keeps. The plan says when this happens.

## Stock-up

`matplan bunkra` suggests extra purchases. An item qualifies when it is a protein source, keeps (frozen or dry), is on a deal right now, and gives more protein per krona than the average of your protein sources. The best protein per krona gets space first. Quantities come in whole packages, within the space left in the freezer or dry store. A suggestion you accept with `--ta` goes in a separate section of the shopping list, outside the budget, and `köpt` puts it into inventory.

## Stores

matplan plans against one store at a time. City Gross Ytterby is the default.

`matplan butik <postcode>` lists all City Gross stores, nearest first. The list comes from the web shop's store pages, which give each store's address, postcode and coordinates. Your postcode's position is taken from the store whose postcode is most like yours: longest shared start, then smallest numeric difference. Swedish postcodes are ordered geographically, so this is good enough to sort by distance. Distances are as the crow flies. `--sök` matches name, town or postcode.

`--välj` takes a store's name (`"City Gross Borås"`, or just `Borås`) and looks up its store number through the web shop's GraphQL (`lindbakstorenumber(siteId)`). The choice is saved as chain, store number and name. Prices and range are saved per store, so switching back to an earlier store brings back its range and deal history right away. Groups, inventory, locks and settings aren't affected by a switch. Databases from before the store picker get Ytterby, or Willys Kungälv if that was the only store turned on.

| Store | Status | Notes |
|---|---|---|
| City Gross (all 38 stores) | ✅ | Range sync and prices per store number. Ytterby is store 3240 (siteId 31) |
| Willys Kungälv | ⏸ (kept, not selectable in the picker) | Store 2104 (Komarken). The store is selected in the session with a CSRF token and `store/activate`. Results have no category, so the module filters with the search's category facet |

The plan works with ingredient groups (Kycklingfilé, Potatis, Keso …). The built-in groups are stored in the database the first time matplan runs. For City Gross, `refresh` doesn't search per group: each group is matched against the synced range. A product counts only if its name contains the group's first search word as a whole word, the other search words appear in the name or description, the store's category fits, and no excluded word is in the name. That keeps out cat food, ready meals, pickled cucumber and chicken sausage. For each group the plan uses the cheapest product by kr/kg, with that product's own price and nutrition. If the product lacks nutrition, the group's values are used. Products that are no longer sold aren't used.

Eggs are compared per egg and converted to kr/kg at 60 g per egg. Products sold by weight count as loose weight. Stores without range sync (Willys) are still searched per group with its Swedish search terms. Responses are cached for 6 hours under `~/.cache/matplan/http`.

## Nutrition values

Each product's nutrition per 100 g comes from the first of these that has it:
1. **The store's own values.**
2. **The product family's Livsmedelsverket match** (CC BY 4.0). A family is the product's group, or for a product outside the groups its normalised name. A built-in group's own Livsmedelsverket number is its confirmed match. For other families, `matplan näring` suggests the closest food from Livsmedelsverket's full list, downloaded once and kept in the database (for example "Vitkål Sverige" → "Vitkål"). Confirm it once with `--bekräfta`, or pick another with `--lmv <number>`. The match then applies to every product in the family, including new ones from later syncs.
3. **Open Food Facts** (ODbL), by the product's barcode. `refresh` asks once per barcode, and only for the groups' products that have nothing better.

Products with no nutrition after that stay searchable but aren't planned. A group where no product has nutrition is skipped by the planner, with a note. Search and the plan show each product's source, and the plan keeps the source credits.

`refresh` also fetches Livsmedelsverket values for the groups' own numbers and confirmed matches, and Open Food Facts values for Keso 1.5 % and Arla Greek yoghurt 0 %. Until fetched, a group uses the catalog's hand-entered values.

## Slots

Every product gets a slot from its nutrition and store category:

| Slot | Rule |
|---|---|
| utesluten | juice, soft drinks, squash, sports and energy drinks, beer, cider: never planned |
| mejeri | milk, plant drinks, protein drinks, and high-protein yoghurt, kvarg and cottage cheese |
| bär | the store's berry categories |
| grönsaker | at most 60 kcal/100 g in a fruit-and-veg or frozen-veg category |
| protein | at least 10 g protein per 100 kcal |
| kombination | at least 4 g protein per 100 kcal and at least 20 % of kcal from carbs (nuggets, fish fingers, beans, ready meals) |
| flingor | cereals and oats (breakfast carbs) |
| kolhydrater | carbs give the largest share of kcal |

If no rule fits (cheese, eggs, oil), the product has no slot. The built-in groups have hand-set slots. A group without a slot takes the slot of the product the plan buys. `matplan slot` sets any group's or product's slot by hand, and that wins over the classifier.

A combination item can fill the lunch/dinner protein slot. Its carbs count toward the meal's kcal, so the carb portion shrinks or is left out, and kcal ceilings and protein floors still hold. To meet 180 g protein within 2000 kcal, a combination item needs roughly 9–10 g protein per 100 kcal. Fish fingers and beans are well below that, so they rarely fit.

## Status

Done: #2–#7 and #9–#15, which is the whole spec in #1. From the second spec (#23): #24–#29.

ICA Maxi (#8) is shelved because ICA blocks automated access.
