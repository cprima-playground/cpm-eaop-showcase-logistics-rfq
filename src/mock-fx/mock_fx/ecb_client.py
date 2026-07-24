"""Live ECB reference-rate feed -- eurofxref-hist-90d.xml, the European
Central Bank's public, unauthenticated daily-rate history (no API key, no
SSO). Used to anchor mock-fx's baseline in real market data instead of a
fabricated number (matches the project's real-reference-data ethos: UN/LOCODE,
ISO 4217, Incoterms, Natural Earth).

Opt-out, not opt-in -- see store.py's FxStore(live_anchor=...): the running
showcase fetches this by default; FX_LIVE_ANCHOR=0 disables it.

Three-tier fallback (all wired in store.py, not here):
  1. live HTTP fetch (fetch_history)
  2. a manually-downloaded copy of the same feed (load_history_from_file --
     offline demo: open the ECB_HIST_URL in a browser, Ctrl+S, point
     FX_ECB_HIST_FILE at the saved file)
  3. committed fixture JSON + synthetic generator (store.py, unchanged)
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

ECB_HIST_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist-90d.xml"
_NS = {"ns": "http://www.ecb.int/vocabulary/2002-08-01/eurofxref"}
TIMEOUT_SECONDS = 5


class EcbUnavailableError(RuntimeError):
    """The ECB feed was unreachable, empty, or not parsable as the expected
    ECB Cube XML -- callers fall back to the next tier (a local cached copy,
    then committed fixtures). Never returns partial/corrupt data instead."""


def fetch_history(currencies: tuple[str, ...]) -> list[tuple[str, dict[str, float]]]:
    """Every day in the ECB 90-day feed, oldest first, as
    (date, {currency: EUR-per-unit rate}) restricted to `currencies`.
    Raises EcbUnavailableError on any network failure."""
    try:
        with urlopen(ECB_HIST_URL, timeout=TIMEOUT_SECONDS) as resp:
            raw = resp.read()
    except (URLError, OSError, TimeoutError) as exc:
        raise EcbUnavailableError(f"could not reach ECB feed {ECB_HIST_URL!r}: {exc}") from exc
    return parse_history(raw, currencies)


def load_history_from_file(path: str | Path, currencies: tuple[str, ...]) -> list[tuple[str, dict[str, float]]]:
    """Same as fetch_history, but from a manually-downloaded copy of the ECB
    feed -- the offline-demo fallback (browser Ctrl+S of ECB_HIST_URL)."""
    p = Path(path)
    if not p.exists():
        raise EcbUnavailableError(f"ECB cache file not found: {p}")
    return parse_history(p.read_bytes(), currencies)


def parse_history(raw: bytes, currencies: tuple[str, ...]) -> list[tuple[str, dict[str, float]]]:
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise EcbUnavailableError(f"could not parse ECB feed: {exc}") from exc

    outer = root.find("ns:Cube", _NS)
    if outer is None:
        raise EcbUnavailableError("ECB feed is missing the expected <Cube> structure")

    days: list[tuple[str, dict[str, float]]] = []
    for day in outer.findall("ns:Cube", _NS):
        date = day.get("time")
        if date is None:
            continue
        rates = {c.get("currency"): float(c.get("rate")) for c in day.findall("ns:Cube", _NS)}
        wanted = {cur: rates[cur] for cur in currencies if cur in rates}
        if wanted:
            days.append((date, wanted))

    if not days:
        raise EcbUnavailableError(f"ECB feed had no data for any of {currencies}")

    days.sort(key=lambda entry: entry[0])  # oldest first
    return days
