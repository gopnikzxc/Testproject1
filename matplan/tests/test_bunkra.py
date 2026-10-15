"""Bunkringsförslag inom lagringsutrymmet (#14).

Rean kommer från butikens erbjudandeflagga (en hämtning, ingen historik). Med
katalogens priser är snittet av proteinkällornas protein per krona ca 2,1 g/kr:
kyckling 2,33, ägg 2,76, torsk 1,59, nötfärs 1,73.
"""

import dataclasses
from datetime import date, datetime

import pytest
from conftest import hel_butik

from matplan.cli import main
from matplan.core import Matplan
from matplan.katalog import STARTKATALOG, Ingrediens

START = date(2026, 10, 15)
NU = datetime(2026, 10, 14, 9, 0)
CITY = "City Gross Ytterby"


def _app(tmp_path, erbjudande, katalog=STARTKATALOG, **butik):
    app = Matplan(tmp_path / "m.db", katalog=katalog, butiker=(hel_butik(CITY, katalog=katalog, erbjudande=erbjudande, **butik),))
    app.refresh(nu=NU)
    return app


def test_bara_varor_som_uppfyller_alla_villkor_foreslas(tmp_path):
    app = _app(tmp_path, erbjudande=(
        "Kycklingfilé",      # protein, fryst, rea, 2,33 g/kr > snittet → ja
        "Nötfärs 10–12 %",   # protein, fryst, rea, men 1,73 g/kr < snittet → nej
        "Ägg",               # protein på rea men färskvara → nej
        "Ris, okokt",        # torrvara på rea men ingen proteinkälla → nej
    ))

    assert [b.ingrediens for b in app.bunkra()] == ["Kycklingfilé"]


def test_utan_rea_inga_forslag(tmp_path):
    assert _app(tmp_path, erbjudande=()).bunkra() == []


def test_mangden_ryms_i_frysen_som_ar_kvar(tmp_path):
    app = _app(tmp_path, erbjudande=("Kycklingfilé",))
    app.satt_lager("Broccoli, fryst", 3000)  # 3 av 10 kg upptagna

    (forslag,) = app.bunkra()

    assert forslag.antal == 7 and forslag.gram == 7000
    assert forslag.kostnad == pytest.approx(7 * forslag.produkt.pris_kr)


def test_frysutrymmet_kan_andras(tmp_path):
    app = _app(tmp_path, erbjudande=("Kycklingfilé",))

    app.satt_installning("frys_kg", 1.5)
    assert [b.gram for b in app.bunkra()] == [1000]  # bara hela förpackningar

    app.satt_installning("frys_kg", 0.5)
    assert app.bunkra() == []


TONFISK = Ingrediens("Tonfisk i vatten", "protein", 116, 26.0, 80, ("tonfisk",), "torrvara", ("konserv",))


def test_torrvaror_begransas_av_torrutrymmet(tmp_path):
    katalog = STARTKATALOG + (TONFISK,)
    app = _app(tmp_path, erbjudande=("Tonfisk i vatten",), katalog=katalog, forpackning_g=500)

    assert [(b.ingrediens, b.gram) for b in app.bunkra()] == [("Tonfisk i vatten", 2000)]
    app.satt_installning("torr_kg", 1)
    assert [b.gram for b in app.bunkra()] == [1000]


def test_bast_protein_per_krona_far_plats_forst(tmp_path):
    katalog = tuple(dataclasses.replace(i, forvaring="fryst") if i.namn == "Ägg" else i for i in STARTKATALOG)
    app = _app(tmp_path, erbjudande=("Kycklingfilé", "Ägg"), katalog=katalog)
    app.satt_installning("frys_kg", 1)

    assert [b.ingrediens for b in app.bunkra()] == ["Ägg"]  # 2,76 g/kr före kycklingens 2,33


def test_accepterad_bunkring_hamnar_i_egen_del_av_listan_och_utanfor_budgeten(tmp_path):
    app = _app(tmp_path, erbjudande=("Kycklingfilé",))
    fore_plan = app.plan(START)
    fore_lista = app.inkopslista(START)

    bunkring = app.acceptera_bunkring("Kycklingfilé")

    lista = app.inkopslista(START)
    assert lista.bunkring == (bunkring,)
    assert lista.bunkring_kr == pytest.approx(bunkring.kostnad)
    assert lista.rader == fore_lista.rader  # vanliga listan och dess totaler är oförändrade
    assert lista.butiker == fore_lista.butiker
    assert app.plan(START).kr == pytest.approx(fore_plan.kr)  # budgeten räknar inte bunkringen
    assert app.bunkra() == []  # redan accepterad, och frysen är nu full


def test_kopt_lagger_bunkringen_i_lagret(tmp_path):
    app = _app(tmp_path, erbjudande=("Kycklingfilé",))
    bunkring = app.acceptera_bunkring("Kycklingfilé")
    planerat = app.inkopslista(START)
    kyckling_i_listan = next((r for r in planerat.rader if r.ingrediens == "Kycklingfilé"), None)
    vanligt = kyckling_i_listan.alternativ[CITY].antal * 1000 if kyckling_i_listan else 0

    app.kopt(START)

    assert app.lager()["Kycklingfilé"] == pytest.approx(vanligt + bunkring.gram)
    assert app.inkopslista(START).bunkring == ()


def test_bunkring_kan_tas_bort_och_okand_vara_avvisas(tmp_path):
    app = _app(tmp_path, erbjudande=("Kycklingfilé",))
    app.acceptera_bunkring("Kycklingfilé")

    assert app.ta_bort_bunkring("Kycklingfilé")
    assert app.inkopslista(START).bunkring == ()
    with pytest.raises(KeyError, match="Inget bunkringsförslag"):
        app.acceptera_bunkring("Ägg")


def test_cli_bunkra(tmp_path, monkeypatch, capsys):
    import matplan.cli as cli

    monkeypatch.setenv("MATPLAN_DB", str(tmp_path / "cli.db"))
    monkeypatch.setattr(cli, "_butiker", lambda: (hel_butik(CITY, erbjudande=("Kycklingfilé",)),))

    assert main(["refresh"]) == 0
    assert main(["bunkra"]) == 0
    assert "Bunkringsförslag" in capsys.readouterr().out
    assert main(["bunkra", "--ta", "Kycklingfilé"]) == 0
    assert main(["lista"]) == 0
    ut = capsys.readouterr().out
    assert "ligger nu på inköpslistan" in ut and "Bunkring (utanför budgeten)" in ut
    assert main(["bunkra", "--ta", "Ägg"]) == 1


def test_bunkring_i_markdownexporten(tmp_path):
    from matplan.export import lista_markdown

    app = _app(tmp_path, erbjudande=("Kycklingfilé",))
    app.acceptera_bunkring("Kycklingfilé")

    text = lista_markdown(app.inkopslista(START))

    assert "## Bunkring (utanför budgeten)" in text
    assert "- [ ] Märke Kycklingfilé City Gross Ytterby 1 kg – 10 st (10 kg) – 990,00 kr – City Gross Ytterby" in text
