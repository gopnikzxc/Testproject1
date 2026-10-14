"""Kontraktstester: City Gross-adaptern mot inspelade svar från webbutiken."""

import json
from pathlib import Path

import pytest

from matplan.butiker import ButiksFel
from matplan.butiker.citygross import CityGross
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
