from datetime import date

import pytest

from matplan.core import Matplan
from matplan.katalog import Ingrediens

START = date(2026, 10, 15)

# Liten fast katalog där proteintäthet, volym och kostnad drar åt olika håll.
FALSK_KATALOG = (
    Ingrediens("Proteinpulver-kyckling", "protein", 110, 25.0, 140),  # tätast, dyr
    Ingrediens("Billig färs", "protein", 200, 18.0, 60),  # billig per g protein, lite volym
    Ingrediens("Torsk", "protein", 75, 17.5, 110),  # mycket volym
    Ingrediens("Potatis", "kolhydrater", 77, 2.0, 15),
    Ingrediens("Ris", "kolhydrater", 350, 7.0, 30),
    Ingrediens("Gurka", "grönsaker", 12, 0.7, 30),
    Ingrediens("Kvarg", "mejeri", 61, 11.0, 45),
    Ingrediens("Havregryn", "flingor", 370, 13.0, 20),
    Ingrediens("Blåbär", "bär", 57, 0.7, 50),
)


def _app(sokvag):
    """Den falska katalogens priser är medvetet höga, så budgeten lyfts ur vägen."""
    app = Matplan(sokvag, katalog=FALSK_KATALOG)
    app.satt_installning("veckobudget", 100_000)
    app.satt_installning("manadsbudget", 400_000)
    return app


def _lunch(tmp_path, namn, **vikter):
    app = _app(tmp_path / f"{namn}.db")
    for nyckel in ("vikt_protein", "vikt_volym", "vikt_kostnad"):
        app.satt_installning(nyckel, vikter.get(nyckel, 0))
    return app.plan(START).block[0].batch


def test_standardvikterna_ar_lika(tmp_path):
    inst = Matplan(tmp_path / "m.db").installningar()

    assert inst["vikt_protein"] == inst["vikt_volym"] == inst["vikt_kostnad"] == 1


def test_vikt_pa_volym_ger_mer_mat_per_kcal(tmp_path):
    volym = _lunch(tmp_path, "volym", vikt_volym=1)
    protein = _lunch(tmp_path, "protein", vikt_protein=1)
    kostnad = _lunch(tmp_path, "kostnad", vikt_kostnad=1)

    assert volym.volym > protein.volym
    assert volym.volym > kostnad.volym


def test_vikt_pa_protein_ger_hogre_proteintathet(tmp_path):
    volym = _lunch(tmp_path, "volym", vikt_volym=1)
    protein = _lunch(tmp_path, "protein", vikt_protein=1)
    kostnad = _lunch(tmp_path, "kostnad", vikt_kostnad=1)

    assert protein.protein_tathet > volym.protein_tathet
    assert protein.protein_tathet > kostnad.protein_tathet


def test_vikt_pa_kostnad_ger_billigast_protein(tmp_path):
    volym = _lunch(tmp_path, "volym", vikt_volym=1)
    protein = _lunch(tmp_path, "protein", vikt_protein=1)
    kostnad = _lunch(tmp_path, "kostnad", vikt_kostnad=1)

    assert kostnad.kr_per_g_protein < volym.kr_per_g_protein
    assert kostnad.kr_per_g_protein < protein.kr_per_g_protein


@pytest.mark.parametrize("person", ["jag", "fru"])
def test_malen_haller_oavsett_vikter(tmp_path, person):
    app = _app(tmp_path / "m.db")
    app.satt_installning("vikt_volym", 5)
    inst = app.installningar()

    for dag in app.plan(START).dagar:
        assert dag.kcal(person) <= inst[f"{person}.kcal_mal"]
        assert dag.protein(person) >= inst[f"{person}.protein_mal"]


def test_cli_visar_poangdelarna(tmp_path, monkeypatch, capsys):
    from matplan.cli import main

    monkeypatch.setenv("MATPLAN_DB", str(tmp_path / "cli.db"))
    assert main(["plan"]) == 0

    ut = capsys.readouterr().out
    assert "g/100 kcal" in ut and "g/kcal" in ut and "kr/g protein" in ut
