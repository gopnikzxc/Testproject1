"""Markdown-export av plan och inköpslista, för att läsa i mobilen i butiken."""

from pathlib import Path

from .inkop import Inkopslista
from .naring import KALLHANVISNING
from .planerare import Maltid, Plan
from .text import datum, kr, listrad, naringstext


def _maltid(
    rubrik: str, maltid: Maltid, personer: tuple[str, ...], antal: int = 0, rea: tuple[str, ...] = ()
) -> list[str]:
    huvud = ["Ingrediens", *(f"{p.capitalize()} (g)" for p in personer)]
    if antal:
        huvud += ["Batch (g)"]
    rader = [f"### {rubrik}", "", "| " + " | ".join(huvud) + " |", "|" + "---|" * len(huvud)]
    portioner = [maltid.portion(p) for p in personer]
    for i, namn in enumerate(maltid.ingredienser):
        celler = [f"{namn} (rea)" if namn in rea else namn, *(str(p.rader[i].gram) for p in portioner)]
        if antal:
            celler.append(str(sum(p.rader[i].gram for p in portioner) * antal))
        rader.append("| " + " | ".join(celler) + " |")
    rader.append(
        "| **kcal / protein** | "
        + " | ".join(f"{p.kcal:.0f} / {p.protein:.0f} g" for p in portioner)
        + (" | |" if antal else " |")
    )
    return rader + [""]


def plan_markdown(plan: Plan) -> str:
    personer = tuple(p.namn for p in plan.profiler)
    rader = ["# Matplan", ""]
    for nummer, block in enumerate(plan.block, start=1):
        dagar = len(block.dagar)
        rader += [f"## Block {nummer}: {datum(block.dagar[0].datum)} – {datum(block.dagar[-1].datum)}", ""]
        rader += _maltid("Lunch och middag", block.batch, personer, antal=2 * dagar, rea=plan.rea)
    rader += ["## Varje dag", ""]
    for maltid in plan.dagar[0].maltider:
        if maltid.typ not in ("lunch", "middag"):
            rader += _maltid(maltid.typ.capitalize(), maltid, personer, rea=plan.rea)
    rader.append(f"Planerad kostnad: {plan.kr:.0f} kr ({plan.kr_per_dag:.0f} kr/dag)")
    if plan.produktkallor:
        rader += ["", f"Näring per vara: {naringstext(plan.produktkallor)}"]
    rader += ["", *(f"_{KALLHANVISNING[kalla]}_" for kalla in plan.naringskallor)]
    return "\n".join(rader) + "\n"


def lista_markdown(lista: Inkopslista) -> str:
    rader = ["# Inköpslista", ""]
    basta = lista.basta_butik
    if basta is None:
        rader += ["Inga butikspriser än; mängder i gram med platshållarpriser.", ""]
        rader += ["| Vara | Mängd | Ca kr |", "|---|---|---|"]
        for rad in lista.rader:
            rader.append(f"| {rad.ingrediens} | {rad.gram} g | {rad.platshallar_kr:.0f} |")
        rader += ["", f"**Totalt ca {lista.platshallar_kr:.0f} kr**"]
        return "\n".join(rader + _bunkring(lista)) + "\n"

    rader += [f"## {basta.butik}: {kr(basta.kostnad)}", ""]
    rader += ["- [ ] " + _kopstext(rad, rad.alternativ[basta.butik]) for rad in lista.rader if basta.butik in rad.alternativ]
    if basta.saknas:
        rader += ["", f"Saknas i {basta.butik}: {', '.join(basta.saknas)}"]
    if lista.besparing > 0.005:
        rader += ["", f"## Uppdelat på flera butiker: {kr(lista.delad_kostnad)} (spar {kr(lista.besparing)})", ""]
        for rad in lista.rader:
            if rad.billigast:
                butik, kop = rad.billigast
                rader.append(f"- [ ] {_kopstext(rad, kop)} – {butik}")
    return "\n".join(rader + _bunkring(lista)) + "\n"


def _bunkring(lista: Inkopslista) -> list[str]:
    if not lista.bunkring:
        return []
    rader = ["", f"## Bunkring (utanför budgeten): {kr(lista.bunkring_kr)}", ""]
    for b in lista.bunkring:
        rader.append(f"- [ ] {listrad(b.produkt, b.antal, b.gram, b.kostnad)} – {b.produkt.butik}")
    return rader


def _kopstext(rad, kop) -> str:
    rea = " (rea)" if kop.rea else ""
    return f"{listrad(kop.produkt, kop.antal, rad.gram, kop.kostnad)}{rea}"


def exportera(plan: Plan, lista: Inkopslista, katalog: Path) -> tuple[Path, Path]:
    katalog.mkdir(parents=True, exist_ok=True)
    planfil, listfil = katalog / "plan.md", katalog / "inkopslista.md"
    planfil.write_text(plan_markdown(plan), encoding="utf-8")
    listfil.write_text(lista_markdown(lista), encoding="utf-8")
    return planfil, listfil
