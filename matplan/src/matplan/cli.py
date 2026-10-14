"""Kommandoradsskal ovanpå matplan-kärnan."""

import argparse
import os
from datetime import date
from pathlib import Path

from rich.console import Console
from rich.table import Table

from .core import Matplan, PlaneringsFel
from .planerare import Maltid, Plan


def _db_sokvag() -> Path:
    if miljo := os.environ.get("MATPLAN_DB"):
        return Path(miljo)
    return Path.home() / ".local" / "share" / "matplan" / "matplan.db"


VECKODAGAR = ("mån", "tis", "ons", "tor", "fre", "lör", "sön")
MANADER = ("jan", "feb", "mar", "apr", "maj", "jun", "jul", "aug", "sep", "okt", "nov", "dec")


def _datum(d: date) -> str:
    return f"{VECKODAGAR[d.weekday()]} {d.day} {MANADER[d.month - 1]}"


def _maltidstabell(titel: str, maltid: Maltid, personer: tuple[str, ...], antal: int = 0) -> Table:
    """Tabell med en kolumn per person; med antal > 0 även batchens totalmängd."""
    tabell = Table(title=titel, title_justify="left")
    tabell.add_column("Ingrediens")
    for person in personer:
        tabell.add_column(f"{person.capitalize()} (g)", justify="right")
    if antal:
        tabell.add_column("Batch (g)", justify="right")
        tabell.add_column("Batch (kr)", justify="right")

    portioner = [maltid.portion(p) for p in personer]
    for i, namn in enumerate(maltid.ingredienser):
        rader = [p.rader[i] for p in portioner]
        celler = [namn, *(f"{r.gram}" for r in rader)]
        if antal:
            celler += [f"{sum(r.gram for r in rader) * antal}", f"{sum(r.kr for r in rader) * antal:.2f}"]
        tabell.add_row(*celler)
    tabell.add_section()
    extra = ["", ""] if antal else []
    tabell.add_row("kcal", *(f"{p.kcal:.0f}" for p in portioner), *extra, style="bold")
    tabell.add_row("Protein (g)", *(f"{p.protein:.1f}" for p in portioner), *extra, style="bold")
    tabell.add_row("Pris (kr)", *(f"{p.kr:.2f}" for p in portioner), *extra, style="bold")
    tabell.caption = (
        f"Protein {maltid.protein_tathet:.1f} g/100 kcal · Volym {maltid.volym:.2f} g/kcal · "
        f"{maltid.kr_per_g_protein:.2f} kr/g protein"
    )
    tabell.caption_justify = "left"
    return tabell


def _visa_plan(konsol: Console, plan: Plan) -> None:
    personer = tuple(p.namn for p in plan.profiler)
    for nummer, block in enumerate(plan.block, start=1):
        dagar = len(block.dagar)
        konsol.print(
            f"[bold]Block {nummer}: {_datum(block.dagar[0].datum)} – {_datum(block.dagar[-1].datum)} "
            f"({dagar} {'dag' if dagar == 1 else 'dagar'})[/bold]"
        )
        konsol.print(_maltidstabell("Lunch och middag", block.batch, personer, antal=2 * dagar))

    konsol.print("[bold]Varje dag[/bold]")
    for maltid in plan.dagar[0].maltider:
        if maltid.typ not in ("lunch", "middag"):
            konsol.print(_maltidstabell(maltid.typ.capitalize(), maltid, personer))

    summor = Table(title="Dagssummor", title_justify="left")
    summor.add_column("Dag")
    for person in personer:
        summor.add_column(f"{person.capitalize()} kcal", justify="right")
        summor.add_column(f"{person.capitalize()} protein (g)", justify="right")
    summor.add_column("Pris (kr)", justify="right")
    for dag in plan.dagar:
        celler = [_datum(dag.datum)]
        for person in personer:
            celler += [f"{dag.kcal(person):.0f}", f"{dag.protein(person):.1f}"]
        summor.add_row(*celler, f"{dag.kr:.2f}")
    konsol.print(summor)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="matplan", description="Måltidsplanerare")
    kommandon = parser.add_subparsers(dest="kommando", required=True)
    kommandon.add_parser("plan", help="Visa ett tredagarsblock")
    inst = kommandon.add_parser("installningar", help="Visa eller ändra inställningar")
    inst.add_argument("nyckel", nargs="?")
    inst.add_argument("varde", nargs="?", type=float)
    args = parser.parse_args(argv)

    konsol = Console()
    app = Matplan(_db_sokvag())

    if args.kommando == "plan":
        try:
            _visa_plan(konsol, app.plan())
        except PlaneringsFel as fel:
            konsol.print(f"[red]{fel}[/red]")
            return 1
        return 0

    if args.varde is not None:
        try:
            app.satt_installning(args.nyckel, args.varde)
        except KeyError as fel:
            konsol.print(f"[red]{fel.args[0]}[/red]")
            return 1
    installningar = app.installningar()
    if args.nyckel and args.nyckel not in installningar:
        konsol.print(f"[red]Okänd inställning: {args.nyckel}[/red]")
        return 1
    for nyckel, varde in installningar.items():
        if args.nyckel in (None, nyckel):
            konsol.print(f"{nyckel} = {varde:g}")
    return 0
