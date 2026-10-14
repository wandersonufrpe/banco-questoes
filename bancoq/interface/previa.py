"""Prévia rápida (QWebEngineView + MathJax local) sem acesso à rede."""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtWebEngineCore import (
    QWebEnginePage, QWebEngineProfile, QWebEngineSettings, QWebEngineUrlRequestInterceptor,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication

from ..caminhos import recurso
from ..nucleo.midia import GerenciadorMidia

ESQUEMAS_LOCAIS = {"file", "data", "qrc", "about", "blob"}


class BloqueioRede(QWebEngineUrlRequestInterceptor):
    """Bloqueia qualquer requisição que não seja local: o app é 100% offline."""

    def interceptRequest(self, info) -> None:  # noqa: N802 (nome da API Qt)
        if info.requestUrl().scheme().lower() not in ESQUEMAS_LOCAIS:
            info.block(True)


_perfil: QWebEngineProfile | None = None
_interceptor: BloqueioRede | None = None


def perfil() -> QWebEngineProfile:
    """Perfil sem gravação em disco (off-the-record) e com a rede bloqueada."""
    global _perfil, _interceptor
    if _perfil is None:
        _perfil = QWebEngineProfile(QApplication.instance())
        _interceptor = BloqueioRede(_perfil)
        _perfil.setUrlRequestInterceptor(_interceptor)
        _perfil.setHttpCacheType(QWebEngineProfile.HttpCacheType.MemoryHttpCache)
        _perfil.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
        _perfil.setSpellCheckEnabled(False)
    return _perfil


def descartar_perfil() -> None:
    global _perfil, _interceptor
    if _perfil is not None:
        _perfil.deleteLater()
        _perfil = None
        _interceptor = None


class PaginaPrevia(QWebEnginePage):
    def acceptNavigationRequest(self, url, tipo, principal) -> bool:  # noqa: N802
        # só a carga inicial (setHtml) é permitida; cliques em links são ignorados
        return tipo != QWebEnginePage.NavigationType.NavigationTypeLinkClicked

    def javaScriptConsoleMessage(self, nivel, mensagem, linha, origem) -> None:  # noqa: N802
        pass


def url_arquivo(caminho: Path | None) -> str | None:
    if caminho is None:
        return None
    return QUrl.fromLocalFile(str(caminho)).toString()


def resolvedor_imagens(midia: GerenciadorMidia | None):
    def resolver(ident: str) -> str | None:
        if midia is None:
            return None
        return url_arquivo(midia.caminho_previa(ident))

    return resolver


class PreviaWeb(QWebEngineView):
    """Mostra HTML com matemática renderizada pelo MathJax empacotado."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPage(PaginaPrevia(perfil(), self))
        s = self.settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
        s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, False)
        s.setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, False)
        s.setAttribute(QWebEngineSettings.WebAttribute.PdfViewerEnabled, False)
        s.setAttribute(QWebEngineSettings.WebAttribute.DnsPrefetchEnabled, False)
        s.setAttribute(QWebEngineSettings.WebAttribute.NavigateOnDropEnabled, False)
        self.setAcceptDrops(False)
        self._pronto = False
        self._pendente: str | None = None
        self._ultimo: str | None = None
        self._macros: dict = {}
        self.loadFinished.connect(self._carregou)
        self._carregar_pagina()

    def _carregar_pagina(self) -> None:
        self._pronto = False
        pagina = recurso("previa.html").read_text(encoding="utf-8")
        macros = json.dumps(self._macros, ensure_ascii=False).replace("</", "<\\/")
        pagina = pagina.replace("/*MACROS*/{}", macros)
        base = QUrl.fromLocalFile(str(recurso("previa.html")))
        self.setHtml(pagina, base)

    def definir_macros(self, macros: dict) -> None:
        if macros != self._macros:
            self._macros = dict(macros)
            if self._ultimo is not None and self._pendente is None:
                self._pendente = self._ultimo
            self._carregar_pagina()

    def _carregou(self, ok: bool) -> None:
        self._pronto = True
        if self._pendente is not None:
            conteudo, self._pendente = self._pendente, None
            self.mostrar(conteudo)

    def mostrar(self, conteudo_html: str) -> None:
        self._ultimo = conteudo_html
        if not self._pronto:
            self._pendente = conteudo_html
            return
        self.page().runJavaScript(f"atualizar({json.dumps(conteudo_html)});")

    def mostrar_vazio(self, mensagem: str) -> None:
        self.mostrar(f'<div class="vazia">{mensagem}</div>')
