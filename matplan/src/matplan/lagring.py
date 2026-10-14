"""SQLite-lagring för inställningar och prishistorik.

Ingredienskatalogen ägs av koden tills Livsmedelsverket kopplas in (#5).
"""

import sqlite3
from datetime import datetime
from pathlib import Path

from .butiker import Produkt

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

_SCHEMA = """
CREATE TABLE IF NOT EXISTS installningar (
    nyckel TEXT PRIMARY KEY,
    varde REAL NOT NULL
);
DROP TABLE IF EXISTS ingredienser;
CREATE TABLE IF NOT EXISTS hamtningar (
    id INTEGER PRIMARY KEY,
    tid TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS priser (
    hamtning INTEGER NOT NULL REFERENCES hamtningar(id),
    ingrediens TEXT NOT NULL,
    butik TEXT NOT NULL,
    produkt_id TEXT NOT NULL,
    namn TEXT NOT NULL,
    varumarke TEXT NOT NULL,
    forpackning_g REAL,
    pris_kr REAL NOT NULL,
    kr_per_kg REAL NOT NULL,
    erbjudande INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS priser_butik ON priser (butik, hamtning);
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
            nycklar = tuple(STANDARDINSTALLNINGAR)
            self._db.execute(
                f"DELETE FROM installningar WHERE nyckel NOT IN ({','.join('?' * len(nycklar))})",
                nycklar,
            )
            self._db.executemany(
                "INSERT OR IGNORE INTO installningar VALUES (?, ?)",
                STANDARDINSTALLNINGAR.items(),
            )

    def installningar(self) -> dict[str, float]:
        rader = self._db.execute("SELECT nyckel, varde FROM installningar ORDER BY nyckel")
        return {nyckel: varde for nyckel, varde in rader}

    def satt_installning(self, nyckel: str, varde: float) -> None:
        with self._db:
            self._db.execute("UPDATE installningar SET varde = ? WHERE nyckel = ?", (varde, nyckel))

    def spara_hamtning(self, tid: datetime, priser: dict[str, list[Produkt]]) -> None:
        """Sparar en hämtning: produkter per ingrediens."""
        with self._db:
            hamtning = self._db.execute("INSERT INTO hamtningar (tid) VALUES (?)", (tid.isoformat(),)).lastrowid
            self._db.executemany(
                "INSERT INTO priser VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        hamtning, ingrediens, p.butik, p.produkt_id, p.namn, p.varumarke,
                        p.forpackning_g, p.pris_kr, p.kr_per_kg, int(p.erbjudande),
                    )
                    for ingrediens, produkter in priser.items()
                    for p in produkter
                ],
            )

    def senaste_priser(self) -> list[tuple[str, Produkt, datetime]]:
        """Varje butiks priser från dess senaste hämtning med data."""
        rader = self._db.execute(
            """
            SELECT p.ingrediens, p.butik, p.produkt_id, p.namn, p.varumarke, p.forpackning_g,
                   p.pris_kr, p.kr_per_kg, p.erbjudande, h.tid
            FROM priser p
            JOIN hamtningar h ON h.id = p.hamtning
            JOIN (SELECT butik, MAX(hamtning) AS senaste FROM priser GROUP BY butik) s
              ON s.butik = p.butik AND s.senaste = p.hamtning
            ORDER BY p.ingrediens, p.butik, p.produkt_id
            """
        )
        return [
            (ingrediens, Produkt(butik, pid, namn, marke, forp, pris, krkg, bool(erb)), datetime.fromisoformat(tid))
            for ingrediens, butik, pid, namn, marke, forp, pris, krkg, erb, tid in rader
        ]

    def antal_hamtningar(self) -> int:
        return self._db.execute("SELECT COUNT(*) FROM hamtningar").fetchone()[0]
