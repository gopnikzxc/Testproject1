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


# Standardplanen kostar runt 171 kr/dag och billigaste möjliga runt 157 kr/dag,
# så en budget däremellan tvingar fram ett billigare val.
SNAV_VECKA = 1150


def test_planen_haller_sig_inom_veckobudgeten(app):
    assert app.plan(START).kr_per_dag * 7 > SNAV_VECKA
    app.satt_installning("veckobudget", SNAV_VECKA)

    plan = app.plan(START)

    assert all(dag.kr * 7 <= SNAV_VECKA + 1e-6 for dag in plan.dagar)


def test_planen_haller_sig_inom_manadstaket(app):
    app.satt_installning("veckobudget", 10_000)
    app.satt_installning("manadsbudget", 4500)

    plan = app.plan(START)

    assert all(dag.kr * DAGAR_PER_MANAD <= 4500 + 1e-6 for dag in plan.dagar)


def test_malen_haller_aven_med_snav_budget(app):
    app.satt_installning("veckobudget", SNAV_VECKA)

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
