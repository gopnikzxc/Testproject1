"""Kontraktstester: City Gross-adaptern mot inspelade svar från webbutiken."""

import json
from pathlib import Path

import pytest

from matplan.butiker import Butiksplats, ButiksFel
from matplan.butiker.citygross import CityGross, CityGrossButiker
from matplan.http import HttpKlient

FIXTURER = Path(__file__).parent / "fixtures" / "citygross"


def _adapter(tmp_path, svar_for):
    anrop = []

    def transport(url, headers):
        anrop.append(url)
        return svar_for(url)

    http = HttpKlient(tmp_path / "cache", paus_s=0, transport=transport, sov=lambda s: None)
    return CityGross(http), anrop


def _fixtur(namn):
    return (FIXTURER / f"sok_{namn}.json").read_bytes()


def _per_id(produkter):
    return {p.produkt_id: p for p in produkter}


def test_soker_i_ytterbys_butik(tmp_path):
    adapter, anrop = _adapter(tmp_path, lambda url: _fixtur("kycklingfilé"))

    adapter.sok("kycklingfilé")

    assert "searchQuery=kycklingfil%C3%A9" in anrop[0]
    assert "store=3240" in anrop[0]


def test_forpackad_vara_far_forpackning_pris_och_jamforpris(tmp_path):
    adapter, _ = _adapter(tmp_path, lambda url: _fixtur("kycklingfilé"))

    p = _per_id(adapter.sok("kycklingfilé"))["101266948_ST"]

    assert p.butik == "City Gross Ytterby"
    assert p.namn == "Kyckling Filé"
    assert p.forpackning_g == 2000
    assert p.pris_kr == 139
    assert p.kr_per_kg == 69.5
    assert not p.erbjudande
    assert p.kategori == "Fryst / Fryst kött, fågel, burgare mm"


def test_lösviktsvara_saknar_forpackning(tmp_path):
    adapter, _ = _adapter(tmp_path, lambda url: _fixtur("potatis"))

    produkter = _per_id(adapter.sok("potatis"))

    assert produkter["100150587_KG"].forpackning_g is None
    assert produkter["100150587_KG"].kr_per_kg == 14.95
    assert produkter["100225490_ST"].forpackning_g == 5000


def test_erbjudande_markeras(tmp_path):
    adapter, _ = _adapter(tmp_path, lambda url: _fixtur("kycklingfilé"))

    p = _per_id(adapter.sok("kycklingfilé"))["101813806_KG"]

    assert p.erbjudande


def test_agg_raknas_om_fran_styckpris_till_kg(tmp_path):
    adapter, _ = _adapter(tmp_path, lambda url: _fixtur("ägg"))

    p = _per_id(adapter.sok("ägg"))["101187348_ST"]  # 24 st, 2,50 kr/st

    assert p.forpackning_g == 24 * 60
    assert p.kr_per_kg == pytest.approx(2.5 / 60 * 1000)


def test_konstig_enskild_produkt_hoppas_over(tmp_path):
    svar = json.loads(_fixtur("potatis"))
    svar["searchResults"]["products"][0]["productStoreDetails"] = None
    adapter, _ = _adapter(tmp_path, lambda url: json.dumps(svar).encode())

    produkter = adapter.sok("potatis")

    assert len(produkter) == len(svar["searchResults"]["products"]) - 1


@pytest.mark.parametrize("svar", [b"<html>503 Service Temporarily Unavailable</html>", b'{"items": []}'])
def test_andrat_eller_trasigt_svar_ger_butiksfel(tmp_path, svar):
    adapter, _ = _adapter(tmp_path, lambda url: svar)

    with pytest.raises(ButiksFel):
        adapter.sok("keso")


def test_natverksfel_ger_butiksfel(tmp_path):
    import urllib.error

    def nere(url):
        raise urllib.error.URLError("nere")

    adapter, _ = _adapter(tmp_path, nere)

    with pytest.raises(ButiksFel, match="Kunde inte nå"):
        adapter.sok("keso")


# --- Butikslistan och butiksnumret (#27) ---


def _register(tmp_path):
    anrop = []

    def transport(url, headers, metod="GET", data=None):
        anrop.append((url, metod, data))
        if url.endswith("/graphql"):
            return (FIXTURER / "graphql_butiksnummer_31.json").read_bytes()
        return (FIXTURER / "butiker.json").read_bytes()

    http = HttpKlient(tmp_path / "cache", paus_s=0, transport=transport, sov=lambda s: None)
    return CityGrossButiker(http), anrop


def test_butikslistan_ger_namn_adress_postnummer_och_position(tmp_path):
    register, anrop = _register(tmp_path)

    platser = {p.namn: p for p in register.butiker()}

    assert anrop[0][0] == "https://www.citygross.se/api/v1/PageData/stores"
    assert len(platser) == 38
    ytterby = platser["City Gross Ytterby"]
    assert (ytterby.id, ytterby.ort, ytterby.postnummer, ytterby.adress) == ("31", "Ytterby", "44250", "Torsbyvägen 12")
    assert ytterby.lat == pytest.approx(57.8592, abs=1e-3) and ytterby.lng == pytest.approx(11.9182, abs=1e-3)
    # Butiksnamn med blanksteg på slutet och postnummer utan mellanslag normaliseras.
    assert platser["City Gross Kristianstad"].postnummer == "29128"
    assert platser["City Gross Linköping Tornby"].postnummer == "58273"


def test_butiksnumret_slas_upp_via_graphql(tmp_path):
    register, anrop = _register(tmp_path)
    ytterby = next(p for p in register.butiker() if p.id == "31")

    assert register.butiksnummer(ytterby) == 3240

    url, metod, data = anrop[-1]
    assert (url, metod) == ("https://www.citygross.se/graphql", "POST")
    fraga = json.loads(data)
    assert fraga["variables"] == {"siteId": "31"}
    assert "lindbakstorenumber" in fraga["query"]


def test_butiksnummer_saknas_ger_butiksfel(tmp_path):
    def transport(url, headers, metod="GET", data=None):
        return b'{"data":{"lindbakstorenumber":null}}'

    http = HttpKlient(tmp_path / "cache", paus_s=0, transport=transport, sov=lambda s: None)
    plats = Butiksplats("citygross", "999", "City Gross X", "X", "00000")

    with pytest.raises(ButiksFel, match="butiksnummer"):
        CityGrossButiker(http).butiksnummer(plats)


def test_forpackning_ur_pris_och_jamforpris_nar_netcontent_ar_platshallare(tmp_path):
    """Inspelad vara där butikens netContent är 1000 för en burk tonfisk (170/120 g)."""
    adapter, _ = _adapter(tmp_path, lambda url: _fixtur("tonfisk_platshallare"))

    p = adapter.sok("tonfisk")[0]

    assert (p.pris_kr, p.kr_per_kg) == (9.5, 79.17)
    assert p.forpackning_g == 120
