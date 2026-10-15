"""Godkänna produkter som nya grupper och hantera grupper (#31)."""

import time
from datetime import date, datetime

import pytest
from conftest import SortimentButik, katalogvara, standardsortiment

from matplan.cli import main
from matplan.core import Matplan
from matplan.katalog import STARTKATALOG, Ingrediens

START = date(2026, 10, 15)
NU = datetime(2026, 10, 15, 9, 0)
KONSERV = "Skafferiet / Konserver"


def _tonfisk(erbjudande=False):
    def vara(pid, namn, marke, kr, besk="3X170G", fett=0.2, erb=False):
        return katalogvara(pid, namn, marke=marke, besk=besk, kr=kr, kcal=110, protein=26.0, kolhydrater=0.0,
                           fett=fett, kategori=KONSERV, forpackning_g=510, erbjudande=erb)

    return [
        vara("tf-1", "Tonfisk i Vatten", "GARANT", 90),
        vara("tf-2", "Tonfisk Vatten", "ELDORADO", 80, erb=erbjudande),
        vara("tf-3", "Tonfisk i Olja", "GARANT", 85, fett=6.0),
        vara("tf-4", "Tonfisk i Vatten MSC", "ABBA", 120),
    ]


def _app(tmp_path, extra=None, erbjudande=False):
    butik = SortimentButik(standardsortiment() + (extra if extra is not None else _tonfisk(erbjudande)))
    app = Matplan(tmp_path / "m.db", butiker=(butik,))
    app.satt_installning("veckobudget", 5000)
    app.satt_installning("manadsbudget", 20000)
    app.refresh(nu=NU)
    return app


def _ids(app, grupp):
    return sorted(p.produkt_id for p in app.produkter(grupp))


def test_godkand_produkt_blir_grupp_med_foreslagna_varden(tmp_path):
    app = _app(tmp_path)

    g = app.godkann("tf-1")

    assert g.ny and g.produkter == 3
    assert g.grupp.namn == "Tonfisk i vatten"
    assert g.grupp.sokord == ("tonfisk vatten",)
    assert g.grupp.butikskategori == ("konserver",)
    assert (g.grupp.kategori, g.grupp.forvaring) == ("protein", "torrvara")
    # Andra märken av tonfisk i vatten kommer med; tonfisk i olja gör det inte.
    assert _ids(app, "Tonfisk i vatten") == ["tf-1", "tf-2", "tf-4"]


def test_produkt_som_redan_ar_i_en_grupp_ger_den_gruppen(tmp_path):
    app = _app(tmp_path)
    app.godkann("tf-1")

    andra = app.godkann("tf-2")
    inbyggd = app.godkann("id-Kycklingfilé")

    assert (andra.ny, andra.grupp.namn) == (False, "Tonfisk i vatten")
    assert (inbyggd.ny, inbyggd.grupp.namn) == (False, "Kycklingfilé")
    assert sum(1 for g, _ in app.grupper() if g.namn.startswith("Tonfisk")) == 1


def test_ny_grupp_ingar_i_plan_inkopslista_och_rea(tmp_path):
    app = _app(tmp_path, erbjudande=True)
    app.godkann("tf-1")

    plan = app.byt(1, "protein", "Tonfisk i vatten", start=START)

    assert plan.block[0].batch.portioner[0].rader[0].namn == "Tonfisk i vatten"
    assert "Tonfisk i vatten" in plan.rea  # billigaste produkten har butikens erbjudande
    rad = next(r for r in app.inkopslista(START).rader if r.ingrediens == "Tonfisk i vatten")
    assert rad.billigast[1].produkt.produkt_id == "tf-2"


def test_ny_grupp_kan_bunkras(tmp_path):
    app = _app(tmp_path, erbjudande=True)
    app.godkann("tf-1")

    assert "Tonfisk i vatten" in {b.ingrediens for b in app.bunkra()}


def test_byt_namn_flyttar_lager_och_las(tmp_path):
    app = _app(tmp_path)
    app.godkann("tf-1")
    app.satt_lager("Tonfisk i vatten", 510)
    app.las("Tonfisk i vatten", "City Gross Ytterby", "tf-4")

    app.byt_gruppnamn("tonfisk i vatten", "Tonfisk naturell")

    assert "Tonfisk naturell" in {g.namn for g, _ in app.grupper()}
    assert app.lager() == {"Tonfisk naturell": 510}
    assert app.lasningar() == {("Tonfisk naturell", "City Gross Ytterby"): "tf-4"}
    with pytest.raises(ValueError, match="redan en grupp"):
        app.byt_gruppnamn("Tonfisk naturell", "Ägg")


def test_sokord_uteslut_och_inkludera(tmp_path):
    app = _app(tmp_path)
    app.godkann("tf-1")

    app.satt_sokord("Tonfisk i vatten", ("tonfisk",))
    assert _ids(app, "Tonfisk i vatten") == ["tf-1", "tf-2", "tf-3", "tf-4"]

    app.uteslut_produkt("Tonfisk i vatten", "tf-3")
    assert _ids(app, "Tonfisk i vatten") == ["tf-1", "tf-2", "tf-4"]

    app.inkludera_produkt("Tonfisk i vatten", "tf-3")
    assert "tf-3" in _ids(app, "Tonfisk i vatten")

    # En produkt som inte matchar söktermerna kan läggas till för hand.
    app.satt_sokord("Tonfisk i vatten", ("tonfisk vatten",))
    app.inkludera_produkt("Tonfisk i vatten", "tf-3")
    assert _ids(app, "Tonfisk i vatten") == ["tf-1", "tf-2", "tf-3", "tf-4"]


def test_grupp_kan_tas_bort(tmp_path):
    app = _app(tmp_path)
    app.godkann("tf-1")
    app.byt(1, "protein", "Tonfisk i vatten", start=START)
    app.rensa_byten()

    app.ta_bort_grupp("Tonfisk i vatten")

    assert "Tonfisk i vatten" not in {g.namn for g, _ in app.grupper()}
    assert "Tonfisk i vatten" not in app.plan(START).total_gram()
    with pytest.raises(KeyError):
        app.ta_bort_grupp("Tonfisk i vatten")


def test_juice_och_fasta_grupper_kan_inte_godkannas(tmp_path):
    juice = katalogvara("j-1", "Apelsinjuice", kcal=45, protein=0.7, kolhydrater=9.0, fett=0.0,
                        kategori="Dryck / Juice, fruktdrycker & smoothies")
    app = _app(tmp_path, extra=[juice])
    with pytest.raises(ValueError, match="planeras aldrig"):
        app.godkann("j-1")

    fast = Matplan(tmp_path / "f.db", katalog=STARTKATALOG)
    with pytest.raises(ValueError, match="fasta"):
        fast.godkann("tf-1")


def _stor_katalog():
    """Omkring 50 grupper i poolen, med platshållarpriser."""
    grupper = list(STARTKATALOG)
    for n in range(12):
        grupper.append(Ingrediens(f"Protein {n}", "protein", 100 + 8 * n, 18 + n % 7, 70 + 5 * n))
    for n in range(9):
        typ = "spannmål" if n % 2 else ""
        grupper.append(Ingrediens(f"Kolhydrat {n}", "kolhydrater", 340 + 3 * n, 8 + n % 4, 20 + 2 * n,
                                  ("ris",) if typ else ()))
    for n in range(10):
        grupper.append(Ingrediens(f"Grönsak {n}", "grönsaker", 20 + 3 * n, 1 + n % 3, 15 + 3 * n))
    for n in range(3):
        grupper.append(Ingrediens(f"Mejeri {n}", "mejeri", 60 + 5 * n, 10 + n, 40 + 5 * n))
    return tuple(grupper)


def test_stor_pool_planeras_snabbt(tmp_path):
    katalog = _stor_katalog()
    assert len(katalog) >= 50
    app = Matplan(tmp_path / "m.db", katalog=katalog)
    app.satt_installning("veckobudget", 5000)
    app.satt_installning("manadsbudget", 20000)

    borjan = time.perf_counter()
    plan = app.plan(START)
    tid = time.perf_counter() - borjan

    assert tid < 1.0, f"{tid:.2f} s"
    for dag in plan.dagar:
        for p in plan.profiler:
            assert dag.viktat_protein(p.namn) >= p.protein_mal - 1e-6


def test_cli_godkann_och_grupp(tmp_path, monkeypatch, capsys):
    import matplan.cli as cli

    monkeypatch.setenv("MATPLAN_DB", str(tmp_path / "cli.db"))
    monkeypatch.setenv("COLUMNS", "200")
    monkeypatch.setattr(cli, "_butiker", lambda vald: (SortimentButik(standardsortiment() + _tonfisk()),))
    assert main(["refresh"]) == 0
    capsys.readouterr()

    assert main(["godkänn", "tf-1"]) == 0
    assert "Ny grupp Tonfisk i vatten: slot protein, söktermer tonfisk vatten" in capsys.readouterr().out
    assert main(["godkänn", "tf-4"]) == 0
    assert "hör redan till gruppen Tonfisk i vatten (3 produkter)" in capsys.readouterr().out

    assert main(["grupp"]) == 0
    assert "Tonfisk i vatten" in capsys.readouterr().out
    assert main(["grupp", "Tonfisk i vatten", "--uteslut", "tf-4"]) == 0
    assert main(["grupp", "Tonfisk i vatten"]) == 0
    ut = capsys.readouterr().out
    assert "Uteslutna: tf-4" in ut and "tf-2" in ut
    assert main(["grupp", "Tonfisk i vatten", "--byt-namn", "Tonfisk naturell"]) == 0
    assert main(["grupp", "Tonfisk naturell", "--ta-bort"]) == 0
    assert "Tonfisk naturell är borttagen" in capsys.readouterr().out


def test_forfiltreringen_haller_aven_100_grupper_snabba(tmp_path):
    """Utan förfiltrering per slot tar det här flera sekunder."""
    grupper = list(STARTKATALOG)
    grupper += [Ingrediens(f"P{n}", "protein", 100 + 3 * n, 18 + n % 7, 70 + 2 * n) for n in range(30)]
    grupper += [Ingrediens(f"K{n}", "kolhydrater", 340 + n, 8 + n % 4, 20 + n, ("ris",) if n % 2 else ())
                for n in range(30)]
    grupper += [Ingrediens(f"G{n}", "grönsaker", 20 + n, 1 + n % 3, 15 + n) for n in range(30)]
    app = Matplan(tmp_path / "m.db", katalog=tuple(grupper))
    app.satt_installning("veckobudget", 5000)
    app.satt_installning("manadsbudget", 20000)

    borjan = time.perf_counter()
    app.plan(START)

    assert time.perf_counter() - borjan < 1.0
