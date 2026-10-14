"""Lager: köpt, lagat, justera och lager först (#11)."""

from datetime import date, datetime

import pytest
from conftest import hel_butik

from matplan.core import Matplan
from matplan.katalog import STARTKATALOG

START = date(2026, 10, 15)
NU = datetime(2026, 10, 14, 9, 30)


@pytest.fixture
def app(tmp_path):
    app = Matplan(tmp_path / "m.db", butiker=(hel_butik("City Gross Ytterby", forpackning_g=500),))
    app.refresh(nu=NU)
    return app


def test_varje_ingrediens_har_forvaring():
    assert {i.forvaring for i in STARTKATALOG} <= {"fryst", "torrvara", "kyl"}
    assert next(i for i in STARTKATALOG if i.namn == "Kycklingfilé").forvaring == "fryst"
    assert next(i for i in STARTKATALOG if i.namn == "Keso 1,5 %").forvaring == "kyl"


def test_kopt_lagger_in_hela_forpackningar_i_lagret(app):
    lista = app.inkopslista(START)

    kopt = app.kopt(START)

    lager = app.lager()
    for rad in lista.rader:
        kop = rad.alternativ["City Gross Ytterby"]
        assert kopt[rad.ingrediens] == kop.antal * 500
        assert lager[rad.ingrediens] == kop.antal * 500


def test_efter_kopt_ar_inkopslistan_tom(app):
    app.kopt(START)

    assert app.inkopslista(START).rader == ()


def test_lagat_drar_blockets_batch_fran_lagret(app):
    app.kopt(START)
    fore = app.lager()
    batch = app.plan(START).block[0].batchmangd

    varningar = app.lagat(START, block=1)

    efter = app.lager()
    assert varningar == []
    for namn, gram in batch.items():
        assert efter.get(namn, 0) == pytest.approx(fore[namn] - gram)


def test_lagat_utan_lager_varnar_och_gar_inte_under_noll(app):
    varningar = app.lagat(START, block=1)

    assert varningar and all("räckte inte" in v for v in varningar)
    assert all(gram >= 0 for gram in app.lager().values())


def test_lagret_kan_justeras_for_hand(app):
    app.satt_lager("Havregryn", 750)
    assert app.lager()["Havregryn"] == 750

    app.satt_lager("Havregryn", 0)
    assert "Havregryn" not in app.lager()

    with pytest.raises(KeyError):
        app.satt_lager("Okänd", 1)


def test_planen_foredrar_lagret_och_raknar_det_som_gratis(app):
    utan = app.plan(START)
    assert "Torskfilé, fryst" not in {r.namn for b in utan.block for r in b.batch.portion("jag").rader}

    app.satt_lager("Torskfilé, fryst", 20_000)
    med = app.plan(START)

    torsk = [r for b in med.block for r in b.batch.portion("jag").rader if r.namn == "Torskfilé, fryst"]
    assert torsk and all(r.kr == 0 for r in torsk)


def test_inkopslistan_tacker_bara_det_som_saknas(app):
    behov = app.plan(START).total_gram()
    havre = behov["Havregryn"]
    app.satt_lager("Havregryn", havre - 100)

    rad = next(r for r in app.inkopslista(START).rader if r.ingrediens == "Havregryn")

    assert rad.gram == 100


def test_kopt_plan_blir_aktiv_och_planeras_inte_om(app):
    plan = app.plan(START)

    app.kopt(START)

    aktiv = app.plan(START)
    assert aktiv.aktiv
    assert aktiv.block == plan.block


def test_ny_slapper_den_kopta_planen(app):
    app.kopt(START)

    assert not app.plan(START, ny=True).aktiv
    assert not app.plan(START).aktiv


def test_aktiv_plan_som_tagit_slut_ersatts(app):
    app.kopt(START)

    assert not app.plan(date(2026, 11, 1)).aktiv


def test_lagat_anvander_den_kopta_planen(app):
    app.kopt(START)
    batch = app.plan(START).block[1].batchmangd
    fore = app.lager()

    app.lagat(START, block=2)

    for namn, gram in batch.items():
        assert app.lager().get(namn, 0) == pytest.approx(fore[namn] - gram)


def test_cli_kopt_lagat_och_lager(tmp_path, monkeypatch, capsys):
    from matplan.cli import main

    monkeypatch.setenv("MATPLAN_DB", str(tmp_path / "cli.db"))

    assert main(["köpt"]) == 0
    assert main(["plan"]) == 0
    assert "köpta planen" in capsys.readouterr().out
    assert main(["lagat"]) == 0
    assert main(["lager", "Havregryn", "500"]) == 0
    assert "Havregryn: 500 g" in capsys.readouterr().out
    assert main(["plan", "--ny"]) == 0
    assert "köpta planen" not in capsys.readouterr().out


def test_lagat_okant_block_ger_tydligt_fel(app):
    with pytest.raises(KeyError, match="Block 9 finns inte"):
        app.lagat(START, block=9)


def test_lagat_block_kommer_inte_tillbaka_pa_inkopslistan(app):
    app.kopt(START)

    app.lagat(START, block=1)

    assert app.inkopslista(START).rader == ()


def test_samma_block_dras_inte_tva_ganger(app):
    app.kopt(START)
    app.lagat(START, block=1)
    efter_forsta = app.lager()

    varningar = app.lagat(START, block=1)

    assert varningar == ["Block 1 är redan draget från lagret."]
    assert app.lager() == efter_forsta
