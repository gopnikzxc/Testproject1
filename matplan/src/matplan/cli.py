"""Kommandoradsskal ovanpå matplan-kärnan."""

import argparse
import os
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.table import Table

from .butiker import Butik
from .butiker.citygross import CityGross
from .butiker.willys import Willys
from .core import DAGAR_PER_MANAD, Hamtningsresultat, Matplan, PlaneringsFel
from .export import exportera
from .http import HttpKlient
from .inkop import Inkopslista
from .naring import KALLHANVISNING, Livsmedelsverket, OpenFoodFacts
from .planerare import Maltid, Plan
from .text import datum as _datum
from .text import forpackning


def _db_sokvag() -> Path:
    if miljo := os.environ.get("MATPLAN_DB"):
        return Path(miljo)
    return Path.home() / ".local" / "share" / "matplan" / "matplan.db"


def _http() -> HttpKlient:
    return HttpKlient(Path.home() / ".cache" / "matplan" / "http")


def _butiker() -> tuple[Butik, ...]:
    http = _http()
    return (CityGross(http), Willys(http))


def _naringskallor() -> tuple[Livsmedelsverket | None, OpenFoodFacts | None]:
    http = _http()
    return Livsmedelsverket(http), OpenFoodFacts(http)


def _maltidstabell(
    titel: str, maltid: Maltid, personer: tuple[str, ...], antal: int = 0, rea: tuple[str, ...] = ()
) -> Table:
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
        celler = [f"{namn} [green](rea)[/green]" if namn in rea else namn, *(f"{r.gram}" for r in rader)]
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


def _visa_prisstatus(konsol: Console, plan: Plan) -> None:
    if plan.priser_hamtade is None:
        konsol.print("[yellow]Platshållarpriser – kör `matplan refresh` för butikspriser.[/yellow]")
        return
    dagar = (datetime.now() - plan.priser_hamtade).days
    konsol.print(f"Priser hämtade {plan.priser_hamtade:%Y-%m-%d %H:%M} ({dagar} {'dag' if dagar == 1 else 'dagar'} sedan)")
    if plan.utan_butikspris:
        konsol.print(f"[yellow]Platshållarpris för: {', '.join(plan.utan_butikspris)}[/yellow]")


def _visa_kallor(konsol: Console, plan: Plan) -> None:
    if not plan.naringskallor:
        konsol.print("[dim]Näringsvärden: handinmatade ungefärliga värden – kör `matplan refresh`.[/dim]")
    for kalla in plan.naringskallor:
        konsol.print(f"[dim]{KALLHANVISNING[kalla]}[/dim]")


def _visa_varningar(konsol: Console, plan: Plan) -> None:
    for varning in plan.varningar:
        konsol.print(f"[yellow]{varning}[/yellow]")


def _visa_budget(konsol: Console, app: Matplan, plan: Plan) -> None:
    inst = app.installningar()
    konsol.print(
        f"Planerad matkostnad: {plan.kr_per_dag * 7:.0f} kr/vecka av {inst['veckobudget']:.0f} · "
        f"{plan.kr_per_dag * DAGAR_PER_MANAD:.0f} kr/månad av {inst['manadsbudget']:.0f}"
    )


def _visa_hamtning(konsol: Console, resultat: Hamtningsresultat) -> None:
    if not resultat.antal_produkter and not resultat.fel:
        konsol.print("[yellow]Inga butiker är konfigurerade ännu.[/yellow]")
    for butik, antal in resultat.antal_produkter.items():
        konsol.print(f"{butik}: {antal} produkter")
    for butik, fel in resultat.fel.items():
        konsol.print(f"[red]{butik}: {fel}[/red]")
    if resultat.naring_hamtad:
        konsol.print(f"Näringsvärden hämtade för {resultat.naring_hamtad} ingredienser")
    for ingrediens, fel in resultat.naring_fel.items():
        konsol.print(f"[yellow]{ingrediens}: {fel}[/yellow]")


def _visa_plan(konsol: Console, app: Matplan, plan: Plan) -> None:
    personer = tuple(p.namn for p in plan.profiler)
    if plan.aktiv:
        konsol.print("[cyan]Visar den köpta planen – kör `matplan plan --ny` för att planera om.[/cyan]")
    _visa_prisstatus(konsol, plan)
    _visa_varningar(konsol, plan)
    for nummer, block in enumerate(plan.block, start=1):
        dagar = len(block.dagar)
        konsol.print(
            f"[bold]Block {nummer}: {_datum(block.dagar[0].datum)} – {_datum(block.dagar[-1].datum)} "
            f"({dagar} {'dag' if dagar == 1 else 'dagar'})[/bold]"
        )
        konsol.print(_maltidstabell("Lunch och middag", block.batch, personer, antal=2 * dagar, rea=plan.rea))

    konsol.print("[bold]Varje dag[/bold]")
    for maltid in plan.dagar[0].maltider:
        if maltid.typ not in ("lunch", "middag"):
            konsol.print(_maltidstabell(maltid.typ.capitalize(), maltid, personer, rea=plan.rea))

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
    _visa_budget(konsol, app, plan)
    _visa_kallor(konsol, plan)


def _visa_lista(konsol: Console, app: Matplan, lista: Inkopslista) -> None:
    basta = lista.basta_butik
    if basta is None:
        tabell = Table(title="Inköpslista (platshållarpriser)", title_justify="left")
        tabell.add_column("Vara")
        tabell.add_column("Mängd (g)", justify="right")
        tabell.add_column("Ca kr", justify="right")
        for rad in lista.rader:
            tabell.add_row(rad.ingrediens, f"{rad.gram}", f"{rad.platshallar_kr:.2f}")
        tabell.add_section()
        tabell.add_row("Totalt", "", f"{lista.platshallar_kr:.2f}", style="bold")
        konsol.print(tabell)
    else:
        tabell = Table(title=f"Inköpslista – {basta.butik}", title_justify="left")
        for rubrik, just in (("Vara", "left"), ("Produkt", "left"), ("Antal", "right"), ("kr/kg", "right"), ("kr", "right")):
            tabell.add_column(rubrik, justify=just)
        for rad in lista.rader:
            kop = rad.alternativ.get(basta.butik)
            if kop is None:
                tabell.add_row(rad.ingrediens, "[red]saknas i butiken[/red]", "", "", "")
                continue
            tabell.add_row(
                rad.ingrediens,
                f"{kop.produkt.namn} ({kop.produkt.produkt_id})" + (" [green](rea)[/green]" if kop.rea else ""),
                forpackning(kop),
                f"{kop.produkt.kr_per_kg:.2f}", f"{kop.kostnad:.2f}",
            )
        tabell.add_section()
        tabell.add_row("Totalt", "", "", "", f"{basta.kostnad:.2f}", style="bold")
        konsol.print(tabell)

        jamforelse = Table(title="Butiker", title_justify="left")
        jamforelse.add_column("Alternativ")
        jamforelse.add_column("Totalt (kr)", justify="right")
        jamforelse.add_column("Saknas")
        for total in lista.butiker:
            jamforelse.add_row(total.butik, f"{total.kostnad:.2f}", ", ".join(total.saknas))
        jamforelse.add_row("Uppdelat (billigast per vara)", f"{lista.delad_kostnad:.2f}", "", style="bold")
        konsol.print(jamforelse)
        if lista.besparing > 0.005:
            konsol.print(f"Uppdelat på flera butiker sparar {lista.besparing:.2f} kr jämfört med {basta.butik}.")
    _visa_budget(konsol, app, app.plan())


def _visa_produkter(konsol: Console, app: Matplan, ingrediens: str) -> None:
    lasta = {butik: pid for (namn, butik), pid in app.lasningar().items() if namn == ingrediens}
    tabell = Table(title=f"Produkter för {ingrediens}", title_justify="left")
    for rubrik in ("Butik", "Id", "Produkt", "Förpackning", "Pris", "kr/kg", ""):
        tabell.add_column(rubrik)
    for p in app.produkter(ingrediens):
        tabell.add_row(
            p.butik, p.produkt_id, p.namn, f"{p.forpackning_g:g} g" if p.forpackning_g else "lösvikt",
            f"{p.pris_kr:.2f}", f"{p.kr_per_kg:.2f}", "låst" if lasta.get(p.butik) == p.produkt_id else "",
        )
    konsol.print(tabell)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="matplan", description="Måltidsplanerare")
    kommandon = parser.add_subparsers(dest="kommando", required=True)
    plan = kommandon.add_parser("plan", help="Planera kommande dagar i tredagarsblock")
    plan.add_argument("--ny", action="store_true", help="Släpp den köpta planen och planera om")
    kommandon.add_parser("lista", help="Inköpslista för planen")
    export = kommandon.add_parser("export", help="Spara plan och inköpslista som Markdown")
    export.add_argument("mapp", nargs="?", default="matplan-export")
    kommandon.add_parser("refresh", help="Hämta aktuella priser från butikerna")
    produkter = kommandon.add_parser("produkter", help="Visa hämtade produkter för en ingrediens")
    produkter.add_argument("ingrediens")
    las = kommandon.add_parser("lås", aliases=["las"], help="Lås en ingrediens till en produkt i en butik")
    las.add_argument("ingrediens", nargs="?")
    las.add_argument("butik", nargs="?")
    las.add_argument("produkt_id", nargs="?")
    las.add_argument("--ta-bort", action="store_true", help="Ta bort låset för ingrediens och butik")
    kopt = kommandon.add_parser("köpt", aliases=["kopt"], help="Lägg in inköpslistan i lagret")
    kopt.add_argument("--butik", help="Butiken där allt köptes (standard: bästa enskilda butik)")
    kopt.add_argument("--delad", action="store_true", help="Varje vara köptes i sin billigaste butik")
    lagat = kommandon.add_parser("lagat", help="Dra ett lagat blocks batch från lagret")
    lagat.add_argument("--block", type=int, default=1)
    lager = kommandon.add_parser("lager", help="Visa lagret eller sätt en varas mängd")
    lager.add_argument("ingrediens", nargs="?")
    lager.add_argument("gram", nargs="?", type=float)
    inst = kommandon.add_parser("installningar", help="Visa eller ändra inställningar")
    inst.add_argument("nyckel", nargs="?")
    inst.add_argument("varde", nargs="?", type=float)
    args = parser.parse_args(argv)

    konsol = Console()
    livsmedelsverket, openfoodfacts = _naringskallor()
    app = Matplan(_db_sokvag(), butiker=_butiker(), livsmedelsverket=livsmedelsverket, openfoodfacts=openfoodfacts)
    try:
        return _kor(konsol, app, args)
    except (PlaneringsFel, KeyError) as fel:
        konsol.print(f"[red]{fel.args[0]}[/red]")
        return 1


def _kor(konsol: Console, app: Matplan, args: argparse.Namespace) -> int:
    kommando = {"las": "lås", "kopt": "köpt"}.get(args.kommando, args.kommando)

    if kommando == "plan":
        _visa_plan(konsol, app, app.plan(ny=args.ny))
    elif kommando == "lista":
        _visa_lista(konsol, app, app.inkopslista())
    elif kommando == "export":
        planfil, listfil = exportera(app.plan(), app.inkopslista(), Path(args.mapp))
        konsol.print(f"Sparade {planfil} och {listfil}")
    elif kommando == "refresh":
        with konsol.status("Hämtar priser …") as status:
            resultat = app.refresh(framsteg=lambda butik, namn: status.update(f"{butik}: {namn} …"))
        _visa_hamtning(konsol, resultat)
        return 1 if resultat.fel and not resultat.antal_produkter else 0
    elif kommando == "produkter":
        _visa_produkter(konsol, app, args.ingrediens)
    elif kommando == "lås":
        if args.ta_bort:
            borttaget = app.ta_bort_las(args.ingrediens, args.butik)
            konsol.print("Låset borttaget." if borttaget else "Inget sådant lås fanns.")
        elif args.produkt_id:
            app.las(args.ingrediens, args.butik, args.produkt_id)
            konsol.print(f"{args.ingrediens} är låst till {args.produkt_id} i {args.butik}.")
        else:
            for (ingrediens, butik), produkt_id in app.lasningar().items():
                konsol.print(f"{ingrediens} – {butik}: {produkt_id}")
    elif kommando == "köpt":
        kopt = app.kopt(butik="delad" if args.delad else args.butik)
        for namn, gram in kopt.items():
            konsol.print(f"+ {namn}: {gram:.0f} g")
    elif kommando == "lagat":
        for varning in app.lagat(block=args.block):
            konsol.print(f"[yellow]{varning}[/yellow]")
        konsol.print(f"Block {args.block} draget från lagret.")
    elif kommando == "lager":
        if args.gram is not None:
            app.satt_lager(args.ingrediens, args.gram)
        for namn, gram in app.lager().items():
            konsol.print(f"{namn}: {gram:.0f} g")
    else:
        if args.varde is not None:
            app.satt_installning(args.nyckel, args.varde)
        installningar = app.installningar()
        if args.nyckel and args.nyckel not in installningar:
            raise KeyError(f"Okänd inställning: {args.nyckel}")
        for nyckel, varde in installningar.items():
            if args.nyckel in (None, nyckel):
                konsol.print(f"{nyckel} = {varde:g}")
    return 0
