"""Butiksval: lista kedjans butiker, välja en, och att bytet behåller allt annat (#27)."""

import sqlite3
from datetime import date, datetime

import pytest
from conftest import SortimentButik, hel_butik, katalogvara

import matplan.cli as cli
from matplan.butiker import Butiksplats, ValdButik
from matplan.cli import main
from matplan.core import Matplan

START = date(2026, 10, 15)
NU = datetime(2026, 10, 15, 9, 0)

YTTERBY = Butiksplats("citygross", "31", "City Gross Ytterby", "Ytterby", "44250", "Torsbyvägen 12", 57.8592, 11.9182)
UDDEVALLA = Butiksplats("citygross", "57", "City Gross Uddevalla", "Uddevalla", "45176", "Östra torpvägen 2", 58.3531, 11.8244)
TROLLHATTAN = Butiksplats("citygross", "1006", "City Gross Trollhättan", "Trollhättan", "46170", "Överbyvägen 25", 58.3149, 12.3016)
BORAS = Butiksplats("citygross", "21", "City Gross Borås", "Borås", "50463", "Göteborgsvägen 181", 57.7142, 12.8670)
MALMO = Butiksplats("citygross", "169", "City Gross Malmö Hyllie", "Malmö", "21534", "Hyllie Allé 3 C", 55.5614, 12.9828)
UPPSALA_B = Butiksplats("citygross", "17", "City Gross Uppsala Boländerna", "Uppsala", "75323", "", 59.8473, 17.6863)
UPPSALA_G = Butiksplats("citygross", "165", "City Gross Uppsala Gränby", "Uppsala", "75460", "", 59.8862, 17.6713)
NUMMER = {"31": 3240, "21": 3204, "57": 3257, "1006": 3206, "169": 3269, "17": 3217, "165": 3265}


class FalsktRegister:
    kedja = "citygross"

    def __init__(self, platser=(YTTERBY, UDDEVALLA, TROLLHATTAN, BORAS, MALMO, UPPSALA_B, UPPSALA_G)):
        self.platser = list(platser)
        self.uppslag = []

    def butiker(self):
        return list(self.platser)

    def butiksnummer(self, plats):
        self.uppslag.append(plats.id)
        return NUMMER[plats.id]


def _sortiment_for(vald, kr=50.0):
    """En sortimentsbutik för den valda butiken, med samma varor till olika pris per butik."""
    varor = [katalogvara("kyckling", "Kyckling Filé", kr=kr, kategori="Fryst / Fryst kött, fågel", butik=vald.namn)]
    return SortimentButik(varor, namn=vald.namn)


def _app(db, register=None, priser=None):
    priser = priser or {}
    return Matplan(
        db,
        butiker=lambda vald: (_sortiment_for(vald, priser.get(vald.namn, 50.0)),),
        butiksregister=(register or FalsktRegister(),),
    )


def test_ny_databas_har_ytterby_vald(tmp_path):
    app = Matplan(tmp_path / "m.db")

    assert app.vald_butik() == ValdButik("citygross", 3240, "City Gross Ytterby")
    assert not any(k.startswith("butik_") for k in app.installningar())


@pytest.mark.parametrize(
    "gamla, vald",
    [
        ({"butik_citygross": 1, "butik_willys": 0}, "City Gross Ytterby"),
        ({"butik_citygross": 1, "butik_willys": 1}, "City Gross Ytterby"),
        ({"butik_citygross": 0, "butik_willys": 1}, "Willys Kungälv"),
        ({}, "City Gross Ytterby"),
    ],
)
def test_gamla_av_pa_installningar_migreras(tmp_path, gamla, vald):
    db = tmp_path / "m.db"
    with sqlite3.connect(db) as anslutning:
        anslutning.execute("CREATE TABLE installningar (nyckel TEXT PRIMARY KEY, varde REAL NOT NULL)")
        anslutning.executemany("INSERT INTO installningar VALUES (?, ?)", [*gamla.items(), ("veckobudget", 1400)])

    app = Matplan(db)

    assert app.vald_butik().namn == vald
    assert "butik_citygross" not in app.installningar() and "butik_willys" not in app.installningar()
    assert app.installningar()["veckobudget"] == 1400


def test_postnummer_listar_narmast_forst(tmp_path):
    app = _app(tmp_path / "m.db")

    rader = app.butikslista(postnummer="442 34")

    assert [r.plats.namn for r in rader[:3]] == ["City Gross Ytterby", "City Gross Uddevalla", "City Gross Trollhättan"]
    assert rader[0].km == pytest.approx(0, abs=0.1) and rader[0].vald
    assert rader[-1].plats.namn in ("City Gross Uppsala Boländerna", "City Gross Uppsala Gränby")
    assert [r.km for r in rader] == sorted(r.km for r in rader)


def test_postnummer_utan_egen_butik_anvander_narmaste_referens(tmp_path):
    app = _app(tmp_path / "m.db")

    # Varken 754 31 eller 413 19 (Göteborg) har en egen butik; närmaste referens avgör.
    assert app.butikslista(postnummer="75431")[0].plats.namn.startswith("City Gross Uppsala")
    assert app.butikslista(postnummer="41319")[0].plats.namn == "City Gross Ytterby"


def test_felaktigt_postnummer(tmp_path):
    with pytest.raises(ValueError, match="fem siffror"):
        _app(tmp_path / "m.db").butikslista(postnummer="442")


def test_sok_pa_ort_och_namn(tmp_path):
    app = _app(tmp_path / "m.db")

    assert [r.plats.namn for r in app.butikslista(sok="uppsala")] == [
        "City Gross Uppsala Boländerna", "City Gross Uppsala Gränby",
    ]
    assert [r.plats.namn for r in app.butikslista(sok="Hyllie")] == ["City Gross Malmö Hyllie"]


def test_val_slar_upp_butiksnumret_och_refresh_synkar_den_butiken(tmp_path):
    register = FalsktRegister()
    app = _app(tmp_path / "m.db", register)

    vald = app.valj_butik("City Gross Borås")
    resultat = app.refresh(nu=NU)

    assert vald == ValdButik("citygross", 3204, "City Gross Borås")
    assert register.uppslag == ["21"]
    assert set(resultat.sortiment) == {"City Gross Borås"}
    assert {p.butik for p in app.produkter("Kycklingfilé")} == {"City Gross Borås"}


def test_val_pa_ort_eller_kort_namn(tmp_path):
    app = _app(tmp_path / "m.db")

    assert app.valj_butik("trollhättan").namn == "City Gross Trollhättan"
    assert app.valj_butik("Borås").namn == "City Gross Borås"


def test_okand_eller_tvetydig_butik(tmp_path):
    app = _app(tmp_path / "m.db")

    with pytest.raises(ValueError, match="Hittar ingen"):
        app.valj_butik("Kiruna")
    with pytest.raises(ValueError, match="Flera butiker"):
        app.valj_butik("Uppsala")
    assert app.vald_butik().namn == "City Gross Ytterby"


def test_byte_behaller_grupper_lager_och_installningar(tmp_path):
    app = _app(tmp_path / "m.db")
    app.satt_lager("Havregryn", 750)
    app.satt_installning("veckobudget", 1400)
    grupper = app._grundkatalog

    app.valj_butik("City Gross Borås")

    assert app.lager() == {"Havregryn": 750}
    assert app.installningar()["veckobudget"] == 1400
    assert app._grundkatalog == grupper


def test_tillbaka_till_tidigare_butik_ger_dess_sortiment_och_historik(tmp_path):
    app = _app(tmp_path / "m.db", priser={"City Gross Ytterby": 60.0, "City Gross Borås": 40.0})
    app.refresh(nu=NU)
    app.valj_butik("Borås")
    app.refresh(nu=NU)
    assert {p.kr_per_kg for p in app.produkter("Kycklingfilé")} == {40.0}

    app.valj_butik("Ytterby")

    # Utan ny hämtning: Ytterbys sparade sortiment och priser gäller igen, Borås syns inte.
    assert {(p.butik, p.kr_per_kg) for p in app.produkter("Kycklingfilé")} == {("City Gross Ytterby", 60.0)}
    assert {t.butik for t in app.inkopslista(START).butiker} <= {"City Gross Ytterby"}
    assert all(p.butik == "City Gross Ytterby" for p in app.sok("kyckling"))


def test_ej_vald_butiks_sparade_priser_ignoreras_aven_utan_adaptrar(tmp_path):
    db = tmp_path / "m.db"
    city = hel_butik("City Gross Ytterby")
    willys = hel_butik("Willys Kungälv", faktor=0.5)  # billigare, så den skulle vinna om den räknades
    city.nyckel, willys.nyckel = "citygross", "willys"
    Matplan(db, butiker=(city, willys)).refresh(nu=NU)

    utan_adaptrar = Matplan(db)

    assert {t.butik for t in utan_adaptrar.inkopslista(START).butiker} == {"City Gross Ytterby"}


def test_cli_listar_och_valjer_butik(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MATPLAN_DB", str(tmp_path / "m.db"))
    monkeypatch.setattr(cli, "_butiksregister", lambda: (FalsktRegister(),))

    assert main(["butik", "442 50"]) == 0
    ut = capsys.readouterr().out
    assert ut.index("City Gross Ytterby") < ut.index("City Gross Uddevalla") < ut.index("City Gross Borås")
    assert "Vald butik: City Gross Ytterby" in ut

    assert main(["butik", "--välj", "City Gross Borås"]) == 0
    assert "Vald butik: City Gross Borås (butiksnummer 3204)" in capsys.readouterr().out

    assert main(["butik", "--sök", "Kiruna"]) == 0
    assert "Inga butiker hittades" in capsys.readouterr().out

    assert main(["butik", "--välj", "Kiruna"]) == 1
    assert "Hittar ingen butik" in capsys.readouterr().out
