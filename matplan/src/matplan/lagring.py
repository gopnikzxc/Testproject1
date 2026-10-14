"""SQLite-lagring för inställningar, prishistorik, produktlås och lager.

Ingredienskatalogen ägs av koden tills Livsmedelsverket kopplas in (#5).
"""

import pickle
import sqlite3
from datetime import datetime
from pathlib import Path

from .butiker import Produkt
from .naring import Naring
from .planerare import Plan

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
    "veckobudget": 1250,
    "manadsbudget": 5000,
    "rea_procent": 25,
    "rea_veckor": 8,
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
CREATE TABLE IF NOT EXISTS las (
    ingrediens TEXT NOT NULL,
    butik TEXT NOT NULL,
    produkt_id TEXT NOT NULL,
    PRIMARY KEY (ingrediens, butik)
);
CREATE TABLE IF NOT EXISTS lager (
    ingrediens TEXT PRIMARY KEY,
    gram REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS naring (
    ingrediens TEXT PRIMARY KEY,
    kalla TEXT NOT NULL,
    kcal REAL NOT NULL,
    protein REAL NOT NULL,
    fett REAL,
    kolhydrater REAL,
    fiber REAL,
    vatten REAL,
    hamtad TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS aktiv_plan (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    plan BLOB NOT NULL
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

    def prishistorik(self, fran: datetime) -> dict[tuple[str, str], list[tuple[datetime, float]]]:
        """kr/kg per (butik, produkt) från hämtningar sedan `fran`."""
        rader = self._db.execute(
            """
            SELECT p.butik, p.produkt_id, h.tid, p.kr_per_kg
            FROM priser p JOIN hamtningar h ON h.id = p.hamtning
            WHERE h.tid >= ?
            """,
            (fran.isoformat(),),
        )
        historik: dict[tuple[str, str], list[tuple[datetime, float]]] = {}
        for butik, produkt_id, tid, kr_per_kg in rader:
            historik.setdefault((butik, produkt_id), []).append((datetime.fromisoformat(tid), kr_per_kg))
        return historik

    def senaste_hamtning(self) -> datetime | None:
        rad = self._db.execute("SELECT MAX(tid) FROM hamtningar").fetchone()
        return datetime.fromisoformat(rad[0]) if rad[0] else None

    def antal_hamtningar(self) -> int:
        return self._db.execute("SELECT COUNT(*) FROM hamtningar").fetchone()[0]

    def las(self, ingrediens: str, butik: str, produkt_id: str) -> None:
        with self._db:
            self._db.execute("INSERT OR REPLACE INTO las VALUES (?, ?, ?)", (ingrediens, butik, produkt_id))

    def ta_bort_las(self, ingrediens: str, butik: str) -> bool:
        with self._db:
            return self._db.execute(
                "DELETE FROM las WHERE ingrediens = ? AND butik = ?", (ingrediens, butik)
            ).rowcount > 0

    def lasningar(self) -> dict[tuple[str, str], str]:
        rader = self._db.execute("SELECT ingrediens, butik, produkt_id FROM las ORDER BY ingrediens, butik")
        return {(ingrediens, butik): pid for ingrediens, butik, pid in rader}

    def lager(self) -> dict[str, float]:
        rader = self._db.execute("SELECT ingrediens, gram FROM lager WHERE gram > 0 ORDER BY ingrediens")
        return dict(rader.fetchall())

    def satt_lager(self, ingrediens: str, gram: float) -> None:
        with self._db:
            self._db.execute("INSERT OR REPLACE INTO lager VALUES (?, ?)", (ingrediens, max(gram, 0.0)))

    def spara_aktiv_plan(self, plan: Plan) -> None:
        with self._db:
            self._db.execute("INSERT OR REPLACE INTO aktiv_plan VALUES (1, ?)", (pickle.dumps(plan),))

    def aktiv_plan(self) -> Plan | None:
        rad = self._db.execute("SELECT plan FROM aktiv_plan WHERE id = 1").fetchone()
        if rad is None:
            return None
        try:
            return pickle.loads(rad[0])
        except Exception:  # sparad med en äldre version av koden
            return None

    def rensa_aktiv_plan(self) -> None:
        with self._db:
            self._db.execute("DELETE FROM aktiv_plan")

    def spara_naring(self, ingrediens: str, naring: Naring, tid: datetime) -> None:
        with self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO naring VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    ingrediens, naring.kalla, naring.kcal, naring.protein, naring.fett,
                    naring.kolhydrater, naring.fiber, naring.vatten, tid.isoformat(),
                ),
            )

    def naring(self) -> dict[str, Naring]:
        rader = self._db.execute(
            "SELECT ingrediens, kalla, kcal, protein, fett, kolhydrater, fiber, vatten FROM naring"
        )
        return {rad[0]: Naring(*rad[1:]) for rad in rader}
