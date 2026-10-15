"""SQLite-lagring för inställningar, prishistorik, produktlås och lager.

Ingredienskatalogen ägs av koden tills Livsmedelsverket kopplas in (#5).
"""

import dataclasses
import json
import pickle
import sqlite3
from datetime import datetime
from pathlib import Path

from .bunkra import Bunkring
from .butiker import WILLYS_KUNGALV, YTTERBY, Produkt, ValdButik
from .katalog import Ingrediens
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
    "frys_kg": 10,
    "torr_kg": 2,
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
CREATE TABLE IF NOT EXISTS bunkring (
    ingrediens TEXT PRIMARY KEY,
    data BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS plan_val (
    block INTEGER NOT NULL,
    slot TEXT NOT NULL,
    ingrediens TEXT NOT NULL,
    PRIMARY KEY (block, slot)
);
CREATE TABLE IF NOT EXISTS katalog (
    butik TEXT NOT NULL,
    produkt_id TEXT NOT NULL,
    varumarke TEXT NOT NULL,
    namn TEXT NOT NULL,
    beskrivning TEXT NOT NULL,
    ean TEXT NOT NULL,
    kategori TEXT NOT NULL,
    forpackning_g REAL,
    pris_kr REAL NOT NULL,
    kr_per_kg REAL NOT NULL,
    erbjudande INTEGER NOT NULL,
    kcal REAL,
    protein REAL,
    fett REAL,
    kolhydrater REAL,
    fiber REAL,
    forst_sedd TEXT NOT NULL,
    senast_sedd TEXT NOT NULL,
    aktiv INTEGER NOT NULL,
    PRIMARY KEY (butik, produkt_id)
);
CREATE TABLE IF NOT EXISTS katalogpriser (
    tid TEXT NOT NULL,
    butik TEXT NOT NULL,
    produkt_id TEXT NOT NULL,
    pris_kr REAL NOT NULL,
    kr_per_kg REAL NOT NULL,
    erbjudande INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS katalogpriser_produkt ON katalogpriser (butik, produkt_id, tid);
CREATE TABLE IF NOT EXISTS grupper (
    namn TEXT PRIMARY KEY,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (
    nyckel TEXT PRIMARY KEY,
    varde TEXT NOT NULL
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
        # GUI:t kör hämtningar och butiksval i en bakgrundstråd (en åt gången).
        self._db = sqlite3.connect(sokvag, check_same_thread=False)
        self._db.executescript(_SCHEMA)
        self._migrera_butiksval()
        self._seeda()

    def _migrera_butiksval(self) -> None:
        """Första gången: gör de gamla av/på-inställningarna butik_citygross och
        butik_willys till ett butiksval. Ytterby är standard; Willys Kungälv blir
        vald bara om den var den enda påslagna."""
        if self._db.execute("SELECT 1 FROM meta WHERE nyckel = 'butik'").fetchone():
            return
        gamla = dict(self._db.execute(
            "SELECT nyckel, varde FROM installningar WHERE nyckel IN ('butik_citygross', 'butik_willys')"
        ))
        vald = WILLYS_KUNGALV if gamla.get("butik_willys") and not gamla.get("butik_citygross", 1) else YTTERBY
        self.spara_vald_butik(vald)

    def vald_butik(self) -> ValdButik:
        rad = self._db.execute("SELECT varde FROM meta WHERE nyckel = 'butik'").fetchone()
        return ValdButik(**json.loads(rad[0])) if rad else YTTERBY

    def spara_vald_butik(self, butik: ValdButik) -> None:
        with self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO meta VALUES ('butik', ?)", (json.dumps(dataclasses.asdict(butik)),)
            )

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
        """kr/kg per (butik, produkt) sedan `fran`, från både sökhämtningar och sortimentssynkar."""
        rader = self._db.execute(
            """
            SELECT p.butik, p.produkt_id, h.tid, p.kr_per_kg
            FROM priser p JOIN hamtningar h ON h.id = p.hamtning
            WHERE h.tid >= ?
            UNION ALL
            SELECT butik, produkt_id, tid, kr_per_kg FROM katalogpriser WHERE tid >= ?
            """,
            (fran.isoformat(), fran.isoformat()),
        )
        historik: dict[tuple[str, str], list[tuple[datetime, float]]] = {}
        for butik, produkt_id, tid, kr_per_kg in rader:
            historik.setdefault((butik, produkt_id), []).append((datetime.fromisoformat(tid), kr_per_kg))
        return historik

    def senaste_hamtning(self) -> datetime | None:
        rad = self._db.execute(
            "SELECT MAX(tid) FROM (SELECT tid FROM hamtningar UNION ALL SELECT tid FROM katalogpriser)"
        ).fetchone()
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

    def spara_bunkring(self, bunkring: Bunkring) -> None:
        with self._db:
            self._db.execute("INSERT OR REPLACE INTO bunkring VALUES (?, ?)", (bunkring.ingrediens, pickle.dumps(bunkring)))

    def ta_bort_bunkring(self, ingrediens: str | None = None) -> bool:
        """Tar bort en accepterad bunkring, eller alla om ingen ingrediens anges."""
        with self._db:
            if ingrediens is None:
                return self._db.execute("DELETE FROM bunkring").rowcount > 0
            return self._db.execute("DELETE FROM bunkring WHERE ingrediens = ?", (ingrediens,)).rowcount > 0

    def bunkringar(self) -> list[Bunkring]:
        rader = self._db.execute("SELECT data FROM bunkring ORDER BY ingrediens")
        resultat = []
        for (data,) in rader:
            try:
                resultat.append(pickle.loads(data))
            except Exception:  # sparad med en äldre version av koden
                continue
        return resultat

    def plan_val(self) -> dict[tuple[int, str], str]:
        rader = self._db.execute("SELECT block, slot, ingrediens FROM plan_val")
        return {(block, slot): ingrediens for block, slot, ingrediens in rader}

    def satt_plan_val(self, val: dict[tuple[int, str], str]) -> None:
        with self._db:
            self._db.execute("DELETE FROM plan_val")
            self._db.executemany(
                "INSERT INTO plan_val VALUES (?, ?, ?)", [(b, slot, namn) for (b, slot), namn in val.items()]
            )

    def synka_katalog(self, butik: str, produkter: list[Produkt], tid: datetime) -> tuple[int, int, int]:
        """Ersätter butikens sortiment: nya läggs till, befintliga uppdateras och de
        som saknas markeras som inte längre sålda. Pris sparas i historiken.
        Returnerar (antal, nya, utgångna)."""
        nu = tid.isoformat()
        with self._db:
            fore = {pid for (pid,) in self._db.execute(
                "SELECT produkt_id FROM katalog WHERE butik = ? AND aktiv = 1", (butik,)
            )}
            kanda = {pid for (pid,) in self._db.execute("SELECT produkt_id FROM katalog WHERE butik = ?", (butik,))}
            unika = {p.produkt_id: p for p in produkter}
            for p in unika.values():
                self._db.execute(
                    """
                    INSERT INTO katalog VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                    ON CONFLICT (butik, produkt_id) DO UPDATE SET
                        varumarke = excluded.varumarke, namn = excluded.namn, beskrivning = excluded.beskrivning,
                        ean = excluded.ean, kategori = excluded.kategori, forpackning_g = excluded.forpackning_g,
                        pris_kr = excluded.pris_kr, kr_per_kg = excluded.kr_per_kg, erbjudande = excluded.erbjudande,
                        kcal = excluded.kcal, protein = excluded.protein, fett = excluded.fett,
                        kolhydrater = excluded.kolhydrater, fiber = excluded.fiber,
                        senast_sedd = excluded.senast_sedd, aktiv = 1
                    """,
                    (
                        butik, p.produkt_id, p.varumarke, p.namn, p.beskrivning, p.ean, p.kategori, p.forpackning_g,
                        p.pris_kr, p.kr_per_kg, int(p.erbjudande), p.kcal, p.protein, p.fett, p.kolhydrater,
                        p.fiber, nu, nu,
                    ),
                )
            self._db.executemany(
                "INSERT INTO katalogpriser VALUES (?, ?, ?, ?, ?, ?)",
                [(nu, butik, p.produkt_id, p.pris_kr, p.kr_per_kg, int(p.erbjudande)) for p in unika.values()],
            )
            utgangna = fore - set(unika)
            self._db.executemany(
                "UPDATE katalog SET aktiv = 0 WHERE butik = ? AND produkt_id = ?", [(butik, pid) for pid in utgangna]
            )
        return len(unika), len(set(unika) - kanda), len(utgangna)

    def katalog(self, butiker: set[str] | None = None, bara_aktiva: bool = True) -> list[Produkt]:
        rader = self._db.execute(
            """
            SELECT butik, produkt_id, namn, varumarke, forpackning_g, pris_kr, kr_per_kg, erbjudande, kategori,
                   beskrivning, ean, kcal, protein, fett, kolhydrater, fiber, aktiv
            FROM katalog ORDER BY butik, namn, produkt_id
            """
        )
        produkter = []
        for (butik, pid, namn, marke, forp, pris, krkg, erb, kat, besk, ean, kcal, prot, fett, kh, fib, aktiv) in rader:
            if bara_aktiva and not aktiv:
                continue
            if butiker is not None and butik not in butiker:
                continue
            produkter.append(Produkt(butik, pid, namn, marke, forp, pris, krkg, bool(erb), kat, besk, ean, kcal, prot, fett, kh, fib))
        return produkter

    def katalogpriser(self, butik: str, produkt_id: str) -> list[tuple[datetime, float]]:
        rader = self._db.execute(
            "SELECT tid, kr_per_kg FROM katalogpriser WHERE butik = ? AND produkt_id = ? ORDER BY tid",
            (butik, produkt_id),
        )
        return [(datetime.fromisoformat(tid), kr) for tid, kr in rader]

    def katalogtider(self) -> dict[str, datetime]:
        """Senaste sortimentssynk per butik."""
        rader = self._db.execute("SELECT butik, MAX(senast_sedd) FROM katalog GROUP BY butik")
        return {butik: datetime.fromisoformat(tid) for butik, tid in rader}

    # --- Ingrediensgrupper ------------------------------------------------

    def seeda_grupper(self, grupper: tuple[Ingrediens, ...]) -> None:
        """Lägger in de inbyggda grupperna första gången. En grupp som tagits
        bort kommer inte tillbaka."""
        if self._db.execute("SELECT 1 FROM meta WHERE nyckel = 'grupper_seedade'").fetchone():
            return
        with self._db:
            for grupp in grupper:
                self._db.execute(
                    "INSERT OR IGNORE INTO grupper VALUES (?, ?)", (grupp.namn, json.dumps(dataclasses.asdict(grupp)))
                )
            self._db.execute("INSERT INTO meta VALUES ('grupper_seedade', '1')")

    def grupper(self) -> list[Ingrediens]:
        falt = {f.name for f in dataclasses.fields(Ingrediens)}
        resultat = []
        for (data,) in self._db.execute("SELECT data FROM grupper ORDER BY namn"):
            varden = {k: tuple(v) if isinstance(v, list) else v for k, v in json.loads(data).items() if k in falt}
            resultat.append(Ingrediens(**varden))
        return resultat

    def spara_grupp(self, grupp: Ingrediens) -> None:
        with self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO grupper VALUES (?, ?)", (grupp.namn, json.dumps(dataclasses.asdict(grupp)))
            )

    def ta_bort_grupp(self, namn: str) -> bool:
        with self._db:
            return self._db.execute("DELETE FROM grupper WHERE namn = ?", (namn,)).rowcount > 0
