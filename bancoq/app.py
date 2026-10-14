"""Ponto de entrada: cria a QApplication, abre o banco e mostra a janela."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def _preparar_ambiente() -> None:
    # O conteúdo da prévia é só local (a rede é bloqueada), então o sandbox do
    # Chromium pode ser desligado onde ele costuma falhar: executável Linux
    # (AppImage/pasta portátil) e execução como root.
    if sys.platform.startswith("linux"):
        from .caminhos import empacotado

        root = hasattr(os, "geteuid") and os.geteuid() == 0
        if empacotado() or root:
            os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
    flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
    for extra in ("--disable-background-networking", "--disable-component-update",
                  "--disable-domain-reliability", "--no-pings"):
        if extra not in flags:
            flags += " " + extra
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = flags.strip()


def _instalar_traducoes(app) -> None:
    from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator

    QLocale.setDefault(QLocale(QLocale.Language.Portuguese, QLocale.Country.Brazil))
    caminho = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    app._tradutores = []
    for nome in ("qtbase_pt_BR", "qt_pt_BR"):
        t = QTranslator(app)
        if t.load(nome, caminho):
            app.installTranslator(t)
            app._tradutores.append(t)
            break


class Aplicativo:
    """Controla qual banco está aberto e a janela correspondente."""

    def __init__(self, app, local):
        self.app = app
        self.local = local
        self.janela = None

    # -- abertura ------------------------------------------------------------------------
    def iniciar(self, pasta_inicial: str | None = None) -> bool:
        from .nucleo.banco import Banco

        pasta = pasta_inicial or self.local.ultimo_banco
        if pasta and Banco.e_banco(pasta):
            if self.abrir(Path(pasta)):
                return True
        return self._dialogo_inicial()

    def _dialogo_inicial(self, mensagem: str = "") -> bool:
        from .interface.abrir_banco import DialogoAbrirBanco

        while True:
            d = DialogoAbrirBanco(self.local.bancos_recentes, mensagem=mensagem)
            if not d.exec() or d.pasta is None:
                return False
            if self.abrir(d.pasta, criar=d.criar):
                return True

    def abrir(self, pasta: Path, criar: bool = False) -> bool:
        from PySide6.QtWidgets import QMessageBox

        from .contexto import Contexto
        from .interface.janela_principal import JanelaPrincipal
        from .nucleo.banco import Banco

        try:
            banco = Banco.criar(pasta) if criar else self._abrir_existente(pasta)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(None, "Banco de Questões", f"Não foi possível abrir o banco em\n{pasta}\n\n{e}")
            return False
        if banco is None:
            return False
        ctx = Contexto(banco, self.local)
        self._apos_abrir(ctx)
        self.local.registrar_banco(str(Path(pasta)))
        ctx.salvar_local()
        janela = JanelaPrincipal(ctx, self)
        anterior = self.janela
        self.janela = janela
        janela.show()
        if anterior is not None:
            anterior.fechar_para_trocar()
        return True

    def _abrir_existente(self, pasta: Path):
        from .nucleo.banco import Banco

        return Banco(pasta)

    def _apos_abrir(self, ctx) -> None:
        """Tarefas feitas logo depois de abrir o banco."""

    def banco_fechado(self, janela) -> None:
        """Chamado quando uma janela de banco fecha."""

    # -- troca de banco -----------------------------------------------------------------------
    def abrir_outro_banco(self) -> None:
        from .interface.abrir_banco import escolher_pasta_banco_existente

        if self.janela is not None and not self.janela.pode_fechar():
            return
        p = escolher_pasta_banco_existente(self.janela)
        if p is not None:
            self._trocar(p, criar=False)

    def criar_outro_banco(self) -> None:
        from .interface.abrir_banco import escolher_pasta_novo_banco
        from .nucleo.banco import Banco

        if self.janela is not None and not self.janela.pode_fechar():
            return
        p = escolher_pasta_novo_banco(self.janela)
        if p is not None:
            self._trocar(p, criar=not Banco.e_banco(p))

    def _trocar(self, pasta: Path, criar: bool) -> None:
        if self.janela is not None and Path(pasta).resolve() == self.janela.ctx.banco.pasta.resolve():
            return
        self.app.setQuitOnLastWindowClosed(False)
        try:
            self.abrir(pasta, criar)
        finally:
            self.app.setQuitOnLastWindowClosed(True)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    parser = argparse.ArgumentParser(prog="bancoq", description="Banco de Questões de Matemática")
    parser.add_argument("--banco", help="pasta do banco a abrir")
    parser.add_argument("--autoteste", action="store_true", help="testa o executável e sai")
    args, resto = parser.parse_known_args(argv[1:])

    _preparar_ambiente()
    from PySide6.QtCore import QCoreApplication, Qt
    from PySide6.QtGui import QIcon
    from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: F401 - precisa vir antes da QApplication
    from PySide6.QtWidgets import QApplication

    from . import NOME_APP
    from .caminhos import limpar_pasta_temporaria, recurso
    from .config_local import ConfigLocal

    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication([argv[0], *resto])
    app.setApplicationName("BancoQuestoes")
    app.setApplicationDisplayName(NOME_APP)
    app.setOrganizationName("BancoQuestoes")
    icone = recurso("icone.png")
    if icone.exists():
        app.setWindowIcon(QIcon(str(icone)))
    _instalar_traducoes(app)

    if args.autoteste:
        from .autoteste import executar_autoteste

        return executar_autoteste(app)

    aplicativo = Aplicativo(app, ConfigLocal.carregar())
    try:
        if not aplicativo.iniciar(args.banco):
            return 0
        return app.exec()
    finally:
        encerrar_qt(app)
        limpar_pasta_temporaria()


def encerrar_qt(app) -> None:
    """Destrói as janelas (e as páginas web) antes do perfil do QtWebEngine."""
    from PySide6.QtCore import QCoreApplication, QEvent

    from .interface import tarefas

    tarefas.aguardar_todas()
    for w in app.topLevelWidgets():
        w.close()
        w.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QCoreApplication.processEvents()
    from .interface import previa

    previa.descartar_perfil()


if __name__ == "__main__":
    sys.exit(main())
