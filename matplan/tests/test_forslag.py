"""Förslag på produkter som inte hör till någon grupp (#32)."""

from datetime import datetime

import pytest
from conftest import SortimentButik, katalogvara, standardsortiment

from matplan.cli import main
from matplan.core import Matplan

NU = datetime(2026, 10, 15, 9, 0)
SENARE = datetime(2026, 10, 16, 9, 0)


def _varor():
    def vara(pid, namn, kategori, kcal, protein, kolhydrater, kr, fett=1.0):
        return katalogvara(pid, namn, kategori=kategori, kcal=kcal, protein=protein, kolhydrater=kolhydrater,
                           fett=fett, kr=kr)

    return [
        vara("tf-1", "Tonfisk Vatten", "Skafferiet / Konserver", 101, 24.0, 0.0, 80),
        vara("sej-1", "Sejfilé", "Fryst / Fryst fisk & skaldjur", 80, 18.0, 0.0, 120),
        vara("sb-1", "Svarta Bönor", "Skafferiet / Bönor, ärtor & linser", 314, 20.0, 45.0, 34),
        vara("cc-1", "Couscous", "Skafferiet / Pasta, ris & mos", 350, 12.0, 72.0, 30),
        vara("bk-1", "Brysselkål", "Fryst / Frysta grönsaker & kryddor", 45, 4.0, 5.0, 43),
        vara("ju-1", "Apelsinjuice", "Dryck / Juice, fruktdrycker & smoothies", 45, 0.7, 9.0, 20),
        vara("ost-1", "Hårdost Lagrad", "Mejeri, ost & ägg / Hårdost", 350, 27.0, 0.0, 120, fett=27.0),
        katalogvara("ok-1", "Okänd Vara", kategori="Skafferiet / Konserver", kcal=None),
    ]


def _app(tmp_path, varor=None):
    butik = SortimentButik(standardsortiment() + (varor if varor is not None else _varor()))
    app = Matplan(tmp_path / "m.db", butiker=(butik,))
    app.refresh(nu=NU)
    return app, butik


def _ids(app):
    return [p.produkt_id for p in app.forslag()]


def test_proteinkallor_rankas_fore_kolhydrater_och_gronsaker(tmp_path):
    app, _ = _app(tmp_path)

    ids = _ids(app)

    for protein in ("tf-1", "sej-1", "sb-1"):
        assert ids.index(protein) < ids.index("cc-1") and ids.index(protein) < ids.index("bk-1")
    assert ids[0] == "tf-1"  # både tät och billig


def test_bara_planerbara_aktiva_produkter_utanfor_grupperna(tmp_path):
    app, butik = _app(tmp_path)

    ids = set(_ids(app))

    assert not ids & {"ju-1", "ok-1", "ost-1"}  # juice, utan näring, utan slot
    assert not any(i.startswith("id-") for i in ids)  # redan i de inbyggda grupperna

    butik.produkter = [p for p in butik.produkter if p.produkt_id != "sej-1"]
    app.refresh(nu=SENARE)
    assert "sej-1" not in _ids(app)  # inte längre i sortimentet


def test_godkand_produkt_och_dess_familj_foreslas_inte_langre(tmp_path):
    andra_tonfisken = katalogvara("tf-2", "Tonfisk Vatten", marke="ABBA", kcal=110, protein=26.0, kolhydrater=0.0,
                                  kategori="Skafferiet / Konserver", kr=150)
    app, _ = _app(tmp_path, _varor() + [andra_tonfisken])
    assert {"tf-1", "tf-2"} <= set(_ids(app))

    app.godkann("tf-1")

    assert not {"tf-1", "tf-2"} & set(_ids(app))


def test_avfardade_kommer_inte_tillbaka(tmp_path):
    app, _ = _app(tmp_path)

    app.avfarda_forslag("sej-1")

    assert "sej-1" not in _ids(app)
    assert "sej-1" not in [p.produkt_id for p in Matplan(tmp_path / "m.db").forslag()]
    assert any(p.produkt_id == "sej-1" for p in app.sok("sejfilé"))  # fortfarande sökbar
    with pytest.raises(KeyError):
        app.avfarda_forslag("finns-inte")


def test_samma_marke_och_namn_visas_en_gang(tmp_path):
    storpack = katalogvara("tf-3", "Tonfisk Vatten", kcal=101, protein=24.0, kolhydrater=0.0,
                           kategori="Skafferiet / Konserver", kr=70)
    app, _ = _app(tmp_path, _varor() + [storpack])

    ids = _ids(app)

    assert "tf-3" in ids and "tf-1" not in ids  # samma märke och namn: den billigaste per kg


def test_cli_forslag_och_avfarda(tmp_path, monkeypatch, capsys):
    import matplan.cli as cli

    monkeypatch.setenv("MATPLAN_DB", str(tmp_path / "cli.db"))
    monkeypatch.setenv("COLUMNS", "200")
    monkeypatch.setattr(cli, "_butiker", lambda vald: (SortimentButik(standardsortiment() + _varor()),))
    assert main(["refresh"]) == 0
    capsys.readouterr()

    assert main(["sök", "--förslag"]) == 0
    ut = capsys.readouterr().out
    assert "Förslag (" in ut and "Tonfisk Vatten" in ut and "Apelsinjuice" not in ut

    assert main(["sök", "--avfärda", "tf-1"]) == 0
    assert main(["sök", "--förslag"]) == 0
    assert "tf-1" not in capsys.readouterr().out.split("föreslås inte igen.")[-1]
