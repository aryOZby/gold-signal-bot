"""שליחת הדוח החודשי במייל, עם קבצי האקסל כצרופות."""
from __future__ import annotations

import logging
import mimetypes
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Iterable, Optional

_LOG = logging.getLogger(__name__)


@dataclass
class EmailSettings:
    host: str = ""
    port: int = 587
    user: str = ""
    password: str = ""
    sender: str = ""
    recipients: tuple[str, ...] = ()

    @property
    def enabled(self) -> bool:
        return bool(self.host and self.recipients)

    @property
    def from_address(self) -> str:
        return self.sender or self.user


def parse_recipients(raw: Optional[str]) -> tuple[str, ...]:
    if not raw:
        return ()
    parts = [p.strip() for p in raw.replace(";", ",").split(",")]
    return tuple(p for p in parts if p)


class EmailSender:
    def __init__(self, settings: EmailSettings, timeout: float = 30.0):
        self.settings = settings
        self.timeout = timeout

    @property
    def enabled(self) -> bool:
        return self.settings.enabled

    def send(self, subject: str, body: str, attachments: Iterable[Path] = ()) -> bool:
        cfg = self.settings
        if not cfg.enabled:
            _LOG.debug("email disabled, skipping %r", subject)
            return False

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = cfg.from_address
        message["To"] = ", ".join(cfg.recipients)
        message.set_content(body)

        for path in attachments:
            path = Path(path)
            if not path.exists():
                _LOG.warning("attachment missing, skipped: %s", path)
                continue
            guessed, _ = mimetypes.guess_type(path.name)
            maintype, _, subtype = (guessed or "application/octet-stream").partition("/")
            message.add_attachment(
                path.read_bytes(),
                maintype=maintype,
                subtype=subtype or "octet-stream",
                filename=path.name,
            )

        try:
            # 465 הוא SSL ישיר, כל השאר STARTTLS (למשל 587 של Gmail).
            if cfg.port == 465:
                context = ssl.create_default_context()
                with smtplib.SMTP_SSL(cfg.host, cfg.port, timeout=self.timeout, context=context) as smtp:
                    self._login_and_send(smtp, message)
            else:
                with smtplib.SMTP(cfg.host, cfg.port, timeout=self.timeout) as smtp:
                    smtp.ehlo()
                    smtp.starttls(context=ssl.create_default_context())
                    smtp.ehlo()
                    self._login_and_send(smtp, message)
        except Exception:
            _LOG.exception("failed to send email %r", subject)
            return False
        _LOG.info("Email sent: %r to %s", subject, ", ".join(cfg.recipients))
        return True

    def _login_and_send(self, smtp: smtplib.SMTP, message: EmailMessage) -> None:
        cfg = self.settings
        if cfg.user and cfg.password:
            smtp.login(cfg.user, cfg.password)
        smtp.send_message(message)
