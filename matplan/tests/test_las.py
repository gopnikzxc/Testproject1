"""Produktlås (#9)."""

from datetime import date, datetime

import pytest
from conftest import FalskButik, produkt

from matplan.core import Matplan

START = date(2026, 10, 15)
NU = datetime(2026, 10, 14, 9, 30)
CITY = "City Gross Ytterby"


def _butik(*produkter):
    return FalskButik(CITY, list(produkter))


BILLIG = produkt(CITY, "billig", "Kycklingfilé Fryst", 80.0)
KRONFAGEL = produkt(CITY, "kronfagel", "Kycklingfilé Kronfågel", 120.0)


def _kyckling(app):
    plan = app.plan(START)
    for block in plan.block:
        for rad in block.batch.portion("jag").rader:
            if rad.namn == "Kycklingfilé":
                return rad.kr / rad.gram * 1000, plan
    pytest.fail("planen använder ingen kycklingfilé")


def _lista_produkt(app):
    rad = next(r for r in app.inkopslista(START).rader if r.ingrediens == "Kycklingfilé")
    return rad.alternativ[CITY].produkt.produkt_id


def test_last_produkt_anvands_trots_billigare_alternativ(tmp_path):
    app = Matplan(tmp_path / "m.db", butiker=(_butik(BILLIG, KRONFAGEL),))
    app.refresh(nu=NU)

    app.las("Kycklingfilé", CITY, "kronfagel")

    kr_per_kg, _ = _kyckling(app)
    assert kr_per_kg == pytest.approx(120.0)
    assert _lista_produkt(app) == "kronfagel"
    assert app.lasningar() == {("Kycklingfilé", CITY): "kronfagel"}


def test_borttaget_las_ger_billigaste_igen(tmp_path):
    app = Matplan(tmp_path / "m.db", butiker=(_butik(BILLIG, KRONFAGEL),))
    app.refresh(nu=NU)
    app.las("Kycklingfilé", CITY, "kronfagel")

    assert app.ta_bort_las("Kycklingfilé", CITY)

    kr_per_kg, _ = _kyckling(app)
    assert kr_per_kg == pytest.approx(80.0)
    assert _lista_produkt(app) == "billig"


def test_saknad_last_produkt_varnar_och_faller_tillbaka(tmp_path):
    db = tmp_path / "m.db"
    app = Matplan(db, butiker=(_butik(BILLIG, KRONFAGEL),))
    app.refresh(nu=NU)
    app.las("Kycklingfilé", CITY, "kronfagel")
    app = Matplan(db, butiker=(_butik(BILLIG),))
    app.refresh(nu=datetime(2026, 10, 21, 9, 0))

    kr_per_kg, plan = _kyckling(app)

    assert kr_per_kg == pytest.approx(80.0)
    assert any("kronfagel" in v for v in plan.varningar)


def test_las_kraver_kand_ingrediens(tmp_path):
    with pytest.raises(KeyError):
        Matplan(tmp_path / "m.db").las("Okänd", CITY, "x")


def test_cli_produkter_och_las(tmp_path, monkeypatch, capsys):
    import matplan.cli as cli

    monkeypatch.setenv("MATPLAN_DB", str(tmp_path / "cli.db"))
    monkeypatch.setattr(cli, "_butiker", lambda vald: (_butik(BILLIG, KRONFAGEL),))

    assert cli.main(["refresh"]) == 0
    assert cli.main(["lås", "Kycklingfilé", CITY, "kronfagel"]) == 0
    assert cli.main(["produkter", "Kycklingfilé"]) == 0
    ut = capsys.readouterr().out
    assert "kronfagel" in ut and "låst" in ut
    assert cli.main(["las", "--ta-bort", "Kycklingfilé", CITY]) == 0
    assert "borttaget" in capsys.readouterr().out
