"""HTTP-klient för butiksadaptrar: lokal cache och artiga pauser mellan anrop."""

import hashlib
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable

ANVANDARAGENT = "matplan/0.1 (personlig maltidsplanerare)"


def _urllib_transport(url: str, headers: dict[str, str]) -> bytes:
    forfragan = urllib.request.Request(url, headers={"User-Agent": ANVANDARAGENT, **headers})
    with urllib.request.urlopen(forfragan, timeout=30) as svar:
        return svar.read()


class HttpKlient:
    def __init__(
        self,
        cachekatalog: Path,
        paus_s: float = 1.5,
        cachetid_s: float = 6 * 3600,
        transport: Callable[[str, dict[str, str]], bytes] = _urllib_transport,
        sov: Callable[[float], None] = time.sleep,
        klocka: Callable[[], float] = time.time,
    ):
        self._cache = Path(cachekatalog)
        self._cache.mkdir(parents=True, exist_ok=True)
        self._paus_s = paus_s
        self._cachetid_s = cachetid_s
        self._transport = transport
        self._sov = sov
        self._klocka = klocka
        self._senaste_anrop: float | None = None

    def hamta_json(self, url: str, params: dict | None = None, headers: dict[str, str] | None = None):
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        fil = self._cache / f"{hashlib.sha256(url.encode()).hexdigest()}.json"
        if fil.exists():
            sparad = json.loads(fil.read_text())
            if self._klocka() - sparad["tid"] < self._cachetid_s:
                return sparad["data"]

        if self._senaste_anrop is not None:
            vanta = self._paus_s - (self._klocka() - self._senaste_anrop)
            if vanta > 0:
                self._sov(vanta)
        self._senaste_anrop = self._klocka()
        data = json.loads(self._transport(url, headers or {}))
        fil.write_text(json.dumps({"tid": self._klocka(), "data": data}))
        return data
