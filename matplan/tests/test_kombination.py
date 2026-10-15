"""Slotar ur näringsvärden, kombinationsvaror i planen och handvalda slotar (#29)."""

from datetime import date, datetime

import pytest
from conftest import SortimentButik, katalogvara, standardsortiment

from matplan.cli import main
from matplan.core import Matplan, PlaneringsFel
from matplan.katalog import STARTKATALOG, Ingrediens

START = date(2026, 10, 15)
NU = datetime(2026, 10, 15, 9, 0)

# Gruppen har ingen handvald slot ("") och klassas ur sin produkts näring.
GRYTA = Ingrediens("Kycklinggryta med ris", "", 120, 11.0, 60, ("kycklinggryta",), "fryst", ("färdigmat",))
GRYTA_VARA = katalogvara(
    "gryta-1", "Kycklinggryta med Ris", kcal=120, protein=11.0, kolhydrater=12.0, fett=3.0,
    kategori="Fryst / Fryst färdigmat", kr=60,
)
JUICE = Ingrediens("Apelsinjuice", "mejeri", 45, 0.7, 20, ("apelsinjuice",))
JUICE_VARA = katalogvara(
    "juice-1", "Apelsinjuice", kcal=45, protein=0.7, kolhydrater=9.0, fett=0.0,
    kategori="Dryck / Juice, fruktdrycker & smoothies", kr=20,
)


def _app(db, katalog=STARTKATALOG + (GRYTA,), extra=(GRYTA_VARA,)):
    """Lägre proteinmål än standard: en kombinationsvara når sällan 180 g på 2000 kcal
    när grönsakernas protein räknas med sin kvalitetsfaktor."""
    app = Matplan(db, katalog=katalog, butiker=(SortimentButik(standardsortiment() + list(extra)),))
    app.satt_installning("veckobudget", 5000)
    app.satt_installning("manadsbudget", 20000)
    app.satt_installning("jag.protein_mal", 150)
    app.satt_installning("fru.protein_mal", 100)
    app.refresh(nu=NU)
    return app


def _gram(plan, block, slot):
    return sum(r.gram for r in plan.block[block - 1].batch.portioner[0].rader if r.slot == slot)


def _mal_nadda(plan):
    for dag in plan.dagar:
        for p in plan.profiler:
            assert dag.kcal(p.namn) <= p.kcal_mal + 1e-6
            assert dag.viktat_protein(p.namn) >= p.protein_mal - 1e-6


def test_gruppens_slot_klassas_ur_produkten(tmp_path):
    app = _app(tmp_path / "m.db")

    assert [p.slot for p in app.produkter("Kycklinggryta med ris")] == ["kombination"]
    assert app.prisoversikt()  # gruppen är planerbar


def test_kombinationsvara_fyller_proteinslotten_och_krymper_kolhydraterna(tmp_path):
    app = _app(tmp_path / "m.db")
    plan = app.byt(1, "protein", "Kycklingfilé", start=START)
    kyckling_kolhydrater = _gram(plan, 1, "kolhydrater")
    assert kyckling_kolhydrater > 0

    plan = app.byt(1, "protein", "Kycklinggryta med ris", start=START)

    rader = plan.block[0].batch.portioner[0].rader
    assert rader[0].namn == "Kycklinggryta med ris" and rader[0].slot == "protein"
    assert _gram(plan, 1, "kolhydrater") < kyckling_kolhydrater
    _mal_nadda(plan)


def test_planen_klarar_sig_med_bara_kombinationsvaror_som_protein(tmp_path):
    utan_protein = tuple(i for i in STARTKATALOG if i.kategori != "protein") + (GRYTA,)
    app = _app(tmp_path / "m.db", katalog=utan_protein)

    plan = app.plan(START)

    assert all(b.batch.portioner[0].rader[0].namn == "Kycklinggryta med ris" for b in plan.block)
    _mal_nadda(plan)


def test_handvald_slot_for_grupp_gar_fore_klassificeringen(tmp_path):
    app = _app(tmp_path / "m.db")
    with pytest.raises(KeyError):
        app.byt(1, "protein", "Keso 1,5 %", start=START)

    app.satt_slot("Keso 1,5 %", "protein")
    plan = app.byt(1, "protein", "Keso 1,5 %", start=START)
    assert plan.block[0].batch.portioner[0].rader[0].namn == "Keso 1,5 %"

    app.satt_slot("Kycklinggryta med ris", "utesluten")
    with pytest.raises(KeyError):
        app.byt(1, "protein", "Kycklinggryta med ris", start=START)

    # Valen sparas i databasen.
    assert Matplan(tmp_path / "m.db", katalog=STARTKATALOG + (GRYTA,)).slotval() == {
        "grupp:Keso 1,5 %": "protein", "grupp:Kycklinggryta med ris": "utesluten",
    }


def test_juice_kommer_aldrig_in_i_planen(tmp_path):
    app = _app(tmp_path / "m.db", katalog=STARTKATALOG + (JUICE,), extra=(JUICE_VARA,))

    plan = app.plan(START)

    assert "Apelsinjuice" not in plan.total_gram()
    assert any("Apelsinjuice" in v for v in plan.varningar)
    assert [p.slot for p in app.sok("apelsinjuice")] == ["utesluten"]


def test_handvald_slot_for_produkt_gar_fore_klassificeringen(tmp_path):
    app = _app(tmp_path / "m.db", katalog=STARTKATALOG + (JUICE,), extra=(JUICE_VARA,))

    app.satt_slot("juice-1", "mejeri")

    assert [p.slot for p in app.sok("apelsinjuice")] == ["mejeri"]
    assert not any("Apelsinjuice" in v for v in app.plan(START).varningar)

    app.satt_slot("juice-1", None)
    assert [p.slot for p in app.sok("apelsinjuice")] == ["utesluten"]


def test_okand_slot_eller_mal(tmp_path):
    app = _app(tmp_path / "m.db")
    with pytest.raises(KeyError, match="Okänd slot"):
        app.satt_slot("Keso 1,5 %", "dessert")
    with pytest.raises(KeyError, match="Hittar ingen"):
        app.satt_slot("finns-inte", "protein")


def test_byte_till_kolhydrat_med_kombinationsvara_utan_kolhydratkalla(tmp_path):
    utan_protein = tuple(i for i in STARTKATALOG if i.kategori != "protein") + (GRYTA,)
    app = _app(tmp_path / "m.db", katalog=utan_protein)

    plan = app.byt(1, "kolhydrater", start=START)  # nästa i tur, även när slotten var tom

    assert plan.block[0].batch.portioner[0].rader[0].namn == "Kycklinggryta med ris"
    _mal_nadda(plan)


def test_cli_slot(tmp_path, monkeypatch, capsys):
    import matplan.cli as cli

    monkeypatch.setenv("MATPLAN_DB", str(tmp_path / "m.db"))
    monkeypatch.setattr(cli, "_butiker", lambda vald: (SortimentButik(standardsortiment()),))
    assert main(["refresh"]) == 0
    capsys.readouterr()

    assert main(["slot", "Keso 1,5 %", "protein"]) == 0
    assert "Keso 1,5 %: protein." in capsys.readouterr().out
    assert main(["slot"]) == 0
    assert "Keso 1,5 %: protein" in capsys.readouterr().out
    assert main(["slot", "Keso 1,5 %", "--ta-bort"]) == 0
    assert main(["slot"]) == 0
    assert "Keso" not in capsys.readouterr().out.split("slot borttagen.")[-1]


def test_planeringsfel_om_inget_nar_malen(tmp_path):
    svag = Ingrediens("Fiskpinnar", "", 190, 12.0, 50, ("fiskpinnar",), "fryst", ("fisk",))
    vara = katalogvara("fp", "Fiskpinnar", kcal=190, protein=12, kolhydrater=17, fett=8.1, kategori="Fryst / Fryst fisk")
    utan_protein = tuple(i for i in STARTKATALOG if i.kategori != "protein") + (svag,)
    app = _app(tmp_path / "m.db", katalog=utan_protein, extra=(vara,))

    with pytest.raises(PlaneringsFel):
        app.plan(START)
