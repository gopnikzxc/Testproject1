"""Vecko- och månadsbudget (#10)."""

from datetime import date

import pytest

from matplan.cli import main
from matplan.core import DAGAR_PER_MANAD, Matplan, PlaneringsFel

START = date(2026, 10, 15)


@pytest.fixture
def app(tmp_path):
    return Matplan(tmp_path / "m.db")


def test_standardbudget(app):
    inst = app.installningar()

    assert inst["veckobudget"] == 1250
    assert inst["manadsbudget"] == 5000


def _snav_dagsbudget(app):
    """En dagsbudget mellan billigaste möjliga dag och standardplanens dyraste dag,
    så att budgeten tvingar fram billigare val men fortfarande går att nå."""
    standard = max(dag.kr for dag in app.plan(START).dagar)
    with pytest.raises(PlaneringsFel) as fel:
        app.satt_installning("veckobudget", 7)
        app.plan(START)
    billigaste = float(str(fel.value).split("kostar ")[1].split(" kr")[0])
    app.satt_installning("veckobudget", 1250)
    assert billigaste + 2 < standard
    return (billigaste + standard) / 2


def test_planen_haller_sig_inom_veckobudgeten(app):
    dag = _snav_dagsbudget(app)
    app.satt_installning("veckobudget", dag * 7)

    plan = app.plan(START)

    assert all(d.kr <= dag + 1e-6 for d in plan.dagar)


def test_planen_haller_sig_inom_manadstaket(app):
    dag = _snav_dagsbudget(app)
    app.satt_installning("veckobudget", 10_000)
    app.satt_installning("manadsbudget", dag * DAGAR_PER_MANAD)

    plan = app.plan(START)

    assert all(d.kr <= dag + 1e-6 for d in plan.dagar)


def test_malen_haller_aven_med_snav_budget(app):
    app.satt_installning("veckobudget", _snav_dagsbudget(app) * 7)

    plan = app.plan(START)

    for dag in plan.dagar:
        assert dag.kcal("jag") <= 2000 and dag.protein("jag") >= 180
        assert dag.kcal("fru") <= 1700 and dag.protein("fru") >= 110


def test_omojlig_budget_ger_tydligt_fel(app):
    app.satt_installning("veckobudget", 100)

    with pytest.raises(PlaneringsFel, match="Budgeten räcker inte"):
        app.plan(START)


def test_cli_visar_kostnad_mot_budget(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MATPLAN_DB", str(tmp_path / "cli.db"))

    assert main(["plan"]) == 0

    ut = capsys.readouterr().out
    assert "kr/vecka av 1250" in ut and "kr/månad av 5000" in ut


def test_cli_omojlig_budget(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MATPLAN_DB", str(tmp_path / "cli.db"))
    main(["installningar", "veckobudget", "100"])

    assert main(["plan"]) == 1
    assert "Budgeten räcker inte" in capsys.readouterr().out
