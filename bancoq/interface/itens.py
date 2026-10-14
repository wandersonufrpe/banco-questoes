"""Editor de alternativas (múltipla escolha) e afirmativas (verdadeiro ou falso)."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QFrame, QHBoxLayout, QLabel, QPushButton, QRadioButton,
    QToolButton, QVBoxLayout, QWidget,
)

from ..nucleo.entidades import Item, letra
from .editor_latex import EditorLatex


class LinhaItem(QFrame):
    alterado = Signal()
    subir = Signal(object)
    descer = Signal(object)
    remover = Signal(object)
    pediu_imagem = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setObjectName("linhaItem")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 4, 6, 6)
        lay.setSpacing(3)

        topo = QHBoxLayout()
        self.rotulo = QLabel()
        self.rotulo.setMinimumWidth(34)
        f = self.rotulo.font()
        f.setBold(True)
        self.rotulo.setFont(f)
        topo.addWidget(self.rotulo)

        self.correta = QCheckBox("Correta")
        self.correta.setToolTip("Marque a alternativa correta")
        topo.addWidget(self.correta)

        self.grupo_vf = QButtonGroup(self)
        self.verdadeira = QRadioButton("V")
        self.falsa = QRadioButton("F")
        self.verdadeira.setToolTip("Afirmativa verdadeira")
        self.falsa.setToolTip("Afirmativa falsa")
        self.grupo_vf.addButton(self.verdadeira)
        self.grupo_vf.addButton(self.falsa)
        self.falsa.setChecked(True)
        topo.addWidget(self.verdadeira)
        topo.addWidget(self.falsa)
        topo.addStretch(1)

        def botao(texto: str, dica: str, sinal) -> QToolButton:
            b = QToolButton()
            b.setText(texto)
            b.setToolTip(dica)
            b.setAutoRaise(True)
            b.clicked.connect(lambda: sinal.emit(self))
            topo.addWidget(b)
            return b

        botao("Imagem…", "Inserir imagem nesta alternativa", self.pediu_imagem)
        self.b_subir = botao("▲", "Mover para cima", self.subir)
        self.b_descer = botao("▼", "Mover para baixo", self.descer)
        botao("✕", "Remover", self.remover)
        lay.addLayout(topo)

        self.texto = EditorLatex(linhas_min=2, linhas_max=10)
        self.texto.setPlaceholderText("Texto em LaTeX")
        lay.addWidget(self.texto)
        self.comentario = EditorLatex(linhas_min=1, linhas_max=8)
        self.comentario.setPlaceholderText("Comentário: por que está certa ou errada (opcional)")
        lay.addWidget(self.comentario)

        self.texto.textChanged.connect(self.alterado)
        self.comentario.textChanged.connect(self.alterado)
        self.correta.toggled.connect(self.alterado)
        self.verdadeira.toggled.connect(self.alterado)

    def configurar(self, tipo: str, indice: int, total: int) -> None:
        vf = tipo == "vf"
        self.rotulo.setText(f"{indice + 1}." if vf else f"({letra(indice)})")
        self.correta.setVisible(not vf)
        self.verdadeira.setVisible(vf)
        self.falsa.setVisible(vf)
        self.b_subir.setEnabled(indice > 0)
        self.b_descer.setEnabled(indice < total - 1)
        self.texto.setPlaceholderText("Afirmativa em LaTeX" if vf else "Alternativa em LaTeX")

    def item(self, tipo: str) -> Item:
        correta = self.verdadeira.isChecked() if tipo == "vf" else self.correta.isChecked()
        return Item(texto=self.texto.toPlainText(), correta=correta, comentario=self.comentario.toPlainText())

    def definir(self, item: Item) -> None:
        self.texto.setPlainText(item.texto)
        self.comentario.setPlainText(item.comentario)
        self.correta.setChecked(item.correta)
        (self.verdadeira if item.correta else self.falsa).setChecked(True)

    def sincronizar_marcacao(self, de_tipo: str) -> None:
        """Ao trocar o tipo, mantém o significado de "correta" ↔ "verdadeira"."""
        if de_tipo == "vf":
            self.correta.setChecked(self.verdadeira.isChecked())
        else:
            (self.verdadeira if self.correta.isChecked() else self.falsa).setChecked(True)


class EditorItens(QWidget):
    alterado = Signal()
    erro_imagem = Signal(str)
    pasta_imagem_usada = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tipo = "multipla"
        self.midia = None
        self.pasta_inicial = ""
        self.linhas: list[LinhaItem] = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self.area = QVBoxLayout()
        self.area.setSpacing(4)
        lay.addLayout(self.area)
        rodape = QHBoxLayout()
        self.b_adicionar = QPushButton("+ Adicionar alternativa")
        self.b_adicionar.clicked.connect(lambda: self.adicionar(Item(), focar=True))
        rodape.addWidget(self.b_adicionar)
        rodape.addStretch(1)
        lay.addLayout(rodape)

    def definir_midia(self, midia) -> None:
        self.midia = midia
        for ln in self.linhas:
            ln.texto.midia = midia
            ln.comentario.midia = midia

    def definir_tipo(self, tipo: str) -> None:
        anterior = self.tipo
        if tipo in ("multipla", "vf") and tipo != anterior:
            for ln in self.linhas:
                ln.sincronizar_marcacao(anterior)
        self.tipo = tipo
        self.b_adicionar.setText("+ Adicionar afirmativa" if tipo == "vf" else "+ Adicionar alternativa")
        self._renumerar()

    def adicionar(self, item: Item, focar: bool = False) -> LinhaItem:
        ln = LinhaItem(self)
        ln.texto.midia = self.midia
        ln.comentario.midia = self.midia
        ln.definir(item)
        ln.alterado.connect(self.alterado)
        ln.subir.connect(lambda l: self._mover(l, -1))
        ln.descer.connect(lambda l: self._mover(l, +1))
        ln.remover.connect(self._remover)
        ln.pediu_imagem.connect(self._imagem)
        ln.texto.erro.connect(self.erro_imagem)
        ln.comentario.erro.connect(self.erro_imagem)
        self.linhas.append(ln)
        self.area.addWidget(ln)
        self._renumerar()
        if focar:
            ln.texto.setFocus()
        self.alterado.emit()
        return ln

    def _remover(self, ln: LinhaItem) -> None:
        self.linhas.remove(ln)
        self.area.removeWidget(ln)
        ln.deleteLater()
        self._renumerar()
        self.alterado.emit()

    def _mover(self, ln: LinhaItem, delta: int) -> None:
        i = self.linhas.index(ln)
        j = i + delta
        if not 0 <= j < len(self.linhas):
            return
        self.linhas[i], self.linhas[j] = self.linhas[j], self.linhas[i]
        for w in self.linhas:
            self.area.removeWidget(w)
        for w in self.linhas:
            self.area.addWidget(w)
        self._renumerar()
        ln.texto.setFocus()
        self.alterado.emit()

    def _imagem(self, ln: LinhaItem) -> None:
        editor = ln.texto if not ln.comentario.hasFocus() else ln.comentario
        pasta = editor.inserir_imagem_de_arquivo(self.pasta_inicial)
        if pasta:
            self.pasta_inicial = pasta
            self.pasta_imagem_usada.emit(pasta)

    def _renumerar(self) -> None:
        for i, ln in enumerate(self.linhas):
            ln.configurar(self.tipo, i, len(self.linhas))

    def itens(self) -> list[Item]:
        return [ln.item(self.tipo) for ln in self.linhas]

    def definir_itens(self, itens: list[Item]) -> None:
        for ln in self.linhas:
            self.area.removeWidget(ln)
            ln.deleteLater()
        self.linhas = []
        for item in itens:
            self.adicionar(item)
        self._renumerar()

    def garantir_minimo(self, n: int) -> None:
        while len(self.linhas) < n:
            self.adicionar(Item())
