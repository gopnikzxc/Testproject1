"""matplan-kärnan: varje användningsfall som ett kommando.

CLI och (senare) Textual-GUI är tunna skal ovanpå den här klassen.
"""

import dataclasses
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from .butiker import Butik, ButiksFel, Produkt, matchar
from .inkop import Inkopslista, bygg_lista
from .katalog import STARTKATALOG, Ingrediens
from .lagring import Lagring
from .planerare import Plan, PlaneringsFel, Profil, Vikter, planera

__all__ = ["Matplan", "PlaneringsFel", "PERSONER", "Hamtningsresultat", "DAGAR_PER_MANAD"]

# Barnet planeras inte (se spec #1).
PERSONER = ("jag", "fru")
# Månadstaket räknas på fyra veckor, så att 1250 kr/vecka och 5000 kr/månad går ihop.
DAGAR_PER_MANAD = 28


@dataclass(frozen=True)
class Hamtningsresultat:
    tid: datetime
    antal_produkter: dict[str, int] = field(default_factory=dict)
    fel: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class _Priser:
    produkter: dict[str, list[Produkt]]  # efter produktlås
    hamtade: datetime | None
    varningar: tuple[str, ...]


class Matplan:
    def __init__(
        self,
        db_sokvag: Path,
        katalog: tuple[Ingrediens, ...] = STARTKATALOG,
        butiker: tuple[Butik, ...] = (),
    ):
        self._lagring = Lagring(db_sokvag)
        self._katalog = tuple(sorted(katalog, key=lambda i: i.namn))
        self._butiker = butiker

    # --- Planering -------------------------------------------------------

    def plan(self, start: date | None = None, ny: bool = False) -> Plan:
        """Den köpta (aktiva) planen gäller tills den är slut eller `ny` begärs.
        En ny plan använder lagret först: det som redan finns hemma kostar 0 kr."""
        if ny:
            self._lagring.rensa_aktiv_plan()
        aktiv = self._lagring.aktiv_plan()
        if aktiv is not None and (start or date.today()) <= aktiv.dagar[-1].datum:
            return dataclasses.replace(aktiv, aktiv=True)
        return self._ny_plan(start)

    def _ny_plan(self, start: date | None) -> Plan:
        priser = self._priser()
        katalog = self._butikspriser(priser)
        lager = self._lagring.lager()

        def med_lager(andel_att_kopa: dict[str, float]) -> tuple[Ingrediens, ...]:
            return tuple(
                dataclasses.replace(i, kr_per_kg=i.kr_per_kg * andel_att_kopa.get(i.namn, 1.0)) for i in katalog
            )

        # Första varvet: allt i lager är gratis. Andra varvet: lagervaror kostar bara
        # för den del av behovet som lagret inte täcker.
        plan = self._planera(med_lager({namn: 0.0 for namn in lager}), start)
        if lager:
            behov = plan.total_gram()
            andel = {
                namn: max(behov[namn] - gram, 0) / behov[namn] if behov.get(namn) else 0.0
                for namn, gram in lager.items()
            }
            plan = self._planera(med_lager(andel), start)

        utan_pris = tuple(i.namn for i in self._katalog if i.namn not in priser.produkter) if priser.hamtade else ()
        return dataclasses.replace(
            plan, priser_hamtade=priser.hamtade, utan_butikspris=utan_pris, varningar=priser.varningar
        )

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
        )

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
        return bygg_lista(behov, self._priser().produkter, {i.namn: i.kr_per_kg for i in self._katalog})

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
        lager = self._lagring.lager()
        for namn, gram in kopt.items():
            self._lagring.satt_lager(namn, lager.get(namn, 0) + gram)
        self._lagring.spara_aktiv_plan(dataclasses.replace(plan, aktiv=False))
        return kopt

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

    def refresh(self, nu: datetime | None = None) -> Hamtningsresultat:
        """Hämtar priser från alla butiker. En trasig butik stoppar inte de andra."""
        resultat = Hamtningsresultat(tid=nu or datetime.now().replace(microsecond=0))
        priser: dict[str, list[Produkt]] = {}
        for butik in self._butiker:
            try:
                fynd = {}
                for ingrediens in self._katalog:
                    traffar = {}
                    for term in ingrediens.sokord:
                        for produkt in butik.sok(term):
                            if produkt.kr_per_kg > 0 and matchar(produkt.namn, ingrediens.sokord):
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
        return resultat

    def produkter(self, ingrediens: str) -> list[Produkt]:
        """Senast hämtade matchande produkter, billigast per kg först (före lås)."""
        self._ingrediens(ingrediens)
        return sorted(
            (p for namn, p, _ in self._lagring.senaste_priser() if namn == ingrediens),
            key=lambda p: (p.kr_per_kg, p.butik, p.produkt_id),
        )

    def las(self, ingrediens: str, butik: str, produkt_id: str) -> None:
        self._ingrediens(ingrediens)
        self._lagring.las(ingrediens, butik, produkt_id)

    def ta_bort_las(self, ingrediens: str, butik: str) -> bool:
        return self._lagring.ta_bort_las(ingrediens, butik)

    def lasningar(self) -> dict[tuple[str, str], str]:
        return self._lagring.lasningar()

    def _priser(self) -> _Priser:
        produkter: dict[str, list[Produkt]] = {}
        hamtade: datetime | None = None
        for ingrediens, produkt, tid in self._lagring.senaste_priser():
            produkter.setdefault(ingrediens, []).append(produkt)
            hamtade = tid if hamtade is None else min(hamtade, tid)

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
        return _Priser(produkter, hamtade, tuple(varningar))

    def _butikspriser(self, priser: _Priser) -> tuple[Ingrediens, ...]:
        """Katalogen med billigaste butikspris per kg; platshållarpris där butikspris saknas."""
        return tuple(
            dataclasses.replace(i, kr_per_kg=min(p.kr_per_kg for p in priser.produkter[i.namn]))
            if priser.produkter.get(i.namn)
            else i
            for i in self._katalog
        )

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
