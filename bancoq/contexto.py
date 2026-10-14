"""Tudo o que as telas precisam saber sobre o banco aberto."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from .caminhos import pasta_temporaria
from .config_local import ConfigLocal
from .nucleo.banco import Banco
from .nucleo.config_banco import ConfigBanco
from .nucleo.midia import GerenciadorMidia
from .nucleo.repositorio import Repositorio


class Sinais(QObject):
    """Avisos entre as telas quando algo muda no banco."""

    questoes_alteradas = Signal()
    categorias_alteradas = Signal()
    tags_alteradas = Signal()
    config_alterada = Signal()


class Contexto:
    def __init__(self, banco: Banco, local: ConfigLocal):
        self.banco = banco
        self.local = local
        self.midia = GerenciadorMidia(banco.pasta_midia, pasta_temporaria())
        self.repo = Repositorio(banco, self.midia)
        self.config = ConfigBanco.carregar(banco.pasta)
        self.sinais = Sinais()

    @property
    def somente_leitura(self) -> bool:
        return self.banco.somente_leitura

    def salvar_config(self) -> None:
        self.config.salvar(self.banco.pasta)
        self.sinais.config_alterada.emit()

    def salvar_local(self) -> None:
        try:
            self.local.salvar()
        except OSError:
            pass
