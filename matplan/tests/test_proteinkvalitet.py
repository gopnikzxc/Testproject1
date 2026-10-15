"""Proteinkvalitet: proteintyp, viktat protein och regeln baljväxt + spannmål (#30)."""

from datetime import date

import pytest

from matplan.cli import main
from matplan.core import Matplan, PlaneringsFel
from matplan.export import plan_markdown
from matplan.katalog import STARTKATALOG, Ingrediens
from matplan.protein import proteintyp

START = date(2026, 10, 15)

# En baljväxt tät nog att bära en måltid (ärtproteinisolat).
ARTPROTEIN = Ingrediens("Ärtprotein", "protein", 370, 80.0, 150, ("ärtprotein",), "torrvara")


@pytest.mark.parametrize("namn, kategori, typ", [
    ("Kyckling Bröstfilé", "Kött & fågel / Kyckling & fågel", "animaliskt"),
    ("Tonfisk Vatten", "Skafferiet / Konserver", "animaliskt"),
    ("Ägg 10P Frigående", "Mejeri, ost & ägg / Ägg", "ägg"),
    ("Keso Naturell", "Mejeri, ost & ägg / Kvarg & cottage cheese", "mejeri"),
    ("Naturell Tofu Fast", "Vegetariskt / Kylt vegetariskt", "soja"),
    ("Svarta Bönor Ekologiska", "Skafferiet / Bönor, ärtor & linser", "baljväxt"),
    ("Röda Linser", "Skafferiet / Bönor, ärtor & linser", "baljväxt"),
    ("Jasminris", "Skafferiet / Pasta, ris & mos", "spannmål"),
    ("Havregryn", "Skafferiet / Flingor, Musli & gryner", "spannmål"),
    ("Fusilli", "Skafferiet / Pasta, ris & mos", "spannmål"),
    ("Havredryck Ekologisk", "Mejeri, ost & ägg / Havre- & Sojadryck mm", "spannmål"),
    ("Sojadryck Vegetabilisk", "Mejeri, ost & ägg / Havre- & Sojadryck mm", "soja"),
    ("Vegofärs", "Vegetariskt / Kylt vegetariskt", "övrigt"),
    ("Potatis Fast", "Frukt & grönt / Potatis & rotsaker", "övrigt"),
    ("Cashewnötter", "Skafferiet / Nötter & torkad frukt", "övrigt"),
])
def test_proteintyp(namn, kategori, typ):
    assert proteintyp(kategori, namn) == typ


def _app(tmp_path, katalog=STARTKATALOG + (ARTPROTEIN,)):
    app = Matplan(tmp_path / "m.db", katalog=katalog)
    app.satt_installning("veckobudget", 5000)
    app.satt_installning("manadsbudget", 20000)
    return app


def _rader(plan, block=1, person="jag"):
    return {r.namn: r for r in plan.block[block - 1].batch.portion(person).rader}


def test_gruppernas_proteintyp_och_handval(tmp_path):
    app = _app(tmp_path)
    typer = app.proteintyper()
    assert (typer["Kycklingfilé"], typer["Ägg"], typer["Keso 1,5 %"], typer["Ärtprotein"]) == (
        "animaliskt", "ägg", "mejeri", "baljväxt",
    )
    assert (typer["Ris, okokt"], typer["Potatis"]) == ("spannmål", "övrigt")

    app.satt_proteintyp("Ärtprotein", "soja")

    assert app.proteintyper()["Ärtprotein"] == "soja"
    assert app.proteintypval() == {"grupp:Ärtprotein": "soja"}


def test_varje_dag_nar_proteingolvet_i_viktat_protein(tmp_path):
    plan = _app(tmp_path).plan(START)

    for dag in plan.dagar:
        for p in plan.profiler:
            assert dag.viktat_protein(p.namn) >= p.protein_mal - 1e-6
            assert dag.protein(p.namn) > dag.viktat_protein(p.namn)  # grönsaker och spannmål väger lägre


def test_baljvaxt_kraver_spannmal_aldrig_bara_potatis(tmp_path):
    app = _app(tmp_path)

    plan = app.byt(1, "protein", "Ärtprotein", start=START)

    kolhydrat = next(r for r in plan.block[0].batch.portioner[0].rader if r.slot == "kolhydrater")
    assert kolhydrat.namn in ("Ris, okokt", "Fullkornspasta, okokt")
    with pytest.raises(PlaneringsFel):
        app.byt(1, "kolhydrater", "Potatis", start=START)


def test_regeln_galler_inte_andra_proteinkallor(tmp_path):
    plan = _app(tmp_path).byt(1, "kolhydrater", "Potatis", start=START)

    assert "Potatis" in _rader(plan)


def test_kvalitetsfaktorn_styr_mangden(tmp_path):
    app = _app(tmp_path)
    vanlig = _rader(app.byt(1, "protein", "Ärtprotein", start=START))["Ärtprotein"].gram

    app.satt_installning("kvalitet_baljväxt", 1.0)
    full = _rader(app.plan(START))["Ärtprotein"]

    assert full.gram < vanlig
    assert full.viktat_protein == pytest.approx(full.protein)


def test_viktat_protein_raknas_med_faktorn(tmp_path):
    app = _app(tmp_path)
    plan = app.byt(1, "protein", "Ärtprotein", start=START)

    rad = _rader(plan)["Ärtprotein"]
    assert rad.viktat_protein == pytest.approx(rad.protein * 0.7)


def test_planens_utdata_visar_ratt_och_viktat_protein(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MATPLAN_DB", str(tmp_path / "cli.db"))
    monkeypatch.setenv("COLUMNS", "200")

    assert main(["plan"]) == 0
    ut = capsys.readouterr().out
    assert "Protein, viktat (g)" in ut and "protein / viktat (g)" in ut

    assert "(viktat)" in plan_markdown(_app(tmp_path).plan(START))

    assert main(["proteintyp"]) == 0
    assert "Kycklingfilé: animaliskt (faktor 1)" in capsys.readouterr().out
    assert main(["proteintyp", "Kycklingfilé", "soja"]) == 0
    assert main(["proteintyp"]) == 0
    assert "Kycklingfilé: soja (faktor 0.9)" in capsys.readouterr().out
