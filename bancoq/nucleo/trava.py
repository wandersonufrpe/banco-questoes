"""Arquivo de trava: indica em qual computador o banco está aberto.

O banco fica numa pasta sincronizada e é usado em mais de um computador (nunca
ao mesmo tempo). Ao abrir, o app grava ``banco.trava`` com o nome do
computador e o horário. Se encontrar a trava de outro computador, avisa.
"""

from __future__ import annotations

import getpass
import json
import os
import socket
import sys
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

ARQUIVO_TRAVA = "banco.trava"


@dataclass
class InfoTrava:
    computador: str
    usuario: str
    horario: str
    pid: int
    sessao: str

    def horario_legivel(self) -> str:
        try:
            return datetime.fromisoformat(self.horario).strftime("%d/%m/%Y às %H:%M")
        except ValueError:
            return self.horario


def nome_computador() -> str:
    return socket.gethostname() or os.environ.get("COMPUTERNAME", "") or "desconhecido"


def _usuario() -> str:
    try:
        return getpass.getuser()
    except Exception:  # noqa: BLE001
        return ""


def ler_trava(pasta: Path) -> InfoTrava | None:
    try:
        dados = json.loads((Path(pasta) / ARQUIVO_TRAVA).read_text(encoding="utf-8"))
        return InfoTrava(
            computador=str(dados.get("computador", "?")), usuario=str(dados.get("usuario", "")),
            horario=str(dados.get("horario", "")), pid=int(dados.get("pid", 0)), sessao=str(dados.get("sessao", "")),
        )
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        # trava ilegível (ex.: conflito de sincronização): trata como de origem desconhecida
        return InfoTrava("desconhecido", "", "", 0, "")


def criar_trava(pasta: Path) -> InfoTrava:
    info = InfoTrava(nome_computador(), _usuario(), datetime.now().isoformat(timespec="seconds"),
                     os.getpid(), uuid.uuid4().hex)
    destino = Path(pasta) / ARQUIVO_TRAVA
    tmp = destino.with_suffix(".trava.tmp")
    tmp.write_text(json.dumps(asdict(info), ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(destino)
    return info


def remover_trava(pasta: Path, sessao: str) -> bool:
    """Remove a trava só se ela for desta sessão (não apaga a de outro computador)."""
    atual = ler_trava(pasta)
    if atual is None or atual.sessao != sessao:
        return False
    try:
        (Path(pasta) / ARQUIVO_TRAVA).unlink()
        return True
    except OSError:
        return False


def e_deste_computador(info: InfoTrava) -> bool:
    return info.computador.casefold() == nome_computador().casefold()


def processo_vivo(pid: int) -> bool:
    if pid <= 0 or pid == os.getpid():
        return False
    if sys.platform.startswith("win"):
        try:
            import ctypes

            processo = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
            if not processo:
                return False
            codigo = ctypes.c_ulong()
            ctypes.windll.kernel32.GetExitCodeProcess(processo, ctypes.byref(codigo))
            ctypes.windll.kernel32.CloseHandle(processo)
            return codigo.value == 259  # STILL_ACTIVE
        except Exception:  # noqa: BLE001
            return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


def situacao(pasta: Path) -> tuple[str, InfoTrava | None]:
    """'livre', 'esquecida' (deste computador, app fechado), 'aberta_aqui' ou 'outro_computador'."""
    info = ler_trava(pasta)
    if info is None:
        return "livre", None
    if e_deste_computador(info):
        return ("aberta_aqui" if processo_vivo(info.pid) else "esquecida"), info
    return "outro_computador", info
