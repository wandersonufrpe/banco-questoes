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
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
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
        self.l_tex = QLabel()
        self.statusBar().addPermanentWidget(self.l_tex)
        self._atualizar_status_tex()
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

        from .montagem import TelaMontagem

        self.montagem = TelaMontagem(self.ctx)
        self.abas.addTab(self.montagem, "Montagem de prova")
        self.telas_extras.append(self.montagem)

        from .importacao import TelaImportacao

        self.importacao = TelaImportacao(self.ctx)
        self.abas.addTab(self.importacao, "Importação")
        self.telas_extras.append(self.importacao)

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
        self._acao(m, "Importar prova em LaTeX (.tex)…", self._importar_tex)
        m.addSeparator()
        self._acao(m, "Sair", self.close, QKeySequence.StandardKey.Quit)

        self.menu_banco = self.menuBar().addMenu("&Banco")
        self._acao(self.menu_banco, "Categorias…", self.banco.gerenciar_categorias)
        self._acao(self.menu_banco, "Tags…", self.banco.gerenciar_tags)
        self.menu_ferramentas = self.menuBar().addMenu("&Ferramentas")
        self._acao(self.menu_ferramentas, "Configurações…", self.abrir_configuracoes, QKeySequence("Ctrl+,"))
        self.menu_ajuda = self.menuBar().addMenu("A&juda")
        self._acao(self.menu_ajuda, "Sobre…", self._sobre)

    def _acao(self, menu, texto, func, atalho=None) -> QAction:
        a = QAction(texto, self)
        if atalho is not None:
            a.setShortcut(atalho)
        a.triggered.connect(func)
        menu.addAction(a)
        return a

    def _importar_tex(self) -> None:
        self.abas.setCurrentWidget(self.importacao)
        self.importacao.abrir_arquivo()

    def abrir_configuracoes(self, aba: int = 0) -> None:
        from .configuracoes import DialogoConfiguracoes

        DialogoConfiguracoes(self.ctx, self, aba if isinstance(aba, int) else 0).exec()
        self._atualizar_status_tex()

    def _atualizar_status_tex(self) -> None:
        info = self.ctx.tex()
        if info is None:
            self.l_tex.setText("TeX não encontrado: só .tex")
            self.l_tex.setStyleSheet("color: #a34a00;")
        else:
            self.l_tex.setText(f"TeX: {info.motor}")
            self.l_tex.setStyleSheet("")
        self.l_tex.setToolTip(info.descricao() if info else "Instale o TeX Live ou o MiKTeX, ou configure o caminho")

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
