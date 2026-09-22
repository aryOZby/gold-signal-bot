from __future__ import annotations

from email.message import EmailMessage
from pathlib import Path

from src.emailer import EmailSender, EmailSettings, parse_recipients


class _FakeSMTP:
    sent: list[EmailMessage] = []
    logins: list[tuple[str, str]] = []

    def __init__(self, host, port, timeout=None, context=None):
        self.host = host
        self.port = port

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def ehlo(self):
        return None

    def starttls(self, context=None):
        return None

    def login(self, user, password):
        _FakeSMTP.logins.append((user, password))

    def send_message(self, message):
        _FakeSMTP.sent.append(message)


def _settings(**kw) -> EmailSettings:
    base = dict(
        host="smtp.example.com",
        port=587,
        user="bot@example.com",
        password="secret",
        sender="",
        recipients=("me@example.com",),
    )
    base.update(kw)
    return EmailSettings(**base)


def test_parse_recipients_handles_separators():
    assert parse_recipients("a@x.com, b@x.com;c@x.com") == ("a@x.com", "b@x.com", "c@x.com")
    assert parse_recipients("") == ()
    assert parse_recipients(None) == ()


def test_disabled_without_host_or_recipient():
    assert not EmailSender(_settings(host="")).enabled
    assert not EmailSender(_settings(recipients=())).enabled
    assert EmailSender(_settings()).enabled


def test_send_attaches_report(tmp_path: Path, monkeypatch):
    _FakeSMTP.sent.clear()
    _FakeSMTP.logins.clear()
    monkeypatch.setattr("smtplib.SMTP", _FakeSMTP)

    report = tmp_path / "2026-09.xlsx"
    report.write_bytes(b"fake workbook")

    sender = EmailSender(_settings())
    assert sender.send("דוח חודשי", "גוף ההודעה", [report, tmp_path / "missing.xlsx"])

    assert _FakeSMTP.logins == [("bot@example.com", "secret")]
    message = _FakeSMTP.sent[0]
    assert message["To"] == "me@example.com"
    assert message["From"] == "bot@example.com"
    names = [p.get_filename() for p in message.iter_attachments()]
    assert names == ["2026-09.xlsx"]


def test_send_returns_false_on_failure(monkeypatch):
    class _Boom(_FakeSMTP):
        def send_message(self, message):
            raise OSError("smtp down")

    monkeypatch.setattr("smtplib.SMTP", _Boom)
    assert EmailSender(_settings()).send("x", "y") is False


def test_disabled_sender_is_a_no_op(monkeypatch):
    def _explode(*a, **kw):
        raise AssertionError("must not connect when disabled")

    monkeypatch.setattr("smtplib.SMTP", _explode)
    assert EmailSender(_settings(host="")).send("x", "y") is False
