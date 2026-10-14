"""Prévia exata: compila a questão sozinha com pdflatex e mostra como imagem."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from ..caminhos import pasta_temporaria
from ..contexto import Contexto
from ..nucleo.checagem import preparar_previa_exata
from ..nucleo.compilador import ResultadoCompilacao
from ..nucleo.entidades import Questao
from ..nucleo.pdf import paginas_png
from . import tarefas

MENSAGEM_SEM_TEX = (
    "O pdflatex (ou latexmk) não foi encontrado, por isso a prévia exata e a geração de PDF "
    "estão desativadas. Instale o TeX Live (Linux) ou o MiKTeX/TeX Live (Windows), ou indique o "
    "caminho em Configurações > LaTeX. A exportação continua gerando os arquivos .tex."
)


def texto_erro_compilacao(res: ResultadoCompilacao, tempo_limite: float) -> str:
    if res.tempo_esgotado:
        return (f"A compilação passou do tempo limite ({tempo_limite:g} s) e foi interrompida. "
                "Pode haver um laço infinito no código ou o TeX está instalando pacotes.")
    if res.erro is None:
        return "A compilação falhou sem mensagem de erro reconhecível. Veja o log."
    partes = [res.erro.mensagem]
    if res.erro.explicacao:
        partes.append(res.erro.explicacao)
    if res.erro.trecho:
        partes.append("Perto de: " + res.erro.trecho)
    return "\n".join(partes)


class PainelPreviaExata(QWidget):
    compilou = Signal(bool)

    def __init__(self, ctx: Contexto, fornecer_questao: Callable[[], Questao], parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.fornecer_questao = fornecer_questao
        self._comp = None
        self._imagens: list[bytes] = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        barra = QHBoxLayout()
        self.b_compilar = QPushButton("Compilar prévia exata")
        self.b_compilar.setToolTip("Compila a questão sozinha com pdflatex, usando o modelo padrão e suas macros")
        self.b_cancelar = QPushButton("Cancelar")
        self.b_cancelar.setVisible(False)
        self.c_zoom = QComboBox()
        for z in (75, 100, 125, 150, 200):
            self.c_zoom.addItem(f"{z}%", z)
        self.c_zoom.setCurrentIndex(1)
        self.l_status = QLabel()
        self.l_status.setWordWrap(True)
        barra.addWidget(self.b_compilar)
        barra.addWidget(self.b_cancelar)
        barra.addWidget(self.l_status, 1)
        barra.addWidget(QLabel("Zoom:"))
        barra.addWidget(self.c_zoom)
        lay.addLayout(barra)

        self.rolagem = QScrollArea()
        self.rolagem.setWidgetResizable(True)
        self.rolagem.setStyleSheet("QScrollArea { background: #8a8f98; }")
        self.conteudo = QWidget()
        self.conteudo.setStyleSheet("background: #8a8f98;")
        self.l_paginas = QVBoxLayout(self.conteudo)
        self.l_paginas.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.rolagem.setWidget(self.conteudo)
        lay.addWidget(self.rolagem, 1)

        self.erro = QPlainTextEdit()
        self.erro.setReadOnly(True)
        self.erro.setVisible(False)
        self.erro.setMaximumHeight(160)
        lay.addWidget(self.erro)
        self.log = ""

        self.b_compilar.clicked.connect(self.compilar)
        self.b_cancelar.clicked.connect(self.cancelar)
        self.c_zoom.currentIndexChanged.connect(self._mostrar_imagens)
        self.atualizar_disponibilidade()

    def atualizar_disponibilidade(self) -> None:
        tem = self.ctx.tex() is not None
        self.b_compilar.setEnabled(tem)
        if not tem:
            self.l_status.setText(MENSAGEM_SEM_TEX)
            self.l_status.setStyleSheet("color: #a34a00;")
        elif not self._imagens:
            self.l_status.setText("Clique em “Compilar prévia exata” para ver a questão como no PDF.")
            self.l_status.setStyleSheet("color: gray;")

    def marcar_desatualizada(self) -> None:
        if self._imagens and self._comp is None:
            self.l_status.setText("A questão mudou desde a última compilação.")
            self.l_status.setStyleSheet("color: #a34a00;")

    def compilar(self) -> None:
        info = self.ctx.tex()
        if info is None or self._comp is not None:
            return
        q = self.fornecer_questao()
        try:
            comp = preparar_previa_exata(
                q, self.ctx.texto_modelo(), self.ctx.config.preambulo, self.ctx.midia, info,
                self.ctx.local.tempo_limite_previa, pasta_temporaria(),
            )
        except OSError as e:
            self.l_status.setText(f"Erro ao preparar a compilação: {e}")
            return
        self._comp = comp
        self.b_compilar.setEnabled(False)
        self.b_cancelar.setVisible(True)
        self.l_status.setText("Compilando…")
        self.l_status.setStyleSheet("")

        def trabalho():
            res = comp.executar()
            imgs = paginas_png(res.pdf, dpi=150) if res.ok and res.pdf else []
            return res, imgs

        tarefas.executar(trabalho, self._terminou, self._falhou, self)

    def cancelar(self) -> None:
        if self._comp is not None:
            self._comp.cancelar()

    def _fim(self) -> None:
        self._comp = None
        self.b_compilar.setEnabled(self.ctx.tex() is not None)
        self.b_cancelar.setVisible(False)

    def _falhou(self, rastro: str) -> None:
        self._fim()
        self.l_status.setText("Erro inesperado ao compilar.")
        self.erro.setPlainText(rastro)
        self.erro.setVisible(True)

    def _terminou(self, resultado) -> None:
        res, imgs = resultado
        self._fim()
        self.log = res.log
        if res.cancelado:
            self.l_status.setText("Compilação cancelada.")
            return
        if not res.ok:
            self.l_status.setText("A compilação falhou:")
            self.l_status.setStyleSheet("color: #b00020; font-weight: bold;")
            self.erro.setPlainText(texto_erro_compilacao(res, self.ctx.local.tempo_limite_previa)
                                   + ("\n\n---- log ----\n" + res.log[-4000:] if res.log else ""))
            self.erro.setVisible(True)
            self.compilou.emit(False)
            return
        self.erro.setVisible(False)
        self._imagens = imgs
        self.l_status.setText(f"Compilado com {self.ctx.tex().motor}.")
        self.l_status.setStyleSheet("color: #1f7a3a;")
        self._mostrar_imagens()
        self.compilou.emit(True)

    def _mostrar_imagens(self) -> None:
        while self.l_paginas.count():
            w = self.l_paginas.takeAt(0).widget()
            if w:
                w.deleteLater()
        fator = (self.c_zoom.currentData() or 100) / 100 * (96 / 150)
        for dados in self._imagens:
            pix = QPixmap()
            pix.loadFromData(dados, "PNG")
            if abs(fator - 1) > 0.01:
                pix = pix.scaledToWidth(int(pix.width() * fator), Qt.TransformationMode.SmoothTransformation)
            rotulo = QLabel()
            rotulo.setPixmap(pix)
            rotulo.setStyleSheet("background: white; border: 1px solid #555;")
            self.l_paginas.addWidget(rotulo)
