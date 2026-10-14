"""SQLite-lagring för inställningar och ingredienskatalog."""

import sqlite3
from pathlib import Path

from .katalog import STARTKATALOG, Ingrediens

STANDARDINSTALLNINGAR = {
    "kcal_mal": 2000,
    "protein_mal": 180,
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS installningar (
    nyckel TEXT PRIMARY KEY,
    varde REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS ingredienser (
    namn TEXT PRIMARY KEY,
    slot TEXT NOT NULL,
    kcal_100g REAL NOT NULL,
    protein_100g REAL NOT NULL,
    kr_per_kg REAL NOT NULL
);
"""


class Lagring:
    def __init__(self, sokvag: Path):
        sokvag = Path(sokvag)
        sokvag.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(sokvag)
        self._db.executescript(_SCHEMA)
        self._seeda()

    def _seeda(self) -> None:
        with self._db:
            self._db.executemany(
                "INSERT OR IGNORE INTO installningar VALUES (?, ?)",
                STANDARDINSTALLNINGAR.items(),
            )
            self._db.executemany(
                "INSERT OR IGNORE INTO ingredienser VALUES (?, ?, ?, ?, ?)",
                [
                    (i.namn, i.slot, i.kcal_100g, i.protein_100g, i.kr_per_kg)
                    for i in STARTKATALOG
                ],
            )

    def installningar(self) -> dict[str, float]:
        rader = self._db.execute("SELECT nyckel, varde FROM installningar ORDER BY nyckel")
        return {nyckel: varde for nyckel, varde in rader}

    def satt_installning(self, nyckel: str, varde: float) -> None:
        with self._db:
            self._db.execute("UPDATE installningar SET varde = ? WHERE nyckel = ?", (varde, nyckel))

    def ingredienser(self) -> list[Ingrediens]:
        rader = self._db.execute(
            "SELECT namn, slot, kcal_100g, protein_100g, kr_per_kg FROM ingredienser ORDER BY namn"
        )
        return [Ingrediens(*rad) for rad in rader]
