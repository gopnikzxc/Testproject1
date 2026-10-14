"""Byta ingrediens i ett blocks lunch och middag (#15)."""

import dataclasses
from datetime import date

import pytest

from matplan.cli import main
from matplan.core import Matplan, PlaneringsFel
from matplan.katalog import STARTKATALOG

START = date(2026, 10, 15)


@pytest.fixture
def app(tmp_path):
    """Gott om budget, så att testerna handlar om bytet och inte om budgeten."""
    app = Matplan(tmp_path / "m.db")
    app.satt_installning("veckobudget", 5000)
    app.satt_installning("manadsbudget", 20000)
    return app


def _slot(plan, block, slot):
    return next(r.namn for r in plan.block[block - 1].batch.portioner[0].rader if r.slot == slot)


def test_byt_till_vald_ingrediens(app):
    plan = app.byt(1, "kolhydrater", "Potatis", start=START)

    assert _slot(plan, 1, "kolhydrater") == "Potatis"
    assert app.byten() == {(1, "kolhydrater"): "Potatis"}


def test_bytet_galler_tills_vidare_och_malen_haller(app):
    app.byt(1, "kolhydrater", "Potatis", start=START)

    plan = app.plan(START)

    assert _slot(plan, 1, "kolhydrater") == "Potatis"
    for dag in plan.block[0].dagar:
        assert dag.kcal("jag") <= 2000 and dag.protein("jag") >= 180


def test_byt_utan_ingrediens_tar_nasta_i_tur(app):
    fore = _slot(app.plan(START), 1, "protein")

    efter = _slot(app.byt(1, "protein", start=START), 1, "protein")

    assert efter != fore


def test_bytet_andrar_totaler_och_inkopslista(app):
    fore_plan, fore_lista = app.plan(START), app.inkopslista(START)

    app.byt(1, "kolhydrater", "Potatis", start=START)

    assert app.plan(START).kr != pytest.approx(fore_plan.kr)
    assert "Potatis" in {r.ingrediens for r in app.inkopslista(START).rader}
    assert {r.ingrediens for r in app.inkopslista(START).rader} != {r.ingrediens for r in fore_lista.rader}


def test_ny_plan_rensar_byten(app):
    app.byt(1, "kolhydrater", "Potatis", start=START)

    app.plan(START, ny=True)

    assert app.byten() == {}


def test_byte_som_spracker_budgeten_avvisas_och_lamnar_planen_orord(tmp_path):
    dyr_torsk = tuple(
        dataclasses.replace(i, kr_per_kg=500) if i.namn == "Torskfilé, fryst" else i for i in STARTKATALOG
    )
    app = Matplan(tmp_path / "m.db", katalog=dyr_torsk)  # standardbudget 1250 kr/vecka
    fore_plan = app.plan(START)

    with pytest.raises(PlaneringsFel, match="Budgeten"):
        app.byt(1, "protein", "Torskfilé, fryst", start=START)

    assert app.byten() == {}
    assert app.plan(START).block == fore_plan.block


def test_ogiltiga_byten_avvisas(app):
    fore = app.byten()

    with pytest.raises(KeyError, match="ingen ingrediens för protein"):
        app.byt(1, "protein", "Potatis", start=START)
    with pytest.raises(KeyError, match="Block 9 finns inte"):
        app.byt(9, "protein", start=START)
    with pytest.raises(KeyError, match="Okänd slot"):
        app.byt(1, "dessert", start=START)
    assert app.byten() == fore


def test_kopt_plan_kan_inte_bytas(app):
    app.kopt(START)

    with pytest.raises(PlaneringsFel, match="köpt"):
        app.byt(1, "kolhydrater", "Potatis", start=START)


def test_cli_byt(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MATPLAN_DB", str(tmp_path / "cli.db"))
    main(["installningar", "veckobudget", "5000"])
    main(["installningar", "manadsbudget", "20000"])

    assert main(["byt", "1", "kolhydrater", "Potatis"]) == 0
    assert main(["byt"]) == 0
    assert "Block 1, kolhydrater: Potatis" in capsys.readouterr().out
    assert main(["byt", "--rensa"]) == 0
    assert main(["byt", "1", "protein", "Potatis"]) == 1
