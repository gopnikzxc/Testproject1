"""matplan-kärnan: varje användningsfall som ett kommando.

CLI och (senare) Textual-GUI är tunna skal ovanpå den här klassen.
"""

import dataclasses
import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable

from .bunkra import Bunkring, forslag
from .butiker import (
    Butik, ButiksFel, Butiksplats, Butiksregister, Produkt, ValdButik, matchar, ratt_kategori, utesluten,
)
from .inkop import Inkopslista, bygg_lista
from .katalog import STARTKATALOG, Ingrediens
from .lagring import Lagring
from .naring import Livsmedelsverket, Naring, NaringsFel, NaringsNatverksFel, OpenFoodFacts, foresla
from .planerare import HUVUDSLOTAR, Plan, PlaneringsFel, Profil, Vikter, planera
from .rea import ar_rea
from .protein import PROTEINTYPER, proteintyp
from .slot import SLOTAR, klassificera

__all__ = [
    "Matplan", "PlaneringsFel", "PERSONER", "Hamtningsresultat", "DAGAR_PER_MANAD", "Butiksrad", "Familj",
    "Godkannande",
]

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
class Butiksrad:
    plats: Butiksplats
    km: float | None  # avstånd från det angivna postnumret, om ett gavs
    vald: bool


def uppskattad_position(postnummer: str, referenser: list[Butiksplats]) -> tuple[float, float] | None:
    """Ungefärlig position för ett postnummer: koordinaterna för den butik vars
    postnummer liknar det mest (längst gemensam början, sedan minst numerisk
    skillnad). Svenska postnummer är geografiskt ordnade, så det räcker för att
    sortera butiker efter närhet."""
    siffror = re.sub(r"\D", "", postnummer)
    if len(siffror) != 5:
        raise ValueError(f"Postnummer ska ha fem siffror, t.ex. 442 50 (fick {postnummer!r}).")
    med_plats = [p for p in referenser if p.lat is not None and len(p.postnummer) == 5]
    if not med_plats:
        return None

    def likhet(p: Butiksplats) -> tuple[int, int]:
        gemensamt = next((i for i, (a, b) in enumerate(zip(siffror, p.postnummer)) if a != b), 5)
        return (-gemensamt, abs(int(siffror) - int(p.postnummer)))

    basta = min(med_plats, key=likhet)
    return (basta.lat, basta.lng)


def avstand_km(position: tuple[float, float] | None, plats: Butiksplats) -> float | None:
    """Fågelvägen (haversine)."""
    if position is None or plats.lat is None:
        return None
    lat1, lng1, lat2, lng2 = map(math.radians, (*position, plats.lat, plats.lng))
    a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(a))


@dataclass(frozen=True)
class Familj:
    """En produktfamilj (en grupp, eller ett normaliserat produktnamn) och dess
    Livsmedelsverket-matchning för produkter som saknar butikens näringsvärden."""

    familj: str
    produkter: tuple[str, ...]  # produkter i familjen som saknar butikens värden
    bekraftad: tuple[int, str] | None  # (nummer, namn)
    forslag: tuple[int, str] | None


@dataclass(frozen=True)
class _Naringsdata:
    """Allt som behövs för att slå upp produkters näring och slot, läst en gång."""

    familjer: dict[str, tuple[int, str]]
    lmv: dict[int, Naring]
    off: dict[str, Naring | None]
    gruppnaring: dict[str, Naring]
    slotval: dict[str, str]
    proteintypval: dict[str, str]


@dataclass(frozen=True)
class Godkannande:
    grupp: Ingrediens
    ny: bool  # False: produkten fanns redan i en grupp
    produkter: int  # produkter i gruppen


# Ord som inte blir söktermer och tecken på förpackningsstorlek i produktnamn.
_STOPPORD = {"i", "med", "m", "och", "&", "utan", "på", "till", "av"}
_ENHETER = {"g", "kg", "st", "p", "pack", "l", "dl", "cl", "ml", "x", "pk", "port", "portioner"}


def _namnord(produkt: Produkt) -> list[str]:
    """Produktnamnets ord utan märke och förpackningsstorlek."""
    marke = set(re.findall(r"\w+", produkt.varumarke.casefold()))
    ord_ = re.findall(r"[^\W_]+(?:-[^\W_]+)?", produkt.namn)
    return [o for o in ord_ if not any(c.isdigit() for c in o) and o.casefold() not in _ENHETER | marke]


def foreslaget_gruppnamn(produkt: Produkt) -> str:
    """"Tonfisk i Vatten 3x170g" -> "Tonfisk i vatten"."""
    text = " ".join(_namnord(produkt)).lower()
    return text[:1].upper() + text[1:]


def foreslagen_sokterm(produkt: Produkt) -> str:
    """"Tonfisk i Vatten" -> "tonfisk vatten"; även "Tonfisk Vatten" från ett annat märke matchar."""
    return " ".join(o.casefold() for o in _namnord(produkt) if o.casefold() not in _STOPPORD)


def familjenamn(produktnamn: str) -> str:
    """Normaliserat produktnamn för produkter utan grupp: gemener, bara ord."""
    return " ".join(re.findall(r"[^\W\d_]+", produktnamn.casefold()))


@dataclass(frozen=True)
class _Priser:
    produkter: dict[str, list[Produkt]]  # efter produktlås
    hamtade: datetime | None
    varningar: tuple[str, ...]
    rea: frozenset[tuple[str, str]] = frozenset()  # (butik, produkt_id) som är rea just nu
    ej_planerbara: tuple[str, ...] = ()  # grupper där ingen produkt har näringsvärden


class Matplan:
    def __init__(
        self,
        db_sokvag: Path,
        katalog: tuple[Ingrediens, ...] | None = None,
        butiker: tuple[Butik, ...] | Callable[[ValdButik], tuple[Butik, ...]] = (),
        livsmedelsverket: Livsmedelsverket | None = None,
        openfoodfacts: OpenFoodFacts | None = None,
        butiksregister: tuple[Butiksregister, ...] = (),
    ):
        """`butiker` är adaptrar, eller en funktion som bygger adaptrarna för den
        valda butiken. `butiksregister` listar kedjornas butiker för butiksvalet."""
        self._lagring = Lagring(db_sokvag)
        self._butiker = butiker
        self._butiksregister = butiksregister
        self._byggda: tuple[ValdButik, tuple[Butik, ...]] | None = None
        self._livsmedelsverket = livsmedelsverket
        self._openfoodfacts = openfoodfacts
        # Utan given katalog används grupperna i databasen (de inbyggda läggs in första gången).
        self._fast_katalog = None if katalog is None else tuple(sorted(katalog, key=lambda i: i.namn))
        if katalog is None:
            self._lagring.seeda_grupper(STARTKATALOG)

    @property
    def _grundkatalog(self) -> tuple[Ingrediens, ...]:
        """Ingrediensgrupperna: från databasen, eller den katalog som gavs (t.ex. i
        tester), med handvalda slotar (#29)."""
        grupper = self._fast_katalog if self._fast_katalog is not None else tuple(self._lagring.grupper())
        slotval = self._lagring.slotval()
        return tuple(
            dataclasses.replace(g, kategori=slotval[f"grupp:{g.namn}"]) if f"grupp:{g.namn}" in slotval else g
            for g in grupper
        )

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
        pool = self._planpool(priser)
        katalog = tuple(i for i, _ in pool.values())
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

        utan_pris = tuple(
            i.namn for i in self._katalog if i.namn not in priser.produkter and i.namn not in priser.ej_planerbara
        ) if priser.hamtade else ()
        anvanda = plan.total_gram()
        produktkallor = tuple((namn, kalla) for namn, (_, kalla) in sorted(pool.items()) if namn in anvanda)
        kallor = tuple(sorted({k for _, k in produktkallor} & {"livsmedelsverket", "openfoodfacts"}))
        hoppade = tuple(
            f"{namn}: ingen produkt har näringsvärden, så gruppen hoppas över i planen." for namn in priser.ej_planerbara
        )
        return dataclasses.replace(
            plan, priser_hamtade=priser.hamtade, utan_butikspris=utan_pris,
            varningar=priser.varningar + notiser + hoppade, naringskallor=kallor, rea=rea,
            produktkallor=produktkallor,
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
        # Proteinslotten kan också fyllas av en kombinationsvara.
        slotar_for = {"protein": ("protein", "kombination")}.get(slot, (slot,))
        alternativ = [g.namn for g, _ in self._planpool(self._priser()).values() if g.kategori in slotar_for]
        if ingrediens is not None:
            if ingrediens not in alternativ:
                raise KeyError(f"{ingrediens} är ingen ingrediens för {slot}.")
            forsok = [ingrediens]
        else:
            nuvarande = next((r.namn for r in plan.block[block - 1].batch.portioner[0].rader if r.slot == slot), None)
            if nuvarande in alternativ:
                i = alternativ.index(nuvarande)
                forsok = alternativ[i + 1 :] + alternativ[:i]
            else:
                forsok = alternativ

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
        self._hamta_produktnaring(resultat, framsteg)
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
        med = self._medraknade_butiker()
        traffar = []
        for p in self._lagring.katalog():
            if p.butik not in med:
                continue
            ord_ = set(re.findall(r"\w+", f"{p.varumarke} {p.namn} {p.beskrivning}".casefold()))
            if sokord <= ord_:
                traffar.append(p)
        if traffar:
            # Produkter i en grupp får gruppens näringsfamilj; övriga sitt normaliserade namn.
            i_grupp = {(p.butik, p.produkt_id): p for lista in self._matchade()[0].values() for p in lista}
            data = self._naringsdata()
            traffar = [i_grupp.get((p.butik, p.produkt_id)) or self._med_naring(p, None, data) for p in traffar]
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

    def _hamta_produktnaring(
        self, resultat: Hamtningsresultat, framsteg: Callable[[str, str], None] | None
    ) -> None:
        """Livsmedelsverkets värden för bekräftade familjer som saknar dem, och Open
        Food Facts (per streckkod) för gruppernas produkter som annars saknar värden."""
        if self._livsmedelsverket:
            lmv = self._lagring.lmv_varden()
            for familj, (nummer, _) in sorted(self._lagring.familjer().items()):
                if nummer in lmv:
                    continue
                if framsteg:
                    framsteg("Livsmedelsverket", familj)
                try:
                    naring = self._livsmedelsverket.hamta(nummer)
                except NaringsFel as fel:
                    resultat.naring_fel[familj] = str(fel)
                    continue
                self._lagring.spara_lmv_varden(nummer, naring, resultat.tid)
                lmv[nummer] = naring
                resultat.naring_hamtad += 1
        if self._openfoodfacts:
            kanda = self._lagring.off_varden()
            saknar = sorted({
                p.ean for lista in self._matchade()[0].values() for p in lista
                if p.naringskalla is None and p.ean and p.ean not in kanda
            })
            for ean in saknar:
                if framsteg:
                    framsteg("Open Food Facts", ean)
                try:
                    naring = self._openfoodfacts.hamta(ean)
                except NaringsNatverksFel as fel:
                    resultat.naring_fel[ean] = str(fel)
                    continue
                except NaringsFel:
                    naring = None  # OFF saknar varan; frågas inte igen
                self._lagring.spara_off_varden(ean, naring, resultat.tid)
                if naring is not None:
                    resultat.naring_hamtad += 1

    def _lmv_lista(self) -> list[tuple[int, str]]:
        """Livsmedelsverkets lista, hämtad en gång och sparad i databasen."""
        lista = self._lagring.lmv_lista()
        if not lista and self._livsmedelsverket:
            try:
                lista = self._livsmedelsverket.lista()
            except NaringsFel:
                return []
            self._lagring.spara_lmv_lista(lista)
        return lista

    def _familjenyckel(self, text: str) -> str:
        """En grupps namn, annars det normaliserade produktnamnet."""
        grupp = next((g.namn for g in self._grundkatalog if g.namn.casefold() == text.strip().casefold()), None)
        return grupp or familjenamn(text)

    def naringsfamiljer(self) -> list[Familj]:
        """Grupper vars produkter saknar butikens näringsvärden, med gruppens
        bekräftade Livsmedelsverket-matchning eller ett förslag, och bekräftade
        familjer för produktnamn utanför grupperna."""
        data = self._naringsdata()
        matchade, _ = self._matchade()
        lista = self._lmv_lista()
        namn_for = dict(lista)
        resultat = []
        for grupp in self._grundkatalog:
            saknar = tuple(sorted({p.namn for p in matchade.get(grupp.namn, []) if p.naringskalla != "butik"}))
            bekraftad = data.familjer.get(grupp.namn)
            if bekraftad is None and grupp.livsmedelsverket is not None:
                bekraftad = (grupp.livsmedelsverket, namn_for.get(grupp.livsmedelsverket, f"nummer {grupp.livsmedelsverket}"))
            if not saknar and grupp.namn not in data.familjer:
                continue
            forslag = None
            if bekraftad is None:
                forslag = foresla(grupp.namn, lista) or next((f for n in saknar if (f := foresla(n, lista))), None)
            resultat.append(Familj(grupp.namn, saknar, bekraftad, forslag))
        grupper = {g.namn for g in self._grundkatalog}
        for familj, match in sorted(data.familjer.items()):
            if familj not in grupper:
                resultat.append(Familj(familj, (), match, None))
        return resultat

    def bekrafta_familj(self, familj: str, nummer: int | None = None, nu: datetime | None = None) -> Familj:
        """Bekräftar en familjs Livsmedelsverket-matchning: förslaget, eller
        livsmedlet med `nummer`. Gäller alla produkter i familjen, även nya."""
        nyckel = self._familjenyckel(familj)
        lista = self._lmv_lista()
        if nummer is None:
            befintlig = next((f for f in self.naringsfamiljer() if f.familj == nyckel), None)
            forslag = (befintlig.forslag if befintlig else None) or foresla(nyckel, lista)
            if forslag is None:
                raise ValueError(
                    f"Inget förslag för {nyckel}. Sök ett livsmedel med `matplan näring --sök <text>` och ange dess nummer."
                )
            nummer, namn = forslag
        else:
            namn = dict(lista).get(nummer)
            if namn is None and lista:
                raise ValueError(f"Livsmedelsverket har inget livsmedel med nummer {nummer}.")
            namn = namn or f"nummer {nummer}"
        self._lagring.bekrafta_familj(nyckel, nummer, namn)
        if self._livsmedelsverket and nummer not in self._lagring.lmv_varden():
            try:
                self._lagring.spara_lmv_varden(
                    nummer, self._livsmedelsverket.hamta(nummer), nu or datetime.now().replace(microsecond=0)
                )
            except NaringsFel:
                pass  # hämtas vid nästa refresh
        return Familj(nyckel, (), (nummer, namn), None)

    def sok_livsmedel(self, text: str) -> list[tuple[int, str]]:
        """Livsmedel i Livsmedelsverkets lista vars namn innehåller alla orden."""
        ord_ = text.casefold().split()
        return [(n, namn) for n, namn in self._lmv_lista() if all(o in namn.casefold() for o in ord_)]

    def satt_slot(self, mal: str, slot: str | None) -> str:
        """Handvald slot för en grupp (namn) eller produkt (produkt-id); None tar
        bort valet. Returnerar vad som ändrades."""
        if slot is not None and slot not in SLOTAR:
            raise KeyError(f"Okänd slot: {slot}. Välj bland {', '.join(SLOTAR)}.")
        nyckel, andrad = self._mal(mal)
        self._lagring.satt_slotval(nyckel, slot)
        return andrad

    def _produkt(self, produkt_id: str) -> Produkt | None:
        """En produkt i sortimentet eller senaste sökhämtningen, efter id."""
        produkt = next((p for p in self._lagring.katalog() if p.produkt_id == produkt_id), None)
        if produkt is None:
            produkt = next((p for _, p, _ in self._lagring.senaste_priser() if p.produkt_id == produkt_id), None)
        return produkt

    def _mal(self, mal: str) -> tuple[str, str]:
        """("grupp:<namn>" eller "produkt:<id>", beskrivning) för en grupp eller produkt."""
        grupp = next((g.namn for g in self._grundkatalog if g.namn.casefold() == mal.strip().casefold()), None)
        if grupp is not None:
            return f"grupp:{grupp}", grupp
        produkt = self._produkt(mal)
        if produkt is None:
            raise KeyError(f"Hittar ingen grupp eller produkt {mal!r}.")
        return f"produkt:{mal}", f"{produkt.namn} ({mal})"

    def slotval(self) -> dict[str, str]:
        return self._lagring.slotval()

    @property
    def _katalog(self) -> tuple[Ingrediens, ...]:
        """Katalogen med gruppernas hämtade eller bekräftade näringsvärden där sådana finns."""
        data = self._naringsdata()
        resultat = []
        for i in self._grundkatalog:
            varden = self._gruppvarden(i, data)
            if varden is not None and varden.kalla != "katalog":
                i = dataclasses.replace(i, kcal_100g=varden.kcal, protein_100g=varden.protein)
            resultat.append(i)
        return tuple(resultat)

    # --- Näring per produkt (#28) och slot (#29) ----------------------------

    def _naringsdata(self) -> _Naringsdata:
        return _Naringsdata(
            self._lagring.familjer(), self._lagring.lmv_varden(), self._lagring.off_varden(),
            self._lagring.naring(), self._lagring.slotval(), self._lagring.proteintypval(),
        )

    def _gruppvarden(self, grupp: Ingrediens, data: _Naringsdata) -> Naring | None:
        """Familjens värden för en grupp: en bekräftad Livsmedelsverket-matchning,
        annars gruppens hämtade värden (från dess nummer eller streckkod), annars
        katalogens handinlagda värden om gruppen har en källa att hämta från."""
        bekraftad = data.familjer.get(grupp.namn)
        if bekraftad and bekraftad[0] in data.lmv:
            return data.lmv[bekraftad[0]]
        if grupp.namn in data.gruppnaring:
            return data.gruppnaring[grupp.namn]
        if grupp.livsmedelsverket is not None or grupp.ean or bekraftad:
            return Naring("katalog", grupp.kcal_100g, grupp.protein_100g, None, None, None, None)
        return None

    def _med_naring(self, produkt: Produkt, grupp: Ingrediens | None, data: _Naringsdata) -> Produkt:
        """Produkten med näringsvärden och källa (butiken, familjens matchning,
        Open Food Facts) och slot (handvald eller klassificerad)."""
        varden: Naring | None = None
        if produkt.kcal and produkt.protein is not None:
            kalla = "butik"
        else:
            if grupp is not None:
                varden = self._gruppvarden(grupp, data)
            else:
                bekraftad = data.familjer.get(familjenamn(produkt.namn))
                varden = data.lmv.get(bekraftad[0]) if bekraftad else None
            if varden is None and produkt.ean:
                varden = data.off.get(produkt.ean)
            kalla = varden.kalla if varden else None
        if varden is not None:
            produkt = dataclasses.replace(
                produkt, kcal=varden.kcal, protein=varden.protein, fett=varden.fett,
                kolhydrater=varden.kolhydrater, fiber=varden.fiber,
            )
        slot = data.slotval.get(f"produkt:{produkt.produkt_id}") or klassificera(
            produkt.kcal, produkt.protein, produkt.kolhydrater, produkt.fett, produkt.kategori, produkt.namn
        )
        typ = data.proteintypval.get(f"produkt:{produkt.produkt_id}") or proteintyp(produkt.kategori, produkt.namn)
        return dataclasses.replace(produkt, naringskalla=kalla, slot=slot, proteintyp=typ)

    @staticmethod
    def _gruppens_proteintyp(grupp: Ingrediens, vald: Produkt | None, data: _Naringsdata) -> str:
        """Handvald typ, annars gruppens egen, annars den köpta produktens, annars ur gruppens namn."""
        return (
            data.proteintypval.get(f"grupp:{grupp.namn}")
            or grupp.proteintyp
            or (vald.proteintyp if vald is not None else None)
            or proteintyp(" ".join(grupp.butikskategori), grupp.namn)
        )

    @staticmethod
    def _planerbar(produkt: Produkt) -> bool:
        return produkt.naringskalla is not None and produkt.slot != "utesluten"

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

    def _adaptrar(self) -> tuple[Butik, ...]:
        """Adaptrarna; byggs en gång per vald butik när de ges som funktion."""
        if not callable(self._butiker):
            return tuple(self._butiker)
        vald = self.vald_butik()
        if self._byggda is None or self._byggda[0] != vald:
            self._byggda = (vald, tuple(self._butiker(vald)))
        return self._byggda[1]

    def _aktiva_butiker(self) -> tuple[Butik, ...]:
        """Adaptrar för den valda butiken. Adaptrar utan kedja (t.ex. i tester) är alltid med."""
        vald = self.vald_butik()
        return tuple(b for b in self._adaptrar() if not hasattr(b, "nyckel") or b.namn == vald.namn)

    def _medraknade_butiker(self) -> set[str]:
        """Butiker vars sparade priser och sortiment räknas: den valda (och adaptrar
        utan kedja). Andra butikers historik ligger kvar och kommer tillbaka när
        man byter tillbaka."""
        return {self.vald_butik().namn} | {b.namn for b in self._adaptrar() if not hasattr(b, "nyckel")}

    # --- Butiksval ---

    def vald_butik(self) -> ValdButik:
        return self._lagring.vald_butik()

    def butikslista(self, postnummer: str | None = None, sok: str | None = None) -> list[Butiksrad]:
        """Kedjornas butiker. Med postnummer: närmast först; med sökord: de vars
        namn, ort eller postnummer innehåller texten; annars i namnordning."""
        alla = [p for register in self._butiksregister for p in register.butiker()]
        platser = alla
        if sok:
            text = sok.casefold().strip()
            platser = [p for p in alla if text in p.namn.casefold() or text in p.ort.casefold()
                       or p.postnummer.startswith(text.replace(" ", ""))]
        vald = self.vald_butik().namn
        if postnummer:
            # Alla butiker är referenspunkter, även de som sökningen sorterat bort.
            position = uppskattad_position(postnummer, alla)
            rader = [Butiksrad(p, avstand_km(position, p), p.namn == vald) for p in platser]
            return sorted(rader, key=lambda r: (r.km is None, r.km or 0, r.plats.namn))
        return sorted((Butiksrad(p, None, p.namn == vald) for p in platser), key=lambda r: r.plats.namn)

    def valj_butik(self, namn: str) -> ValdButik:
        """Väljer butiken vars namn (eller ort, om den är entydig) är `namn`, slår
        upp dess butiksnummer och sparar valet. Grupper, lager och inställningar
        påverkas inte; tidigare butikers priser och sortiment ligger kvar."""
        text = namn.casefold().strip()
        kandidater = [(r, p) for r in self._butiksregister for p in r.butiker()]
        traffar = [(r, p) for r, p in kandidater if p.namn.casefold() in (text, f"city gross {text}")]
        if not traffar:
            traffar = [(r, p) for r, p in kandidater if p.ort.casefold() == text]
        if not traffar:
            raise ValueError(f"Hittar ingen butik som heter {namn!r}. Lista butikerna med `matplan butik`.")
        if len(traffar) > 1:
            raise ValueError(f"Flera butiker passar {namn!r}: " + ", ".join(p.namn for _, p in traffar))
        register, plats = traffar[0]
        vald = ValdButik(plats.kedja, register.butiksnummer(plats), plats.namn)
        self._lagring.spara_vald_butik(vald)
        return vald

    def _matchade(self) -> tuple[dict[str, list[Produkt]], datetime | None]:
        """Produkter per grupp, före lås, med näring och slot. Butiker med synkat
        sortiment matchas lokalt mot det; övriga från senaste sökhämtningen. Andra
        värdet är när de äldsta av priserna hämtades."""
        produkter: dict[str, list[Produkt]] = {}
        med = self._medraknade_butiker()
        katalogtider = {b: t for b, t in self._lagring.katalogtider().items() if b in med}
        tider = list(katalogtider.values())
        grupper = {g.namn: g for g in self._grundkatalog}

        for ingrediens, produkt, tid in self._lagring.senaste_priser():
            if produkt.butik not in med or produkt.butik in katalogtider:
                continue
            if ingrediens in grupper and produkt.produkt_id in grupper[ingrediens].undantag:
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
            for grupp in grupper.values():
                termer = [re.findall(r"\w+", t.casefold()) for t in grupp.sokord]
                uteslut = {o.casefold() for o in grupp.uteslut}
                for p, namnord, ord_ in ordlista:
                    if p.produkt_id in grupp.undantag:
                        continue
                    if p.produkt_id in grupp.med or (
                        any(t and t[0] in namnord and set(t) <= ord_ for t in termer)
                        and ratt_kategori(p.kategori, grupp.butikskategori)
                        and not (namnord & uteslut)
                    ):
                        produkter.setdefault(grupp.namn, []).append(p)
        data = self._naringsdata()
        produkter = {
            namn: [self._med_naring(p, grupper.get(namn), data) for p in lista] for namn, lista in produkter.items()
        }
        return produkter, (min(tider) if tider else None)

    def _priser(self) -> _Priser:
        """Planerbara produkter per grupp (med näringsvärden, inte uteslutna), efter lås.
        Grupper med produkter där ingen är planerbar listas i `ej_planerbara`."""
        matchade, hamtade = self._matchade()
        produkter = {namn: [p for p in lista if self._planerbar(p)] for namn, lista in matchade.items()}
        ej_planerbara = tuple(sorted(namn for namn, lista in produkter.items() if not lista))
        produkter = {namn: lista for namn, lista in produkter.items() if lista}

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
        return _Priser(produkter, hamtade, tuple(varningar), self._rea(produkter), ej_planerbara)

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
        """Planens grupper med pris och näring från den produkt planen köper:
        billigast per kg (efter lås). Utan butikspris gäller gruppens platshållarpris
        och egna värden. Grupper utan planerbar produkt hoppas över, liksom grupper
        utan slot vars produkt inte går att klassificera."""
        return tuple(i for i, _ in self._planpool(priser).values())

    def _planpool(self, priser: _Priser) -> dict[str, tuple[Ingrediens, str]]:
        """Grupp -> (gruppen som planen ser den, näringskälla). Varje grupp får
        proteintyp och kvalitetsfaktor (#30)."""
        data = self._naringsdata()
        inst = self._lagring.installningar()
        pool: dict[str, tuple[Ingrediens, str]] = {}
        for i in self._katalog:
            if i.namn in priser.ej_planerbara:
                continue
            kandidater = priser.produkter.get(i.namn)
            vald = min(kandidater, key=lambda p: (p.kr_per_kg, p.butik, p.produkt_id)) if kandidater else None
            typ = self._gruppens_proteintyp(i, vald, data)
            i = dataclasses.replace(i, proteintyp=typ, proteinkvalitet=inst.get(f"kvalitet_{typ}", 1.0))
            if vald is None:
                varden = self._gruppvarden(i, data)
                pool[i.namn] = (i, varden.kalla if varden else "katalog")
                continue
            slot = i.kategori or vald.slot
            if slot not in SLOTAR or slot == "utesluten":
                continue
            pool[i.namn] = (
                dataclasses.replace(i, kategori=slot, kr_per_kg=vald.kr_per_kg, kcal_100g=vald.kcal, protein_100g=vald.protein),
                vald.naringskalla,
            )
        return pool

    # --- Grupper (#31) ----------------------------------------------------

    def _andringsbar_grupp(self, namn: str) -> Ingrediens:
        if self._fast_katalog is not None:
            raise ValueError("Grupperna är fasta i den här körningen och kan inte ändras.")
        grupp = next((g for g in self._lagring.grupper() if g.namn.casefold() == namn.strip().casefold()), None)
        if grupp is None:
            raise KeyError(f"Okänd grupp: {namn}")
        return grupp

    def godkann(self, produkt_id: str) -> Godkannande:
        """Gör en produkt i sortimentet till en ny ingrediensgrupp med föreslaget
        namn, sökterm, butikskategori och slot. Liknande produkter (t.ex. andra
        märkens tonfisk i vatten) kommer med automatiskt. Matchar produkten redan
        en grupp returneras den i stället."""
        if self._fast_katalog is not None:
            raise ValueError("Grupperna är fasta i den här körningen och kan inte ändras.")
        produkt = self._produkt(produkt_id)
        if produkt is None:
            raise KeyError(f"Hittar ingen produkt {produkt_id!r} i sortimentet. Sök med `matplan sök`.")
        matchade, _ = self._matchade()
        befintlig = next((namn for namn, lista in matchade.items() if any(p.produkt_id == produkt_id for p in lista)), None)
        if befintlig is not None:
            grupp = next(g for g in self._grundkatalog if g.namn == befintlig)
            return Godkannande(grupp, False, len(matchade[befintlig]))

        produkt = self._med_naring(produkt, None, self._naringsdata())
        if produkt.slot == "utesluten":
            raise ValueError(f"{produkt.namn} planeras aldrig (juice, läsk o.d.).")
        namn = foreslaget_gruppnamn(produkt) or produkt.namn
        if any(g.namn.casefold() == namn.casefold() for g in self._grundkatalog):
            namn = f"{namn} ({produkt.varumarke.title() or produkt_id})"
            if any(g.namn.casefold() == namn.casefold() for g in self._grundkatalog):
                raise ValueError(f"Det finns redan en grupp som heter {namn}.")
        kategori = produkt.kategori.casefold()
        underkategori = kategori.rsplit("/", 1)[-1].strip()
        grupp = Ingrediens(
            namn=namn,
            kategori=produkt.slot or "",
            kcal_100g=produkt.kcal or 0.0,
            protein_100g=produkt.protein or 0.0,
            kr_per_kg=produkt.kr_per_kg,
            sokord=(foreslagen_sokterm(produkt) or produkt.namn.casefold(),),
            forvaring="fryst" if "fryst" in kategori else "torrvara" if "skafferi" in kategori else "kyl",
            butikskategori=(underkategori,) if underkategori else (),
        )
        if not (matchar(produkt.namn, grupp.sokord, produkt.beskrivning) and ratt_kategori(produkt.kategori, grupp.butikskategori)):
            grupp = dataclasses.replace(grupp, med=(produkt_id,))
        self._lagring.spara_grupp(grupp)
        return Godkannande(grupp, True, len(self._matchade()[0].get(grupp.namn, [])))

    def grupper(self) -> list[tuple[Ingrediens, int]]:
        """Alla grupper och hur många produkter i sortimentet som hör till var."""
        matchade, _ = self._matchade()
        return [(g, len(matchade.get(g.namn, []))) for g in self._grundkatalog]

    def byt_gruppnamn(self, namn: str, nytt: str) -> Ingrediens:
        grupp = self._andringsbar_grupp(namn)
        nytt = nytt.strip()
        if not nytt:
            raise ValueError("Gruppen behöver ett namn.")
        if any(g.namn.casefold() == nytt.casefold() and g.namn != grupp.namn for g in self._lagring.grupper()):
            raise ValueError(f"Det finns redan en grupp som heter {nytt}.")
        aktiv = self._lagring.aktiv_plan()
        if aktiv is not None and grupp.namn in aktiv.total_gram():
            raise ValueError(f"{grupp.namn} ingår i den köpta planen. Kör `matplan plan --ny` först.")
        ny_grupp = dataclasses.replace(grupp, namn=nytt)
        self._lagring.byt_gruppnamn(ny_grupp, grupp.namn)
        return ny_grupp

    def satt_sokord(self, namn: str, sokord: tuple[str, ...]) -> Ingrediens:
        grupp = self._andringsbar_grupp(namn)
        sokord = tuple(t.strip().casefold() for t in sokord if t.strip())
        if not sokord:
            raise ValueError("Gruppen behöver minst en sökterm.")
        grupp = dataclasses.replace(grupp, sokord=sokord)
        self._lagring.spara_grupp(grupp)
        return grupp

    def uteslut_produkt(self, namn: str, produkt_id: str) -> Ingrediens:
        """Tar bort en enskild produkt ur gruppen, även om den matchar söktermerna."""
        grupp = self._andringsbar_grupp(namn)
        grupp = dataclasses.replace(
            grupp, undantag=tuple(sorted({*grupp.undantag, produkt_id})), med=tuple(m for m in grupp.med if m != produkt_id)
        )
        self._lagring.spara_grupp(grupp)
        return grupp

    def inkludera_produkt(self, namn: str, produkt_id: str) -> Ingrediens:
        """Tar med en enskild produkt i gruppen: tar bort ett undantag, och lägger
        till den för hand om den inte matchar söktermerna."""
        grupp = self._andringsbar_grupp(namn)
        if self._produkt(produkt_id) is None:
            raise KeyError(f"Hittar ingen produkt {produkt_id!r}.")
        grupp = dataclasses.replace(grupp, undantag=tuple(u for u in grupp.undantag if u != produkt_id))
        if not any(p.produkt_id == produkt_id for p in self._matchade()[0].get(grupp.namn, [])):
            grupp = dataclasses.replace(grupp, med=tuple(sorted({*grupp.med, produkt_id})))
        self._lagring.spara_grupp(grupp)
        return grupp

    def ta_bort_grupp(self, namn: str) -> None:
        """Tar bort gruppen ur planeringen. Lager och lås för den ligger kvar."""
        grupp = self._andringsbar_grupp(namn)
        self._lagring.ta_bort_grupp(grupp.namn)

    def satt_proteintyp(self, mal: str, typ: str | None) -> str:
        """Handvald proteintyp för en grupp (namn) eller produkt (produkt-id); None tar bort valet."""
        if typ is not None and typ not in PROTEINTYPER:
            raise KeyError(f"Okänd proteintyp: {typ}. Välj bland {', '.join(PROTEINTYPER)}.")
        nyckel, andrad = self._mal(mal)
        self._lagring.satt_proteintypval(nyckel, typ)
        return andrad

    def proteintypval(self) -> dict[str, str]:
        return self._lagring.proteintypval()

    def proteintyper(self) -> dict[str, str]:
        """Varje grupps proteintyp som planen räknar med."""
        return {namn: i.proteintyp for namn, (i, _) in self._planpool(self._priser()).items()}

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
