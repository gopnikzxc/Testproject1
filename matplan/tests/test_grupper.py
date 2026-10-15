"""Ingrediensgrupper som matchas mot det lokala sortimentet (#26)."""

from datetime import date, datetime, timedelta

import pytest
from conftest import SortimentButik, katalogvara, standardsortiment

from matplan.core import Matplan
from matplan.katalog import STARTKATALOG

START = date(2026, 10, 15)
NU = datetime(2026, 10, 15, 9, 0)


_sortiment = standardsortiment


def test_inbyggda_grupper_laggs_in_forsta_gangen(tmp_path):
    app = Matplan(tmp_path / "m.db")

    assert sorted(i.namn for i in app._lagring.grupper()) == sorted(i.namn for i in STARTKATALOG)


def test_borttagen_grupp_kommer_inte_tillbaka(tmp_path):
    db = tmp_path / "m.db"
    Matplan(db)._lagring.ta_bort_grupp("Gurka")

    app = Matplan(db)

    assert "Gurka" not in {i.namn for i in app._lagring.grupper()}


def test_butik_med_sortiment_soks_inte_per_term(tmp_path):
    app = Matplan(tmp_path / "m.db", butiker=(SortimentButik(_sortiment()),))

    resultat = app.refresh(nu=NU)  # SortimentButik.sok kastar om den anropas

    assert resultat.antal_produkter == {}
    assert app.produkter("Kycklingfilé")


def test_grupperna_matchas_mot_sortimentet(tmp_path):
    produkter = _sortiment() + [
        katalogvara("kyckling-2", "Kyckling Filé", kr=60, kategori="Fryst / Fryst kött, fågel"),
        katalogvara("korv", "Kycklingkorv", kr=30, kategori="Chark / Korv"),
    ]
    app = Matplan(tmp_path / "m.db", butiker=(SortimentButik(produkter),))
    app.refresh(nu=NU)

    ids = {p.produkt_id for p in app.produkter("Kycklingfilé")}

    assert "kyckling-2" in ids and "korv" not in ids


def test_planen_anvander_pris_och_naring_fran_vald_produkt(tmp_path):
    produkter = _sortiment() + [
        katalogvara("kyckling-billig", "Kyckling Filé", kr=60, kcal=120, protein=25,
                    kategori="Fryst / Fryst kött, fågel"),
    ]
    app = Matplan(tmp_path / "m.db", butiker=(SortimentButik(produkter),))
    app.refresh(nu=NU)

    rader = [r for b in app.plan(START).block for r in b.batch.portion("jag").rader if r.namn == "Kycklingfilé"]

    assert rader
    for rad in rader:
        assert rad.kcal == pytest.approx(120 * rad.gram / 100)
        assert rad.protein == pytest.approx(25 * rad.gram / 100)
        assert rad.kr == pytest.approx(60 * rad.gram / 1000)


def test_produkt_utan_naring_far_gruppens_varden(tmp_path):
    kyckling = next(i for i in STARTKATALOG if i.namn == "Kycklingfilé")
    produkter = [p for p in _sortiment() if p.produkt_id != "id-Kycklingfilé"] + [
        katalogvara("kyckling-utan", "Kyckling Filé", kr=60, kcal=None, protein=None,
                    kategori="Fryst / Fryst kött, fågel"),
    ]
    app = Matplan(tmp_path / "m.db", butiker=(SortimentButik(produkter),))
    app.refresh(nu=NU)

    for block in app.plan(START).block:
        for rad in block.batch.portion("jag").rader:
            if rad.namn == "Kycklingfilé":
                assert rad.kcal == pytest.approx(kyckling.kcal_100g * rad.gram / 100)


def test_las_och_rea_fungerar_med_sortimentsprodukter(tmp_path):
    def sortiment(kr):
        return _sortiment() + [katalogvara("kyckling-x", "Kyckling Filé", kr=kr, kategori="Fryst / Fryst kött, fågel")]

    butik = SortimentButik(sortiment(100))
    app = Matplan(tmp_path / "m.db", butiker=(butik,))
    for vecka in (3, 2, 1):
        app.refresh(nu=NU - timedelta(weeks=vecka))
    butik.produkter = sortiment(60)
    app.refresh(nu=NU)

    assert "Kycklingfilé" in app.plan(START, ny=True).rea  # 60 mot medianen 100

    app.las("Kycklingfilé", "City Gross Ytterby", "id-Kycklingfilé")
    rad = next(r for r in app.inkopslista(START).rader if r.ingrediens == "Kycklingfilé")
    assert rad.alternativ["City Gross Ytterby"].produkt.produkt_id == "id-Kycklingfilé"


def test_utgangen_produkt_anvands_inte(tmp_path):
    produkter = _sortiment() + [katalogvara("kyckling-x", "Kyckling Filé", kr=30, kategori="Fryst / Fryst kött, fågel")]
    butik = SortimentButik(produkter)
    app = Matplan(tmp_path / "m.db", butiker=(butik,))
    app.refresh(nu=NU)
    butik.produkter = _sortiment()

    app.refresh(nu=NU + timedelta(days=1))

    assert "kyckling-x" not in {p.produkt_id for p in app.produkter("Kycklingfilé")}
