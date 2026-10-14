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


class DialogoDuplicada(QDialog):
    """Mostra lado a lado a questão nova e as parecidas do banco."""

    def __init__(self, ctx, q, achadas: list[tuple[int, float]], parent=None):
        from PySide6.QtWidgets import QComboBox, QHBoxLayout, QSplitter, QWidget

        from ..nucleo.macros import extrair_macros
        from ..nucleo.previa_html import html_questao
        from .previa import PreviaWeb, resolvedor_imagens

        super().__init__(parent)
        self.setWindowTitle("Questão parecida no banco")
        self.resize(1100, 640)
        self.salvar_mesmo_assim = False
        self.ctx = ctx
        self._html = html_questao
        self._resolver = resolvedor_imagens(ctx.midia)
        lay = QVBoxLayout(self)
        melhor = achadas[0][1]
        cab = QLabel(f"<h3>Encontrada(s) {len(achadas)} questão(ões) parecida(s) — até {melhor:g}% de semelhança</h3>"
                     f"<p>Limite configurado: {ctx.config.limite_duplicadas}% (Configurações &gt; Banco).</p>")
        cab.setWordWrap(True)
        lay.addWidget(cab)
        divisor = QSplitter(Qt.Orientation.Horizontal)
        esq = QWidget()
        le = QVBoxLayout(esq)
        le.setContentsMargins(0, 0, 0, 0)
        le.addWidget(QLabel("<b>Questão que você está salvando</b>"))
        self.p_nova = PreviaWeb()
        le.addWidget(self.p_nova, 1)
        dir_ = QWidget()
        ld = QVBoxLayout(dir_)
        ld.setContentsMargins(0, 0, 0, 0)
        linha = QHBoxLayout()
        linha.addWidget(QLabel("<b>Já existe no banco:</b>"))
        self.combo = QComboBox()
        for qid, pontos in achadas:
            self.combo.addItem(f"questão nº {qid} — {pontos:g}% parecida", qid)
        linha.addWidget(self.combo, 1)
        ld.addLayout(linha)
        self.p_banco = PreviaWeb()
        ld.addWidget(self.p_banco, 1)
        divisor.addWidget(esq)
        divisor.addWidget(dir_)
        lay.addWidget(divisor, 1)
        macros = extrair_macros(ctx.config.preambulo)
        self.p_nova.definir_macros(macros)
        self.p_banco.definir_macros(macros)
        self.p_nova.mostrar(html_questao(q, self._resolver))
        self.combo.currentIndexChanged.connect(self._mostrar)
        self._mostrar()
        botoes = QDialogButtonBox()
        voltar = botoes.addButton("Voltar sem salvar", QDialogButtonBox.ButtonRole.RejectRole)
        salvar = botoes.addButton("Salvar mesmo assim", QDialogButtonBox.ButtonRole.AcceptRole)
        voltar.setDefault(True)
        botoes.rejected.connect(self.reject)
        salvar.clicked.connect(self._salvar)
        lay.addWidget(botoes)

    def _mostrar(self) -> None:
        qid = self.combo.currentData()
        q = self.ctx.repo.obter_questao(qid) if qid is not None else None
        if q is not None:
            caminho = self.ctx.repo.caminhos_categorias().get(q.categoria_id, "sem categoria")
            info = f'<div class="info">Nº {q.id} · {caminho} · alterada em {q.alterada_em}</div><hr class="sep">'
            self.p_banco.mostrar(info + self._html(q, self._resolver))

    def _salvar(self) -> None:
        self.salvar_mesmo_assim = True
        self.accept()
