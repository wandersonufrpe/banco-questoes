"""Diálogos de aviso: erro de LaTeX ao salvar, progresso."""

from __future__ import annotations

import html

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout,
)

from ..nucleo.checagem import ResultadoChecagem


class DialogoErroLatex(QDialog):
    """Mostra o erro de compilação de forma legível. ``self.salvar_mesmo_assim`` diz a escolha."""

    def __init__(self, r: ResultadoChecagem, tempo_limite: float, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Problema no LaTeX da questão")
        self.resize(640, 260)
        self.salvar_mesmo_assim = False
        lay = QVBoxLayout(self)

        if r.tempo_esgotado:
            titulo = f"A compilação passou do tempo limite ({tempo_limite:g} s)."
            detalhe = "Pode haver um laço infinito no código, ou o TeX está instalando pacotes que faltam."
        else:
            onde = r.campo_nome or "campo não identificado"
            titulo = f"Erro no campo: <b>{html.escape(onde)}</b>"
            partes = []
            if r.erro is not None:
                partes.append(f"<p><b>Mensagem do LaTeX:</b> <code>{html.escape(r.erro.mensagem)}</code></p>")
                if r.erro.explicacao:
                    partes.append(f"<p>{html.escape(r.erro.explicacao)}</p>")
                if r.erro.trecho:
                    partes.append(f"<p><b>Perto de:</b> <code>{html.escape(r.erro.trecho)}</code></p>")
            else:
                partes.append("<p>A compilação falhou sem mensagem reconhecível. Veja o log abaixo.</p>")
            if r.campo_chave == "preambulo":
                partes.append("<p>O problema parece estar no preâmbulo/macros (Configurações) ou no modelo de prova.</p>")
            detalhe = "".join(partes)
        cab = QLabel(f"<h3>{titulo}</h3>")
        cab.setTextFormat(Qt.TextFormat.RichText)
        cab.setWordWrap(True)
        lay.addWidget(cab)
        texto = QLabel(detalhe)
        texto.setTextFormat(Qt.TextFormat.RichText)
        texto.setWordWrap(True)
        texto.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(texto)

        self.log = QPlainTextEdit(r.log[-8000:] if r.log else "(sem log)")
        self.log.setReadOnly(True)
        self.log.setVisible(False)
        b_log = QPushButton("Mostrar log completo")
        b_log.setCheckable(True)
        b_log.toggled.connect(self.log.setVisible)
        b_log.toggled.connect(lambda v: b_log.setText("Esconder log" if v else "Mostrar log completo"))
        lay.addWidget(b_log, alignment=Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(self.log, 1)

        botoes = QDialogButtonBox()
        corrigir = botoes.addButton("Corrigir", QDialogButtonBox.ButtonRole.RejectRole)
        salvar = botoes.addButton("Salvar mesmo assim", QDialogButtonBox.ButtonRole.AcceptRole)
        corrigir.setDefault(True)
        botoes.rejected.connect(self.reject)
        salvar.clicked.connect(self._salvar)
        lay.addWidget(botoes)

    def _salvar(self) -> None:
        self.salvar_mesmo_assim = True
        self.accept()
