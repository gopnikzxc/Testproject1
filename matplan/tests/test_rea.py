"""Erbjudanden från prishistorik och färska erbjudanden före lager (#13)."""

import dataclasses
from datetime import date, datetime, timedelta

import pytest
from conftest import FalskButik, hel_butik, produkt

from matplan.cli import main
from matplan.core import Matplan
from matplan.katalog import STARTKATALOG
from matplan.rea import ar_rea

START = date(2026, 10, 15)
NU = datetime(2026, 10, 14, 9, 0)
CITY = "City Gross Ytterby"


# --- Regeln -----------------------------------------------------------------


def _dagar(*priser, fran=NU):
    return [(fran - timedelta(weeks=len(priser) - 1 - i), kr) for i, kr in enumerate(priser)]


def test_minst_25_procent_under_medianen_ar_rea():
    historik = _dagar(100, 100, 100, 75)

    assert ar_rea(historik, 75, flagga=False, grans=0.25)
    assert not ar_rea(historik, 80, flagga=True, grans=0.25)  # historiken går före flaggan


def test_for_lite_historik_ger_butikens_flagga():
    assert ar_rea(_dagar(100, 60), 60, flagga=True, grans=0.25)
    assert not ar_rea(_dagar(100, 60), 60, flagga=False, grans=0.25)


def test_flera_hamtningar_samma_dag_raknas_en_gang():
    samma_dag = [(NU, 100), (NU + timedelta(hours=1), 100), (NU + timedelta(hours=2), 70)]

    assert ar_rea(samma_dag, 70, flagga=True, grans=0.25)  # bara en dag: flaggan avgör


# --- Kärnan, med inspelad historik --------------------------------------------


def _kyckling(kr, erbjudande=False):
    return FalskButik(CITY, [produkt(CITY, "kyckling", "Kycklingfilé Fryst", kr, erbjudande=erbjudande)])


def _historik(db, priser, sista):
    """En hämtning i veckan med 100 kr/kg, sist `sista` (med flagga) vid NU."""
    for vecka, kr in enumerate(priser):
        Matplan(db, butiker=(_kyckling(kr),)).refresh(nu=NU - timedelta(weeks=len(priser) - vecka))
    app = Matplan(db, butiker=(_kyckling(sista[0], sista[1]),))
    app.refresh(nu=NU)
    return app


def test_pris_under_granssnittet_markeras_i_plan_och_lista(tmp_path):
    app = _historik(tmp_path / "m.db", [100, 100, 100], sista=(70, False))

    plan = app.plan(START)
    lista = app.inkopslista(START)

    assert "Kycklingfilé" in plan.rea
    kyckling = next(r for r in lista.rader if r.ingrediens == "Kycklingfilé")
    assert kyckling.alternativ[CITY].rea


def test_pris_strax_over_granssnittet_ar_inte_rea_trots_flagga(tmp_path):
    app = _historik(tmp_path / "m.db", [100, 100, 100], sista=(80, True))

    assert "Kycklingfilé" not in app.plan(START).rea


def test_granssnittet_kan_andras(tmp_path):
    app = _historik(tmp_path / "m.db", [100, 100, 100], sista=(80, False))

    app.satt_installning("rea_procent", 15)

    assert "Kycklingfilé" in app.plan(START).rea


def test_fonstret_kan_andras(tmp_path):
    # Historiken är 10-12 veckor gammal: utanför 8 veckor räcker den inte, och
    # utan flagga blir det ingen rea. Med 13 veckors fönster räknas den.
    db = tmp_path / "m.db"
    for veckor in (12, 11, 10):
        Matplan(db, butiker=(_kyckling(100),)).refresh(nu=NU - timedelta(weeks=veckor))
    app = Matplan(db, butiker=(_kyckling(70),))
    app.refresh(nu=NU)

    assert "Kycklingfilé" not in app.plan(START).rea
    app.satt_installning("rea_veckor", 13)
    assert "Kycklingfilé" in app.plan(START).rea


def test_utan_historik_galler_butikens_flagga(tmp_path):
    app = Matplan(tmp_path / "m.db", butiker=(_kyckling(90, erbjudande=True),))
    app.refresh(nu=NU)

    assert "Kycklingfilé" in app.plan(START).rea


def test_cli_markerar_rea(tmp_path, monkeypatch, capsys):
    import matplan.cli as cli

    monkeypatch.setenv("MATPLAN_DB", str(tmp_path / "cli.db"))
    monkeypatch.setattr(cli, "_butiker", lambda vald: (hel_butik(CITY, erbjudande=("Kycklingfilé", "Ris, okokt", "Morot")),))

    assert main(["refresh"]) == 0
    assert main(["plan", "--ny"]) == 0
    assert main(["lista"]) == 0

    ut = capsys.readouterr().out
    assert ut.count("(rea)") >= 2


# --- Färskt erbjudande före lager ------------------------------------------------


FARSK = dataclasses.replace(
    next(i for i in STARTKATALOG if i.namn == "Kycklingfilé"),
    namn="Kycklingfilé, färsk", sokord=("färsk kycklingfilé",), forvaring="kyl", livsmedelsverket=None,
)
# Den frysta får inte matcha den färska produkten.
KATALOG = tuple(
    dataclasses.replace(i, uteslut=("färsk",)) if i.namn == "Kycklingfilé" else i for i in STARTKATALOG
) + (FARSK,)


def _lunch_protein(plan):
    return {r.namn for b in plan.block for r in b.batch.portion("jag").rader if r.slot == "protein"}


def _app_med_lager(tmp_path, farsk_kr):
    butik = hel_butik(CITY, katalog=KATALOG, undantag={"Kycklingfilé, färsk": farsk_kr}, erbjudande=("Kycklingfilé, färsk",))
    app = Matplan(tmp_path / "m.db", katalog=KATALOG, butiker=(butik,))
    app.refresh(nu=NU)
    app.satt_lager("Kycklingfilé", 20_000)
    return app


def test_farskt_erbjudande_med_mer_protein_per_krona_gar_fore_fryst_lager(tmp_path):
    app = _app_med_lager(tmp_path, farsk_kr=60)  # fryst kostar 99 kr/kg ordinarie

    plan = app.plan(START)

    assert "Kycklingfilé, färsk" in plan.rea
    assert _lunch_protein(plan) == {"Kycklingfilé, färsk"}
    assert any("går före Kycklingfilé i lagret" in v for v in plan.varningar)


def test_farskt_erbjudande_som_inte_slar_lagret_gar_inte_fore(tmp_path):
    app = _app_med_lager(tmp_path, farsk_kr=120)  # flaggad som erbjudande men dyrare än fryst

    plan = app.plan(START)

    assert "Kycklingfilé, färsk" in plan.rea
    assert _lunch_protein(plan) == {"Kycklingfilé"}
    assert not any("går före" in v for v in plan.varningar)
