"""HTTP-klient för butiksadaptrar: lokal cache, artiga pauser mellan anrop och
cookies (för butiker som kräver en session, t.ex. Willys butiksval)."""

import hashlib
import http.cookiejar
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable

ANVANDARAGENT = "matplan/0.1 (personlig maltidsplanerare)"

# transport(url, headers, metod) -> svarets bytes
Transport = Callable[..., bytes]


def _urllib_transport() -> Transport:
    oppnare = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def transport(url: str, headers: dict[str, str], metod: str = "GET") -> bytes:
        forfragan = urllib.request.Request(url, headers={"User-Agent": ANVANDARAGENT, **headers}, method=metod)
        with oppnare.open(forfragan, timeout=30) as svar:
            return svar.read()

    return transport


class HttpKlient:
    def __init__(
        self,
        cachekatalog: Path,
        paus_s: float = 1.5,
        cachetid_s: float = 6 * 3600,
        transport: Transport | None = None,
        sov: Callable[[float], None] = time.sleep,
        klocka: Callable[[], float] = time.time,
    ):
        self._cache = Path(cachekatalog)
        self._cache.mkdir(parents=True, exist_ok=True)
        self._paus_s = paus_s
        self._cachetid_s = cachetid_s
        self._transport = transport or _urllib_transport()
        self._sov = sov
        self._klocka = klocka
        self._senaste_anrop: float | None = None

    def hamta_json(
        self,
        url: str,
        params: dict | None = None,
        headers: dict[str, str] | None = None,
        cachenyckel: str = "",
    ):
        """GET med cache. `cachenyckel` skiljer svar som beror på mer än url:en,
        t.ex. vilken butik som är vald i sessionen."""
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        fil = self._cache / f"{hashlib.sha256(f'{cachenyckel}{url}'.encode()).hexdigest()}.json"
        if fil.exists():
            sparad = json.loads(fil.read_text())
            if self._klocka() - sparad["tid"] < self._cachetid_s:
                return sparad["data"]

        data = json.loads(self._anropa(url, headers or {}))
        fil.write_text(json.dumps({"tid": self._klocka(), "data": data}))
        return data

    def skicka(self, url: str, headers: dict[str, str] | None = None, metod: str = "POST") -> bytes:
        """Anrop utan cache, t.ex. för att hämta en CSRF-token eller välja butik."""
        return self._anropa(url, headers or {}, metod)

    def _anropa(self, url: str, headers: dict[str, str], metod: str = "GET") -> bytes:
        if self._senaste_anrop is not None:
            vanta = self._paus_s - (self._klocka() - self._senaste_anrop)
            if vanta > 0:
                self._sov(vanta)
        self._senaste_anrop = self._klocka()
        if metod == "GET":
            return self._transport(url, headers)
        return self._transport(url, headers, metod)
