"""Janela principal: abas de cadastro, banco, montagem e importação."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QLabel, QMainWindow, QMessageBox, QTabWidget

from .. import NOME_APP, __version__
from ..contexto import Contexto
from .cadastro import TelaCadastro


class JanelaPrincipal(QMainWindow):
    def __init__(self, ctx: Contexto, aplicativo):
        super().__init__()
        self.ctx = ctx
        self.aplicativo = aplicativo
        self._fechando_para_trocar = False
        titulo = f"{NOME_APP} — {ctx.banco.nome}"
        if ctx.somente_leitura:
            titulo += " [somente leitura]"
        self.setWindowTitle(titulo)
        self.resize(1360, 860)

        self.abas = QTabWidget()
        self.abas.setDocumentMode(True)
        self.setCentralWidget(self.abas)

        self.cadastro = TelaCadastro(ctx)
        self.abas.addTab(self.cadastro, "Cadastro")
        self.telas_extras: list = []
        self._criar_telas_extras()
        self._criar_menus()

        self.l_banco = QLabel(str(ctx.banco.pasta))
        self.statusBar().addPermanentWidget(self.l_banco)
        if ctx.somente_leitura:
            aviso = QLabel("  SOMENTE LEITURA  ")
            aviso.setStyleSheet("background:#c25e00;color:white;font-weight:bold;border-radius:3px;")
            self.statusBar().addPermanentWidget(aviso)
        self._restaurar_geometria()

    # -- telas adicionadas nas etapas seguintes ------------------------------------------
    def _criar_telas_extras(self) -> None:
        from .tela_banco import TelaBanco

        self.banco = TelaBanco(self.ctx)
        self.abas.addTab(self.banco, "Banco")
        self.banco.pediu_editar.connect(lambda q: self._abrir_no_cadastro(q, como_nova=False))
        self.banco.pediu_duplicar.connect(lambda q: self._abrir_no_cadastro(q, como_nova=True))
        self.banco.questoes_excluidas.connect(self.cadastro.questoes_excluidas)

    def _abrir_no_cadastro(self, q, como_nova: bool) -> None:
        if not como_nova and self.cadastro.questao_id == q.id and not self.cadastro.modificado():
            self.abas.setCurrentWidget(self.cadastro)
            return
        if not self.cadastro.pode_descartar():
            return
        self.cadastro.carregar_questao(q, como_nova=como_nova)
        self.abas.setCurrentWidget(self.cadastro)

    # -- menus ------------------------------------------------------------------------------
    def _criar_menus(self) -> None:
        m = self.menuBar().addMenu("&Arquivo")
        self._acao(m, "Criar novo banco…", self.aplicativo.criar_outro_banco)
        self._acao(m, "Abrir outro banco…", self.aplicativo.abrir_outro_banco)
        self.menu_arquivo = m
        m.addSeparator()
        self._acao(m, "Sair", self.close, QKeySequence.StandardKey.Quit)

        self.menu_banco = self.menuBar().addMenu("&Banco")
        self._acao(self.menu_banco, "Categorias…", self.banco.gerenciar_categorias)
        self._acao(self.menu_banco, "Tags…", self.banco.gerenciar_tags)
        self.menu_ajuda = self.menuBar().addMenu("A&juda")
        self._acao(self.menu_ajuda, "Sobre…", self._sobre)

    def _acao(self, menu, texto, func, atalho=None) -> QAction:
        a = QAction(texto, self)
        if atalho is not None:
            a.setShortcut(atalho)
        a.triggered.connect(func)
        menu.addAction(a)
        return a

    def _sobre(self) -> None:
        QMessageBox.about(
            self, f"Sobre o {NOME_APP}",
            f"<h3>{NOME_APP} {__version__}</h3>"
            "<p>Cadastro de questões de matemática, montagem de provas em LaTeX e PDF.</p>"
            "<p>Funciona 100% offline. A matemática da prévia é mostrada pelo MathJax 3 "
            "(licença Apache 2.0), empacotado com o aplicativo.</p>"
            f"<p>Banco aberto: <code>{self.ctx.banco.pasta}</code></p>",
        )

    # -- geometria -----------------------------------------------------------------------------
    def _restaurar_geometria(self) -> None:
        geo = self.ctx.local.geometria.get("janela")
        if geo:
            from PySide6.QtCore import QByteArray

            self.restoreGeometry(QByteArray.fromHex(geo.encode()))

    def _salvar_geometria(self) -> None:
        self.ctx.local.geometria["janela"] = bytes(self.saveGeometry().toHex()).decode()
        self.ctx.salvar_local()

    # -- fechar ------------------------------------------------------------------------------------
    def pode_fechar(self) -> bool:
        """Confere alterações não salvas em todas as telas."""
        if not self.cadastro.pode_descartar():
            self.abas.setCurrentWidget(self.cadastro)
            return False
        for tela in self.telas_extras:
            if hasattr(tela, "pode_descartar") and not tela.pode_descartar():
                self.abas.setCurrentWidget(tela)
                return False
        return True

    def closeEvent(self, ev) -> None:  # noqa: N802
        if not self._fechando_para_trocar and not self.pode_fechar():
            ev.ignore()
            return
        self._salvar_geometria()
        self.aplicativo.banco_fechado(self)
        ev.accept()

    def fechar_para_trocar(self) -> None:
        self._fechando_para_trocar = True
        self.close()
