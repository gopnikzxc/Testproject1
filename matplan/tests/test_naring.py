"""Näringsvärden från Livsmedelsverket och Open Food Facts (#5)."""

import urllib.error
from datetime import date, datetime
from pathlib import Path

import pytest

from matplan.core import Matplan
from matplan.export import plan_markdown
from matplan.http import HttpKlient
from matplan.katalog import STARTKATALOG
from matplan.naring import Livsmedelsverket, Naring, NaringsFel, OpenFoodFacts

FIXTURER = Path(__file__).parent / "fixtures" / "naring"
START = date(2026, 10, 15)
NU = datetime(2026, 10, 14, 9, 30)


def _http(tmp_path, svar_for, anrop=None):
    def transport(url, headers):
        if anrop is not None:
            anrop.append(url)
        return svar_for(url)

    return HttpKlient(tmp_path / "cache", paus_s=0, transport=transport, sov=lambda s: None)


def _fixtur(namn):
    return (FIXTURER / namn).read_bytes()


# --- Kontraktstester mot inspelade svar ---------------------------------


def test_livsmedelsverket_laser_kcal_inte_kj(tmp_path):
    anrop = []
    lmv = Livsmedelsverket(_http(tmp_path, lambda url: _fixtur("lmv_1173_naringsvarden.json"), anrop))

    naring = lmv.hamta(1173)

    assert anrop == ["https://dataportal.livsmedelsverket.se/livsmedel/api/v1/livsmedel/1173/naringsvarden?sprak=1"]
    assert naring == Naring("livsmedelsverket", kcal=104, protein=23.1, fett=1.2, kolhydrater=0.0, fiber=0.0, vatten=74.7)


def test_open_food_facts_per_ean(tmp_path):
    anrop = []
    off = OpenFoodFacts(_http(tmp_path, lambda url: _fixtur("off_7310865051998.json"), anrop))

    naring = off.hamta("7310865051998")

    assert "/product/7310865051998.json" in anrop[0]
    assert naring.kalla == "openfoodfacts"
    assert (naring.kcal, naring.protein, naring.fett) == (73, 13, 1.5)
    assert naring.vatten is None


def test_open_food_facts_okand_vara_ger_fel(tmp_path):
    off = OpenFoodFacts(_http(tmp_path, lambda url: _fixtur("off_saknas.json")))

    with pytest.raises(NaringsFel, match="ingen vara"):
        off.hamta("0000000000017")


@pytest.mark.parametrize("svar", [b"<html>fel</html>", b"[]", b'[{"okand": 1}]'])
def test_livsmedelsverket_trasigt_svar_ger_fel(tmp_path, svar):
    lmv = Livsmedelsverket(_http(tmp_path, lambda url: svar))

    with pytest.raises(NaringsFel):
        lmv.hamta(1173)


def test_natverksfel_ger_naringsfel(tmp_path):
    def nere(url):
        raise urllib.error.URLError("nere")

    with pytest.raises(NaringsFel, match="Kunde inte nå"):
        Livsmedelsverket(_http(tmp_path, nere)).hamta(1)


# --- Kärnan ---------------------------------------------------------------


# Falska källor svarar med katalogens egna värden plus 1 kcal, så att planen
# går att lösa men det syns att de hämtade värdena används.
def _katalogvarden(kalla, ingrediens):
    return Naring(kalla, ingrediens.kcal_100g + 1, ingrediens.protein_100g, None, None, None, None)


class FalskLivsmedelsverket:
    def __init__(self, fel_for=()):
        self.anrop = []
        self._fel_for = fel_for

    def hamta(self, nummer):
        self.anrop.append(nummer)
        if nummer in self._fel_for:
            raise NaringsFel("nere")
        return _katalogvarden("livsmedelsverket", next(i for i in STARTKATALOG if i.livsmedelsverket == nummer))


class FalskOpenFoodFacts:
    def __init__(self):
        self.anrop = []

    def hamta(self, ean):
        self.anrop.append(ean)
        return _katalogvarden("openfoodfacts", next(i for i in STARTKATALOG if i.ean == ean))


def test_varje_ingrediens_har_en_naringskalla():
    for i in STARTKATALOG:
        assert (i.livsmedelsverket is None) != (i.ean is None), i.namn


def test_refresh_hamtar_naring_och_planen_anvander_den(tmp_path):
    lmv, off = FalskLivsmedelsverket(), FalskOpenFoodFacts()
    app = Matplan(tmp_path / "m.db", livsmedelsverket=lmv, openfoodfacts=off)

    resultat = app.refresh(nu=NU)
    plan = app.plan(START)

    assert resultat.naring_hamtad == len(STARTKATALOG)
    assert sorted(lmv.anrop) == sorted(i.livsmedelsverket for i in STARTKATALOG if i.livsmedelsverket)
    assert sorted(off.anrop) == sorted(i.ean for i in STARTKATALOG if i.ean)
    katalog = {i.namn: i for i in STARTKATALOG}
    for maltid in plan.dagar[0].maltider:
        for rad in maltid.portion("jag").rader:
            assert rad.kcal == pytest.approx((katalog[rad.namn].kcal_100g + 1) * rad.gram / 100)
    assert set(plan.naringskallor) <= {"livsmedelsverket", "openfoodfacts"}
    assert "livsmedelsverket" in plan.naringskallor


def test_sparade_varden_hamtas_inte_igen(tmp_path):
    db = tmp_path / "m.db"
    Matplan(db, livsmedelsverket=FalskLivsmedelsverket(), openfoodfacts=FalskOpenFoodFacts()).refresh(nu=NU)
    lmv = FalskLivsmedelsverket()

    resultat = Matplan(db, livsmedelsverket=lmv, openfoodfacts=FalskOpenFoodFacts()).refresh(nu=NU)

    assert lmv.anrop == [] and resultat.naring_hamtad == 0


def test_misslyckad_hamtning_rapporteras_och_katalogvardet_galler(tmp_path):
    kyckling = next(i for i in STARTKATALOG if i.namn == "Kycklingfilé")
    lmv = FalskLivsmedelsverket(fel_for=(kyckling.livsmedelsverket,))
    app = Matplan(tmp_path / "m.db", livsmedelsverket=lmv, openfoodfacts=FalskOpenFoodFacts())

    resultat = app.refresh(nu=NU)

    assert "Kycklingfilé" in resultat.naring_fel
    assert resultat.naring_hamtad == len(STARTKATALOG) - 1
    plan = app.plan(START)
    for block in plan.block:
        for rad in block.batch.portion("jag").rader:
            if rad.namn == "Kycklingfilé":
                assert rad.kcal == pytest.approx(kyckling.kcal_100g * rad.gram / 100)


def test_utan_hamtade_varden_ingen_kallhanvisning(tmp_path):
    assert Matplan(tmp_path / "m.db").plan(START).naringskallor == ()


def test_kallhanvisning_i_export_och_cli(tmp_path, monkeypatch, capsys):
    import matplan.cli as cli

    monkeypatch.setenv("MATPLAN_DB", str(tmp_path / "cli.db"))
    monkeypatch.setattr(cli, "_naringskallor", lambda: (FalskLivsmedelsverket(), FalskOpenFoodFacts()))

    assert cli.main(["refresh"]) == 0
    assert cli.main(["plan"]) == 0

    ut = capsys.readouterr().out
    assert "Näringsvärden hämtade för" in ut
    assert "Livsmedelsverkets livsmedelsdatabas (CC BY 4.0)" in ut
    app = Matplan(tmp_path / "cli.db")
    assert "Livsmedelsverkets livsmedelsdatabas" in plan_markdown(app.plan(START))


def test_livsmedelsverket_rader_utan_matrisenhetkod(tmp_path):
    lmv = Livsmedelsverket(_http(tmp_path, lambda url: _fixtur("lmv_1225_naringsvarden.json")))

    naring = lmv.hamta(1225)

    assert (naring.kcal, naring.protein, naring.fett) == (136, 12.1, 9.8)
