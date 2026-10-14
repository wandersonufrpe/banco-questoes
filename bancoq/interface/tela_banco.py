"""Tela do banco: lista filtrável, prévia, editar/duplicar/excluir."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton, QSplitter, QTableView, QVBoxLayout, QWidget,
)

from ..contexto import Contexto
from ..nucleo.macros import extrair_macros
from ..nucleo.previa_html import html_questao
from .categorias import GerenciadorCategorias
from .filtros import ModeloQuestoes, PainelFiltros, configurar_tabela
from .previa import PreviaWeb, resolvedor_imagens
from .tags import GerenciadorTags


class TelaBanco(QWidget):
    pediu_editar = Signal(object)      # Questao
    pediu_duplicar = Signal(object)    # Questao
    questoes_excluidas = Signal(list)

    def __init__(self, ctx: Contexto, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self._precisa_recarregar = True
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(6, 6, 6, 6)

        self.filtros = PainelFiltros(ctx)
        caixa = QFrame()
        caixa.setFrameShape(QFrame.Shape.StyledPanel)
        lc = QVBoxLayout(caixa)
        lc.setContentsMargins(8, 6, 8, 6)
        lc.addWidget(self.filtros)
        raiz.addWidget(caixa)

        divisor = QSplitter(Qt.Orientation.Horizontal)
        raiz.addWidget(divisor, 1)

        esquerda = QWidget()
        le = QVBoxLayout(esquerda)
        le.setContentsMargins(0, 0, 0, 0)
        self.tabela = QTableView()
        self.modelo = ModeloQuestoes(self)
        self.proxy = configurar_tabela(self.tabela, self.modelo)
        le.addWidget(self.tabela, 1)

        botoes = QHBoxLayout()
        self.l_contagem = QLabel()
        botoes.addWidget(self.l_contagem)
        botoes.addStretch(1)
        self.b_editar = QPushButton("Editar")
        self.b_duplicar = QPushButton("Duplicar")
        self.b_excluir = QPushButton("Excluir…")
        self.b_categorias = QPushButton("Categorias…")
        self.b_tags = QPushButton("Tags…")
        self.b_duplicar.setToolTip("Abre uma cópia não salva na tela de cadastro")
        for b in (self.b_editar, self.b_duplicar, self.b_excluir, self.b_categorias, self.b_tags):
            botoes.addWidget(b)
        le.addLayout(botoes)
        divisor.addWidget(esquerda)

        self.previa = PreviaWeb()
        divisor.addWidget(self.previa)
        divisor.setStretchFactor(0, 3)
        divisor.setStretchFactor(1, 2)
        divisor.setSizes([800, 480])

        self.filtros.alterado.connect(self.recarregar)
        self.tabela.selectionModel().selectionChanged.connect(self._selecao_mudou)
        self.tabela.doubleClicked.connect(lambda *_: self._editar())
        self.b_editar.clicked.connect(self._editar)
        self.b_duplicar.clicked.connect(self._duplicar)
        self.b_excluir.clicked.connect(self._excluir)
        self.b_categorias.clicked.connect(self.gerenciar_categorias)
        self.b_tags.clicked.connect(self.gerenciar_tags)
        ctx.sinais.questoes_alteradas.connect(self._marcar_para_recarregar)
        ctx.sinais.categorias_alteradas.connect(self._marcar_para_recarregar)
        ctx.sinais.tags_alteradas.connect(self._marcar_para_recarregar)
        ctx.sinais.config_alterada.connect(
            lambda: self.previa.definir_macros(extrair_macros(ctx.config.preambulo))
        )
        self.previa.definir_macros(extrair_macros(ctx.config.preambulo))
        if ctx.somente_leitura:
            self.b_excluir.setEnabled(False)
        self._selecao_mudou()

    # -- carregamento ----------------------------------------------------------------------
    def _marcar_para_recarregar(self) -> None:
        self._precisa_recarregar = True
        if self.isVisible():
            self.recarregar()

    def showEvent(self, ev) -> None:  # noqa: N802
        super().showEvent(ev)
        if self._precisa_recarregar:
            self.recarregar()

    def recarregar(self) -> None:
        self._precisa_recarregar = False
        selecionadas = set(self.ids_selecionados())
        linhas = self.ctx.repo.buscar(self.filtros.filtro())
        self.modelo.definir(linhas, self.ctx.repo.caminhos_categorias())
        total = self.ctx.repo.contar_questoes()
        if len(linhas) == total:
            self.l_contagem.setText(f"{total} questão(ões) no banco")
        else:
            self.l_contagem.setText(f"{len(linhas)} de {total} questão(ões)")
        if selecionadas:
            sm = self.tabela.selectionModel()
            for linha in range(self.proxy.rowCount()):
                if self.modelo.id_na_linha(self.proxy.mapToSource(self.proxy.index(linha, 0)).row()) in selecionadas:
                    sm.select(self.proxy.index(linha, 0),
                              sm.SelectionFlag.Select | sm.SelectionFlag.Rows)
        self._selecao_mudou()

    def ids_selecionados(self) -> list[int]:
        linhas = sorted({self.proxy.mapToSource(i).row() for i in self.tabela.selectionModel().selectedRows()})
        return [self.modelo.id_na_linha(r) for r in linhas]

    def _selecao_mudou(self, *_a) -> None:
        ids = self.ids_selecionados()
        um = len(ids) == 1
        self.b_editar.setEnabled(um)
        self.b_duplicar.setEnabled(um)
        self.b_excluir.setEnabled(bool(ids) and not self.ctx.somente_leitura)
        if not ids:
            total = self.ctx.repo.contar_questoes()
            if total == 0:
                self.previa.mostrar_vazio("O banco ainda não tem questões. Cadastre a primeira na aba Cadastro.")
            else:
                self.previa.mostrar_vazio("Selecione uma questão para ver a prévia.")
            return
        q = self.ctx.repo.obter_questao(ids[0])
        if q is None:
            return
        caminho = self.ctx.repo.caminhos_categorias().get(q.categoria_id, "sem categoria")
        info = (f'<div class="info">Nº {q.id} · {caminho} · dificuldade {q.dificuldade}'
                f'{" · " + ", ".join(q.tags) if q.tags else ""}'
                f'{" · " + q.fonte if q.fonte else ""}{" · " + str(q.ano) if q.ano else ""}</div><hr class="sep">')
        if len(ids) > 1:
            info = f'<div class="info">{len(ids)} questões selecionadas; mostrando a primeira.</div>' + info
        self.previa.mostrar(info + html_questao(q, resolvedor_imagens(self.ctx.midia)))

    # -- ações --------------------------------------------------------------------------------
    def _editar(self) -> None:
        ids = self.ids_selecionados()
        if len(ids) == 1:
            q = self.ctx.repo.obter_questao(ids[0])
            if q is not None:
                self.pediu_editar.emit(q)

    def _duplicar(self) -> None:
        ids = self.ids_selecionados()
        if len(ids) == 1:
            q = self.ctx.repo.obter_questao(ids[0])
            if q is not None:
                self.pediu_duplicar.emit(q)

    def _excluir(self) -> None:
        ids = self.ids_selecionados()
        if not ids:
            return
        if len(ids) == 1:
            texto = f"Excluir a questão nº {ids[0]}?"
        else:
            texto = f"Excluir {len(ids)} questões ({', '.join(map(str, ids[:10]))}{'…' if len(ids) > 10 else ''})?"
        r = QMessageBox.question(
            self, "Excluir questões", texto + "\n\nEsta ação não pode ser desfeita (a não ser restaurando um backup).",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No,
        )
        if r != QMessageBox.StandardButton.Yes:
            return
        try:
            for qid in ids:
                self.ctx.repo.excluir_questao(qid)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Excluir", f"Erro ao excluir: {e}")
        self.questoes_excluidas.emit(ids)
        self.ctx.sinais.questoes_alteradas.emit()
        self.ctx.sinais.tags_alteradas.emit()

    def gerenciar_categorias(self) -> None:
        d = GerenciadorCategorias(self.ctx.repo, self)
        d.alterou.connect(self.ctx.sinais.categorias_alteradas)
        d.exec()

    def gerenciar_tags(self) -> None:
        d = GerenciadorTags(self.ctx.repo, self)
        d.alterou.connect(self.ctx.sinais.tags_alteradas)
        d.exec()
