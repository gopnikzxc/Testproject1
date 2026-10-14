"""matplan-kärnan: varje användningsfall som ett kommando.

CLI och (senare) Textual-GUI är tunna skal ovanpå den här klassen.
"""

from pathlib import Path

from .lagring import Lagring
from .planerare import Plan, PlaneringsFel, planera

__all__ = ["Matplan", "PlaneringsFel"]


class Matplan:
    def __init__(self, db_sokvag: Path):
        self._lagring = Lagring(db_sokvag)

    def plan(self) -> Plan:
        installningar = self._lagring.installningar()
        return planera(
            self._lagring.ingredienser(),
            kcal_mal=installningar["kcal_mal"],
            protein_mal=installningar["protein_mal"],
        )

    def installningar(self) -> dict[str, float]:
        return self._lagring.installningar()

    def satt_installning(self, nyckel: str, varde: float) -> None:
        if nyckel not in self._lagring.installningar():
            raise KeyError(f"Okänd inställning: {nyckel}")
        self._lagring.satt_installning(nyckel, float(varde))
