"""Fixtures comuns. Os dados fictícios usados nos testes existem só aqui."""

import os
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
DADOS = Path(__file__).resolve().parent / "dados"


@pytest.fixture(autouse=True)
def config_isolada(tmp_path, monkeypatch):
    monkeypatch.setenv("BANCOQ_CONFIG", str(tmp_path / "config-local"))


@pytest.fixture
def banco(tmp_path):
    from bancoq.nucleo.banco import Banco

    return Banco.criar(tmp_path / "MeuBanco")


@pytest.fixture
def repo(banco, tmp_path):
    from bancoq.nucleo.midia import GerenciadorMidia
    from bancoq.nucleo.repositorio import Repositorio

    return Repositorio(banco, GerenciadorMidia(banco.pasta_midia, tmp_path / "temp"))


def png_minimo(cor: int = 0) -> bytes:
    """PNG 1x1 válido (dados de teste)."""
    import struct
    import zlib

    def bloco(tipo, dados):
        return struct.pack(">I", len(dados)) + tipo + dados + struct.pack(">I", zlib.crc32(tipo + dados) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    idat = zlib.compress(bytes([0, cor & 255, 0, 0]))
    return b"\x89PNG\r\n\x1a\n" + bloco(b"IHDR", ihdr) + bloco(b"IDAT", idat) + bloco(b"IEND", b"")
