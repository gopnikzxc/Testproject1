"""Näring per produkt: butiken, familjens Livsmedelsverket-matchning, Open Food
Facts, och att produkter utan värden inte planeras (#28)."""

from datetime import date, datetime

import pytest
from conftest import SortimentButik, katalogvara, standardsortiment

from matplan.cli import main
from matplan.core import Familj, Matplan
from matplan.katalog import STARTKATALOG, Ingrediens
from matplan.naring import Naring, NaringsFel

START = date(2026, 10, 15)
NU = datetime(2026, 10, 15, 9, 0)

SPETSKAL = Ingrediens("Spetskål", "grönsaker", 25, 1.2, 30, ("spetskål",), butikskategori=("frukt & grönt",))
GRONT = "Frukt & grönt / Grönsaker"
LISTA = [
    (370, "Vitkål"), (371, "Spetskål"), (372, "Spetskål kokt m. salt"), (373, "Spenat"),
    (1278, "Tonfisk i vatten konserv. avrunnen"),
]
VARDEN = {371: (24, 1.4), 372: (22, 1.3), 373: (23, 2.9), 1278: (110, 26.0)}
VARDEN.update({i.livsmedelsverket: (i.kcal_100g, i.protein_100g) for i in STARTKATALOG if i.livsmedelsverket})


class FalskLivsmedelsverket:
    def __init__(self):
        self.hamtade = []
        self.listhamtningar = 0

    def lista(self):
        self.listhamtningar += 1
        return list(LISTA)

    def hamta(self, nummer):
        self.hamtade.append(nummer)
        kcal, protein = VARDEN[nummer]
        return Naring("livsmedelsverket", kcal, protein, 0.3, 4.0, 2.0, 90.0)


class FalskOpenFoodFacts:
    def __init__(self, varden):
        self.varden = varden
        self.fragade = []

    def hamta(self, ean):
        self.fragade.append(ean)
        if ean not in self.varden:
            raise NaringsFel(f"Open Food Facts har ingen vara med EAN {ean}")
        kcal, protein = self.varden[ean]
        return Naring("openfoodfacts", kcal, protein, None, None, None, None)


def _spetskal(*extra):
    return [
        katalogvara("spets-1", "Spetskål Sverige", kcal=None, kategori=GRONT, ean="111", kr=25),
        katalogvara("spets-2", "Spetskål Ekologisk", kcal=None, kategori=GRONT, ean="222", kr=35),
        *extra,
    ]


def _app(db, produkter, off=None, katalog=STARTKATALOG + (SPETSKAL,)):
    lmv = FalskLivsmedelsverket()
    off = off if off is not None else FalskOpenFoodFacts({})
    butik = SortimentButik(standardsortiment() + produkter)
    app = Matplan(db, katalog=katalog, butiker=(butik,), livsmedelsverket=lmv, openfoodfacts=off)
    return app, butik, lmv, off


def _kallor(app, grupp):
    return {p.namn: p.naringskalla for p in app.produkter(grupp)}


def test_butikens_varden_sedan_familjen_sedan_open_food_facts(tmp_path):
    egen = katalogvara("spets-3", "Spetskål Färsk", kcal=26, protein=1.5, kategori=GRONT, kr=40)
    app, _, _, _ = _app(tmp_path / "m.db", _spetskal(egen), off=FalskOpenFoodFacts({"111": (27, 1.1)}))
    app.refresh(nu=NU)

    assert _kallor(app, "Spetskål") == {
        "Spetskål Färsk": "butik", "Spetskål Sverige": "openfoodfacts", "Spetskål Ekologisk": None,
    }

    app.bekrafta_familj("Spetskål")

    # Familjens matchning går före Open Food Facts; butikens egna värden går före allt.
    assert _kallor(app, "Spetskål") == {
        "Spetskål Färsk": "butik", "Spetskål Sverige": "livsmedelsverket", "Spetskål Ekologisk": "livsmedelsverket",
    }
    sverige = next(p for p in app.produkter("Spetskål") if p.namn == "Spetskål Sverige")
    assert (sverige.kcal, sverige.protein) == (24, 1.4)


def test_forslag_bekraftas_en_gang_och_galler_nya_produkter_i_familjen(tmp_path):
    app, butik, lmv, _ = _app(tmp_path / "m.db", _spetskal())
    app.refresh(nu=NU)

    familj = next(f for f in app.naringsfamiljer() if f.familj == "Spetskål")
    assert familj == Familj("Spetskål", ("Spetskål Ekologisk", "Spetskål Sverige"), None, (371, "Spetskål"))

    app.bekrafta_familj("spetskål")
    assert 371 in lmv.hamtade

    butik.produkter.append(katalogvara("spets-4", "Spetskål Röd", kcal=None, kategori=GRONT))
    app.refresh(nu=NU)

    assert set(_kallor(app, "Spetskål").values()) == {"livsmedelsverket"}
    assert next(f for f in app.naringsfamiljer() if f.familj == "Spetskål").bekraftad == (371, "Spetskål")
    assert lmv.listhamtningar == 1  # listan hämtas en gång och sparas


def test_matchningen_kan_bytas(tmp_path):
    app, _, _, _ = _app(tmp_path / "m.db", _spetskal())
    app.refresh(nu=NU)
    app.bekrafta_familj("Spetskål")

    app.bekrafta_familj("Spetskål", 372)

    assert {p.kcal for p in app.produkter("Spetskål")} == {22}


def test_inbyggda_grupper_har_sitt_nummer_som_bekraftad_matchning(tmp_path):
    vitkal = katalogvara("vitkal-1", "Vitkål Sverige", kcal=None, kategori=GRONT, kr=18)
    app, _, _, _ = _app(tmp_path / "m.db", [vitkal])
    app.refresh(nu=NU)

    familj = next(f for f in app.naringsfamiljer() if f.familj == "Vitkål")
    assert familj.bekraftad == (370, "Vitkål") and familj.forslag is None
    assert _kallor(app, "Vitkål")["Vitkål Sverige"] == "livsmedelsverket"


def test_open_food_facts_fragas_bara_om_varor_utan_annan_kalla_och_en_gang(tmp_path):
    off = FalskOpenFoodFacts({"111": (27, 1.1)})
    egen = katalogvara("spets-3", "Spetskål Färsk", kcal=26, protein=1.5, kategori=GRONT, ean="333")
    app, _, _, _ = _app(tmp_path / "m.db", _spetskal(egen), off=off)

    app.refresh(nu=NU)
    app.refresh(nu=NU)

    # (Gruppernas egna streckkoder, Keso och grekisk yoghurt, frågas som förut.)
    assert sorted(e for e in off.fragade if e in ("111", "222", "333")) == ["111", "222"]


def test_produkter_utan_naring_planeras_inte_och_gruppen_hoppas_over(tmp_path):
    app, _, _, _ = _app(tmp_path / "m.db", _spetskal())
    app.refresh(nu=NU)

    plan = app.plan(START)

    assert "Spetskål" not in plan.total_gram()
    assert any("Spetskål" in v and "hoppas över" in v for v in plan.varningar)
    assert "Spetskål" not in plan.utan_butikspris
    # Sökbara, men utan näring och inte planerbara.
    assert {(p.namn, p.naringskalla) for p in app.sok("spetskål")} == {
        ("Spetskål Sverige", None), ("Spetskål Ekologisk", None),
    }


def test_kallan_syns_i_planen_och_kallhanvisningen_finns_kvar(tmp_path):
    utan_gront = tuple(i for i in STARTKATALOG if i.kategori != "grönsaker") + (SPETSKAL,)
    app, _, _, _ = _app(tmp_path / "m.db", _spetskal(), katalog=utan_gront)
    app.refresh(nu=NU)
    app.bekrafta_familj("Spetskål")

    plan = app.plan(START)

    kallor = dict(plan.produktkallor)
    assert kallor["Spetskål"] == "livsmedelsverket"
    assert kallor["Kycklingfilé"] == "butik"
    assert "livsmedelsverket" in plan.naringskallor


def test_familj_for_produktnamn_utanfor_grupperna(tmp_path):
    spenat = katalogvara("spenat-1", "Spenat Hackad", kcal=None, kategori="Fryst / Frysta grönsaker & kryddor")
    app, _, _, _ = _app(tmp_path / "m.db", [spenat])
    app.refresh(nu=NU)
    assert app.sok("spenat")[0].naringskalla is None

    app.bekrafta_familj("Spenat Hackad", 373)

    traff = app.sok("spenat")[0]
    assert (traff.naringskalla, traff.kcal) == ("livsmedelsverket", 23)
    assert Familj("spenat hackad", (), (373, "Spenat"), None) in app.naringsfamiljer()


def test_okant_nummer_och_inget_forslag(tmp_path):
    app, _, _, _ = _app(tmp_path / "m.db", _spetskal())
    app.refresh(nu=NU)

    with pytest.raises(ValueError, match="inget livsmedel med nummer 9999"):
        app.bekrafta_familj("Spetskål", 9999)
    with pytest.raises(ValueError, match="Inget förslag"):
        app.bekrafta_familj("Rabarberkräm")


def test_cli_naring(tmp_path, monkeypatch, capsys):
    import matplan.cli as cli

    monkeypatch.setenv("MATPLAN_DB", str(tmp_path / "m.db"))
    monkeypatch.setenv("COLUMNS", "200")
    monkeypatch.setattr(cli, "_butiker", lambda vald: (SortimentButik(standardsortiment() + _spetskal()),))
    monkeypatch.setattr(cli, "_naringskallor", lambda: (FalskLivsmedelsverket(), FalskOpenFoodFacts({})))
    # CLI:t använder databasens grupper; lägg till Spetskål som grupp där.
    Matplan(tmp_path / "m.db")._lagring.spara_grupp(SPETSKAL)

    assert main(["refresh"]) == 0
    assert main(["näring"]) == 0
    ut = capsys.readouterr().out
    assert "Spetskål" in ut and "förslag: Spetskål (371)" in ut

    assert main(["näring", "--bekräfta", "Spetskål"]) == 0
    assert "Spetskål: Spetskål (Livsmedelsverket 371)." in capsys.readouterr().out

    assert main(["näring", "--sök", "spetskål"]) == 0
    assert "372  Spetskål kokt m. salt" in capsys.readouterr().out

    assert main(["sök", "spetskål"]) == 0
    assert "Livsmedelsverket" in capsys.readouterr().out
