"""SQLite-lagring för inställningar och ingredienskatalog."""

import sqlite3
from pathlib import Path

from .katalog import STARTKATALOG, Ingrediens

STANDARDINSTALLNINGAR = {
    "jag.kcal_mal": 2000,
    "jag.protein_mal": 180,
    "fru.kcal_mal": 1700,
    "fru.protein_mal": 110,
    "frukost": 1,
    "antal_mellanmal": 2,
    "plandagar": 7,
    "vikt_protein": 1,
    "vikt_volym": 1,
    "vikt_kostnad": 1,
}

# Katalogen ägs av koden tills Livsmedelsverket och butikspriser finns
# (#5, #6), så tabellen byggs om från startkatalogen vid varje start.
_SCHEMA = """
CREATE TABLE IF NOT EXISTS installningar (
    nyckel TEXT PRIMARY KEY,
    varde REAL NOT NULL
);
DROP TABLE IF EXISTS ingredienser;
CREATE TABLE ingredienser (
    namn TEXT PRIMARY KEY,
    kategori TEXT NOT NULL,
    kcal_100g REAL NOT NULL,
    protein_100g REAL NOT NULL,
    kr_per_kg REAL NOT NULL
);
"""


class Lagring:
    def __init__(self, sokvag: Path, katalog: tuple[Ingrediens, ...] = STARTKATALOG):
        self._katalog = katalog
        sokvag = Path(sokvag)
        sokvag.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(sokvag)
        self._db.executescript(_SCHEMA)
        self._seeda()

    def _seeda(self) -> None:
        with self._db:
            nycklar = tuple(STANDARDINSTALLNINGAR)
            self._db.execute(
                f"DELETE FROM installningar WHERE nyckel NOT IN ({','.join('?' * len(nycklar))})",
                nycklar,
            )
            self._db.executemany(
                "INSERT OR IGNORE INTO installningar VALUES (?, ?)",
                STANDARDINSTALLNINGAR.items(),
            )
            self._db.executemany(
                "INSERT INTO ingredienser VALUES (?, ?, ?, ?, ?)",
                [
                    (i.namn, i.kategori, i.kcal_100g, i.protein_100g, i.kr_per_kg)
                    for i in self._katalog
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
            "SELECT namn, kategori, kcal_100g, protein_100g, kr_per_kg FROM ingredienser ORDER BY namn"
        )
        return [Ingrediens(*rad) for rad in rader]
