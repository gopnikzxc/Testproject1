"""matplan-kärnan: varje användningsfall som ett kommando.

CLI och (senare) Textual-GUI är tunna skal ovanpå den här klassen.
"""

from datetime import date
from pathlib import Path

from .lagring import Lagring
from .planerare import Plan, PlaneringsFel, Profil, planera

__all__ = ["Matplan", "PlaneringsFel", "PERSONER"]

# Barnet planeras inte (se spec #1).
PERSONER = ("jag", "fru")


class Matplan:
    def __init__(self, db_sokvag: Path):
        self._lagring = Lagring(db_sokvag)

    def plan(self, start: date | None = None) -> Plan:
        inst = self._lagring.installningar()
        profiler = tuple(
            Profil(namn, inst[f"{namn}.kcal_mal"], inst[f"{namn}.protein_mal"]) for namn in PERSONER
        )
        return planera(
            self._lagring.ingredienser(),
            profiler,
            start=start or date.today(),
            plandagar=int(inst["plandagar"]),
            frukost=bool(inst["frukost"]),
            antal_mellanmal=int(inst["antal_mellanmal"]),
        )

    def installningar(self) -> dict[str, float]:
        return self._lagring.installningar()

    def satt_installning(self, nyckel: str, varde: float) -> None:
        if nyckel not in self._lagring.installningar():
            raise KeyError(f"Okänd inställning: {nyckel}")
        self._lagring.satt_installning(nyckel, float(varde))
