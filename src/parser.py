from __future__ import annotations

import logging
import re
from typing import Optional

from .models import ParsedSignal, Side

_LOG = logging.getLogger(__name__)

_DASHES = str.maketrans(
    {
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2212": "-",
        "\xa0": " ",
        "\u202f": " ",
        "\u2007": " ",
    }
)

# שתי התבניות הנתמכות:
#   #XAUUSD SELL 4315-4318   /  TP 4312      /  SL 4327
#   XAUUSD SELL PLAN @4365_4368  /  tp @4349  /  SL@4381
_HEADER = re.compile(
    r"^#?\s*(?P<symbol>[A-Za-z0-9._]+)\s+"
    r"(?P<side>BUY|SELL)"
    r"(?:\s+PLAN)?\s+"
    r"@?(?P<low>\d+(?:\.\d+)?)\s*[-_]\s*@?(?P<high>\d+(?:\.\d+)?)\s*$",
    re.IGNORECASE,
)
_TP = re.compile(
    r"^T(?:P|ake\s*Profit)\s*[:@]?\s*@?(?P<price>\d+(?:\.\d+)?)\s*$", re.IGNORECASE
)
_SL = re.compile(
    r"^S(?:L|top(?:\s*Loss)?)\s*[:@]?\s*@?(?P<price>\d+(?:\.\d+)?)\s*$", re.IGNORECASE
)


def _normalize(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.translate(_DASHES)
    lines = [" ".join(line.strip().split()) for line in text.split("\n")]
    return "\n".join(line for line in lines if line)


def parse_signal(text: str) -> Optional[ParsedSignal]:
    """Return a ParsedSignal if the message matches the XAUUSD BUY/SELL template."""
    if not text or not text.strip():
        return None

    normalized = _normalize(text)
    lines = normalized.split("\n")
    header = None
    header_index = None
    for i, line in enumerate(lines):
        match = _HEADER.match(line)
        if match:
            header = match
            header_index = i
            break
    if header is None:
        return None

    tps: list[float] = []
    sl: Optional[float] = None
    for line in lines[header_index + 1 :]:
        tp_match = _TP.match(line)
        if tp_match:
            tps.append(float(tp_match.group("price")))
            continue
        sl_match = _SL.match(line)
        if sl_match:
            sl = float(sl_match.group("price"))

    if not tps or sl is None:
        _LOG.info("Header matched but missing TP/SL: tps=%s sl=%s", tps, sl)
        return None

    low = float(header.group("low"))
    high = float(header.group("high"))
    return ParsedSignal(
        symbol=header.group("symbol").upper(),
        side=Side.BUY if header.group("side").upper() == "BUY" else Side.SELL,
        zone_low=min(low, high),
        zone_high=max(low, high),
        tps=tuple(tps),
        sl=sl,
        raw_text=text.strip(),
    )
