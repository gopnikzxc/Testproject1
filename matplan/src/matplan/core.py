"""matplan-kärnan: varje användningsfall som ett kommando.

CLI och (senare) Textual-GUI är tunna skal ovanpå den här klassen.
"""

import dataclasses
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable

from .bunkra import Bunkring, forslag
from .butiker import BUTIKSNYCKLAR, Butik, ButiksFel, Produkt, matchar, ratt_kategori, utesluten
from .inkop import Inkopslista, bygg_lista
from .katalog import STARTKATALOG, Ingrediens
from .lagring import Lagring
from .naring import Livsmedelsverket, NaringsFel, OpenFoodFacts
from .planerare import HUVUDSLOTAR, Plan, PlaneringsFel, Profil, Vikter, planera
from .rea import ar_rea

__all__ = ["Matplan", "PlaneringsFel", "PERSONER", "Hamtningsresultat", "DAGAR_PER_MANAD"]

# Barnet planeras inte (se spec #1).
PERSONER = ("jag", "fru")
# Månadstaket räknas på fyra veckor, så att 1250 kr/vecka och 5000 kr/månad går ihop.
DAGAR_PER_MANAD = 28


@dataclass
class Hamtningsresultat:
    tid: datetime
    antal_produkter: dict[str, int] = field(default_factory=dict)
    fel: dict[str, str] = field(default_factory=dict)
    naring_hamtad: int = 0
    naring_fel: dict[str, str] = field(default_factory=dict)  # ingrediens -> fel
    sortiment: dict[str, tuple[int, int, int]] = field(default_factory=dict)  # butik -> (antal, nya, utgångna)


@dataclass(frozen=True)
class _Priser:
    produkter: dict[str, list[Produkt]]  # efter produktlås
    hamtade: datetime | None
    varningar: tuple[str, ...]
    rea: frozenset[tuple[str, str]] = frozenset()  # (butik, produkt_id) som är rea just nu


class Matplan:
    def __init__(
        self,
        db_sokvag: Path,
        katalog: tuple[Ingrediens, ...] | None = None,
        butiker: tuple[Butik, ...] = (),
        livsmedelsverket: Livsmedelsverket | None = None,
        openfoodfacts: OpenFoodFacts | None = None,
    ):
        self._lagring = Lagring(db_sokvag)
        self._butiker = butiker
        self._livsmedelsverket = livsmedelsverket
        self._openfoodfacts = openfoodfacts
        # Utan given katalog används grupperna i databasen (de inbyggda läggs in första gången).
        self._fast_katalog = None if katalog is None else tuple(sorted(katalog, key=lambda i: i.namn))
        if katalog is None:
            self._lagring.seeda_grupper(STARTKATALOG)

    @property
    def _grundkatalog(self) -> tuple[Ingrediens, ...]:
        """Ingrediensgrupperna: från databasen, eller den katalog som gavs (t.ex. i tester)."""
        if self._fast_katalog is not None:
            return self._fast_katalog
        return tuple(self._lagring.grupper())

    # --- Planering -------------------------------------------------------

    def plan(self, start: date | None = None, ny: bool = False) -> Plan:
        """Den köpta (aktiva) planen gäller tills den är slut eller `ny` begärs.
        En ny plan använder lagret först: det som redan finns hemma kostar 0 kr."""
        if ny:
            self._lagring.rensa_aktiv_plan()
            self._lagring.satt_plan_val({})
        aktiv = self._lagring.aktiv_plan()
        if aktiv is not None and (start or date.today()) <= aktiv.dagar[-1].datum:
            return dataclasses.replace(aktiv, aktiv=True)
        return self._ny_plan(start)

    def _ny_plan(self, start: date | None) -> Plan:
        priser = self._priser()
        katalog = self._butikspriser(priser)
        rea = self._rea_ingredienser(priser)
        lager = self._lagring.lager()
        vantar, notiser = self._farska_rea_fore_lager(katalog, rea, lager)

        def med_lager(andel_att_kopa: dict[str, float]) -> tuple[Ingrediens, ...]:
            return tuple(
                dataclasses.replace(i, kr_per_kg=i.kr_per_kg * andel_att_kopa.get(i.namn, 1.0)) for i in katalog
            )

        # Första varvet: allt i lager är gratis. Andra varvet: lagervaror kostar bara
        # för den del av behovet som lagret inte täcker.
        # Lagervaror som får vänta på ett färskt erbjudande kostar sitt vanliga pris.
        plan = self._planera(med_lager({namn: 0.0 for namn in lager if namn not in vantar}), start)
        if lager:
            behov = plan.total_gram()
            andel = {
                namn: max(behov[namn] - gram, 0) / behov[namn] if behov.get(namn) else 0.0
                for namn, gram in lager.items()
                if namn not in vantar
            }
            plan = self._planera(med_lager(andel), start)

        utan_pris = tuple(i.namn for i in self._katalog if i.namn not in priser.produkter) if priser.hamtade else ()
        anvanda = plan.total_gram()
        kallor = tuple(sorted({n.kalla for namn, n in self._lagring.naring().items() if namn in anvanda}))
        return dataclasses.replace(
            plan, priser_hamtade=priser.hamtade, utan_butikspris=utan_pris,
            varningar=priser.varningar + notiser, naringskallor=kallor, rea=rea,
        )

    def _farska_rea_fore_lager(
        self, katalog: tuple[Ingrediens, ...], rea: tuple[str, ...], lager: dict[str, float]
    ) -> tuple[set[str], tuple[str, ...]]:
        """Frysta och torra proteinkällor i lager som får vänta, eftersom en färsk
        proteinkälla på rea ger mer protein per krona än lagervaran till ordinarie
        pris. De håller sig, det färska erbjudandet gör det inte."""

        def protein_per_kr(i: Ingrediens) -> float:
            return i.protein_100g * 10 / i.kr_per_kg if i.kr_per_kg > 0 else 0.0

        per_namn = {i.namn: i for i in katalog}
        farska = [
            per_namn[namn] for namn in rea
            if per_namn[namn].forvaring == "kyl" and per_namn[namn].kategori in ("protein", "mejeri")
        ]
        vantar, notiser = set(), []
        for namn in lager:
            lagrad = per_namn.get(namn)
            if lagrad is None or lagrad.forvaring == "kyl" or lagrad.kategori not in ("protein", "mejeri"):
                continue
            battre = [f for f in farska if protein_per_kr(f) > protein_per_kr(lagrad)]
            if battre:
                vantar.add(namn)
                notiser.append(f"{battre[0].namn} är på rea och går före {namn} i lagret, som håller sig.")
        return vantar, tuple(notiser)

    def _rea_ingredienser(self, priser: _Priser) -> tuple[str, ...]:
        """Ingredienser vars billigaste produkt per kg är på rea."""
        rea = []
        for namn, produkter in sorted(priser.produkter.items()):
            billigast = min(produkter, key=lambda p: (p.kr_per_kg, p.butik, p.produkt_id))
            if (billigast.butik, billigast.produkt_id) in priser.rea:
                rea.append(namn)
        return tuple(rea)

    def _planera(self, katalog: tuple[Ingrediens, ...], start: date | None) -> Plan:
        inst = self._lagring.installningar()
        profiler = tuple(
            Profil(namn, inst[f"{namn}.kcal_mal"], inst[f"{namn}.protein_mal"]) for namn in PERSONER
        )
        return planera(
            list(katalog),
            profiler,
            start=start or date.today(),
            plandagar=int(inst["plandagar"]),
            frukost=bool(inst["frukost"]),
            antal_mellanmal=int(inst["antal_mellanmal"]),
            vikter=Vikter(inst["vikt_protein"], inst["vikt_volym"], inst["vikt_kostnad"]),
            dagsbudget=self.dagsbudget(),
            val=self._lagring.plan_val(),
        )

    def byt(self, block: int, slot: str, ingrediens: str | None = None, start: date | None = None) -> Plan:
        """Byter ingrediensen i en slot ("protein", "kolhydrater" eller "grönsaker")
        i ett blocks lunch- och middagsbatch. Utan ingrediens väljs nästa i tur som
        går att planera. Bytet sparas tills `plan --ny` eller `rensa_byten`."""
        plan = self.plan(start)
        if plan.aktiv:
            raise PlaneringsFel("Planen är köpt och ligger fast. Kör `matplan plan --ny` för att kunna byta.")
        if not 1 <= block <= len(plan.block):
            raise KeyError(f"Block {block} finns inte; planen har {len(plan.block)} block.")
        if slot not in HUVUDSLOTAR:
            raise KeyError(f"Okänd slot: {slot}. Välj {', '.join(HUVUDSLOTAR)}.")
        alternativ = [i.namn for i in self._grundkatalog if i.kategori == slot]
        if ingrediens is not None:
            if ingrediens not in alternativ:
                raise KeyError(f"{ingrediens} är ingen ingrediens för {slot}.")
            forsok = [ingrediens]
        else:
            nuvarande = next(r.namn for r in plan.block[block - 1].batch.portioner[0].rader if r.slot == slot)
            i = alternativ.index(nuvarande)
            forsok = alternativ[i + 1 :] + alternativ[:i]

        tidigare = self._lagring.plan_val()
        senaste_fel: PlaneringsFel | None = None
        for namn in forsok:
            self._lagring.satt_plan_val({**tidigare, (block, slot): namn})
            try:
                return self.plan(start)
            except PlaneringsFel as fel:
                senaste_fel = fel
        self._lagring.satt_plan_val(tidigare)
        if ingrediens is not None and senaste_fel is not None:
            raise senaste_fel
        raise PlaneringsFel(f"Inget annat val för {slot} i block {block} når allas mål.")

    def byten(self) -> dict[tuple[int, str], str]:
        return self._lagring.plan_val()

    def rensa_byten(self) -> None:
        self._lagring.satt_plan_val({})

    def dagsbudget(self) -> float:
        """Den strängaste av veckobudgeten och månadstaket, per dag."""
        inst = self._lagring.installningar()
        return min(inst["veckobudget"] / 7, inst["manadsbudget"] / DAGAR_PER_MANAD)

    # --- Inköpslista, lager ------------------------------------------------

    def inkopslista(self, start: date | None = None) -> Inkopslista:
        """Det planen behöver minus det som redan finns i lager."""
        return self._lista(self.plan(start))

    def _lista(self, plan: Plan) -> Inkopslista:
        lager = self._lagring.lager()
        behov = plan.total_gram()
        for nummer in plan.lagade_block:
            for namn, gram in plan.block[nummer - 1].batchmangd.items():
                behov[namn] -= gram
        behov = {namn: max(gram - int(lager.get(namn, 0)), 0) for namn, gram in behov.items()}
        priser = self._priser()
        lista = bygg_lista(behov, priser.produkter, {i.namn: i.kr_per_kg for i in self._katalog}, priser.rea)
        return dataclasses.replace(lista, bunkring=tuple(self._lagring.bunkringar()))

    def kopt(self, start: date | None = None, butik: str | None = None) -> dict[str, float]:
        """Lägger in inköpslistan i lagret och gör planen aktiv, så att den inte
        planeras om när lagret ändras. `butik` väljer var allt köptes; "delad"
        betyder varje vara i sin billigaste butik; utan val antas bästa enskilda butik."""
        plan = self.plan(start)
        lista = self._lista(plan)
        if butik is None and lista.basta_butik:
            butik = lista.basta_butik.butik
        kopt: dict[str, float] = {}
        for rad in lista.rader:
            kop = rad.alternativ.get(butik) if butik != "delad" else None
            if kop is None and rad.billigast:
                kop = rad.billigast[1]
            if kop and kop.antal is not None and kop.produkt.forpackning_g:
                kopt[rad.ingrediens] = kop.antal * kop.produkt.forpackning_g
            else:
                kopt[rad.ingrediens] = rad.gram
        for bunkring in lista.bunkring:
            kopt[bunkring.ingrediens] = kopt.get(bunkring.ingrediens, 0) + bunkring.gram
        lager = self._lagring.lager()
        for namn, gram in kopt.items():
            self._lagring.satt_lager(namn, lager.get(namn, 0) + gram)
        self._lagring.ta_bort_bunkring()
        self._lagring.spara_aktiv_plan(dataclasses.replace(plan, aktiv=False))
        return kopt

    # --- Bunkring ----------------------------------------------------------

    def bunkra(self) -> list[Bunkring]:
        """Förslag på bunkring av proteinkällor som håller sig och är på rea.
        Utrymmet räknas efter det som redan finns i lagret och det som redan
        accepterats för bunkring."""
        inst = self._lagring.installningar()
        priser = self._priser()
        lager = dict(self._lagring.lager())
        accepterade = {b.ingrediens for b in self._lagring.bunkringar()}
        for bunkring in self._lagring.bunkringar():
            lager[bunkring.ingrediens] = lager.get(bunkring.ingrediens, 0) + bunkring.gram
        return [
            b
            for b in forslag(
                self._butikspriser(priser), priser.produkter, priser.rea, lager,
                {"fryst": inst["frys_kg"] * 1000, "torrvara": inst["torr_kg"] * 1000},
            )
            if b.ingrediens not in accepterade
        ]

    def acceptera_bunkring(self, ingrediens: str) -> Bunkring:
        """Lägger förslaget för ingrediensen på inköpslistan, i bunkringsdelen."""
        for bunkring in self.bunkra():
            if bunkring.ingrediens == ingrediens:
                self._lagring.spara_bunkring(bunkring)
                return bunkring
        raise KeyError(f"Inget bunkringsförslag för {ingrediens}.")

    def ta_bort_bunkring(self, ingrediens: str) -> bool:
        return self._lagring.ta_bort_bunkring(ingrediens)

    def lagat(self, start: date | None = None, block: int = 1) -> list[str]:
        """Drar ett lagat blocks lunch- och middagsbatch från lagret. Returnerar
        varningar för varor som inte räckte."""
        plan = self.plan(start)
        if not 1 <= block <= len(plan.block):
            raise KeyError(f"Block {block} finns inte; planen har {len(plan.block)} block.")
        if block in plan.lagade_block:
            return [f"Block {block} är redan draget från lagret."]
        lager = self._lagring.lager()
        varningar = []
        for namn, gram in plan.block[block - 1].batchmangd.items():
            kvar = lager.get(namn, 0) - gram
            if kvar < 0:
                varningar.append(f"{namn}: lagret räckte inte ({-kvar:.0f} g saknades)")
            self._lagring.satt_lager(namn, kvar)
        if plan.aktiv:
            self._lagring.spara_aktiv_plan(
                dataclasses.replace(plan, aktiv=False, lagade_block=plan.lagade_block + (block,))
            )
        return varningar

    def lager(self) -> dict[str, float]:
        return self._lagring.lager()

    def satt_lager(self, ingrediens: str, gram: float) -> None:
        self._ingrediens(ingrediens)
        self._lagring.satt_lager(ingrediens, gram)

    # --- Priser, produktlås --------------------------------------------------

    def refresh(
        self, nu: datetime | None = None, framsteg: Callable[[str, str], None] | None = None
    ) -> Hamtningsresultat:
        """Hämtar priser från alla butiker. En trasig butik stoppar inte de andra.
        `framsteg(butik, ingrediens)` anropas före varje ingrediens."""
        resultat = Hamtningsresultat(tid=nu or datetime.now().replace(microsecond=0))
        self._synka_sortiment(resultat, framsteg)
        priser: dict[str, list[Produkt]] = {}
        for butik in self._aktiva_butiker():
            if getattr(butik, "sortiment", None) is not None:
                continue  # hela sortimentet är synkat; grupperna matchas mot det lokalt
            try:
                fynd = {}
                for ingrediens in self._katalog:
                    if framsteg:
                        framsteg(butik.namn, ingrediens.namn)
                    traffar = {}
                    for term in ingrediens.sokord:
                        for produkt in butik.sok(term, ingrediens.butikskategori):
                            if (
                                produkt.kr_per_kg > 0
                                and matchar(produkt.namn, ingrediens.sokord, produkt.beskrivning)
                                and ratt_kategori(produkt.kategori, ingrediens.butikskategori)
                                and not utesluten(produkt.namn, ingrediens.uteslut)
                            ):
                                traffar[produkt.produkt_id] = produkt
                    fynd[ingrediens.namn] = list(traffar.values())
            except ButiksFel as fel:
                resultat.fel[butik.namn] = str(fel)
                continue
            except Exception as fel:  # en adapter får aldrig fälla hela hämtningen
                resultat.fel[butik.namn] = f"Oväntat fel ({type(fel).__name__}): {fel}"
                continue
            for namn, produkter in fynd.items():
                priser.setdefault(namn, []).extend(produkter)
            resultat.antal_produkter[butik.namn] = sum(len(p) for p in fynd.values())
        if resultat.antal_produkter:
            self._lagring.spara_hamtning(resultat.tid, priser)
        self._hamta_naring(resultat, framsteg)
        return resultat

    def _synka_sortiment(self, resultat: Hamtningsresultat, framsteg: Callable[[str, str], None] | None) -> None:
        """Synkar hela sortimentet för butiker som kan lista det. Misslyckas en
        synk ligger det tidigare sortimentet kvar."""
        for butik in self._aktiva_butiker():
            sortiment = getattr(butik, "sortiment", None)
            if sortiment is None:
                continue
            try:
                produkter = sortiment(framsteg)
            except ButiksFel as fel:
                resultat.fel[butik.namn] = f"Sortimentet: {fel}"
                continue
            resultat.sortiment[butik.namn] = self._lagring.synka_katalog(butik.namn, produkter, resultat.tid)

    def sok(self, text: str) -> list[Produkt]:
        """Aktiva produkter i sortimentet där alla sökorden finns som hela ord i
        märke, namn eller beskrivning."""
        sokord = set(re.findall(r"\w+", text.casefold()))
        if not sokord:
            return []
        avstangda = self._avstangda_butiker()
        traffar = []
        for p in self._lagring.katalog():
            if p.butik in avstangda:
                continue
            ord_ = set(re.findall(r"\w+", f"{p.varumarke} {p.namn} {p.beskrivning}".casefold()))
            if sokord <= ord_:
                traffar.append(p)
        return sorted(traffar, key=lambda p: (p.kr_per_kg <= 0, p.kr_per_kg, p.namn))

    def _hamta_naring(self, resultat: Hamtningsresultat, framsteg: Callable[[str, str], None] | None) -> None:
        """Hämtar näringsvärden för ingredienser som saknar sparade värden.
        Livsmedelsverket i första hand, Open Food Facts för märkesvaror."""
        sparade = self._lagring.naring()
        for ingrediens in self._grundkatalog:
            if ingrediens.namn in sparade:
                continue
            try:
                if ingrediens.livsmedelsverket is not None and self._livsmedelsverket:
                    if framsteg:
                        framsteg("Livsmedelsverket", ingrediens.namn)
                    naring = self._livsmedelsverket.hamta(ingrediens.livsmedelsverket)
                elif ingrediens.ean and self._openfoodfacts:
                    if framsteg:
                        framsteg("Open Food Facts", ingrediens.namn)
                    naring = self._openfoodfacts.hamta(ingrediens.ean)
                else:
                    continue
            except NaringsFel as fel:
                resultat.naring_fel[ingrediens.namn] = str(fel)
                continue
            self._lagring.spara_naring(ingrediens.namn, naring, resultat.tid)
            resultat.naring_hamtad += 1

    @property
    def _katalog(self) -> tuple[Ingrediens, ...]:
        """Katalogen med hämtade näringsvärden där sådana finns."""
        naring = self._lagring.naring()
        return tuple(
            dataclasses.replace(i, kcal_100g=naring[i.namn].kcal, protein_100g=naring[i.namn].protein)
            if i.namn in naring
            else i
            for i in self._grundkatalog
        )

    def produkter(self, ingrediens: str) -> list[Produkt]:
        """Matchande produkter för gruppen, billigast per kg först (före lås)."""
        self._ingrediens(ingrediens)
        produkter, _ = self._matchade()
        return sorted(produkter.get(ingrediens, []), key=lambda p: (p.kr_per_kg, p.butik, p.produkt_id))

    def prisoversikt(self) -> list[tuple[str, Produkt | None, bool, bool]]:
        """Per ingrediens: billigaste produkt per kg (efter lås), om den är på rea
        och om den är låst."""
        priser = self._priser()
        lasta = self._lagring.lasningar()
        rader = []
        for ingrediens in self._grundkatalog:
            produkter = priser.produkter.get(ingrediens.namn)
            if not produkter:
                rader.append((ingrediens.namn, None, False, False))
                continue
            p = min(produkter, key=lambda p: (p.kr_per_kg, p.butik, p.produkt_id))
            rader.append((
                ingrediens.namn, p, (p.butik, p.produkt_id) in priser.rea,
                lasta.get((ingrediens.namn, p.butik)) == p.produkt_id,
            ))
        return rader

    def las(self, ingrediens: str, butik: str, produkt_id: str) -> None:
        self._ingrediens(ingrediens)
        self._lagring.las(ingrediens, butik, produkt_id)

    def ta_bort_las(self, ingrediens: str, butik: str) -> bool:
        return self._lagring.ta_bort_las(ingrediens, butik)

    def lasningar(self) -> dict[tuple[str, str], str]:
        return self._lagring.lasningar()

    def _aktiva_butiker(self) -> tuple[Butik, ...]:
        """Butiker som är påslagna med inställningen butik_<nyckel> (utan nyckel: alltid på)."""
        inst = self._lagring.installningar()
        return tuple(b for b in self._butiker if inst.get(f"butik_{getattr(b, 'nyckel', '')}", 1))

    def _avstangda_butiker(self) -> set[str]:
        """Namnen på avstängda butiker, så att deras sparade priser ignoreras även
        när kärnan körs utan butiksadaptrar."""
        inst = self._lagring.installningar()
        nycklar = {**BUTIKSNYCKLAR, **{b.namn: b.nyckel for b in self._butiker if hasattr(b, "nyckel")}}
        return {namn for namn, nyckel in nycklar.items() if not inst.get(f"butik_{nyckel}", 1)}

    def _matchade(self) -> tuple[dict[str, list[Produkt]], datetime | None]:
        """Produkter per grupp, före lås. Butiker med synkat sortiment matchas lokalt
        mot det; övriga från senaste sökhämtningen. Andra värdet är när de äldsta
        av priserna hämtades."""
        produkter: dict[str, list[Produkt]] = {}
        avstangda = self._avstangda_butiker()
        katalogtider = {b: t for b, t in self._lagring.katalogtider().items() if b not in avstangda}
        tider = list(katalogtider.values())

        for ingrediens, produkt, tid in self._lagring.senaste_priser():
            if produkt.butik in avstangda or produkt.butik in katalogtider:
                continue
            produkter.setdefault(ingrediens, []).append(produkt)
            tider.append(tid)

        if katalogtider:
            katalog = [p for p in self._lagring.katalog(set(katalogtider)) if p.kr_per_kg > 0]
            # Samma regler som matchar/ratt_kategori/utesluten, men med orden förberäknade
            # eftersom varje grupp jämförs mot hela sortimentet.
            ordlista = []
            for p in katalog:
                namnord = set(re.findall(r"\w+", p.namn.casefold()))
                ordlista.append((p, namnord, namnord | set(re.findall(r"\w+", p.beskrivning.casefold()))))
            for grupp in self._grundkatalog:
                termer = [re.findall(r"\w+", t.casefold()) for t in grupp.sokord]
                uteslut = {o.casefold() for o in grupp.uteslut}
                for p, namnord, ord_ in ordlista:
                    if (
                        any(t and t[0] in namnord and set(t) <= ord_ for t in termer)
                        and ratt_kategori(p.kategori, grupp.butikskategori)
                        and not (namnord & uteslut)
                    ):
                        produkter.setdefault(grupp.namn, []).append(p)
        return produkter, (min(tider) if tider else None)

    def _priser(self) -> _Priser:
        produkter, hamtade = self._matchade()

        varningar = []
        for (ingrediens, butik), produkt_id in self._lagring.lasningar().items():
            i_butiken = [p for p in produkter.get(ingrediens, []) if p.butik == butik]
            if not i_butiken:
                continue
            last = [p for p in i_butiken if p.produkt_id == produkt_id]
            if not last:
                varningar.append(
                    f"Låst produkt {produkt_id} för {ingrediens} saknas i senaste hämtningen från {butik}; "
                    "använder billigaste."
                )
                continue
            produkter[ingrediens] = [p for p in produkter[ingrediens] if p.butik != butik] + last
        return _Priser(produkter, hamtade, tuple(varningar), self._rea(produkter))

    def _rea(self, produkter: dict[str, list[Produkt]]) -> frozenset[tuple[str, str]]:
        """Produkter vars pris är minst rea_procent under medianen de senaste
        rea_veckor veckorna; med för lite historik gäller butikens erbjudandeflagga."""
        senaste = self._lagring.senaste_hamtning()
        if senaste is None:
            return frozenset()
        inst = self._lagring.installningar()
        historik = self._lagring.prishistorik(senaste - timedelta(weeks=inst["rea_veckor"]))
        grans = inst["rea_procent"] / 100
        return frozenset(
            (p.butik, p.produkt_id)
            for lista in produkter.values()
            for p in lista
            if ar_rea(historik.get((p.butik, p.produkt_id), []), p.kr_per_kg, p.erbjudande, grans)
        )

    def _butikspriser(self, priser: _Priser) -> tuple[Ingrediens, ...]:
        """Varje grupp med pris och näring från den produkt planen köper: billigast
        per kg (efter lås). Saknar produkten näringsvärden gäller gruppens egna.
        Utan butikspris gäller gruppens platshållarpris."""
        resultat = []
        for i in self._katalog:
            kandidater = priser.produkter.get(i.namn)
            if not kandidater:
                resultat.append(i)
                continue
            vald = min(kandidater, key=lambda p: (p.kr_per_kg, p.butik, p.produkt_id))
            grupp = dataclasses.replace(i, kr_per_kg=vald.kr_per_kg)
            if vald.kcal and vald.protein is not None:
                grupp = dataclasses.replace(grupp, kcal_100g=vald.kcal, protein_100g=vald.protein)
            resultat.append(grupp)
        return tuple(resultat)

    # --- Inställningar ---------------------------------------------------

    def installningar(self) -> dict[str, float]:
        return self._lagring.installningar()

    def satt_installning(self, nyckel: str, varde: float) -> None:
        if nyckel not in self._lagring.installningar():
            raise KeyError(f"Okänd inställning: {nyckel}")
        self._lagring.satt_installning(nyckel, float(varde))

    def _ingrediens(self, namn: str) -> Ingrediens:
        for ingrediens in self._katalog:
            if ingrediens.namn == namn:
                return ingrediens
        raise KeyError(f"Okänd ingrediens: {namn}")
