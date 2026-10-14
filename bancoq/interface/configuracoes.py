"""Configurações: preâmbulo/macros, TeX, modelos de prova e opções do banco."""

from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QInputDialog,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton,
    QSizePolicy, QSpinBox, QTabWidget, QVBoxLayout, QWidget,
)

from ..caminhos import pasta_temporaria
from ..contexto import Contexto
from ..nucleo.checagem import nova_pasta_compilacao
from ..nucleo.compilador import Compilacao, localizar_tex
from ..nucleo.macros import extrair_macros
from ..nucleo.modelos_prova import (
    NOME_GENERICO, listar_modelos, ler_modelo, nome_arquivo_valido, preambulo, texto_generico,
    validar_modelo,
)
from . import tarefas
from .editor_latex import EditorLatex
from .previa_exata import MENSAGEM_SEM_TEX, texto_erro_compilacao


def nota(texto: str) -> QLabel:
    l = QLabel(texto)
    l.setWordWrap(True)
    l.setStyleSheet("color: #555;")
    l.setTextFormat(Qt.TextFormat.RichText)
    l.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
    return l


class EditorModelo(QDialog):
    """Edita o texto de um modelo de prova."""

    def __init__(self, nome: str, texto: str, somente_leitura: bool, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Modelo: {nome}")
        self.resize(900, 700)
        lay = QVBoxLayout(self)
        lay.addWidget(nota(
            "Marcadores: <code>&lt;&lt;titulo&gt;&gt;</code>, <code>&lt;&lt;disciplina&gt;&gt;</code>, "
            "<code>&lt;&lt;turma&gt;&gt;</code>, <code>&lt;&lt;professor&gt;&gt;</code>, "
            "<code>&lt;&lt;data&gt;&gt;</code>, <code>&lt;&lt;versao&gt;&gt;</code>, "
            "<code>&lt;&lt;instrucoes&gt;&gt;</code>, <code>&lt;&lt;macros&gt;&gt;</code>, "
            "<code>&lt;&lt;questoes&gt;&gt;</code>. O modelo precisa definir os ambientes "
            "<code>questao</code>, <code>alternativas</code>, <code>afirmativas</code> e os comandos "
            "<code>\\alt</code>, <code>\\afirmativa</code>, <code>\\espacoresposta</code>, <code>\\respostacurta</code>."
        ))
        self.editor = EditorLatex(linhas_min=20, linhas_max=10000, aceita_imagens=False)
        self.editor.setMinimumHeight(400)
        self.editor.setPlainText(texto)
        self.editor.setReadOnly(somente_leitura)
        lay.addWidget(self.editor, 1)
        botoes = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        if not somente_leitura:
            b = botoes.addButton("Salvar modelo", QDialogButtonBox.ButtonRole.AcceptRole)
            b.clicked.connect(self._salvar)
        botoes.rejected.connect(self.reject)
        lay.addWidget(botoes)
        self.texto = texto

    def _salvar(self) -> None:
        texto = self.editor.toPlainText()
        avisos = validar_modelo(texto)
        if avisos:
            r = QMessageBox.question(
                self, "Modelo", "Possíveis problemas no modelo:\n\n• " + "\n• ".join(avisos)
                + "\n\nSalvar mesmo assim?",
            )
            if r != QMessageBox.StandardButton.Yes:
                return
        self.texto = texto
        self.accept()


class DialogoConfiguracoes(QDialog):
    def __init__(self, ctx: Contexto, parent=None, aba: int = 0):
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle("Configurações")
        self.resize(820, 640)
        ro = ctx.somente_leitura
        lay = QVBoxLayout(self)
        self.abas = QTabWidget()
        lay.addWidget(self.abas, 1)

        # ---- preâmbulo e macros (banco) --------------------------------------------------
        w = QWidget()
        l = QVBoxLayout(w)
        l.addWidget(nota(
            "Pacotes e macros usados nas suas questões (<code>\\usepackage</code>, <code>\\newcommand</code>, "
            "<code>\\DeclareMathOperator</code>…). Entram no lugar do marcador <code>&lt;&lt;macros&gt;&gt;</code> "
            "do modelo e valem na <b>prévia exata</b>, na <b>checagem ao salvar</b> e na <b>exportação</b>. "
            "Na <b>prévia rápida</b> valem as definições <code>\\newcommand</code>, <code>\\renewcommand</code>, "
            "<code>\\DeclareMathOperator</code> e <code>\\def</code> usadas dentro da matemática. "
            "Ficam salvas na pasta do banco."
        ))
        self.preambulo = EditorLatex(linhas_min=14, linhas_max=10000, aceita_imagens=False)
        self.preambulo.setPlaceholderText("% exemplo:\n% \\usepackage{tikz}\n% \\newcommand{\\R}{\\mathbb{R}}")
        self.preambulo.setPlainText(ctx.config.preambulo)
        self.preambulo.setReadOnly(ro)
        l.addWidget(self.preambulo, 1)
        linha = QHBoxLayout()
        self.l_macros = QLabel()
        linha.addWidget(self.l_macros, 1)
        self.b_testar = QPushButton("Testar compilação")
        self.b_testar.setToolTip("Compila um documento vazio com o modelo padrão e este preâmbulo")
        linha.addWidget(self.b_testar)
        l.addLayout(linha)
        self.l_teste = QLabel()
        self.l_teste.setWordWrap(True)
        l.addWidget(self.l_teste)
        self.preambulo.textChanged.connect(self._contar_macros)
        self.b_testar.clicked.connect(self._testar)
        self._contar_macros()
        self.abas.addTab(w, "Preâmbulo e macros")

        # ---- LaTeX (máquina) -------------------------------------------------------------------
        w = QWidget()
        f = QFormLayout(w)
        self.caminho_tex = QLineEdit(ctx.local.caminho_tex)
        self.caminho_tex.setPlaceholderText("vazio = procurar pdflatex/latexmk automaticamente")
        b_proc = QPushButton("Procurar…")
        b_det = QPushButton("Detectar")
        h = QHBoxLayout()
        h.addWidget(self.caminho_tex, 1)
        h.addWidget(b_proc)
        h.addWidget(b_det)
        f.addRow("Caminho do pdflatex ou latexmk:", h)
        self.l_tex = QLabel()
        self.l_tex.setWordWrap(True)
        f.addRow("", self.l_tex)
        self.s_limite_previa = QSpinBox()
        self.s_limite_previa.setRange(5, 600)
        self.s_limite_previa.setSuffix(" s")
        self.s_limite_previa.setValue(int(ctx.local.tempo_limite_previa))
        f.addRow("Tempo limite (prévia exata e checagem):", self.s_limite_previa)
        self.s_limite_prova = QSpinBox()
        self.s_limite_prova.setRange(10, 3600)
        self.s_limite_prova.setSuffix(" s")
        self.s_limite_prova.setValue(int(ctx.local.tempo_limite_prova))
        f.addRow("Tempo limite (cada PDF exportado):", self.s_limite_prova)
        self.ch_checar = QCheckBox("Compilar a questão para checar o LaTeX ao salvar")
        self.ch_checar.setChecked(ctx.config.checar_latex_ao_salvar)
        self.ch_checar.setEnabled(not ro)
        f.addRow("", self.ch_checar)
        f.addRow("", nota(
            "O caminho do TeX e os tempos limite valem só para este computador. "
            "A compilação nunca usa <code>--shell-escape</code>; usa sempre "
            "<code>-interaction=nonstopmode</code> e <code>-halt-on-error</code>."
        ))
        b_proc.clicked.connect(self._procurar_tex)
        b_det.clicked.connect(self._detectar)
        self._detectar()
        self.abas.addTab(w, "LaTeX")

        # ---- modelos (banco) ---------------------------------------------------------------------
        w = QWidget()
        l = QVBoxLayout(w)
        l.addWidget(nota(
            "Modelos de prova ficam na pasta <code>modelos</code> do banco. O marcado com ★ é usado na "
            "prévia exata, na checagem e como sugestão na montagem."
        ))
        h = QHBoxLayout()
        self.lista_modelos = QListWidget()
        h.addWidget(self.lista_modelos, 1)
        col = QVBoxLayout()
        self.botoes_modelo = []
        for texto, func in (("Novo…", self._novo_modelo), ("Editar…", self._editar_modelo),
                            ("Importar .tex…", self._importar_modelo), ("Duplicar…", self._duplicar_modelo),
                            ("Excluir", self._excluir_modelo), ("Usar como padrão ★", self._padrao_modelo)):
            b = QPushButton(texto)
            b.clicked.connect(func)
            b.setEnabled(not ro or texto.startswith("Editar"))
            col.addWidget(b)
        col.addStretch(1)
        h.addLayout(col)
        l.addLayout(h, 1)
        self.modelo_padrao = ctx.config.modelo_padrao
        self.lista_modelos.itemDoubleClicked.connect(lambda *_: self._editar_modelo())
        self._recarregar_modelos()
        self.abas.addTab(w, "Modelos de prova")

        # ---- banco ---------------------------------------------------------------------------------
        w = QWidget()
        f = QFormLayout(w)
        self.s_duplicadas = QSpinBox()
        self.s_duplicadas.setRange(50, 100)
        self.s_duplicadas.setSuffix(" %")
        self.s_duplicadas.setValue(int(ctx.config.limite_duplicadas))
        f.addRow("Avisar de duplicada a partir de:", self.s_duplicadas)
        self.ch_duplicadas = QCheckBox("Procurar questões parecidas ao salvar")
        self.ch_duplicadas.setChecked(ctx.config.checar_duplicadas_ao_salvar)
        f.addRow("", self.ch_duplicadas)
        self.s_backups = QSpinBox()
        self.s_backups.setRange(1, 200)
        self.s_backups.setValue(int(ctx.config.num_backups))
        f.addRow("Backups automáticos mantidos:", self.s_backups)
        f.addRow("", nota(f"Pasta do banco: <code>{ctx.banco.pasta}</code>"))
        for wid in (self.s_duplicadas, self.ch_duplicadas, self.s_backups):
            wid.setEnabled(not ro)
        self.abas.addTab(w, "Banco")
        self.abas.setCurrentIndex(aba)

        if ro:
            lay.addWidget(nota("<b>Banco aberto somente para leitura:</b> só as opções desta máquina podem ser alteradas."))
        botoes = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        salvar = botoes.addButton("Salvar", QDialogButtonBox.ButtonRole.AcceptRole)
        salvar.setDefault(True)
        salvar.clicked.connect(self._salvar)
        botoes.rejected.connect(self.reject)
        lay.addWidget(botoes)
        self._modelos_alterados = False

    # -- macros -----------------------------------------------------------------------------------
    def _contar_macros(self) -> None:
        n = len(extrair_macros(self.preambulo.toPlainText()))
        self.l_macros.setText(f"{n} macro(s) reconhecida(s) para a prévia rápida.")

    def _testar(self) -> None:
        info = localizar_tex(self.caminho_tex.text())
        if info is None:
            self.l_teste.setText(MENSAGEM_SEM_TEX)
            return
        modelo = ler_modelo(self.ctx.banco.pasta_modelos, self.modelo_padrao)
        texto = preambulo(modelo, self.preambulo.toPlainText()) + "\\begin{document}\n\\mbox{}\n\\end{document}\n"
        pasta = nova_pasta_compilacao(pasta_temporaria())
        (pasta / "teste.tex").write_text(texto, encoding="utf-8")
        comp = Compilacao(info, pasta, "teste.tex", self.s_limite_previa.value())
        self.b_testar.setEnabled(False)
        self.l_teste.setText("Compilando…")

        def fim(res) -> None:
            self.b_testar.setEnabled(True)
            if res.ok:
                self.l_teste.setText("✔ O preâmbulo compilou sem erros com o modelo padrão.")
                self.l_teste.setStyleSheet("color: #1f7a3a;")
            else:
                self.l_teste.setText("✘ " + texto_erro_compilacao(res, self.s_limite_previa.value()))
                self.l_teste.setStyleSheet("color: #b00020;")

        tarefas.executar(comp.executar, fim, lambda r: self.l_teste.setText(r[-500:]), self)

    # -- TeX ----------------------------------------------------------------------------------------
    def _procurar_tex(self) -> None:
        arq, _ = QFileDialog.getOpenFileName(self, "pdflatex ou latexmk", self.caminho_tex.text())
        if arq:
            self.caminho_tex.setText(arq)
            self._detectar()

    def _detectar(self) -> None:
        info = localizar_tex(self.caminho_tex.text())
        if info is None:
            self.l_tex.setText("✘ " + MENSAGEM_SEM_TEX)
            self.l_tex.setStyleSheet("color: #a34a00;")
        else:
            self.l_tex.setText("✔ Encontrado — " + info.descricao() + (" [MiKTeX]" if info.miktex else ""))
            self.l_tex.setStyleSheet("color: #1f7a3a;")

    # -- modelos ------------------------------------------------------------------------------------
    def _recarregar_modelos(self, selecionar: str | None = None) -> None:
        self.lista_modelos.clear()
        for nome in listar_modelos(self.ctx.banco.pasta_modelos):
            it = QListWidgetItem(("★ " if nome == self.modelo_padrao else "    ") + nome)
            it.setData(Qt.ItemDataRole.UserRole, nome)
            self.lista_modelos.addItem(it)
            if nome == (selecionar or self.modelo_padrao):
                self.lista_modelos.setCurrentItem(it)

    def _modelo_atual(self) -> str | None:
        it = self.lista_modelos.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it else None

    def _pedir_nome(self, titulo: str, sugestao: str = "") -> str | None:
        nome, ok = QInputDialog.getText(self, titulo, "Nome do arquivo do modelo:", text=sugestao)
        if not ok or not nome.strip():
            return None
        try:
            nome = nome_arquivo_valido(nome)
        except ValueError as e:
            QMessageBox.warning(self, "Modelos", str(e))
            return None
        if (self.ctx.banco.pasta_modelos / nome).exists():
            QMessageBox.warning(self, "Modelos", f"Já existe um modelo chamado {nome}.")
            return None
        return nome

    def _gravar_modelo(self, nome: str, texto: str) -> None:
        self.ctx.banco.pasta_modelos.mkdir(parents=True, exist_ok=True)
        (self.ctx.banco.pasta_modelos / nome).write_text(texto, encoding="utf-8")
        self._modelos_alterados = True
        self._recarregar_modelos(nome)

    def _novo_modelo(self) -> None:
        nome = self._pedir_nome("Novo modelo", "meu-modelo.tex")
        if not nome:
            return
        d = EditorModelo(nome, texto_generico(), False, self)
        if d.exec():
            self._gravar_modelo(nome, d.texto)

    def _editar_modelo(self) -> None:
        nome = self._modelo_atual()
        if not nome:
            return
        texto = ler_modelo(self.ctx.banco.pasta_modelos, nome)
        d = EditorModelo(nome, texto, self.ctx.somente_leitura, self)
        if d.exec() and d.texto != texto:
            self._gravar_modelo(nome, d.texto)

    def _duplicar_modelo(self) -> None:
        nome = self._modelo_atual()
        if not nome:
            return
        novo = self._pedir_nome("Duplicar modelo", "copia-" + nome)
        if novo:
            self._gravar_modelo(novo, ler_modelo(self.ctx.banco.pasta_modelos, nome))

    def _importar_modelo(self) -> None:
        arq, _ = QFileDialog.getOpenFileName(self, "Importar modelo", "", "LaTeX (*.tex)")
        if not arq:
            return
        try:
            texto = Path(arq).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            texto = Path(arq).read_text(encoding="latin-1")
        avisos = validar_modelo(texto)
        if avisos:
            QMessageBox.information(
                self, "Importar modelo",
                "O arquivo foi importado, mas precisa de ajustes para funcionar como modelo:\n\n• "
                + "\n• ".join(avisos) + "\n\nAbra-o com “Editar…” para incluir os marcadores e ambientes.",
            )
        nome = self._pedir_nome("Importar modelo", Path(arq).name)
        if nome:
            self._gravar_modelo(nome, texto)

    def _excluir_modelo(self) -> None:
        nome = self._modelo_atual()
        if not nome:
            return
        if nome == self.modelo_padrao:
            QMessageBox.information(self, "Modelos", "Escolha outro modelo como padrão antes de excluir este.")
            return
        r = QMessageBox.question(self, "Excluir modelo", f"Excluir o modelo {nome}?")
        if r == QMessageBox.StandardButton.Yes:
            try:
                (self.ctx.banco.pasta_modelos / nome).unlink()
            except OSError as e:
                QMessageBox.warning(self, "Modelos", str(e))
            self._modelos_alterados = True
            self._recarregar_modelos()

    def _padrao_modelo(self) -> None:
        nome = self._modelo_atual()
        if nome:
            self.modelo_padrao = nome
            self._recarregar_modelos(nome)

    # -- salvar --------------------------------------------------------------------------------------
    def _salvar(self) -> None:
        local = self.ctx.local
        local.caminho_tex = self.caminho_tex.text().strip()
        local.tempo_limite_previa = self.s_limite_previa.value()
        local.tempo_limite_prova = self.s_limite_prova.value()
        self.ctx.salvar_local()
        self.ctx.redetectar_tex()
        if not self.ctx.somente_leitura:
            cfg = self.ctx.config
            cfg.preambulo = self.preambulo.toPlainText()
            cfg.checar_latex_ao_salvar = self.ch_checar.isChecked()
            cfg.limite_duplicadas = self.s_duplicadas.value()
            cfg.checar_duplicadas_ao_salvar = self.ch_duplicadas.isChecked()
            cfg.num_backups = self.s_backups.value()
            if (self.ctx.banco.pasta_modelos / self.modelo_padrao).exists() or self.modelo_padrao == NOME_GENERICO:
                cfg.modelo_padrao = self.modelo_padrao
            try:
                self.ctx.salvar_config()
            except OSError as e:
                QMessageBox.critical(self, "Configurações", f"Não foi possível salvar: {e}")
                return
        else:
            self.ctx.sinais.config_alterada.emit()
        self.accept()
