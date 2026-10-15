"""Slot ur näringsvärden och butikskategori.

| Slot | Regel |
|---|---|
| utesluten | juice, läsk, saft, sport- och energidryck, öl, cider m.m. (aldrig i planen) |
| mejeri | mjölk, växtdryck, proteindryck och proteinrik yoghurt, kvarg, keso |
| bär | butikens bärkategori |
| grönsaker | högst 60 kcal/100 g i en frukt-och-grönt- eller frysta-grönsaker-kategori |
| protein | minst 10 g protein per 100 kcal |
| kombination | rejält med både protein (minst 4 g/100 kcal) och kolhydrater (minst 20 % av kcal) |
| flingor | flingor och gryn där kolhydraterna dominerar (frukostens kolhydrat) |
| kolhydrater | kolhydraterna ger störst andel av kcal |

Reglerna prövas uppifrån och ned. Passar ingen (t.ex. ost, ägg, olja) blir
slotten None. De inbyggda grupperna har handvalda slotar, och varje produkts
eller grupps slot kan sättas för hand; det valet går före klassificeringen.
"""

SLOTAR = ("protein", "kolhydrater", "grönsaker", "mejeri", "flingor", "bär", "kombination", "utesluten")

# Delar av butikskategorin (gemener), City Gross och Willys.
UTESLUTNA_DRYCKER = (
    "juice", "läsk", "saft", "energidryck", "fruktdryck", "stilldrink", "cider", "/ öl", "alkoholfritt vin",
    "drinkmixer", "glögg", "dryck / vatten",
)
DRYCK_MEJERI = ("mjölk & dryck", "havre- & sojadryck", "filmjölk", "mjölk- & laktosfritt")
MEJERI = ("kvarg", "cottage", "yoghurt")
GRONT = ("frukt & grönt", "frysta grönsaker", "grönsaker", "potatis & rotsaker")
FLINGOR = ("flingor", "gryn", "müsli", "musli")

PROTEIN_PER_100_KCAL = 10
GRONSAK_KCAL = 60
KOMBINATION_PROTEIN = 4  # g per 100 kcal
KOMBINATION_KOLHYDRATER = 0.2  # andel av kcal
MEJERI_PROTEIN = 7  # g per 100 kcal


def klassificera(
    kcal: float | None,
    protein: float | None,
    kolhydrater: float | None = None,
    fett: float | None = None,
    kategori: str = "",
    namn: str = "",
) -> str | None:
    kategori, namn = kategori.casefold(), namn.casefold()
    if any(d in kategori for d in UTESLUTNA_DRYCKER) and "protein" not in namn:
        return "utesluten"
    if any(d in kategori for d in DRYCK_MEJERI) or (kategori.startswith("dryck") and "protein" in namn):
        return "mejeri"
    if not kcal or protein is None:
        return None
    protein_tathet = 100 * protein / kcal
    if any(m in kategori for m in MEJERI) and protein_tathet >= MEJERI_PROTEIN:
        return "mejeri"
    if "bär" in kategori:
        return "bär"
    if kcal <= GRONSAK_KCAL and any(g in kategori for g in GRONT) and not kategori.endswith("/ frukt"):
        return "grönsaker"
    if protein_tathet >= PROTEIN_PER_100_KCAL:
        return "protein"
    if kolhydrater is None:
        return None
    kolhydratandel = 4 * kolhydrater / kcal
    if protein_tathet >= KOMBINATION_PROTEIN and kolhydratandel >= KOMBINATION_KOLHYDRATER:
        return "kombination"
    if 4 * kolhydrater >= 4 * protein and 4 * kolhydrater >= 9 * (fett or 0):
        return "flingor" if any(f in kategori for f in FLINGOR) else "kolhydrater"
    return None
