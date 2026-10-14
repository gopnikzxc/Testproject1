from datetime import date

import pytest

from matplan.cli import main
from matplan.core import Matplan, PlaneringsFel

START = date(2026, 10, 15)  # en torsdag, så blocken korsar en helg


@pytest.fixture
def app(tmp_path):
    return Matplan(tmp_path / "matplan.db")


def _mal(app, person):
    inst = app.installningar()
    return inst[f"{person}.kcal_mal"], inst[f"{person}.protein_mal"]


def test_dag_har_frukost_lunch_middag_och_tva_mellanmal(app):
    dag = app.plan(START).dagar[0]

    assert [m.typ for m in dag.maltider] == ["frukost", "lunch", "middag", "mellanmål 1", "mellanmål 2"]


def test_antal_maltider_styrs_av_installningar(app):
    app.satt_installning("frukost", 0)
    app.satt_installning("antal_mellanmal", 1)

    dag = app.plan(START).dagar[0]

    assert [m.typ for m in dag.maltider] == ["lunch", "middag", "mellanmål 1"]


def test_rullande_tredagarsblock_over_hela_veckan(app):
    plan = app.plan(START)

    assert [d.datum for d in plan.dagar] == [date(2026, 10, 15 + i) for i in range(7)]
    assert [len(b.dagar) for b in plan.block] == [3, 3, 1]
    for block in plan.block:
        for dag in block.dagar:
            assert dag.maltid("lunch") == block.batch
            assert dag.maltid("middag").portioner == block.batch.portioner


def test_efterfoljande_block_lagar_olika_batcher(app):
    plan = app.plan(START)

    for forra, nasta in zip(plan.block, plan.block[1:]):
        assert forra.batch.ingredienser != nasta.batch.ingredienser


def test_frukost_och_mellanmal_upprepas_varje_dag(app):
    plan = app.plan(START)

    forsta = plan.dagar[0]
    for dag in plan.dagar:
        for typ in ("frukost", "mellanmål 1", "mellanmål 2"):
            assert dag.maltid(typ) == forsta.maltid(typ)


@pytest.mark.parametrize("person", ["jag", "fru"])
def test_varje_persons_dag_nar_sina_mal(app, person):
    kcal_mal, protein_mal = _mal(app, person)

    for dag in app.plan(START).dagar:
        assert dag.kcal(person) <= kcal_mal
        assert dag.protein(person) >= protein_mal


def test_alla_ater_samma_ingredienser_i_egna_portioner(app):
    dag = app.plan(START).dagar[0]

    for maltid in dag.maltider:
        jag, fru = maltid.portion("jag"), maltid.portion("fru")
        assert jag.ingredienser == fru.ingredienser
        assert jag.kcal > fru.kcal


def test_batchmangd_ar_summan_av_portionerna(app):
    block = app.plan(START).block[0]

    for rad_jag, rad_fru in zip(block.batch.portion("jag").rader, block.batch.portion("fru").rader):
        # lunch + middag i tre dagar
        assert block.batchmangd[rad_jag.namn] == (rad_jag.gram + rad_fru.gram) * 2 * 3


def test_fruns_mal_kan_andras(app):
    app.satt_installning("fru.kcal_mal", 1500)
    app.satt_installning("fru.protein_mal", 130)

    for dag in app.plan(START).dagar:
        assert dag.kcal("fru") <= 1500
        assert dag.protein("fru") >= 130


def test_mina_mal_styr_planen(app):
    app.satt_installning("jag.kcal_mal", 1800)
    app.satt_installning("jag.protein_mal", 170)

    for dag in app.plan(START).dagar:
        assert dag.kcal("jag") <= 1800
        assert dag.protein("jag") >= 170


def test_maltider_har_ratt_slotar(app):
    dag = app.plan(START).dagar[0]

    assert {r.slot for r in dag.maltid("lunch").portion("jag").rader} == {"protein", "kolhydrater", "grönsaker"}
    assert all(r.gram > 0 for m in dag.maltider for p in m.portioner for r in p.rader)


def test_installningar_sparas_mellan_sessioner(tmp_path):
    Matplan(tmp_path / "m.db").satt_installning("jag.protein_mal", 170)

    assert Matplan(tmp_path / "m.db").installningar()["jag.protein_mal"] == 170


def test_samma_indata_ger_samma_plan(tmp_path):
    assert Matplan(tmp_path / "a.db").plan(START) == Matplan(tmp_path / "b.db").plan(START)


def test_omojliga_mal_ger_tydligt_fel(app):
    app.satt_installning("jag.kcal_mal", 800)
    app.satt_installning("jag.protein_mal", 300)

    with pytest.raises(PlaneringsFel, match="Ingen kombination"):
        app.plan(START)


def test_okand_installning_avvisas(app):
    with pytest.raises(KeyError):
        app.satt_installning("finns_inte", 1)


def test_cli_skriver_plan_som_tabeller(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MATPLAN_DB", str(tmp_path / "cli.db"))

    assert main(["plan"]) == 0

    ut = capsys.readouterr().out
    for text in ("Frukost", "Lunch och middag", "Mellanmål 1", "Jag", "Fru", "Batch", "kcal", "Protein"):
        assert text in ut


def test_cli_installningar(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MATPLAN_DB", str(tmp_path / "cli.db"))

    assert main(["installningar", "fru.kcal_mal", "1650"]) == 0
    assert main(["installningar", "fru.kcal_mal"]) == 0

    assert "1650" in capsys.readouterr().out
