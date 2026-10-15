"""Inköpslista (#7) och jämförelse enskild butik mot uppdelat (#8)."""

from datetime import date, datetime

import pytest
from conftest import hel_butik

from matplan.cli import main
from matplan.core import Matplan
from matplan.export import exportera

START = date(2026, 10, 15)
NU = datetime(2026, 10, 14, 9, 30)


def _app(tmp_path, *butiker):
    tmp_path.mkdir(parents=True, exist_ok=True)
    app = Matplan(tmp_path / "m.db", butiker=butiker)
    app.refresh(nu=NU)
    return app


def test_hela_forpackningar_tacker_planens_behov(tmp_path):
    app = _app(tmp_path, hel_butik("City Gross Ytterby", forpackning_g=400))

    lista = app.inkopslista(START)
    behov = app.plan(START).total_gram()

    assert {rad.ingrediens for rad in lista.rader} == set(behov)
    for rad in lista.rader:
        kop = rad.alternativ["City Gross Ytterby"]
        assert rad.gram == behov[rad.ingrediens]
        assert kop.antal * 400 >= rad.gram > (kop.antal - 1) * 400
        assert kop.kostnad == pytest.approx(kop.antal * kop.produkt.pris_kr)


def test_maltidskostnad_ar_kr_per_kg_ganger_gram(tmp_path):
    app = _app(tmp_path, hel_butik("City Gross Ytterby", forpackning_g=400))

    for maltid in app.plan(START).dagar[0].maltider:
        for portion in maltid.portioner:
            for rad in portion.rader:
                kr_per_kg = next(p.kr_per_kg for p in app.produkter(rad.namn))
                assert rad.kr == pytest.approx(kr_per_kg * rad.gram / 1000)


def test_total_per_butik(tmp_path):
    app = _app(tmp_path, hel_butik("City Gross Ytterby"), hel_butik("Coop Kungälv", faktor=1.2))

    lista = app.inkopslista(START)

    totaler = {t.butik: t for t in lista.butiker}
    assert set(totaler) == {"City Gross Ytterby", "Coop Kungälv"}
    for butik, total in totaler.items():
        assert total.kostnad == pytest.approx(sum(r.alternativ[butik].kostnad for r in lista.rader))
        assert total.saknas == ()
    assert lista.basta_butik.butik == "City Gross Ytterby"


def test_uppdelat_valjer_billigaste_butik_per_vara_och_visar_besparing(tmp_path):
    city = hel_butik("City Gross Ytterby", undantag={"Kycklingfilé": 140})
    coop = hel_butik("Coop Kungälv", faktor=1.1, undantag={"Kycklingfilé": 70})
    app = _app(tmp_path, city, coop)

    lista = app.inkopslista(START)

    kyckling = next(r for r in lista.rader if r.ingrediens == "Kycklingfilé")
    assert kyckling.billigast[0] == "Coop Kungälv"
    assert lista.delad_kostnad == pytest.approx(sum(min(k.kostnad for k in r.alternativ.values()) for r in lista.rader))
    assert lista.besparing == pytest.approx(lista.basta_butik.kostnad - lista.delad_kostnad)
    assert lista.besparing > 0


def test_butik_som_saknar_varor_rankas_efter_kompletta(tmp_path):
    planerat = sorted(_app(tmp_path / "a", hel_butik("Coop Kungälv")).plan(START).total_gram())[:2]
    city = hel_butik("City Gross Ytterby", undantag={namn: None for namn in planerat})
    app = _app(tmp_path / "b", city, hel_butik("Coop Kungälv"))

    lista = app.inkopslista(START)

    assert lista.basta_butik.butik == "Coop Kungälv"
    city_total = next(t for t in lista.butiker if t.butik == "City Gross Ytterby")
    assert set(city_total.saknas) == set(planerat)
    assert city_total.kostnad < lista.basta_butik.kostnad  # billigare men ofullständig


def test_utan_butikspriser_listas_gram_med_platshallarpris(tmp_path):
    lista = Matplan(tmp_path / "m.db").inkopslista(START)

    assert lista.basta_butik is None
    assert lista.platshallar_kr > 0
    assert all(rad.gram > 0 and rad.alternativ == {} for rad in lista.rader)


def test_markdown_export_innehaller_plan_och_lista(tmp_path):
    app = _app(tmp_path, hel_butik("City Gross Ytterby"), hel_butik("Coop Kungälv", faktor=1.2))

    planfil, listfil = exportera(app.plan(START), app.inkopslista(START), tmp_path / "ut")

    plan = planfil.read_text(encoding="utf-8")
    assert "# Matplan" in plan and "Lunch och middag" in plan and "Frukost" in plan and "kcal / protein" in plan
    lista = listfil.read_text(encoding="utf-8")
    assert "# Inköpslista" in lista and "City Gross Ytterby" in lista and "- [ ] Märke " in lista and " st (" in lista


def test_cli_lista_och_export(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MATPLAN_DB", str(tmp_path / "cli.db"))

    assert main(["lista"]) == 0
    assert main(["export", str(tmp_path / "ut")]) == 0

    ut = capsys.readouterr().out
    assert "Inköpslista" in ut and "Planerad matkostnad" in ut
    assert (tmp_path / "ut" / "plan.md").exists() and (tmp_path / "ut" / "inkopslista.md").exists()
