"""Campo de texto LaTeX com destaque de sintaxe e inserção de imagens."""

from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRegularExpression, Qt, Signal
from PySide6.QtGui import (
    QColor, QFont, QFontDatabase, QImage, QSyntaxHighlighter, QTextCharFormat, QTextCursor,
)
from PySide6.QtWidgets import QFileDialog, QInputDialog, QMenu, QMessageBox, QPlainTextEdit

from ..nucleo.midia import EXTENSOES, RE_MARCADOR, ErroMidia, GerenciadorMidia, largura_de, marcador

FILTRO_IMAGENS = "Imagens (*.png *.jpg *.jpeg *.pdf *.PNG *.JPG *.JPEG *.PDF)"


def _formato(cor: str, negrito: bool = False, italico: bool = False, fundo: str | None = None) -> QTextCharFormat:
    f = QTextCharFormat()
    f.setForeground(QColor(cor))
    if negrito:
        f.setFontWeight(QFont.Weight.Bold)
    if italico:
        f.setFontItalic(True)
    if fundo:
        f.setBackground(QColor(fundo))
    return f


class RealceLatex(QSyntaxHighlighter):
    """Destaque simples: comandos, chaves, matemática, ambientes, comentários e imagens."""

    def __init__(self, documento):
        super().__init__(documento)
        self.regras = [
            (QRegularExpression(r"\$\$.*?\$\$|\$[^$\n]+\$|\\\(.*?\\\)|\\\[.*?\\\]"), _formato("#0b6e4f", fundo="#eef8f3")),
            (QRegularExpression(r"\\[A-Za-z@]+\*?|\\[^A-Za-z@\s]"), _formato("#1f4fbf")),
            (QRegularExpression(r"[{}]"), _formato("#9a6a00", negrito=True)),
            (QRegularExpression(r"\\(?:begin|end)\{[^}]*\}"), _formato("#8a1f8a", negrito=True)),
            (QRegularExpression(r"\[\[img:[^\]]*\]\]"), _formato("#b35900", negrito=True, fundo="#fff1e0")),
            (QRegularExpression(r"(?<!\\)%.*$"), _formato("#8a8a8a", italico=True)),
        ]

    def highlightBlock(self, texto: str) -> None:
        for regex, formato in self.regras:
            it = regex.globalMatch(texto)
            while it.hasNext():
                m = it.next()
                self.setFormat(m.capturedStart(), m.capturedLength(), formato)


def bytes_de_qimage(img: QImage) -> bytes:
    dados = QByteArray()
    buf = QBuffer(dados)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    buf.close()
    return bytes(dados.data())


class EditorLatex(QPlainTextEdit):
    """Editor de um campo LaTeX.

    Aceita imagens por arrastar e soltar, colar (área de transferência) e pelo
    método ``inserir_imagem_de_arquivo``. A imagem vira um marcador
    ``[[img:ID|largura]]`` na posição do cursor.
    """

    erro = Signal(str)

    def __init__(self, parent=None, linhas_min: int = 3, linhas_max: int = 14,
                 aceita_imagens: bool = True, latex: bool = True):
        super().__init__(parent)
        self.midia: GerenciadorMidia | None = None
        self.aceita_imagens = aceita_imagens
        self.linhas_min = linhas_min
        self.linhas_max = linhas_max
        fonte = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        fonte.setPointSize(max(fonte.pointSize(), 10))
        self.setFont(fonte)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * 4)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        if latex:
            self.realce = RealceLatex(self.document())
        self.document().contentsChanged.connect(self._ajustar_altura)
        self._ajustar_altura()

    # -- altura automática --------------------------------------------------------
    def _ajustar_altura(self) -> None:
        linhas = 0
        bloco = self.document().begin()
        while bloco.isValid():
            linhas += max(1, bloco.layout().lineCount() if bloco.layout() else 1)
            bloco = bloco.next()
        linhas = max(self.linhas_min, min(self.linhas_max, linhas + 1))
        altura = int(linhas * self.fontMetrics().lineSpacing() + 2 * self.frameWidth()
                     + self.document().documentMargin() * 2 + 4)
        self.setFixedHeight(altura)

    def resizeEvent(self, ev) -> None:
        super().resizeEvent(ev)
        self._ajustar_altura()

    # -- imagens ----------------------------------------------------------------------
    def _inserir_marcador(self, ident: str) -> None:
        cur = self.textCursor()
        self.setTextCursor(cur)
        cur.insertText(marcador(ident))
        self.setFocus()

    def _adicionar_arquivos(self, caminhos: list[Path]) -> bool:
        if self.midia is None or not self.aceita_imagens:
            return False
        algum = False
        for p in caminhos:
            try:
                ident = self.midia.adicionar_arquivo(p)
            except ErroMidia as e:
                self.erro.emit(str(e))
                continue
            self._inserir_marcador(ident)
            algum = True
        return algum

    def inserir_imagem_de_arquivo(self, pasta_inicial: str = "") -> str | None:
        """Abre o seletor de arquivos; devolve a pasta usada (para lembrar)."""
        if self.midia is None:
            return None
        arquivos, _ = QFileDialog.getOpenFileNames(self, "Inserir imagem", pasta_inicial, FILTRO_IMAGENS)
        if arquivos:
            self._adicionar_arquivos([Path(a) for a in arquivos])
            return str(Path(arquivos[0]).parent)
        return None

    @staticmethod
    def _arquivos_aceitos(mime) -> list[Path]:
        if not mime.hasUrls():
            return []
        res = []
        for url in mime.urls():
            if url.isLocalFile():
                p = Path(url.toLocalFile())
                ext = p.suffix.lower().lstrip(".")
                if ext in EXTENSOES or ext == "jpeg":
                    res.append(p)
        return res

    def canInsertFromMimeData(self, source) -> bool:
        if self.aceita_imagens and (source.hasImage() or self._arquivos_aceitos(source)):
            return True
        return super().canInsertFromMimeData(source)

    def insertFromMimeData(self, source) -> None:
        if self.aceita_imagens and self.midia is not None:
            arquivos = self._arquivos_aceitos(source)
            if arquivos:
                self._adicionar_arquivos(arquivos)
                return
            if source.hasImage():
                img = source.imageData()
                if isinstance(img, QImage) and not img.isNull():
                    try:
                        ident = self.midia.adicionar_bytes(bytes_de_qimage(img))
                    except ErroMidia as e:
                        self.erro.emit(str(e))
                        return
                    self._inserir_marcador(ident)
                    return
        if source.hasText():
            self.textCursor().insertText(source.text())
            return
        super().insertFromMimeData(source)

    def dragEnterEvent(self, ev) -> None:
        if self.aceita_imagens and self._arquivos_aceitos(ev.mimeData()):
            ev.acceptProposedAction()
            return
        super().dragEnterEvent(ev)

    def dragMoveEvent(self, ev) -> None:
        if self.aceita_imagens and self._arquivos_aceitos(ev.mimeData()):
            cur = self.cursorForPosition(ev.position().toPoint())
            self.setTextCursor(cur)
            ev.acceptProposedAction()
            return
        super().dragMoveEvent(ev)

    def dropEvent(self, ev) -> None:
        arquivos = self._arquivos_aceitos(ev.mimeData()) if self.aceita_imagens else []
        if arquivos:
            cur = self.cursorForPosition(ev.position().toPoint())
            self.setTextCursor(cur)
            self._adicionar_arquivos(arquivos)
            ev.acceptProposedAction()
            return
        super().dropEvent(ev)

    # -- largura do marcador sob o cursor ------------------------------------------------
    def _marcador_no_cursor(self) -> tuple[int, re.Match] | None:
        cur = self.textCursor()
        bloco = cur.block()
        pos = cur.positionInBlock()
        for m in RE_MARCADOR.finditer(bloco.text()):
            if m.start() <= pos <= m.end():
                return bloco.position(), m
        return None

    def ajustar_largura(self) -> None:
        achado = self._marcador_no_cursor()
        if achado is None:
            return
        inicio_bloco, m = achado
        atual = int(round(largura_de(m) * 100))
        valor, ok = QInputDialog.getInt(
            self, "Largura da imagem", "Largura (% da largura da linha):", atual, 5, 100, 5
        )
        if not ok:
            return
        cur = QTextCursor(self.document())
        cur.setPosition(inicio_bloco + m.start())
        cur.setPosition(inicio_bloco + m.end(), QTextCursor.MoveMode.KeepAnchor)
        cur.insertText(marcador(m.group(1), valor / 100))

    def contextMenuEvent(self, ev) -> None:
        menu: QMenu = self.createStandardContextMenu()
        if self.aceita_imagens and self.midia is not None:
            menu.addSeparator()
            menu.addAction("Inserir imagem…", self.inserir_imagem_de_arquivo)
            cur = self.cursorForPosition(ev.pos())
            if not self.textCursor().hasSelection():
                self.setTextCursor(cur)
            if self._marcador_no_cursor() is not None:
                menu.addAction("Largura desta imagem…", self.ajustar_largura)
        menu.exec(ev.globalPos())
        menu.deleteLater()


def mostrar_erro_imagem(parent, mensagem: str) -> None:
    QMessageBox.warning(parent, "Imagem", mensagem)
