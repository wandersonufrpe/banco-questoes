"""Figuras TikZ na prévia rápida: compiladas em segundo plano, uma por vez, com cache.

A prévia pede a figura ao resolvedor; se o PNG ainda não existe, a compilação entra
na fila e a prévia mostra "desenhando…". Quando fica pronta, ``figura_pronta`` avisa
as telas para redesenharem a prévia.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from ..caminhos import pasta_config_local
from ..nucleo.latex_html import ResolverTikz
from ..nucleo.tikz import chave_figura, compilar_figura, preambulo_figuras
from . import tarefas
from .previa import url_arquivo


class GerenciadorFiguras(QObject):
    figura_pronta = Signal()

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.pasta = pasta_config_local() / "cache-tikz"
        self._erros: dict[str, str] = {}
        self._fila: list[tuple[str, str, str]] = []      # (chave, código, preâmbulo)
        self._em_andamento: str | None = None
        self._preambulo: str | None = None
        ctx.sinais.config_alterada.connect(self._config_mudou)

    def _config_mudou(self) -> None:
        self._preambulo = None
        self._erros.clear()

    def preambulo(self) -> str:
        """Linhas de TikZ do modelo + preâmbulo e macros do banco."""
        if self._preambulo is None:
            try:
                modelo = self.ctx.texto_modelo()
            except OSError:
                modelo = ""
            self._preambulo = preambulo_figuras(modelo, self.ctx.config.preambulo)
        return self._preambulo

    def resolvedor(self, extra: list[str] | None = None) -> ResolverTikz:
        """Função para ``html_questao``; ``extra``: linhas de preâmbulo da questão."""
        pre = self.preambulo()
        if extra:
            pre = (pre + "\n" + "\n".join(extra)).strip()

        def resolver(codigo: str) -> tuple[str, str]:
            chave = chave_figura(codigo, pre)
            png = self.pasta / f"tikz-{chave}.png"
            if png.exists():
                return "ok", url_arquivo(png)
            if chave in self._erros:
                return "erro", self._erros[chave]
            if self.ctx.tex() is None:
                return "erro", "TeX não encontrado: instale-o para ver as figuras TikZ"
            self._enfileirar(chave, codigo, pre)
            return "pendente", ""

        return resolver

    def _enfileirar(self, chave: str, codigo: str, pre: str) -> None:
        if chave == self._em_andamento or any(c == chave for c, _, _ in self._fila):
            return
        self._fila.append((chave, codigo, pre))
        self._proxima()

    def _proxima(self) -> None:
        if self._em_andamento is not None or not self._fila:
            return
        info = self.ctx.tex()
        if info is None:
            self._fila.clear()
            return
        chave, codigo, pre = self._fila.pop(0)
        self._em_andamento = chave
        limite = max(20, self.ctx.local.tempo_limite_previa)

        def compilar():
            return compilar_figura(codigo, pre, info, self.pasta, limite)

        def concluiu(res) -> None:
            if not res.ok:
                self._erros[chave] = res.erro or "falha na compilação"
            self._terminar()

        def falhou(rastro: str) -> None:
            self._erros[chave] = rastro.strip().splitlines()[-1][:200]
            self._terminar()

        tarefas.executar(compilar, concluiu, falhou)

    def _terminar(self) -> None:
        self._em_andamento = None
        self.figura_pronta.emit()
        self._proxima()
