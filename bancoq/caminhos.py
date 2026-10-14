"""Localização de recursos empacotados e da pasta de configuração local."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


def empacotado() -> bool:
    """Indica se o app está rodando a partir do executável do PyInstaller."""
    return bool(getattr(sys, "frozen", False))


def pasta_recursos() -> Path:
    if empacotado():
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        return base / "bancoq" / "recursos"
    return Path(__file__).resolve().parent / "recursos"


def recurso(*partes: str) -> Path:
    return pasta_recursos().joinpath(*partes)


def pasta_config_local() -> Path:
    """Pasta de configurações da máquina (fora da pasta sincronizada).

    A variável de ambiente BANCOQ_CONFIG permite trocar a pasta (usada nos testes).
    """
    forcada = os.environ.get("BANCOQ_CONFIG")
    if forcada:
        return Path(forcada)
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config"))
    return base / "BancoQuestoes"


_pasta_temp: Path | None = None


def pasta_temporaria() -> Path:
    """Pasta temporária da sessão (imagens ainda não salvas, compilações, cache)."""
    global _pasta_temp
    if _pasta_temp is None or not _pasta_temp.exists():
        _pasta_temp = Path(tempfile.mkdtemp(prefix="bancoq-"))
    return _pasta_temp


def limpar_pasta_temporaria() -> None:
    import shutil

    global _pasta_temp
    if _pasta_temp is not None:
        shutil.rmtree(_pasta_temp, ignore_errors=True)
        _pasta_temp = None
