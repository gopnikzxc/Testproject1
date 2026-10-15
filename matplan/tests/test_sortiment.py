"""Hela City Gross-sortimentet och sökning i det (#24).

Fixturen är en inspelad, bantad sida ur kategorilistningen för Ytterby (2026-10-14).
Den tomma platshållardeklarationen på Garants tonfisk är tillagd för testet; sådana
förekommer i butikens data men inte just på den produkten.
"""

import json
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path

import pytest

import matplan.butiker.citygross as citygross
from conftest import SortimentButik, katalogvara

from matplan.butiker import ButiksFel, Produkt
from matplan.butiker.citygross import CityGross
from matplan.cli import main
from matplan.core import Matplan
from matplan.http import HttpKlient

FIXTUR = Path(__file__).parent / "fixtures" / "citygross" / "sortiment.json"
NU = datetime(2026, 10, 15, 9, 0)


def _http(tmp_path, svar_for, anrop=None):
    def transport(url, headers, metod="GET"):
        if anrop is not None:
            anrop.append(url)
        return svar_for(url)

    return HttpKlient(tmp_path / "cache", paus_s=0, transport=transport, sov=lambda s: None)


def _sidor(sidstorlek):
    """Serverar fixturen i sidor om `sidstorlek`, som butikens skip/take."""
    data = json.loads(FIXTUR.read_text())

    def svar(url):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        skip, take = int(q["skip"][0]), int(q["take"][0])
        return json.dumps(dict(data, items=data["items"][skip : skip + take])).encode()

    return svar


def _per_id(produkter):
    return {p.produkt_id: p for p in produkter}


# --- Adaptern mot inspelade svar ---------------------------------------------


def test_sortimentet_hamtas_sida_for_sida_for_butiken(tmp_path, monkeypatch):
    monkeypatch.setattr(citygross, "SIDSTORLEK", 5)
    anrop = []

    CityGross(_http(tmp_path, _sidor(5), anrop)).sortiment()

    assert len(anrop) == 3  # 13 produkter i sidor om 5
    assert all("/Loop54/category/69/products" in url and "store=3240" in url for url in anrop)
    assert ["skip=0" in anrop[0], "skip=5" in anrop[1], "skip=10" in anrop[2]] == [True] * 3


def test_bara_livsmedel_behalls(tmp_path):
    produkter = _per_id(CityGross(_http(tmp_path, _sidor(2000))).sortiment())

    # Godis, choklad, kattmat och glass sorteras bort.
    for bort in ("100164778_ST", "101773953_ST", "101340586_ST", "100717814_ST"):
        assert bort not in produkter
    # Konserver, fryst fisk, bönor, fryst färdigmat, lös frukt & grönt, mjölk, läsk och kosttillskott är kvar.
    for kvar in ("101361686_ST", "101545504_ST", "101245204_ST", "101191252_ST", "100148868_KG",
                 "101206929_ST", "101872392_ST", "101418664_ST"):
        assert kvar in produkter


def test_naringsvarden_per_100_g_ur_butikens_data(tmp_path):
    produkter = _per_id(CityGross(_http(tmp_path, _sidor(2000))).sortiment())

    tonfisk = produkter["101361686_ST"]  # har både en 100 g-deklaration och en tom platshållare
    assert (tonfisk.varumarke, tonfisk.namn, tonfisk.beskrivning) == ("GARANT", "Tonfisk Vatten", "510/360G 3X170G GARANT")
    assert tonfisk.ean
    assert tonfisk.kcal is not None and tonfisk.protein is not None and tonfisk.protein > 15

    assert produkter["101228286_ST"].kcal is None  # bara deklaration utan uttalad bas
    assert produkter["100148868_KG"].kcal is None  # lösvikt utan näringsdata


def test_annan_bas_raknas_om_till_100(tmp_path):
    data = json.loads(FIXTUR.read_text())
    shake = next(p for p in data["items"] if p["id"] == "101418664_ST")
    (dekl,) = [d for d in shake["foodAndBeverageExtension"]["nutrientInformations"] if d.get("nutrients")]
    kcal_per_bas = next(n["value"] for n in dekl["nutrients"] if n["typeCode"] == "ENER-" and n["unitOfMeasure"] == "kilokalori")

    p = _per_id(CityGross(_http(tmp_path, _sidor(2000))).sortiment())["101418664_ST"]

    assert dekl["nutrientBasisQuantity"] == 235
    assert p.kcal == pytest.approx(kcal_per_bas * 100 / 235)


def test_literpris_och_styckpris(tmp_path):
    produkter = _per_id(CityGross(_http(tmp_path, _sidor(2000))).sortiment())

    assert produkter["101206929_ST"].kr_per_kg == pytest.approx(13.3)  # kr/liter räknas som kr/kg
    assert produkter["101418664_ST"].kr_per_kg == 0  # styckpris: sökbar men inte planerbar


@pytest.mark.parametrize("svar", [b"<html>503</html>", b'{"searchResults": {}}'])
def test_trasigt_svar_ger_butiksfel(tmp_path, svar):
    with pytest.raises(ButiksFel):
        CityGross(_http(tmp_path, lambda url: svar)).sortiment()


# --- Kärnan ----------------------------------------------------------------------


_vara = katalogvara


def test_refresh_synkar_och_rapporterar(tmp_path):
    butik = SortimentButik([_vara("1", "Tonfisk Vatten"), _vara("2", "Sejfilé"), _vara("3", "Svarta Bönor")])
    app = Matplan(tmp_path / "m.db", butiker=(butik,))

    resultat = app.refresh(nu=NU)

    assert resultat.sortiment == {"City Gross Ytterby": (3, 3, 0)}
    assert [p.namn for p in app.sok("tonfisk")] == ["Tonfisk Vatten"]


def test_utgangna_varor_markeras_och_doljs(tmp_path):
    butik = SortimentButik([_vara("1", "Tonfisk Vatten"), _vara("2", "Sejfilé")])
    app = Matplan(tmp_path / "m.db", butiker=(butik,))
    app.refresh(nu=NU)

    butik.produkter = [_vara("2", "Sejfilé"), _vara("4", "Alaska Pollock")]
    resultat = app.refresh(nu=NU + timedelta(days=1))

    assert resultat.sortiment["City Gross Ytterby"] == (2, 1, 1)
    assert app.sok("tonfisk") == []
    assert [p.namn for p in app.sok("pollock")] == ["Alaska Pollock"]
    assert "1" in {p.produkt_id for p in app._lagring.katalog(bara_aktiva=False)}


def test_prishistorik_per_produkt(tmp_path):
    butik = SortimentButik([_vara("1", "Tonfisk Vatten", kr=150)])
    app = Matplan(tmp_path / "m.db", butiker=(butik,))
    app.refresh(nu=NU)
    butik.produkter = [_vara("1", "Tonfisk Vatten", kr=120)]
    app.refresh(nu=NU + timedelta(days=7))

    historik = app._lagring.katalogpriser("City Gross Ytterby", "1")

    assert [kr for _, kr in historik] == [150, 120]
    assert app.sok("tonfisk")[0].kr_per_kg == 120


def test_misslyckad_synk_behaller_sortimentet(tmp_path):
    butik = SortimentButik([_vara("1", "Tonfisk Vatten")])
    app = Matplan(tmp_path / "m.db", butiker=(butik,))
    app.refresh(nu=NU)

    butik.fel = ButiksFel("nere")
    resultat = app.refresh(nu=NU + timedelta(days=1))

    assert "City Gross Ytterby" in resultat.fel and resultat.sortiment == {}
    assert [p.namn for p in app.sok("tonfisk")] == ["Tonfisk Vatten"]


def test_sokning_kraver_hela_ord_och_soker_marke_och_beskrivning(tmp_path):
    butik = SortimentButik([
        _vara("1", "Koljafilé", besk="400G FINDUS"),
        _vara("2", "Stekolja Raps"),
        _vara("3", "Tonfisk Vatten", marke="ABBA", besk="3X95G ABBA"),
    ])
    app = Matplan(tmp_path / "m.db", butiker=(butik,))
    app.refresh(nu=NU)

    assert [p.namn for p in app.sok("koljafilé")] == ["Koljafilé"]
    assert app.sok("kolja") == []  # "stekolja" och "koljafilé" är andra ord
    assert [p.namn for p in app.sok("abba tonfisk")] == ["Tonfisk Vatten"]
    assert [p.namn for p in app.sok("findus")] == ["Koljafilé"]


def test_cli_sok(tmp_path, monkeypatch, capsys):
    import matplan.cli as cli

    monkeypatch.setenv("MATPLAN_DB", str(tmp_path / "cli.db"))
    monkeypatch.setattr(cli, "_butiker", lambda: (SortimentButik([_vara("1", "Tonfisk Vatten", besk="3X170G")]),))

    assert main(["refresh"]) == 0
    assert main(["sök", "tonfisk"]) == 0

    ut = capsys.readouterr().out
    assert "sortiment 1 livsmedel (1 nya, 0 utgångna)" in ut
    assert "GARANT" in ut and "Tonfisk Vatten" in ut and "3X170G" in ut
