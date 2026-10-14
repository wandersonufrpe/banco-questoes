"""Tela de montagem de prova: escolha manual, sorteio por regras, versões e exportação."""

from __future__ import annotations

import random
from datetime import date
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QFrame, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QPlainTextEdit, QProgressDialog, QPushButton, QSpinBox, QSplitter, QStyledItemDelegate, QTableView,
    QTableWidget, QTableWidgetItem, QTabWidget, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from ..contexto import Contexto
from ..nucleo.entidades import TIPOS, Questao, nome_tipo
from ..nucleo.exportar import Exportacao, nomes_arquivos
from ..nucleo.latex_html import texto_simples
from ..nucleo.macros import extrair_macros
from ..nucleo.modelos_prova import listar_modelos
from ..nucleo.previa_html import html_questao
from ..nucleo.prova import (
    MAX_VERSOES, Montagem, Regra, contar_disponiveis, nova_semente, ressortear, sortear_regras,
    valor_numerico, valor_total,
)
from . import tarefas
from .categorias import SeletorCategoria
from .editor_latex import EditorLatex
from .filtros import ModeloQuestoes, PainelFiltros, configurar_tabela
from .previa import PreviaWeb, resolvedor_imagens
from .tags import CampoTags

PAPEL_QID = Qt.ItemDataRole.UserRole
COL_NUM, COL_ID, COL_TIPO, COL_ENUN, COL_VALOR, COL_ESPACO, COL_ORIGEM = range(7)


def formatar_numero(v: float) -> str:
    return f"{v:g}".replace(".", ",")


# =============================================================================
# lista de questões da prova (arrastar para reordenar)
# =============================================================================
class _SoValorEspaco(QStyledItemDelegate):
    """Só as colunas Valor e Espaço podem ser editadas."""

    def createEditor(self, parent, opcao, indice):  # noqa: N802
        if indice.column() in (COL_VALOR, COL_ESPACO):
            return super().createEditor(parent, opcao, indice)
        return None


class ListaProva(QTreeWidget):
    reordenada = Signal(list)   # nova ordem de questao_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderLabels(["#", "Nº", "Tipo", "Enunciado", "Valor", "Espaço (cm)", "Origem"])
        self.setRootIsDecorated(False)
        self.setAlternatingRowColors(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked
                             | QAbstractItemView.EditTrigger.EditKeyPressed
                             | QAbstractItemView.EditTrigger.SelectedClicked)
        cab = self.header()
        for col, larg in ((COL_NUM, 34), (COL_ID, 50), (COL_TIPO, 110), (COL_VALOR, 60),
                          (COL_ESPACO, 84), (COL_ORIGEM, 80)):
            self.setColumnWidth(col, larg)
        cab.setSectionResizeMode(COL_ENUN, QHeaderView.ResizeMode.Stretch)
        cab.setStretchLastSection(False)
        self.invisibleRootItem().setFlags(self.invisibleRootItem().flags() | Qt.ItemFlag.ItemIsDropEnabled)
        self.setItemDelegate(_SoValorEspaco(self))

    def dropEvent(self, ev) -> None:  # noqa: N802
        super().dropEvent(ev)
        ordem = [self.topLevelItem(i).data(0, PAPEL_QID) for i in range(self.topLevelItemCount())]
        self.reordenada.emit(ordem)


# =============================================================================
# diálogos auxiliares
# =============================================================================
class DialogoRegra(QDialog):
    def __init__(self, ctx: Contexto, regra: Regra, excluir: list[int], parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.excluir = excluir
        self.setWindowTitle("Regra de sorteio")
        self.resize(520, 300)
        f = QFormLayout(self)
        self.n = QSpinBox()
        self.n.setRange(1, 200)
        self.n.setValue(regra.n)
        f.addRow("Quantidade de questões:", self.n)
        self.categoria = SeletorCategoria(ctx.repo, permitir_criar=False, texto_vazio="(qualquer categoria)")
        self.categoria.definir(regra.categoria_id)
        f.addRow("Categoria:", self.categoria)
        self.sub = QCheckBox("incluir subcategorias")
        self.sub.setChecked(regra.incluir_subcategorias)
        f.addRow("", self.sub)
        h = QHBoxLayout()
        self.tags = CampoTags()
        self.tags.definir_sugestoes(ctx.repo.nomes_tags())
        self.tags.definir_tags(regra.tags)
        self.modo = QComboBox()
        self.modo.addItem("todas", "todas")
        self.modo.addItem("qualquer uma", "qualquer")
        self.modo.setCurrentIndex(0 if regra.tags_modo == "todas" else 1)
        h.addWidget(self.tags, 1)
        h.addWidget(self.modo)
        f.addRow("Tags:", h)
        h = QHBoxLayout()
        self.dmin = QSpinBox()
        self.dmin.setRange(1, 5)
        self.dmin.setValue(regra.dif_min)
        self.dmax = QSpinBox()
        self.dmax.setRange(1, 5)
        self.dmax.setValue(regra.dif_max)
        h.addWidget(self.dmin)
        h.addWidget(QLabel("a"))
        h.addWidget(self.dmax)
        h.addStretch(1)
        f.addRow("Dificuldade:", h)
        self.tipo = QComboBox()
        self.tipo.addItem("Qualquer tipo", None)
        for k, v in TIPOS.items():
            self.tipo.addItem(v, k)
        self.tipo.setCurrentIndex(max(0, self.tipo.findData(regra.tipo)))
        f.addRow("Tipo:", self.tipo)
        self.l_disp = QLabel()
        f.addRow("", self.l_disp)
        botoes = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)
        f.addRow(botoes)
        self.regra_id = regra.id
        for s in (self.n.valueChanged, self.categoria.alterado, self.sub.toggled, self.tags.textChanged,
                  self.modo.currentIndexChanged, self.dmin.valueChanged, self.dmax.valueChanged,
                  self.tipo.currentIndexChanged):
            s.connect(self._contar)
        self._contar()

    def regra(self) -> Regra:
        return Regra(
            n=self.n.value(), categoria_id=self.categoria.categoria_id, incluir_subcategorias=self.sub.isChecked(),
            tags=self.tags.tags(), tags_modo=self.modo.currentData(), dif_min=self.dmin.value(),
            dif_max=self.dmax.value(), tipo=self.tipo.currentData(), id=self.regra_id,
        )

    def _contar(self, *_a) -> None:
        n = contar_disponiveis(self.ctx.repo, self.regra(), self.excluir)
        cor = "#1f7a3a" if n >= self.n.value() else "#b00020"
        self.l_disp.setText(f"<span style='color:{cor}'>{n} questão(ões) disponível(is) com esses critérios.</span>")


class DialogoAbrirMontagem(QDialog):
    def __init__(self, ctx: Contexto, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.escolhida: int | None = None
        self.setWindowTitle("Abrir montagem")
        self.resize(520, 400)
        lay = QVBoxLayout(self)
        self.lista = QListWidget()
        lay.addWidget(self.lista, 1)
        botoes = QDialogButtonBox()
        abrir = botoes.addButton("Abrir", QDialogButtonBox.ButtonRole.AcceptRole)
        self.b_excluir = botoes.addButton("Excluir…", QDialogButtonBox.ButtonRole.DestructiveRole)
        botoes.addButton("Cancelar", QDialogButtonBox.ButtonRole.RejectRole)
        abrir.clicked.connect(self._abrir)
        self.b_excluir.clicked.connect(self._excluir)
        self.b_excluir.setEnabled(not ctx.somente_leitura)
        botoes.rejected.connect(self.reject)
        self.lista.itemDoubleClicked.connect(lambda *_: self._abrir())
        lay.addWidget(botoes)
        self._carregar()

    def _carregar(self) -> None:
        self.lista.clear()
        for mid, nome, alterada in self.ctx.repo.listar_montagens():
            it = QListWidgetItem(f"{nome}    —    alterada em {alterada}")
            it.setData(Qt.ItemDataRole.UserRole, mid)
            self.lista.addItem(it)
        if self.lista.count():
            self.lista.setCurrentRow(0)

    def _abrir(self) -> None:
        it = self.lista.currentItem()
        if it:
            self.escolhida = it.data(Qt.ItemDataRole.UserRole)
            self.accept()

    def _excluir(self) -> None:
        it = self.lista.currentItem()
        if not it:
            return
        r = QMessageBox.question(self, "Excluir montagem", f"Excluir a montagem salva “{it.text().split('    —')[0]}”?")
        if r == QMessageBox.StandardButton.Yes:
            self.ctx.repo.excluir_montagem(it.data(Qt.ItemDataRole.UserRole))
            self._carregar()


class _Ponte(QObject):
    progresso = Signal(str, int, int)


class DialogoRelatorio(QDialog):
    def __init__(self, rel, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Exportação concluída" if not rel.erros else "Exportação com problemas")
        self.resize(640, 420)
        lay = QVBoxLayout(self)
        partes = [f"<p>Pasta: <code>{rel.pasta}</code></p>"]
        if rel.cancelado:
            partes.append("<p><b>A geração dos PDFs foi cancelada.</b></p>")
        if rel.pdfs:
            partes.append(f"<p>✔ {len(rel.pdfs)} PDF(s) gerado(s).</p>")
        partes.append(f"<p>{len(rel.arquivos)} arquivo(s) .tex/.json escritos e as imagens copiadas para "
                      "<code>midia/</code>.</p>")
        rotulo = QLabel("".join(partes))
        rotulo.setWordWrap(True)
        lay.addWidget(rotulo)
        if rel.erros or rel.avisos:
            texto = QPlainTextEdit()
            texto.setReadOnly(True)
            linhas = [("ERRO: " + e) for e in rel.erros] + [("Aviso: " + a) for a in rel.avisos]
            texto.setPlainText("\n\n".join(linhas))
            lay.addWidget(texto, 1)
        lista = QListWidget()
        for p in sorted(set(rel.arquivos + rel.pdfs)):
            lista.addItem(p.name)
        lay.addWidget(lista, 1)
        botoes = QDialogButtonBox()
        abrir = botoes.addButton("Abrir pasta", QDialogButtonBox.ButtonRole.ActionRole)
        botoes.addButton("Fechar", QDialogButtonBox.ButtonRole.RejectRole)
        abrir.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(rel.pasta))))
        botoes.rejected.connect(self.reject)
        lay.addWidget(botoes)


# =============================================================================
# tela
# =============================================================================
class TelaMontagem(QWidget):
    def __init__(self, ctx: Contexto, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.m = Montagem()
        self.montagem_id: int | None = None
        self._base = self.m.para_dict()
        self._cache: dict[int, Questao] = {}
        self._atualizando = False
        self.ultima_pasta: Path | None = None

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(6, 6, 6, 6)

        topo = QHBoxLayout()
        self.l_nome = QLabel()
        f = self.l_nome.font()
        f.setBold(True)
        f.setPointSize(f.pointSize() + 2)
        self.l_nome.setFont(f)
        topo.addWidget(self.l_nome)
        self.l_mod = QLabel("● alterações não salvas")
        self.l_mod.setStyleSheet("color: #c25e00; font-weight: bold;")
        topo.addWidget(self.l_mod)
        topo.addStretch(1)
        self.b_nova = QPushButton("Nova montagem")
        self.b_abrir = QPushButton("Abrir…")
        self.b_salvar = QPushButton("Salvar montagem")
        self.b_salvar_como = QPushButton("Salvar como…")
        for b in (self.b_nova, self.b_abrir, self.b_salvar, self.b_salvar_como):
            topo.addWidget(b)
        raiz.addLayout(topo)

        divisor = QSplitter(Qt.Orientation.Horizontal)
        raiz.addWidget(divisor, 1)

        # ---- esquerda: banco ------------------------------------------------------------------
        esquerda = QSplitter(Qt.Orientation.Vertical)
        cima = QWidget()
        lc = QVBoxLayout(cima)
        lc.setContentsMargins(0, 0, 0, 0)
        titulo = QLabel("<b>Questões do banco</b> — marque e envie para a prova (ou dê duplo clique)")
        lc.addWidget(titulo)
        self.filtros = PainelFiltros(ctx, compacto=True)
        lc.addWidget(self.filtros)
        self.tabela = QTableView()
        self.modelo_banco = ModeloQuestoes(self, marcavel=True)
        self.proxy = configurar_tabela(self.tabela, self.modelo_banco)
        for col in (3, 4, 6, 7, 8):
            self.tabela.setColumnHidden(col, True)
        lc.addWidget(self.tabela, 1)
        h = QHBoxLayout()
        self.l_marcadas = QLabel()
        b_todas = QPushButton("Marcar todas")
        b_nenhuma = QPushButton("Desmarcar")
        self.b_enviar = QPushButton("Adicionar marcadas à prova →")
        f = self.b_enviar.font()
        f.setBold(True)
        self.b_enviar.setFont(f)
        h.addWidget(self.l_marcadas)
        h.addStretch(1)
        h.addWidget(b_todas)
        h.addWidget(b_nenhuma)
        h.addWidget(self.b_enviar)
        lc.addLayout(h)
        esquerda.addWidget(cima)
        self.previa = PreviaWeb()
        esquerda.addWidget(self.previa)
        esquerda.setSizes([520, 260])
        divisor.addWidget(esquerda)

        # ---- direita: abas ------------------------------------------------------------------------
        self.abas = QTabWidget()
        divisor.addWidget(self.abas)
        divisor.setSizes([560, 760])

        # questões da prova
        w = QWidget()
        lw = QVBoxLayout(w)
        self.lista = ListaProva()
        lw.addWidget(self.lista, 1)
        h = QHBoxLayout()
        self.b_subir = QPushButton("▲")
        self.b_descer = QPushButton("▼")
        self.b_remover = QPushButton("Remover")
        self.b_ressortear = QPushButton("Ressortear")
        self.b_ressortear.setToolTip("Troca a questão selecionada por outra da mesma regra de sorteio")
        self.b_valor_todas = QPushButton("Mesmo valor para todas…")
        for b in (self.b_subir, self.b_descer, self.b_remover, self.b_ressortear, self.b_valor_todas):
            h.addWidget(b)
        h.addStretch(1)
        self.l_total = QLabel()
        h.addWidget(self.l_total)
        lw.addLayout(h)
        dica = QLabel("Arraste as linhas para reordenar. Dê duplo clique em Valor ou Espaço para editar "
                      "(o espaço para resposta vale para questões discursivas).")
        dica.setWordWrap(True)
        dica.setStyleSheet("color: gray;")
        lw.addWidget(dica)
        self.abas.addTab(w, "Questões da prova")

        # regras
        w = QWidget()
        lw = QVBoxLayout(w)
        lw.addWidget(QLabel("Cada regra sorteia N questões que atendem aos critérios. Questões já na prova não são repetidas."))
        self.t_regras = QTableWidget(0, 2)
        self.t_regras.setHorizontalHeaderLabels(["Regra", "Disponíveis"])
        self.t_regras.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.t_regras.verticalHeader().setVisible(False)
        self.t_regras.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.t_regras.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        lw.addWidget(self.t_regras, 1)
        h = QHBoxLayout()
        b_add = QPushButton("Adicionar regra…")
        b_edit = QPushButton("Editar…")
        b_del = QPushButton("Remover")
        self.b_sortear = QPushButton("Sortear")
        self.b_sortear.setToolTip("Refaz o sorteio de todas as regras (as questões escolhidas à mão ficam)")
        for b in (b_add, b_edit, b_del):
            h.addWidget(b)
        h.addStretch(1)
        h.addWidget(self.b_sortear)
        lw.addLayout(h)
        self.abas.addTab(w, "Sorteio por regras")
        b_add.clicked.connect(self._adicionar_regra)
        b_edit.clicked.connect(self._editar_regra)
        b_del.clicked.connect(self._remover_regra)
        self.t_regras.itemDoubleClicked.connect(lambda *_: self._editar_regra())

        # cabeçalho
        w = QWidget()
        fl = QFormLayout(w)
        self.e_titulo = QLineEdit()
        self.e_titulo.setPlaceholderText("ex.: Primeira avaliação")
        self.e_disciplina = QLineEdit()
        self.e_turma = QLineEdit()
        self.e_professor = QLineEdit()
        h = QHBoxLayout()
        self.e_data = QLineEdit()
        b_hoje = QPushButton("Hoje")
        b_hoje.clicked.connect(lambda: self.e_data.setText(date.today().strftime("%d/%m/%Y")))
        h.addWidget(self.e_data, 1)
        h.addWidget(b_hoje)
        self.e_instrucoes = EditorLatex(linhas_min=5, linhas_max=14, aceita_imagens=False)
        self.e_instrucoes.setPlaceholderText("Instruções (LaTeX), ex.: Justifique todas as respostas.")
        self.c_modelo = QComboBox()
        fl.addRow("Título:", self.e_titulo)
        fl.addRow("Disciplina:", self.e_disciplina)
        fl.addRow("Turma:", self.e_turma)
        fl.addRow("Professor(a):", self.e_professor)
        fl.addRow("Data:", h)
        fl.addRow("Instruções:", self.e_instrucoes)
        fl.addRow("Modelo de prova:", self.c_modelo)
        nota = QLabel("Os campos do cabeçalho são LaTeX: caracteres especiais como & % # _ precisam de barra (\\&).")
        nota.setWordWrap(True)
        nota.setStyleSheet("color: gray;")
        fl.addRow("", nota)
        self.abas.addTab(w, "Cabeçalho")

        # versões e exportação
        w = QWidget()
        fl = QFormLayout(w)
        self.s_versoes = QSpinBox()
        self.s_versoes.setRange(1, MAX_VERSOES)
        fl.addRow("Número de versões:", self.s_versoes)
        self.ch_emb_q = QCheckBox("Embaralhar a ordem das questões")
        self.ch_emb_a = QCheckBox("Embaralhar as alternativas (respeita “não embaralhar” de cada questão)")
        fl.addRow("", self.ch_emb_q)
        fl.addRow("", self.ch_emb_a)
        h = QHBoxLayout()
        self.e_semente = QLineEdit()
        self.e_semente.setMaximumWidth(140)
        self.e_semente.setToolTip("Com a mesma semente (e as mesmas questões e opções) a prova sai idêntica")
        b_semente = QPushButton("Nova semente")
        b_semente.clicked.connect(lambda: self.e_semente.setText(str(nova_semente())))
        h.addWidget(self.e_semente)
        h.addWidget(b_semente)
        h.addStretch(1)
        fl.addRow("Semente:", h)
        self.ch_pdf = QCheckBox("Gerar também os PDFs (pdflatex)")
        self.ch_pdf.setChecked(True)
        fl.addRow("", self.ch_pdf)
        self.l_tex = QLabel()
        self.l_tex.setWordWrap(True)
        fl.addRow("", self.l_tex)
        h = QHBoxLayout()
        self.b_exportar = QPushButton("Exportar prova…")
        f = self.b_exportar.font()
        f.setBold(True)
        self.b_exportar.setFont(f)
        self.b_abrir_pasta = QPushButton("Abrir pasta da última exportação")
        self.b_abrir_pasta.setEnabled(False)
        h.addWidget(self.b_exportar)
        h.addWidget(self.b_abrir_pasta)
        h.addStretch(1)
        fl.addRow("", h)
        expl = QLabel(
            "Para cada versão são gerados: <code>prova_A.tex</code>/<code>.pdf</code> e "
            "<code>resolucao_A.tex</code>/<code>.pdf</code> (resolução e comentários das alternativas). "
            "O <code>gabarito.tex</code>/<code>.pdf</code> traz a tabela de respostas de cada versão. "
            "As imagens vão para <code>midia/</code> com caminhos relativos, e <code>montagem.json</code> "
            "registra a semente e a ordem das questões."
        )
        expl.setWordWrap(True)
        expl.setStyleSheet("color: #555;")
        fl.addRow("", expl)
        self.abas.addTab(w, "Versões e exportação")

        # ---- ligações ---------------------------------------------------------------------------------
        self.filtros.alterado.connect(self._recarregar_banco)
        self.modelo_banco.marcacoes_mudaram.connect(self._atualizar_marcadas)
        self.tabela.selectionModel().currentRowChanged.connect(self._previa_banco)
        self.tabela.doubleClicked.connect(self._adicionar_duplo_clique)
        b_todas.clicked.connect(lambda: self.modelo_banco.marcar_todas(True))
        b_nenhuma.clicked.connect(lambda: self.modelo_banco.marcar_todas(False))
        self.b_enviar.clicked.connect(self._adicionar_marcadas)
        self.lista.reordenada.connect(self._reordenar)
        self.lista.itemChanged.connect(self._item_editado)
        self.lista.currentItemChanged.connect(self._previa_prova)
        self.b_subir.clicked.connect(lambda: self._mover(-1))
        self.b_descer.clicked.connect(lambda: self._mover(1))
        self.b_remover.clicked.connect(self._remover)
        self.b_ressortear.clicked.connect(self._ressortear)
        self.b_valor_todas.clicked.connect(self._valor_todas)
        self.b_sortear.clicked.connect(self._sortear)
        self.b_nova.clicked.connect(self.nova)
        self.b_abrir.clicked.connect(self.abrir)
        self.b_salvar.clicked.connect(self.salvar)
        self.b_salvar_como.clicked.connect(lambda: self.salvar(como=True))
        self.b_exportar.clicked.connect(self.exportar)
        self.b_abrir_pasta.clicked.connect(
            lambda: self.ultima_pasta and QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.ultima_pasta)))
        )
        for wdg in (self.e_titulo, self.e_disciplina, self.e_turma, self.e_professor, self.e_data, self.e_semente):
            wdg.textChanged.connect(self._formulario_mudou)
        self.e_instrucoes.textChanged.connect(self._formulario_mudou)
        self.c_modelo.currentIndexChanged.connect(self._formulario_mudou)
        self.s_versoes.valueChanged.connect(self._formulario_mudou)
        self.ch_emb_q.toggled.connect(self._formulario_mudou)
        self.ch_emb_a.toggled.connect(self._formulario_mudou)
        ctx.sinais.questoes_alteradas.connect(self._questoes_mudaram)
        ctx.sinais.config_alterada.connect(self._config_mudou)
        if ctx.somente_leitura:
            for b in (self.b_salvar, self.b_salvar_como):
                b.setEnabled(False)
        self._config_mudou()
        self._carregar_no_formulario()
        self._recarregar_banco()
        self._marcar_base()

    # =========================================================================
    # estado
    # =========================================================================
    def _formulario_para_montagem(self) -> None:
        if self._atualizando:
            return
        c = self.m.cabecalho
        c.titulo = self.e_titulo.text()
        c.disciplina = self.e_disciplina.text()
        c.turma = self.e_turma.text()
        c.professor = self.e_professor.text()
        c.data = self.e_data.text()
        c.instrucoes = self.e_instrucoes.toPlainText()
        self.m.modelo = self.c_modelo.currentData() or ""
        self.m.num_versoes = self.s_versoes.value()
        self.m.embaralhar_questoes = self.ch_emb_q.isChecked()
        self.m.embaralhar_alternativas = self.ch_emb_a.isChecked()
        try:
            self.m.semente = int(self.e_semente.text().strip())
        except ValueError:
            pass

    def _carregar_no_formulario(self) -> None:
        self._atualizando = True
        try:
            c = self.m.cabecalho
            self.e_titulo.setText(c.titulo)
            self.e_disciplina.setText(c.disciplina)
            self.e_turma.setText(c.turma)
            self.e_professor.setText(c.professor)
            self.e_data.setText(c.data)
            self.e_instrucoes.setPlainText(c.instrucoes)
            self._preencher_modelos()
            self.s_versoes.setValue(self.m.num_versoes)
            self.ch_emb_q.setChecked(self.m.embaralhar_questoes)
            self.ch_emb_a.setChecked(self.m.embaralhar_alternativas)
            self.e_semente.setText(str(self.m.semente))
        finally:
            self._atualizando = False
        self._atualizar_tudo()

    def _preencher_modelos(self) -> None:
        self.c_modelo.blockSignals(True)
        self.c_modelo.clear()
        padrao = self.ctx.config.modelo_padrao
        for nome in listar_modelos(self.ctx.banco.pasta_modelos):
            self.c_modelo.addItem(nome + ("  (padrão)" if nome == padrao else ""), nome)
        alvo = self.m.modelo or padrao
        i = self.c_modelo.findData(alvo)
        self.c_modelo.setCurrentIndex(i if i >= 0 else max(0, self.c_modelo.findData(padrao)))
        self.c_modelo.blockSignals(False)

    def modificado(self) -> bool:
        self._formulario_para_montagem()
        return self.m.para_dict() != self._base

    def _marcar_base(self) -> None:
        self._formulario_para_montagem()
        self._base = self.m.para_dict()
        self._atualizar_titulo()

    def _formulario_mudou(self, *_a) -> None:
        if self._atualizando:
            return
        self._formulario_para_montagem()
        self._atualizar_titulo()

    def _atualizar_titulo(self) -> None:
        nome = self.m.nome or "Montagem nova (não salva)"
        self.l_nome.setText(nome)
        self.l_mod.setVisible(self.m.para_dict() != self._base)

    def _questoes(self, ids) -> dict[int, Questao]:
        faltam = [i for i in ids if i not in self._cache]
        if faltam:
            self._cache.update(self.ctx.repo.obter_questoes(faltam))
        return {i: self._cache[i] for i in ids if i in self._cache}

    def _questoes_mudaram(self) -> None:
        self._cache.clear()
        self._recarregar_banco()
        self._atualizar_lista()
        self._atualizar_regras()

    def _config_mudou(self) -> None:
        self.previa.definir_macros(extrair_macros(self.ctx.config.preambulo))
        info = self.ctx.tex()
        self.ch_pdf.setEnabled(info is not None)
        if info is None:
            self.l_tex.setText("TeX não encontrado: a exportação vai gerar só os arquivos .tex. "
                               "Instale o TeX Live/MiKTeX ou configure o caminho em Configurações.")
            self.l_tex.setStyleSheet("color: #a34a00;")
        else:
            self.l_tex.setText(f"PDF com {info.motor} ({info.caminho}).")
            self.l_tex.setStyleSheet("color: gray;")
        if not self._atualizando:
            self._atualizando = True
            self._preencher_modelos()
            self._atualizando = False

    # =========================================================================
    # banco (esquerda)
    # =========================================================================
    def _recarregar_banco(self) -> None:
        linhas = self.ctx.repo.buscar(self.filtros.filtro())
        self.modelo_banco.destacadas = set(self.m.ids())
        self.modelo_banco.definir(linhas, self.ctx.repo.caminhos_categorias())
        self._atualizar_marcadas()

    def _atualizar_marcadas(self) -> None:
        n = len(self.modelo_banco.marcadas)
        visiveis = {r.id for r in self.modelo_banco.linhas}
        fora = len(self.modelo_banco.marcadas - visiveis)
        texto = f"{self.modelo_banco.rowCount()} no filtro · {n} marcada(s)"
        if fora:
            texto += f" ({fora} fora do filtro atual)"
        self.l_marcadas.setText(texto)
        self.b_enviar.setEnabled(n > 0)

    def _previa_banco(self, atual, _anterior=None) -> None:
        if not atual.isValid():
            return
        qid = self.modelo_banco.id_na_linha(self.proxy.mapToSource(atual).row())
        self._mostrar_previa(qid)

    def _mostrar_previa(self, qid: int) -> None:
        q = self._questoes([qid]).get(qid)
        if q is None:
            return
        info = f'<div class="info">Nº {q.id}{" · já está na prova" if qid in self.m.ids() else ""}</div>'
        self.previa.mostrar(info + html_questao(q, resolvedor_imagens(self.ctx.midia)))

    def _adicionar(self, ids: list[int]) -> None:
        n = self.m.adicionar_manual(ids)
        if n < len(ids):
            QMessageBox.information(self, "Montagem", f"{len(ids) - n} questão(ões) já estava(m) na prova.")
        self._atualizar_tudo()
        self.abas.setCurrentIndex(0)

    def _adicionar_marcadas(self) -> None:
        marcadas = self.modelo_banco.marcadas
        ordem = [r.id for r in self.modelo_banco.linhas if r.id in marcadas]
        ordem += sorted(marcadas - set(ordem))          # marcadas em filtros anteriores
        existentes = self._questoes(ordem)               # ignora questões excluídas nesse meio-tempo
        self._adicionar([q for q in ordem if q in existentes])
        self.modelo_banco.marcar_todas(False)

    def _adicionar_duplo_clique(self, indice) -> None:
        self._adicionar([self.modelo_banco.id_na_linha(self.proxy.mapToSource(indice).row())])

    # =========================================================================
    # lista da prova
    # =========================================================================
    def _atualizar_tudo(self) -> None:
        self._atualizar_lista()
        self._atualizar_regras()
        self._recarregar_banco()
        self._atualizar_titulo()

    def _atualizar_lista(self, selecionar: list[int] | None = None) -> None:
        if selecionar is None:
            selecionar = [it.data(0, PAPEL_QID) for it in self.lista.selectedItems()]
        qs = self._questoes(self.m.ids())
        regras = {r.id: i + 1 for i, r in enumerate(self.m.regras)}
        self._atualizando = True
        self.lista.clear()
        for n, item in enumerate(self.m.itens, start=1):
            q = qs.get(item.questao_id)
            tipo = q.tipo if q else ""
            origem = f"regra {regras[item.regra]}" if item.regra in regras else "manual"
            ti = QTreeWidgetItem([
                str(n), str(item.questao_id), nome_tipo(tipo) if q else "?",
                texto_simples(q.enunciado, 120) if q else "(questão excluída do banco)",
                item.valor, formatar_numero(item.espaco_cm) if item.espaco_cm else "", origem,
            ])
            ti.setData(0, PAPEL_QID, item.questao_id)
            flags = (Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsDragEnabled
                     | Qt.ItemFlag.ItemIsEditable)
            ti.setFlags(flags)
            if q is not None:
                ti.setToolTip(3, texto_simples(q.enunciado, 600))
            if tipo != "discursiva":
                ti.setForeground(COL_ESPACO, Qt.GlobalColor.gray)
            self.lista.addTopLevelItem(ti)
            if item.questao_id in selecionar:
                ti.setSelected(True)
                self.lista.setCurrentItem(ti)
        self._atualizando = False
        total = valor_total(self.m)
        partes = [f"{len(self.m.itens)} questão(ões)"]
        if total is not None:
            partes.append(f"valor total: {formatar_numero(total)}")
        self.l_total.setText(" · ".join(partes))
        self.abas.setTabText(0, f"Questões da prova ({len(self.m.itens)})")

    def _indices_selecionados(self) -> list[int]:
        return sorted(self.lista.indexOfTopLevelItem(it) for it in self.lista.selectedItems())

    def _item_editado(self, ti: QTreeWidgetItem, coluna: int) -> None:
        if self._atualizando:
            return
        i = self.lista.indexOfTopLevelItem(ti)
        if not 0 <= i < len(self.m.itens):
            return
        item = self.m.itens[i]
        if coluna == COL_VALOR:
            item.valor = ti.text(COL_VALOR).strip()
            if item.valor and valor_numerico(item.valor) is None:
                QMessageBox.information(self, "Valor", "Use um número, como 1,5 (o texto foi mantido, mas não entra no total).")
        elif coluna == COL_ESPACO:
            q = self._questoes([item.questao_id]).get(item.questao_id)
            v = valor_numerico(ti.text(COL_ESPACO)) if ti.text(COL_ESPACO).strip() else 0.0
            if q is None or q.tipo != "discursiva":
                v = 0.0
            item.espaco_cm = max(0.0, min(v or 0.0, 40.0))
        QTimerUnico.depois(self, lambda: (self._atualizar_lista(), self._atualizar_titulo()))

    def _reordenar(self, ordem: list[int]) -> None:
        por_id = {i.questao_id: i for i in self.m.itens}
        self.m.itens = [por_id[q] for q in ordem if q in por_id]
        QTimerUnico.depois(self, lambda: (self._atualizar_lista(), self._atualizar_titulo()))

    def _mover(self, delta: int) -> None:
        sel = self._indices_selecionados()
        if len(sel) != 1:
            return
        i = sel[0]
        j = i + delta
        if not 0 <= j < len(self.m.itens):
            return
        self.m.itens[i], self.m.itens[j] = self.m.itens[j], self.m.itens[i]
        self._atualizar_lista([self.m.itens[j].questao_id])
        self._atualizar_titulo()

    def _remover(self) -> None:
        sel = self._indices_selecionados()
        if not sel:
            return
        for i in reversed(sel):
            del self.m.itens[i]
        self._atualizar_tudo()

    def _ressortear(self) -> None:
        sel = self._indices_selecionados()
        if len(sel) != 1:
            QMessageBox.information(self, "Ressortear", "Selecione uma questão da prova.")
            return
        item = self.m.itens[sel[0]]
        if self.m.regra(item.regra) is None:
            QMessageBox.information(self, "Ressortear", "Esta questão foi escolhida à mão; só questões sorteadas por regra podem ser ressorteadas.")
            return
        novo = ressortear(self.ctx.repo, self.m, sel[0], random.Random())
        if novo is None:
            QMessageBox.information(self, "Ressortear", "Não há outra questão disponível para esta regra.")
            return
        self._atualizar_lista([novo])
        self._recarregar_banco()
        self._atualizar_titulo()
        self._mostrar_previa(novo)

    def _valor_todas(self) -> None:
        texto, ok = QInputDialog.getText(self, "Valor", "Valor de cada questão (vazio = sem valor):")
        if ok:
            for it in self.m.itens:
                it.valor = texto.strip()
            self._atualizar_lista()
            self._atualizar_titulo()

    def _previa_prova(self, atual, _anterior=None) -> None:
        if atual is not None and not self._atualizando:
            self._mostrar_previa(atual.data(0, PAPEL_QID))

    # =========================================================================
    # regras
    # =========================================================================
    def _atualizar_regras(self) -> None:
        caminhos = self.ctx.repo.caminhos_categorias()
        self.t_regras.setRowCount(len(self.m.regras))
        for i, r in enumerate(self.m.regras):
            it = QTableWidgetItem(f"{i + 1}. {r.descricao(caminhos)}")
            self.t_regras.setItem(i, 0, it)
            n = contar_disponiveis(self.ctx.repo, r)
            d = QTableWidgetItem(str(n))
            d.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if n < r.n:
                d.setForeground(Qt.GlobalColor.red)
            self.t_regras.setItem(i, 1, d)
        self.b_sortear.setEnabled(bool(self.m.regras))

    def _regra_selecionada(self) -> int | None:
        linhas = {i.row() for i in self.t_regras.selectedIndexes()}
        return min(linhas) if linhas else None

    def _adicionar_regra(self) -> None:
        d = DialogoRegra(self.ctx, Regra(), self.m.ids(), self)
        if d.exec():
            self.m.regras.append(d.regra())
            self._atualizar_regras()
            self._atualizar_titulo()

    def _editar_regra(self) -> None:
        i = self._regra_selecionada()
        if i is None:
            return
        d = DialogoRegra(self.ctx, self.m.regras[i], self.m.ids(), self)
        if d.exec():
            self.m.regras[i] = d.regra()
            self._atualizar_tudo()

    def _remover_regra(self) -> None:
        i = self._regra_selecionada()
        if i is None:
            return
        self.m.remover_regra(self.m.regras[i].id)
        self._atualizar_tudo()

    def _sortear(self) -> None:
        if any(it.regra for it in self.m.itens):
            r = QMessageBox.question(self, "Sortear", "Refazer o sorteio de todas as regras? "
                                     "As questões sorteadas antes serão trocadas (as escolhidas à mão ficam).")
            if r != QMessageBox.StandardButton.Yes:
                return
        avisos = sortear_regras(self.ctx.repo, self.m, random.Random())
        self._atualizar_tudo()
        self.abas.setCurrentIndex(0)
        if avisos:
            QMessageBox.information(self, "Sorteio", "\n".join(avisos))

    # =========================================================================
    # nova / abrir / salvar
    # =========================================================================
    def pode_descartar(self) -> bool:
        if not self.modificado() or (not self.m.itens and not self.m.regras and self.montagem_id is None):
            return True
        caixa = QMessageBox(self)
        caixa.setWindowTitle("Montagem não salva")
        caixa.setIcon(QMessageBox.Icon.Question)
        caixa.setText("A montagem de prova tem alterações não salvas.")
        salvar = caixa.addButton("Salvar", QMessageBox.ButtonRole.AcceptRole)
        descartar = caixa.addButton("Descartar", QMessageBox.ButtonRole.DestructiveRole)
        caixa.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
        if self.ctx.somente_leitura:
            salvar.setEnabled(False)
        caixa.exec()
        if caixa.clickedButton() is salvar:
            return self.salvar()
        return caixa.clickedButton() is descartar

    def nova(self) -> None:
        if not self.pode_descartar():
            return
        self.m = Montagem()
        self.montagem_id = None
        self._carregar_no_formulario()
        self._marcar_base()

    def abrir(self) -> None:
        if not self.pode_descartar():
            return
        d = DialogoAbrirMontagem(self.ctx, self)
        if not d.exec() or d.escolhida is None:
            return
        res = self.ctx.repo.obter_montagem(d.escolhida)
        if res is None:
            return
        nome, dados = res
        m = Montagem.de_dict(dados)
        m.nome = nome
        qs = self.ctx.repo.obter_questoes(m.ids())
        faltando = [i.questao_id for i in m.itens if i.questao_id not in qs]
        self.m = m
        self.montagem_id = d.escolhida
        self._cache.clear()
        self._carregar_no_formulario()
        self._marcar_base()
        if faltando:
            m.itens = [i for i in m.itens if i.questao_id in qs]
            self._atualizar_tudo()
            QMessageBox.warning(self, "Montagem", "Estas questões foram excluídas do banco e saíram da prova: "
                                + ", ".join(map(str, faltando)))

    def salvar(self, como: bool = False) -> bool:
        if self.ctx.somente_leitura:
            QMessageBox.information(self, "Salvar", "O banco está aberto somente para leitura.")
            return False
        self._formulario_para_montagem()
        nome = self.m.nome
        if como or not nome:
            sugestao = nome or self.m.cabecalho.titulo or "Prova"
            nome, ok = QInputDialog.getText(self, "Salvar montagem", "Nome da montagem:", text=sugestao)
            if not ok or not nome.strip():
                return False
            nome = nome.strip()
        self.m.nome = nome
        try:
            self.montagem_id = self.ctx.repo.salvar_montagem(nome, self.m.para_dict(),
                                                             None if como else self.montagem_id)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Salvar", f"Não foi possível salvar a montagem: {e}")
            return False
        self._marcar_base()
        return True

    # =========================================================================
    # exportação
    # =========================================================================
    def exportar(self) -> None:
        self._formulario_para_montagem()
        if not self.m.itens:
            QMessageBox.information(self, "Exportar", "A prova não tem questões.")
            return
        inicio = self.ctx.local.ultima_pasta_saida or str(Path.home())
        pasta = QFileDialog.getExistingDirectory(self, "Pasta de saída da prova", inicio)
        if not pasta:
            return
        pasta = Path(pasta)
        existentes = [n for n in nomes_arquivos(self.m) if (pasta / n).exists()]
        if existentes:
            r = QMessageBox.question(
                self, "Exportar", f"A pasta já tem {len(existentes)} arquivo(s) com os mesmos nomes "
                f"(ex.: {', '.join(existentes[:4])}). Substituir?")
            if r != QMessageBox.StandardButton.Yes:
                return
        self.ctx.local.ultima_pasta_saida = str(pasta)
        self.ctx.salvar_local()
        questoes = self.ctx.repo.obter_questoes(self.m.ids())
        info = self.ctx.tex()
        gerar_pdf = self.ch_pdf.isChecked() and info is not None
        ponte = _Ponte(self)
        exp = Exportacao(self.m, questoes, self.ctx.texto_modelo(self.m.modelo or None), self.ctx.config.preambulo,
                         self.ctx.midia, pasta, info, gerar_pdf, self.ctx.local.tempo_limite_prova,
                         lambda t, i, n: ponte.progresso.emit(t, i, n))
        prog = QProgressDialog("Gerando os arquivos…", "Cancelar", 0, 0, self)
        prog.setWindowTitle("Exportar prova")
        prog.setWindowModality(Qt.WindowModality.WindowModal)
        prog.setMinimumDuration(0)
        prog.canceled.connect(exp.cancelar)

        def progresso(texto: str, i: int, n: int) -> None:
            prog.setMaximum(n)
            prog.setValue(i)
            prog.setLabelText(texto)

        ponte.progresso.connect(progresso)
        prog.show()

        def fim(rel) -> None:
            prog.canceled.disconnect()
            prog.close()
            self.ultima_pasta = rel.pasta
            self.b_abrir_pasta.setEnabled(True)
            DialogoRelatorio(rel, self).exec()

        def falhou(rastro: str) -> None:
            prog.close()
            QMessageBox.critical(self, "Exportar", f"Erro inesperado na exportação:\n{rastro[-2000:]}")

        tarefas.executar(exp.executar, fim, falhou, self)


class QTimerUnico:
    """Executa uma função logo depois do evento atual (evita mexer na lista durante o próprio sinal)."""

    @staticmethod
    def depois(parent, funcao) -> None:
        from PySide6.QtCore import QTimer

        QTimer.singleShot(0, parent, funcao)
