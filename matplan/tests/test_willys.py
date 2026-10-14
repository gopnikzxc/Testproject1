"""Kontraktstester: Willys-adaptern mot inspelade svar från webbutiken."""

import json
import urllib.error
import urllib.parse
from pathlib import Path

import pytest

from matplan.butiker import ButiksFel
from matplan.butiker.willys import Willys
from matplan.http import HttpKlient

FIXTURER = Path(__file__).parent / "fixtures" / "willys"
SOKNINGAR = {
    "broccoli": "sok_broccoli.json",
    "broccoli:category:Grönsaker & kryddor": "sok_broccoli_grönsaker_kryddor.json",
    "ägg": "sok_ägg.json",
}


class Inspelning:
    """Svarar som Willys med inspelade svar och minns anropen."""

    def __init__(self, sokning=None):
        self.anrop = []
        self._sokning = sokning

    def __call__(self, url, headers, metod="GET"):
        self.anrop.append((metod, url, headers))
        if "csrf-token" in url:
            return (FIXTURER / "csrf-token.json").read_bytes()
        if "store/activate" in url:
            return (FIXTURER / "activate.json").read_bytes()
        if self._sokning:
            return self._sokning(url)
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["q"][0]
        return (FIXTURER / SOKNINGAR[q]).read_bytes()


def _adapter(tmp_path, transport):
    return Willys(HttpKlient(tmp_path / "cache", paus_s=0, transport=transport, sov=lambda s: None))


def _per_id(produkter):
    return {p.produkt_id: p for p in produkter}


def test_valjer_butiken_med_csrf_token_fore_sokning(tmp_path):
    transport = Inspelning()

    _adapter(tmp_path, transport).sok("ägg")

    (m1, url1, _), (m2, url2, h2), (m3, url3, _) = transport.anrop
    assert (m1, url1) == ("GET", "https://www.willys.se/axfood/rest/csrf-token")
    assert m2 == "POST" and "store/activate?storeId=2104" in url2
    assert h2["X-CSRF-TOKEN"] == "00000000-0000-0000-0000-000000000000"
    assert m3 == "GET" and "/search?q=%C3%A4gg" in url3


def test_butiken_valjs_bara_en_gang(tmp_path):
    transport = Inspelning()
    adapter = _adapter(tmp_path, transport)

    adapter.sok("ägg")
    adapter.sok("broccoli")

    assert sum("store/activate" in url for _, url, _ in transport.anrop) == 1


def test_kategori_hamtas_via_facettfilter(tmp_path):
    transport = Inspelning()

    produkter = _per_id(_adapter(tmp_path, transport).sok("broccoli", ("frysta grönsaker", "grönsaker & kryddor")))

    # Färsk broccoli ("Grönsaker") filtreras bort; de frysta får facettens namn som kategori.
    assert "101274134_ST" not in produkter
    assert {p.kategori for p in produkter.values()} == {"Grönsaker & kryddor"}
    fryst = produkter["101273514_ST"]
    assert fryst.namn == "Broccoli Buketter Frysta"
    assert (fryst.forpackning_g, fryst.pris_kr, fryst.kr_per_kg) == (1000, 25.9, 25.9)
    assert fryst.beskrivning == "ELDORADO, 1kg"
    assert any("category%3AGr%C3%B6nsaker+%26+kryddor" in url for _, url, _ in transport.anrop)


def test_utan_kategoriord_en_bred_sokning(tmp_path):
    transport = Inspelning()

    produkter = _per_id(_adapter(tmp_path, transport).sok("broccoli"))

    assert set(produkter) == {"101273514_ST", "101274134_ST"}
    assert all(p.kategori == "" for p in produkter.values())


def test_agg_raknas_om_fran_styckpris_till_kg(tmp_path):
    p = _per_id(_adapter(tmp_path, Inspelning()).sok("ägg"))["101718037_ST"]  # 24 st, 2,50 kr/st

    assert p.forpackning_g == 24 * 60
    assert p.kr_per_kg == pytest.approx(2.5 / 60 * 1000)


def test_losviktsvara_och_erbjudande(tmp_path):
    svar = json.loads((FIXTURER / "sok_broccoli.json").read_text())
    rad = dict(svar["results"][0], code="100150587_KG", priceUnit="kr/kg", priceValue=13.9,
               comparePrice="13,90 kr", potentialPromotions=[{"code": "x"}])
    svar["results"] = [rad]
    transport = Inspelning(lambda url: json.dumps(svar).encode())

    (p,) = _adapter(tmp_path, transport).sok("potatis")

    assert p.forpackning_g is None
    assert p.kr_per_kg == 13.9
    assert p.erbjudande


@pytest.mark.parametrize("svar", [b"<html>fel</html>", b'{"items": []}'])
def test_andrat_eller_trasigt_svar_ger_butiksfel(tmp_path, svar):
    with pytest.raises(ButiksFel):
        _adapter(tmp_path, Inspelning(lambda url: svar)).sok("keso")


def test_natverksfel_ger_butiksfel(tmp_path):
    def nere(url, headers, metod="GET"):
        raise urllib.error.URLError("nere")

    with pytest.raises(ButiksFel, match="Kunde inte nå Willys"):
        _adapter(tmp_path, nere).sok("keso")
