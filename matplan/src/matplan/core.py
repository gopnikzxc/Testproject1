"""matplan-kärnan: varje användningsfall som ett kommando.

CLI och (senare) Textual-GUI är tunna skal ovanpå den här klassen.
"""

import dataclasses
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from .butiker import Butik, ButiksFel, Produkt, matchar
from .katalog import STARTKATALOG, Ingrediens
from .lagring import Lagring
from .planerare import Plan, PlaneringsFel, Profil, Vikter, planera

__all__ = ["Matplan", "PlaneringsFel", "PERSONER", "Hamtningsresultat"]

# Barnet planeras inte (se spec #1).
PERSONER = ("jag", "fru")


@dataclass(frozen=True)
class Hamtningsresultat:
    tid: datetime
    antal_produkter: dict[str, int] = field(default_factory=dict)
    fel: dict[str, str] = field(default_factory=dict)


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

    def plan(self, start: date | None = None) -> Plan:
        inst = self._lagring.installningar()
        profiler = tuple(
            Profil(namn, inst[f"{namn}.kcal_mal"], inst[f"{namn}.protein_mal"]) for namn in PERSONER
        )
        ingredienser, hamtade, utan_pris = self._prissatt_katalog()
        plan = planera(
            list(ingredienser),
            profiler,
            start=start or date.today(),
            plandagar=int(inst["plandagar"]),
            frukost=bool(inst["frukost"]),
            antal_mellanmal=int(inst["antal_mellanmal"]),
            vikter=Vikter(inst["vikt_protein"], inst["vikt_volym"], inst["vikt_kostnad"]),
        )
        return dataclasses.replace(plan, priser_hamtade=hamtade, utan_butikspris=utan_pris)

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

    def _prissatt_katalog(self) -> tuple[tuple[Ingrediens, ...], datetime | None, tuple[str, ...]]:
        """Katalogen med billigaste butikspris per kg; platshållarpris där butikspris saknas."""
        billigast: dict[str, float] = {}
        hamtade: datetime | None = None
        for ingrediens, produkt, tid in self._lagring.senaste_priser():
            if ingrediens not in billigast or produkt.kr_per_kg < billigast[ingrediens]:
                billigast[ingrediens] = produkt.kr_per_kg
            hamtade = tid if hamtade is None else min(hamtade, tid)
        if not billigast:
            return self._katalog, None, ()
        prissatt = tuple(
            dataclasses.replace(i, kr_per_kg=billigast[i.namn]) if i.namn in billigast else i for i in self._katalog
        )
        return prissatt, hamtade, tuple(i.namn for i in self._katalog if i.namn not in billigast)

    def installningar(self) -> dict[str, float]:
        return self._lagring.installningar()

    def satt_installning(self, nyckel: str, varde: float) -> None:
        if nyckel not in self._lagring.installningar():
            raise KeyError(f"Okänd inställning: {nyckel}")
        self._lagring.satt_installning(nyckel, float(varde))
