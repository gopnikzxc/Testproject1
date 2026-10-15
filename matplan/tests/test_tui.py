"""Röktest för terminalgränssnittet (#15) med Textuals pilot."""

import asyncio
from datetime import date

from conftest import hel_butik

from matplan.core import Matplan
from matplan.tui import MatplanApp


def _karna(tmp_path):
    karna = Matplan(tmp_path / "m.db", butiker=(hel_butik("City Gross Ytterby", erbjudande=("Kycklingfilé",)),))
    karna.satt_installning("veckobudget", 5000)
    karna.satt_installning("manadsbudget", 20000)
    return karna


def _kor(tui, scenario):
    async def kor():
        async with tui.run_test(size=(180, 50)) as pilot:
            await scenario(pilot)

    asyncio.run(kor())


def test_alla_flikar_har_data_och_byte_uppdaterar_totalerna(tmp_path):
    karna = _karna(tmp_path)
    karna.refresh()
    tui = MatplanApp(karna, exportmapp=tmp_path / "ut")

    async def scenario(pilot):
        for id in ("plantabell", "listtabell", "pristabell", "installningstabell", "bunkringstabell"):
            assert tui.query_one(f"#{id}").row_count > 0, id
        fore_summa, fore_val = tui.summa_text, karna.byten()

        await pilot.press("b")  # första raden: block 1, protein
        await pilot.pause()

        assert karna.byten() != fore_val
        assert tui.summa_text != fore_summa

    _kor(tui, scenario)


def test_kopt_lagat_och_export_med_en_tangent(tmp_path):
    karna = _karna(tmp_path)
    tui = MatplanApp(karna, exportmapp=tmp_path / "ut")

    async def scenario(pilot):
        await pilot.press("k")
        await pilot.pause()
        assert karna.lager()
        assert tui.query_one("#lagertabell").row_count == len(karna.lager())
        fore = dict(karna.lager())

        await pilot.press("l")
        await pilot.pause()
        assert karna.lager() != fore

        await pilot.press("e")
        await pilot.pause()
        assert (tmp_path / "ut" / "plan.md").exists() and (tmp_path / "ut" / "inkopslista.md").exists()

    _kor(tui, scenario)


def test_installning_kan_andras_i_granssnittet(tmp_path):
    karna = _karna(tmp_path)
    tui = MatplanApp(karna)

    async def scenario(pilot):
        tui.query_one("#flikar").active = "installningar"
        await pilot.pause()
        inmatning = tui.query_one("#installningsinmatning")
        inmatning.focus()
        inmatning.value = "plandagar 3"
        await pilot.press("enter")
        await pilot.pause()

        assert karna.installningar()["plandagar"] == 3
        assert len(karna.plan(date.today()).dagar) == 3

    _kor(tui, scenario)


def test_butik_valjs_i_butikslistan(tmp_path):
    from test_butiksval import FalsktRegister

    karna = Matplan(tmp_path / "m.db", butiker=(hel_butik("City Gross Ytterby"),), butiksregister=(FalsktRegister(),))
    tui = MatplanApp(karna, exportmapp=tmp_path / "ut")

    async def scenario(pilot):
        tui.query_one("#flikar").active = "butik"
        await pilot.pause()
        await tui.workers.wait_for_complete()
        await pilot.pause()
        tabell = tui.query_one("#butikstabell")
        assert tabell.row_count == 7

        inmatning = tui.query_one("#butiksinmatning")
        inmatning.focus()
        await pilot.press(*"50463", "enter")  # Borås postnummer: Borås hamnar först
        await tui.workers.wait_for_complete()
        await pilot.pause()
        assert tabell.coordinate_to_cell_key((0, 0)).row_key.value == "City Gross Borås"

        tabell.focus()
        tabell.move_cursor(row=0)
        await pilot.press("enter")
        await tui.workers.wait_for_complete()
        await pilot.pause()

        assert karna.vald_butik().namn == "City Gross Borås"
        assert "Butik: City Gross Borås" in tui.summa_text

    _kor(tui, scenario)


def test_hamta_priser_i_bakgrunden(tmp_path):
    karna = _karna(tmp_path)
    tui = MatplanApp(karna, exportmapp=tmp_path / "ut")

    async def scenario(pilot):
        await pilot.press("r")
        await tui.workers.wait_for_complete()
        await pilot.pause()
        assert tui.query_one("#pristabell").row_count > 0
        assert all(p.butik == "City Gross Ytterby" for p in karna.produkter("Kycklingfilé"))

    _kor(tui, scenario)


def _upptack_karna(tmp_path):
    from conftest import SortimentButik, standardsortiment
    from test_forslag import _varor

    karna = Matplan(tmp_path / "u.db", butiker=(SortimentButik(standardsortiment() + _varor()),))
    karna.satt_installning("veckobudget", 5000)
    karna.satt_installning("manadsbudget", 20000)
    karna.refresh()
    return karna


def _rader(tabell):
    return [tabell.coordinate_to_cell_key((r, 0)).row_key.value for r in range(tabell.row_count)]


def test_upptack_soker_godkanner_och_avfardar(tmp_path):
    karna = _upptack_karna(tmp_path)
    tui = MatplanApp(karna, exportmapp=tmp_path / "ut")

    async def scenario(pilot):
        tui.query_one("#flikar").active = "upptack"
        await pilot.pause()
        tabell = tui.query_one("#upptacktabell")
        assert _rader(tabell)[0] == "tf-1"  # förslagen visas direkt
        priser_fore = tui.query_one("#pristabell").row_count

        # Sök i sortimentet.
        tui.query_one("#upptacksok").focus()
        await pilot.press(*"tonfisk", "enter")
        await pilot.pause()
        assert _rader(tabell) == ["tf-1"]

        # Godkänn den valda produkten med en tangent.
        tabell.focus()
        await pilot.press("g")
        await pilot.pause()
        assert "Tonfisk vatten" in {g.namn for g, _ in karna.grupper()}
        assert tui.query_one("#pristabell").row_count == priser_fore + 1  # planen och priserna uppdaterade

        # Tom sökning ger förslagen igen; avfärda den översta.
        tui.query_one("#upptacksok").focus()
        await pilot.press("enter")
        await pilot.pause()
        overst = _rader(tabell)[0]
        assert overst != "tf-1"
        tabell.focus()
        await pilot.press("x")
        await pilot.pause()
        assert overst not in _rader(tabell)
        assert overst not in [p.produkt_id for p in karna.forslag()]

    _kor(tui, scenario)


def test_godkann_utanfor_upptack_gor_inget(tmp_path):
    karna = _upptack_karna(tmp_path)
    tui = MatplanApp(karna, exportmapp=tmp_path / "ut")
    grupper_fore = len(karna.grupper())

    async def scenario(pilot):
        await pilot.press("g")
        await pilot.pause()
        assert len(karna.grupper()) == grupper_fore

    _kor(tui, scenario)
