import pytest

from matplan.http import HttpKlient


class Klocka:
    def __init__(self):
        self.nu = 1000.0
        self.sovningar = []

    def __call__(self):
        return self.nu

    def sov(self, sekunder):
        self.sovningar.append(sekunder)
        self.nu += sekunder


@pytest.fixture
def klocka():
    return Klocka()


def _klient(tmp_path, klocka, svar):
    anrop = []

    def transport(url, headers):
        anrop.append(url)
        return svar

    klient = HttpKlient(tmp_path / "cache", paus_s=2, cachetid_s=3600, transport=transport, sov=klocka.sov, klocka=klocka)
    return klient, anrop


def test_svar_cachas_inom_cachetiden(tmp_path, klocka):
    klient, anrop = _klient(tmp_path, klocka, b'{"a": 1}')

    assert klient.hamta_json("https://x.se/api", {"q": "keso"}) == {"a": 1}
    klocka.nu += 60
    assert klient.hamta_json("https://x.se/api", {"q": "keso"}) == {"a": 1}

    assert anrop == ["https://x.se/api?q=keso"]


def test_gammal_cache_hamtas_om(tmp_path, klocka):
    klient, anrop = _klient(tmp_path, klocka, b"{}")

    klient.hamta_json("https://x.se/api")
    klocka.nu += 3601
    klient.hamta_json("https://x.se/api")

    assert len(anrop) == 2


def test_pausar_mellan_anrop(tmp_path, klocka):
    klient, anrop = _klient(tmp_path, klocka, b"{}")

    klient.hamta_json("https://x.se/a")
    klient.hamta_json("https://x.se/b")

    assert klocka.sovningar == [2]


def test_ogiltigt_svar_cachas_inte(tmp_path, klocka):
    klient, anrop = _klient(tmp_path, klocka, b"<html>fel</html>")

    for _ in range(2):
        with pytest.raises(ValueError):
            klient.hamta_json("https://x.se/a")

    assert len(anrop) == 2
