"""Markdown-export av plan och inköpslista, för att läsa i mobilen i butiken."""

from pathlib import Path

from .inkop import Inkopslista
from .planerare import Maltid, Plan
from .text import datum, forpackning


def _maltid(rubrik: str, maltid: Maltid, personer: tuple[str, ...], antal: int = 0) -> list[str]:
    huvud = ["Ingrediens", *(f"{p.capitalize()} (g)" for p in personer)]
    if antal:
        huvud += ["Batch (g)"]
    rader = [f"### {rubrik}", "", "| " + " | ".join(huvud) + " |", "|" + "---|" * len(huvud)]
    portioner = [maltid.portion(p) for p in personer]
    for i, namn in enumerate(maltid.ingredienser):
        celler = [namn, *(str(p.rader[i].gram) for p in portioner)]
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
        rader += _maltid("Lunch och middag", block.batch, personer, antal=2 * dagar)
    rader += ["## Varje dag", ""]
    for maltid in plan.dagar[0].maltider:
        if maltid.typ not in ("lunch", "middag"):
            rader += _maltid(maltid.typ.capitalize(), maltid, personer)
    rader.append(f"Planerad kostnad: {plan.kr:.0f} kr ({plan.kr_per_dag:.0f} kr/dag)")
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
        return "\n".join(rader) + "\n"

    rader += [f"## {basta.butik}: {basta.kostnad:.2f} kr", ""]
    rader += ["- [ ] " + _kopstext(rad.ingrediens, rad.alternativ[basta.butik]) for rad in lista.rader if basta.butik in rad.alternativ]
    if basta.saknas:
        rader += ["", f"Saknas i {basta.butik}: {', '.join(basta.saknas)}"]
    if lista.besparing > 0.005:
        rader += ["", f"## Uppdelat på flera butiker: {lista.delad_kostnad:.2f} kr (spar {lista.besparing:.2f} kr)", ""]
        for rad in lista.rader:
            if rad.billigast:
                butik, kop = rad.billigast
                rader.append(f"- [ ] {_kopstext(rad.ingrediens, kop)} – {butik}")
    return "\n".join(rader) + "\n"


def _kopstext(ingrediens: str, kop) -> str:
    return f"{ingrediens}: {forpackning(kop)} {kop.produkt.namn} ({kop.kostnad:.2f} kr, {kop.produkt.kr_per_kg:.2f} kr/kg)"


def exportera(plan: Plan, lista: Inkopslista, katalog: Path) -> tuple[Path, Path]:
    katalog.mkdir(parents=True, exist_ok=True)
    planfil, listfil = katalog / "plan.md", katalog / "inkopslista.md"
    planfil.write_text(plan_markdown(plan), encoding="utf-8")
    listfil.write_text(lista_markdown(lista), encoding="utf-8")
    return planfil, listfil
