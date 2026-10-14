import pytest

from matplan.cli import main
from matplan.core import Matplan, PlaneringsFel


@pytest.fixture
def app(tmp_path):
    return Matplan(tmp_path / "matplan.db")


def test_plan_ar_ett_tredagarsblock_med_samma_lunch_och_middag(app):
    plan = app.plan()

    assert len(plan.dagar) == 3
    forsta = plan.dagar[0]
    for dag in plan.dagar:
        assert dag.lunch == forsta.lunch
        assert dag.middag == forsta.middag


def test_dagens_kcal_under_tak_och_protein_over_golv(app):
    plan = app.plan()

    for dag in plan.dagar:
        assert dag.kcal <= 2000
        assert dag.protein >= 180


def test_maltider_har_protein_kolhydrater_och_gronsaker(app):
    plan = app.plan()

    for maltid in (plan.dagar[0].lunch, plan.dagar[0].middag):
        assert {rad.slot for rad in maltid.rader} == {"protein", "kolhydrater", "grönsaker"}
        assert all(rad.gram > 0 for rad in maltid.rader)
        assert maltid.kr > 0


def test_andrade_mal_styr_planen(app):
    app.satt_installning("kcal_mal", 1600)
    app.satt_installning("protein_mal", 150)

    plan = app.plan()

    assert app.installningar()["kcal_mal"] == 1600
    for dag in plan.dagar:
        assert dag.kcal <= 1600
        assert dag.protein >= 150


def test_installningar_sparas_mellan_sessioner(tmp_path):
    Matplan(tmp_path / "m.db").satt_installning("protein_mal", 170)

    assert Matplan(tmp_path / "m.db").installningar()["protein_mal"] == 170


def test_samma_indata_ger_samma_plan(tmp_path):
    a = Matplan(tmp_path / "a.db").plan()
    b = Matplan(tmp_path / "b.db").plan()

    assert a == b


def test_omojliga_mal_ger_tydligt_fel(app):
    app.satt_installning("kcal_mal", 800)
    app.satt_installning("protein_mal", 300)

    with pytest.raises(PlaneringsFel, match="Ingen kombination"):
        app.plan()


def test_okand_installning_avvisas(app):
    with pytest.raises(KeyError):
        app.satt_installning("finns_inte", 1)


def test_cli_skriver_plan_som_tabell(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MATPLAN_DB", str(tmp_path / "cli.db"))

    assert main(["plan"]) == 0

    ut = capsys.readouterr().out
    assert "Lunch" in ut and "Middag" in ut
    assert "kcal" in ut and "Protein" in ut


def test_cli_installningar(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MATPLAN_DB", str(tmp_path / "cli.db"))

    assert main(["installningar", "kcal_mal", "1800"]) == 0
    assert main(["installningar", "kcal_mal"]) == 0

    assert "1800" in capsys.readouterr().out
