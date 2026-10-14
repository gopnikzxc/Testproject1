"""Kommandoradsskal ovanpå matplan-kärnan."""

import argparse
import os
from pathlib import Path

from rich.console import Console
from rich.table import Table

from .core import Matplan, PlaneringsFel
from .planerare import Maltid, Plan


def _db_sokvag() -> Path:
    if miljo := os.environ.get("MATPLAN_DB"):
        return Path(miljo)
    return Path.home() / ".local" / "share" / "matplan" / "matplan.db"


def _maltidstabell(titel: str, maltid: Maltid) -> Table:
    tabell = Table(title=titel, title_justify="left")
    tabell.add_column("Ingrediens")
    tabell.add_column("Gram", justify="right")
    tabell.add_column("kcal", justify="right")
    tabell.add_column("Protein (g)", justify="right")
    tabell.add_column("Pris (kr)", justify="right")
    for rad in maltid.rader:
        tabell.add_row(rad.namn, f"{rad.gram}", f"{rad.kcal:.0f}", f"{rad.protein:.1f}", f"{rad.kr:.2f}")
    tabell.add_section()
    tabell.add_row("Summa", "", f"{maltid.kcal:.0f}", f"{maltid.protein:.1f}", f"{maltid.kr:.2f}", style="bold")
    return tabell


def _visa_plan(konsol: Console, plan: Plan) -> None:
    konsol.print(f"[bold]Block: {len(plan.dagar)} dagar, samma lunch och middag varje dag[/bold]")
    dag = plan.dagar[0]
    konsol.print(_maltidstabell("Lunch", dag.lunch))
    konsol.print(_maltidstabell("Middag", dag.middag))

    dagar = Table(title="Dagssummor", title_justify="left")
    dagar.add_column("Dag")
    dagar.add_column("kcal", justify="right")
    dagar.add_column("Protein (g)", justify="right")
    dagar.add_column("Pris (kr)", justify="right")
    for nummer, d in enumerate(plan.dagar, start=1):
        dagar.add_row(f"Dag {nummer}", f"{d.kcal:.0f}", f"{d.protein:.1f}", f"{d.kr:.2f}")
    konsol.print(dagar)


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
