from __future__ import annotations

from .base import Broker
from .dry_run import DryRunBroker
from .file_bridge import FileBridgeBroker
from .mt5_native import Mt5NativeBroker
from ..config import AppConfig


def make_broker(cfg: AppConfig) -> Broker:
    kind = (cfg.broker_type or "dry_run").lower()
    if cfg.dry_run or kind == "dry_run":
        return DryRunBroker()
    if kind == "file_bridge":
        return FileBridgeBroker(cfg.common_files_dir)
    if kind in {"mt5_native", "mt5", "native"}:
        return Mt5NativeBroker(
            login=cfg.mt5_login,
            password=cfg.mt5_password,
            server=cfg.mt5_server,
            path=cfg.mt5_terminal_path,
        )
    raise ValueError(f"Unknown broker.type: {cfg.broker_type}")
