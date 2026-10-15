"""Inköpslistans rader: märke, namn, förpackning, antal, totalvikt och pris (#25)."""

from datetime import date, datetime

import pytest
from conftest import FalskButik

from matplan.butiker import Produkt
from matplan.core import Matplan
from matplan.export import lista_markdown
from matplan.text import kr, listrad, mangd, marke, produkttext, vikt

START = date(2026, 10, 15)
NU = datetime(2026, 10, 14, 9, 0)
CITY = "City Gross Ytterby"

TONFISK = Produkt(CITY, "t", "Tonfisk Vatten", "GARANT", 510, 55.75, 109.31)
POTATIS = Produkt(CITY, "p", "Potatis Mjölig", "", None, 11.83, 11.83)


@pytest.mark.parametrize("belopp, text", [(111.5, "111,50 kr"), (1041.81, "1 041,81 kr"), (9.5, "9,50 kr")])
def test_kronor(belopp, text):
    assert kr(belopp) == text


@pytest.mark.parametrize("gram, text", [(510, "510 g"), (1020, "1,02 kg"), (3000, "3 kg"), (5680, "5,68 kg")])
def test_vikt(gram, text):
    assert vikt(gram) == text


def test_marke_med_versaler_skrivs_normalt():
    assert marke("GARANT EKO") == "Garant Eko"
    assert marke("Arla") == "Arla"


def test_forpackad_rad():
    assert produkttext(TONFISK) == "Garant Tonfisk Vatten 510 g"
    assert mangd(2, 510, 900) == "2 st (1,02 kg)"
    assert listrad(TONFISK, 2, 900, 111.5) == "Garant Tonfisk Vatten 510 g – 2 st (1,02 kg) – 111,50 kr"


def test_losviktsrad():
    assert listrad(POTATIS, None, 3000, 35.5) == "Potatis Mjölig – lösvikt 3 kg – 35,50 kr"


def test_listan_i_exporten_har_det_nya_formatet(tmp_path):
    from matplan.katalog import STARTKATALOG

    # En produkt per ingrediens; potatisen säljs i lösvikt.
    produkter = [
        Produkt(CITY, f"id-{i.namn}", f"{i.sokord[0].capitalize()} Vara", "GARANT", 500.0, i.kr_per_kg / 2, i.kr_per_kg)
        for i in STARTKATALOG if i.namn != "Potatis"
    ] + [Produkt(CITY, "potatis", "Potatis Mjölig", "", None, 15.0, 15.0)]
    app = Matplan(tmp_path / "m.db", butiker=(FalskButik(CITY, produkter),))
    app.refresh(nu=NU)

    text = lista_markdown(app.inkopslista(START))

    forpackade = [r for r in text.splitlines() if r.startswith("- [ ] Garant ")]
    assert forpackade and all(" 500 g – " in r and " st (" in r and r.endswith(" kr") for r in forpackade)
    potatis = [r for r in text.splitlines() if "Potatis Mjölig" in r]
    if potatis:  # bara om planen använder potatis
        assert "lösvikt" in potatis[0]


def test_cli_listan_har_det_nya_formatet(tmp_path, monkeypatch, capsys):
    import matplan.cli as cli
    from conftest import hel_butik

    monkeypatch.setenv("MATPLAN_DB", str(tmp_path / "cli.db"))
    monkeypatch.setattr(cli, "_butiker", lambda vald: (hel_butik(CITY),))

    assert cli.main(["refresh"]) == 0
    assert cli.main(["lista"]) == 0

    ut = capsys.readouterr().out
    assert "Märke " in ut and " st (" in ut and " kr" in ut
