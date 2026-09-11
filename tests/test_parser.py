from src.parser import parse_signal
from src.models import Side

SELL = """#XAUUSD SELL 4315-4318

TP 4312
TP 4309
TP 4305
TP 4300
TP 4295
TP 4285

SL 4327
"""

BUY = """#XAUUSD BUY 4349-4346

TP 4352
TP 4355
TP 4359
TP 4364
TP 4369
TP 4379

SL 4337
"""


def test_parse_sell_template():
    sig = parse_signal(SELL)
    assert sig is not None
    assert sig.symbol == "XAUUSD"
    assert sig.side is Side.SELL
    assert sig.zone_low == 4315
    assert sig.zone_high == 4318
    assert sig.tps == (4312, 4309, 4305, 4300, 4295, 4285)
    assert sig.sl == 4327
    assert sig.tp_count == 6


def test_parse_buy_template():
    sig = parse_signal(BUY)
    assert sig is not None
    assert sig.side is Side.BUY
    assert sig.zone_low == 4346
    assert sig.zone_high == 4349
    assert sig.tps[0] == 4352
    assert sig.sl == 4337


def test_parse_messy_whitespace_and_dashes():
    text = "#XAUUSD  buy  4349–4346\n\nTP: 4352\nTP 4355\nSL:4337"
    sig = parse_signal(text)
    assert sig is not None
    assert sig.side is Side.BUY
    assert sig.tps == (4352, 4355)
    assert sig.sl == 4337


def test_ignore_non_signal():
    assert parse_signal("good morning") is None
    assert parse_signal("#XAUUSD SELL 4315-4318\nTP 4312") is None  # no SL
