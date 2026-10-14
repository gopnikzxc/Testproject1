"""Bunkring: förslag på extra inköp när en proteinkälla som håller sig är på rea.

En vara föreslås bara om den
- är en proteinkälla (katalogkategori "protein"),
- håller sig (fryst eller torrvara; färskt bunkras aldrig),
- är på rea just nu, och
- ger mer protein per krona än snittet av dina proteinkällor.

Mängden begränsas av det lagringsutrymme som är kvar (tak minus det som redan
ligger i lagret av samma förvaringstyp). Bästa protein per krona får plats
först. Bunkring ligger utanför vecko- och månadsbudgeten.
"""

import math
from dataclasses import dataclass

from .butiker import Produkt
from .katalog import Ingrediens


@dataclass(frozen=True)
class Bunkring:
    ingrediens: str
    forvaring: str
    produkt: Produkt
    antal: int | None  # förpackningar; None betyder lösvikt
    gram: float
    kostnad: float
    protein_per_kr: float


def _protein_per_kr(ingrediens: Ingrediens, kr_per_kg: float) -> float:
    return ingrediens.protein_100g * 10 / kr_per_kg if kr_per_kg > 0 else 0.0


def forslag(
    katalog: tuple[Ingrediens, ...],
    produkter: dict[str, list[Produkt]],
    rea: frozenset[tuple[str, str]],
    lager: dict[str, float],
    utrymme_g: dict[str, float],
) -> list[Bunkring]:
    """`utrymme_g`: tak i gram per förvaringstyp ("fryst", "torrvara")."""
    per_namn = {i.namn: i for i in katalog}
    proteinkallor = [i for i in katalog if i.kategori == "protein" and produkter.get(i.namn)]
    if not proteinkallor:
        return []
    snitt = sum(
        _protein_per_kr(i, min(p.kr_per_kg for p in produkter[i.namn])) for i in proteinkallor
    ) / len(proteinkallor)

    kandidater = []
    for ingrediens in proteinkallor:
        if ingrediens.forvaring not in utrymme_g:
            continue
        pa_rea = [p for p in produkter[ingrediens.namn] if (p.butik, p.produkt_id) in rea]
        if not pa_rea:
            continue
        basta = min(pa_rea, key=lambda p: (p.kr_per_kg, p.butik, p.produkt_id))
        protein_per_kr = _protein_per_kr(ingrediens, basta.kr_per_kg)
        if protein_per_kr > snitt:
            kandidater.append((protein_per_kr, ingrediens, basta))

    kvar = {
        forvaring: tak - sum(gram for namn, gram in lager.items() if per_namn.get(namn) and per_namn[namn].forvaring == forvaring)
        for forvaring, tak in utrymme_g.items()
    }
    resultat = []
    for protein_per_kr, ingrediens, produkt in sorted(kandidater, key=lambda k: (-k[0], k[1].namn)):
        plats = kvar[ingrediens.forvaring]
        if produkt.forpackning_g:
            antal = math.floor(plats / produkt.forpackning_g + 1e-9)
            if antal < 1:
                continue
            gram, kostnad = antal * produkt.forpackning_g, antal * produkt.pris_kr
        else:
            antal, gram = None, math.floor(plats / 100) * 100.0  # lösvikt i hela hektogram
            if gram <= 0:
                continue
            kostnad = produkt.kr_per_kg * gram / 1000
        kvar[ingrediens.forvaring] -= gram
        resultat.append(Bunkring(ingrediens.namn, ingrediens.forvaring, produkt, antal, gram, kostnad, protein_per_kr))
    return resultat
