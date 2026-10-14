"""Interaktivt terminalgränssnitt (Textual) ovanpå matplan-kärnan.

Allt hämtas från kärnans kommandon; gränssnittet innehåller ingen egen logik.
"""

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import DataTable, Footer, Header, Input, Static, TabbedContent, TabPane

from .core import DAGAR_PER_MANAD, Matplan, PlaneringsFel
from .export import exportera
from .naring import KALLHANVISNING
from .text import datum, forpackning


class MatplanApp(App):
    TITLE = "matplan"
    CSS = """
    TabbedContent { height: 1fr; }
    TabPane { height: 1fr; }
    DataTable { height: 1fr; }
    #summa { height: auto; padding: 0 1; background: $boost; }
    """
    BINDINGS = [
        Binding("b", "byt", "Byt ingrediens"),
        Binding("k", "kopt", "Köpt"),
        Binding("l", "lagat", "Lagat block"),
        Binding("t", "ta_bunkring", "Bunkra vald"),
        Binding("r", "hamta", "Hämta priser"),
        Binding("e", "exportera", "Exportera"),
        Binding("n", "ny_plan", "Ny plan"),
        Binding("q", "quit", "Avsluta"),
    ]

    def __init__(self, karna: Matplan, exportmapp: Path = Path("matplan-export")):
        super().__init__()
        self.karna = karna
        self.exportmapp = exportmapp
        self.summa_text = ""
        self._markorer: dict[str, int] = {}  # markörens rad per tabell, så den står kvar efter uppdatering

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent(id="flikar"):
            with TabPane("Plan", id="plan"):
                yield DataTable(id="plantabell", cursor_type="row")
            with TabPane("Inköpslista", id="lista"):
                yield DataTable(id="listtabell", cursor_type="row")
            with TabPane("Lager", id="lager"):
                yield DataTable(id="lagertabell", cursor_type="row")
                yield Input(placeholder="Sätt lager: <ingrediens> <gram>, t.ex. Havregryn 750", id="lagerinmatning")
            with TabPane("Bunkring", id="bunkring"):
                yield DataTable(id="bunkringstabell", cursor_type="row")
            with TabPane("Priser", id="priser"):
                yield DataTable(id="pristabell", cursor_type="row")
            with TabPane("Inställningar", id="installningar"):
                yield DataTable(id="installningstabell", cursor_type="row")
                yield Input(placeholder="Ändra: <nyckel> <värde>, t.ex. veckobudget 1300", id="installningsinmatning")
        yield Static(id="summa")
        yield Footer()

    def on_mount(self) -> None:
        self.uppdatera()
        self.query_one("#plantabell", DataTable).focus()

    # --- Visning -------------------------------------------------------------

    def uppdatera(self) -> None:
        try:
            plan = self.karna.plan()
            lista = self.karna.inkopslista()
        except PlaneringsFel as fel:
            self._visa_summa(f"[red]{fel}[/red]")
            return
        self._fyll_plan(plan)
        self._fyll_lista(lista)
        self._fyll_lager()
        self._fyll_bunkring()
        self._fyll_priser(plan)
        self._fyll_installningar()

        inst = self.karna.installningar()
        delar = [
            f"Matkostnad {plan.kr_per_dag * 7:.0f} kr/vecka av {inst['veckobudget']:.0f} · "
            f"{plan.kr_per_dag * DAGAR_PER_MANAD:.0f} kr/månad av {inst['manadsbudget']:.0f}",
            " · ".join(
                f"{p.namn.capitalize()} {plan.dagar[0].kcal(p.namn):.0f} kcal / {plan.dagar[0].protein(p.namn):.0f} g protein"
                for p in plan.profiler
            ),
        ]
        if lista.basta_butik:
            delar.append(f"Inköp {lista.basta_butik.butik}: {lista.basta_butik.kostnad:.0f} kr")
        if plan.aktiv:
            delar.append("köpt plan (n = ny plan)")
        self._visa_summa("  |  ".join(delar))

    def _visa_summa(self, text: str) -> None:
        self.summa_text = text
        self.query_one("#summa", Static).update(text)

    def _tabell(self, id: str, *kolumner: str) -> DataTable:
        tabell = self.query_one(f"#{id}", DataTable)
        self._markorer[id] = tabell.cursor_row
        tabell.clear(columns=True)
        tabell.add_columns(*kolumner)
        return tabell

    def _aterstall(self, tabell: DataTable) -> None:
        rad = self._markorer.pop(tabell.id, 0)
        if tabell.row_count:
            tabell.move_cursor(row=min(rad, tabell.row_count - 1))

    def _fyll_plan(self, plan) -> None:
        personer = tuple(p.namn for p in plan.profiler)
        tabell = self._tabell("plantabell", "Måltid", "Slot", "Ingrediens", *(f"{p.capitalize()} (g)" for p in personer), "kr")
        for nummer, block in enumerate(plan.block, start=1):
            rubrik = f"Block {nummer}: {datum(block.dagar[0].datum)}–{datum(block.dagar[-1].datum)}"
            portioner = [block.batch.portion(p) for p in personer]
            for i, rad in enumerate(portioner[0].rader):
                namn = f"{rad.namn} (rea)" if rad.namn in plan.rea else rad.namn
                tabell.add_row(
                    rubrik if i == 0 else "", rad.slot, namn, *(str(p.rader[i].gram) for p in portioner),
                    f"{sum(p.rader[i].kr for p in portioner):.2f}", key=f"block:{nummer}:{rad.slot}",
                )
        for maltid in plan.dagar[0].maltider:
            if maltid.typ in ("lunch", "middag"):
                continue
            portioner = [maltid.portion(p) for p in personer]
            for i, rad in enumerate(portioner[0].rader):
                tabell.add_row(
                    maltid.typ.capitalize() if i == 0 else "", rad.slot, rad.namn,
                    *(str(p.rader[i].gram) for p in portioner), f"{sum(p.rader[i].kr for p in portioner):.2f}",
                    key=f"fast:{maltid.typ}:{i}",
                )
        self._aterstall(tabell)

    def _fyll_lista(self, lista) -> None:
        tabell = self._tabell("listtabell", "Vara", "Produkt", "Butik", "Antal", "kr/kg", "kr")
        for rad in lista.rader:
            if rad.billigast is None:
                tabell.add_row(rad.ingrediens, "platshållarpris", "", f"{rad.gram} g", "", f"{rad.platshallar_kr:.2f}")
                continue
            butik = lista.basta_butik.butik if lista.basta_butik and lista.basta_butik.butik in rad.alternativ else rad.billigast[0]
            kop = rad.alternativ[butik]
            tabell.add_row(
                rad.ingrediens, kop.produkt.namn + (" (rea)" if kop.rea else ""), butik, forpackning(kop),
                f"{kop.produkt.kr_per_kg:.2f}", f"{kop.kostnad:.2f}",
            )
        for total in lista.butiker:
            tabell.add_row("", f"Allt i {total.butik}", "", "", "", f"{total.kostnad:.2f}")
        if lista.butiker:
            tabell.add_row("", "Uppdelat (billigast per vara)", "", "", "", f"{lista.delad_kostnad:.2f}")
        for b in lista.bunkring:
            tabell.add_row(b.ingrediens, f"Bunkring: {b.produkt.namn}", b.produkt.butik, f"{b.gram / 1000:g} kg", "", f"{b.kostnad:.2f}")
        self._aterstall(tabell)

    def _fyll_lager(self) -> None:
        tabell = self._tabell("lagertabell", "Vara", "Gram")
        for namn, gram in self.karna.lager().items():
            tabell.add_row(namn, f"{gram:.0f}", key=namn)
        self._aterstall(tabell)

    def _fyll_bunkring(self) -> None:
        tabell = self._tabell("bunkringstabell", "Vara", "Produkt", "Butik", "Mängd", "g protein/kr", "kr")
        for b in self.karna.bunkra():
            tabell.add_row(
                b.ingrediens, b.produkt.namn, b.produkt.butik, f"{b.gram / 1000:g} kg",
                f"{b.protein_per_kr:.2f}", f"{b.kostnad:.2f}", key=b.ingrediens,
            )
        self._aterstall(tabell)

    def _fyll_priser(self, plan) -> None:
        tabell = self._tabell("pristabell", "Ingrediens", "Billigast", "Butik", "kr/kg", "")
        for namn, produkt, rea, last in self.karna.prisoversikt():
            if produkt is None:
                tabell.add_row(namn, "inget butikspris", "", "", "")
                continue
            tabell.add_row(
                namn, produkt.namn, produkt.butik, f"{produkt.kr_per_kg:.2f}",
                " ".join(t for t, pa in (("rea", rea), ("låst", last)) if pa),
            )
        if plan.priser_hamtade:
            tabell.add_row("", f"Hämtade {plan.priser_hamtade:%Y-%m-%d %H:%M}", "", "", "")
        for kalla in plan.naringskallor:
            tabell.add_row("", KALLHANVISNING[kalla], "", "", "")
        self._aterstall(tabell)

    def _fyll_installningar(self) -> None:
        tabell = self._tabell("installningstabell", "Nyckel", "Värde")
        for nyckel, varde in self.karna.installningar().items():
            tabell.add_row(nyckel, f"{varde:g}", key=nyckel)
        self._aterstall(tabell)

    # --- Åtgärder --------------------------------------------------------------

    def _gor(self, atgard, meddelande=None) -> None:
        try:
            resultat = atgard()
        except (PlaneringsFel, KeyError) as fel:
            self.notify(str(fel.args[0]), severity="error")
            return
        self.uppdatera()
        if meddelande:
            self.notify(meddelande(resultat) if callable(meddelande) else meddelande)

    def _vald_nyckel(self, tabell_id: str) -> str | None:
        tabell = self.query_one(f"#{tabell_id}", DataTable)
        if not tabell.row_count:
            return None
        return tabell.coordinate_to_cell_key(tabell.cursor_coordinate).row_key.value

    def _valt_block(self) -> tuple[int, str] | None:
        nyckel = self._vald_nyckel("plantabell") or ""
        if not nyckel.startswith("block:"):
            return None
        _, block, slot = nyckel.split(":")
        return int(block), slot

    def action_byt(self) -> None:
        valt = self._valt_block()
        if valt is None:
            self.notify("Välj en rad i ett blocks lunch och middag först.", severity="warning")
            return
        block, slot = valt
        self._gor(
            lambda: self.karna.byt(block, slot),
            lambda plan: f"Block {block}: {', '.join(plan.block[block - 1].batch.ingredienser)}",
        )

    def action_kopt(self) -> None:
        self._gor(self.karna.kopt, lambda kopt: f"Lagt {len(kopt)} varor i lagret. Planen är nu köpt.")

    def action_lagat(self) -> None:
        block = (self._valt_block() or (1, ""))[0]
        self._gor(
            lambda: self.karna.lagat(block=block),
            lambda varningar: "; ".join(varningar) or f"Block {block} draget från lagret.",
        )

    def action_ta_bunkring(self) -> None:
        ingrediens = self._vald_nyckel("bunkringstabell")
        if ingrediens is None:
            self.notify("Inget bunkringsförslag att ta.", severity="warning")
            return
        self._gor(lambda: self.karna.acceptera_bunkring(ingrediens), f"{ingrediens} ligger nu på inköpslistan.")

    def action_ny_plan(self) -> None:
        self._gor(lambda: self.karna.plan(ny=True), "Ny plan.")

    def action_exportera(self) -> None:
        self._gor(
            lambda: exportera(self.karna.plan(), self.karna.inkopslista(), self.exportmapp),
            lambda filer: f"Sparade {filer[0]} och {filer[1]}",
        )

    def action_hamta(self) -> None:
        self.notify("Hämtar priser … det tar runt en minut.")
        self.run_worker(self._hamta, thread=True, exclusive=True)

    def _hamta(self) -> None:
        resultat = self.karna.refresh()
        delar = [f"{butik}: {antal}" for butik, antal in resultat.antal_produkter.items()]
        delar += [f"{butik}: {fel}" for butik, fel in resultat.fel.items()]
        self.call_from_thread(self.uppdatera)
        self.call_from_thread(self.notify, "Priser hämtade. " + " · ".join(delar) if delar else "Inga butiker.")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        event.input.value = ""
        if not text or " " not in text:
            return
        nyckel, varde = text.rsplit(" ", 1)
        try:
            tal = float(varde.replace(",", "."))
        except ValueError:
            self.notify(f"{varde} är inget tal.", severity="error")
            return
        if event.input.id == "installningsinmatning":
            self._gor(lambda: self.karna.satt_installning(nyckel, tal), f"{nyckel} = {tal:g}")
        else:
            self._gor(lambda: self.karna.satt_lager(nyckel, tal), f"{nyckel}: {tal:g} g")
