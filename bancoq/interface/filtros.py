"""Painel de filtros e tabela de questões (usados no banco e na montagem)."""

from __future__ import annotations

from PySide6.QtCore import (
    QAbstractTableModel, QModelIndex, QSortFilterProxyModel, QStringListModel, Qt, QTimer, Signal,
)
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QCompleter, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QSpinBox, QWidget,
)

from ..contexto import Contexto
from ..nucleo.entidades import TIPOS, ResumoQuestao, nome_tipo
from ..nucleo.latex_html import texto_simples
from ..nucleo.repositorio import Filtro
from .categorias import SeletorCategoria
from .tags import CampoTags


class PainelFiltros(QWidget):
    alterado = Signal()

    def __init__(self, ctx: Contexto, parent=None, compacto: bool = False):
        super().__init__(parent)
        self.ctx = ctx
        self._silencio = False
        g = QGridLayout(self)
        g.setContentsMargins(0, 0, 0, 0)
        g.setHorizontalSpacing(6)
        g.setVerticalSpacing(4)

        self.busca = QLineEdit()
        self.busca.setPlaceholderText("Buscar no enunciado, alternativas, resolução e observações…")
        self.busca.setClearButtonEnabled(True)
        self.categoria = SeletorCategoria(ctx.repo, permitir_criar=False, texto_vazio="(todas as categorias)")
        self.ch_sub = QCheckBox("incluir subcategorias")
        self.ch_sub.setChecked(True)
        self.ch_sem = QCheckBox("só sem categoria")
        self.tags = CampoTags()
        self.tags.setPlaceholderText("tags (separadas por vírgula)")
        self.c_modo_tags = QComboBox()
        self.c_modo_tags.addItem("todas", "todas")
        self.c_modo_tags.addItem("qualquer uma", "qualquer")
        self.c_modo_tags.setToolTip("Exigir todas as tags ou qualquer uma delas")
        self.c_tipo = QComboBox()
        self.c_tipo.addItem("Todos os tipos", None)
        for chave, nome in TIPOS.items():
            self.c_tipo.addItem(nome, chave)
        self.s_dif_min = QSpinBox()
        self.s_dif_min.setRange(1, 5)
        self.s_dif_max = QSpinBox()
        self.s_dif_max.setRange(1, 5)
        self.s_dif_max.setValue(5)
        self.fonte = QLineEdit()
        self.fonte.setPlaceholderText("fonte contém…")
        self.fonte.setClearButtonEnabled(True)
        self._completar_fonte = QCompleter([], self)
        self._completar_fonte.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._completar_fonte.setFilterMode(Qt.MatchFlag.MatchContains)
        self.fonte.setCompleter(self._completar_fonte)
        self.s_ano_min = QSpinBox()
        self.s_ano_max = QSpinBox()
        for s in (self.s_ano_min, self.s_ano_max):
            s.setRange(0, 2100)
            s.setSpecialValueText("—")
        self.b_limpar = QPushButton("Limpar filtros")

        dif = QHBoxLayout()
        dif.addWidget(self.s_dif_min)
        dif.addWidget(QLabel("a"))
        dif.addWidget(self.s_dif_max)
        ano = QHBoxLayout()
        ano.addWidget(self.s_ano_min)
        ano.addWidget(QLabel("a"))
        ano.addWidget(self.s_ano_max)
        cat_opcoes = QHBoxLayout()
        cat_opcoes.addWidget(self.ch_sub)
        cat_opcoes.addWidget(self.ch_sem)
        cat_opcoes.addStretch(1)
        tags_l = QHBoxLayout()
        tags_l.addWidget(self.tags, 1)
        tags_l.addWidget(self.c_modo_tags)

        if compacto:
            linhas = [
                ("Busca:", self.busca), ("Categoria:", self.categoria), ("", cat_opcoes), ("Tags:", tags_l),
                ("Tipo:", self.c_tipo), ("Dificuldade:", dif), ("Fonte:", self.fonte), ("Ano:", ano),
            ]
            for i, (rot, w) in enumerate(linhas):
                g.addWidget(QLabel(rot), i, 0)
                if isinstance(w, QWidget):
                    g.addWidget(w, i, 1)
                else:
                    g.addLayout(w, i, 1)
            g.addWidget(self.b_limpar, len(linhas), 1, alignment=Qt.AlignmentFlag.AlignRight)
            g.setColumnStretch(1, 1)
        else:
            g.addWidget(QLabel("Busca:"), 0, 0)
            g.addWidget(self.busca, 0, 1, 1, 3)
            g.addWidget(QLabel("Tipo:"), 0, 4)
            g.addWidget(self.c_tipo, 0, 5)
            g.addWidget(self.b_limpar, 0, 6)
            g.addWidget(QLabel("Categoria:"), 1, 0)
            g.addWidget(self.categoria, 1, 1)
            g.addLayout(cat_opcoes, 1, 2, 1, 2)
            g.addWidget(QLabel("Dificuldade:"), 1, 4)
            g.addLayout(dif, 1, 5)
            g.addWidget(QLabel("Tags:"), 2, 0)
            g.addLayout(tags_l, 2, 1, 1, 3)
            g.addWidget(QLabel("Ano:"), 2, 4)
            g.addLayout(ano, 2, 5)
            g.addWidget(QLabel("Fonte:"), 3, 0)
            g.addWidget(self.fonte, 3, 1, 1, 3)
            g.setColumnStretch(1, 3)
            g.setColumnStretch(3, 1)

        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(300)
        self.timer.timeout.connect(self.alterado)
        for sinal in (
            self.busca.textChanged, self.categoria.alterado, self.ch_sub.toggled, self.ch_sem.toggled,
            self.tags.textChanged, self.c_modo_tags.currentIndexChanged, self.c_tipo.currentIndexChanged,
            self.s_dif_min.valueChanged, self.s_dif_max.valueChanged, self.fonte.textChanged,
            self.s_ano_min.valueChanged, self.s_ano_max.valueChanged,
        ):
            sinal.connect(self._mudou)
        self.ch_sem.toggled.connect(lambda v: self.categoria.setEnabled(not v))
        self.b_limpar.clicked.connect(self.limpar)
        ctx.sinais.tags_alteradas.connect(self.recarregar_sugestoes)
        ctx.sinais.questoes_alteradas.connect(self.recarregar_sugestoes)
        ctx.sinais.categorias_alteradas.connect(self.categoria.recarregar)
        self.recarregar_sugestoes()

    def _mudou(self, *_a) -> None:
        if not self._silencio:
            self.timer.start()

    def recarregar_sugestoes(self) -> None:
        self.tags.definir_sugestoes(self.ctx.repo.nomes_tags())
        self._completar_fonte.setModel(QStringListModel(self.ctx.repo.fontes(), self._completar_fonte))

    def filtro(self) -> Filtro:
        dmin, dmax = sorted((self.s_dif_min.value(), self.s_dif_max.value()))
        return Filtro(
            categoria_id=None if self.ch_sem.isChecked() else self.categoria.categoria_id,
            incluir_subcategorias=self.ch_sub.isChecked(),
            sem_categoria=self.ch_sem.isChecked(),
            tags=self.tags.tags(),
            tags_modo=self.c_modo_tags.currentData(),
            tipos=[self.c_tipo.currentData()] if self.c_tipo.currentData() else [],
            dif_min=dmin, dif_max=dmax,
            fonte=self.fonte.text(),
            ano_min=self.s_ano_min.value() or None,
            ano_max=self.s_ano_max.value() or None,
            texto=self.busca.text(),
        )

    def definir_filtro(self, f: Filtro) -> None:
        self._silencio = True
        try:
            self.busca.setText(f.texto)
            self.categoria.definir(f.categoria_id)
            self.ch_sub.setChecked(f.incluir_subcategorias)
            self.ch_sem.setChecked(f.sem_categoria)
            self.tags.definir_tags(f.tags)
            self.c_modo_tags.setCurrentIndex(max(0, self.c_modo_tags.findData(f.tags_modo)))
            self.c_tipo.setCurrentIndex(max(0, self.c_tipo.findData(f.tipos[0] if f.tipos else None)))
            self.s_dif_min.setValue(f.dif_min)
            self.s_dif_max.setValue(f.dif_max)
            self.fonte.setText(f.fonte)
            self.s_ano_min.setValue(f.ano_min or 0)
            self.s_ano_max.setValue(f.ano_max or 0)
        finally:
            self._silencio = False
        self.alterado.emit()

    def limpar(self) -> None:
        self.definir_filtro(Filtro())


COLUNAS = ["Nº", "Tipo", "Enunciado", "Categoria", "Tags", "Dif.", "Fonte", "Ano", "Alterada em"]
PAPEL_ORDENAR = Qt.ItemDataRole.UserRole + 10


class ModeloQuestoes(QAbstractTableModel):
    """Lista de questões; com ``marcavel`` a primeira coluna tem caixas de seleção."""

    marcacoes_mudaram = Signal()

    def __init__(self, parent=None, marcavel: bool = False):
        super().__init__(parent)
        self.linhas: list[ResumoQuestao] = []
        self.resumos: list[str] = []
        self.caminhos: dict[int, str] = {}
        self.marcavel = marcavel
        self.marcadas: set[int] = set()
        self.destacadas: set[int] = set()

    def definir(self, linhas: list[ResumoQuestao], caminhos: dict[int, str]) -> None:
        self.beginResetModel()
        self.linhas = linhas
        self.resumos = [texto_simples(r.enunciado, 140) for r in linhas]
        self.caminhos = caminhos
        ids = {r.id for r in linhas}
        self.marcadas &= ids
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.linhas)

    def columnCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return len(COLUNAS)

    def headerData(self, secao, orientacao, papel=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if orientacao == Qt.Orientation.Horizontal and papel == Qt.ItemDataRole.DisplayRole:
            return COLUNAS[secao]
        return None

    def flags(self, indice):
        f = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if self.marcavel and indice.column() == 0:
            f |= Qt.ItemFlag.ItemIsUserCheckable
        return f

    def data(self, indice, papel=Qt.ItemDataRole.DisplayRole):
        if not indice.isValid():
            return None
        r = self.linhas[indice.row()]
        col = indice.column()
        if papel == Qt.ItemDataRole.CheckStateRole and self.marcavel and col == 0:
            return Qt.CheckState.Checked if r.id in self.marcadas else Qt.CheckState.Unchecked
        if papel in (Qt.ItemDataRole.DisplayRole, PAPEL_ORDENAR):
            valores = [
                r.id, nome_tipo(r.tipo), self.resumos[indice.row()],
                self.caminhos.get(r.categoria_id, "") if r.categoria_id else "",
                ", ".join(r.tags), r.dificuldade, r.fonte, r.ano if r.ano else "", r.alterada_em,
            ]
            v = valores[col]
            if papel == PAPEL_ORDENAR:
                if col in (0, 5):
                    return v
                if col == 7:
                    return r.ano or 0
                return str(v).casefold()
            return v
        if papel == Qt.ItemDataRole.ToolTipRole and col == 2:
            return texto_simples(r.enunciado, 600)
        if papel == Qt.ItemDataRole.TextAlignmentRole and col in (0, 5, 7):
            return int(Qt.AlignmentFlag.AlignCenter)
        if papel == Qt.ItemDataRole.BackgroundRole and r.id in self.destacadas:
            from PySide6.QtGui import QColor

            return QColor("#e8f0fe")
        return None

    def setData(self, indice, valor, papel=Qt.ItemDataRole.EditRole) -> bool:  # noqa: N802
        if papel == Qt.ItemDataRole.CheckStateRole and self.marcavel and indice.column() == 0:
            qid = self.linhas[indice.row()].id
            if Qt.CheckState(valor) == Qt.CheckState.Checked:
                self.marcadas.add(qid)
            else:
                self.marcadas.discard(qid)
            self.dataChanged.emit(indice, indice, [papel])
            self.marcacoes_mudaram.emit()
            return True
        return False

    def marcar_todas(self, marcar: bool) -> None:
        if marcar:
            self.marcadas = {r.id for r in self.linhas}
        else:
            self.marcadas.clear()
        if self.linhas:
            self.dataChanged.emit(self.index(0, 0), self.index(len(self.linhas) - 1, 0))
        self.marcacoes_mudaram.emit()

    def id_na_linha(self, linha: int) -> int:
        return self.linhas[linha].id


class ProxyOrdenacao(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSortRole(PAPEL_ORDENAR)


def configurar_tabela(tabela, modelo: ModeloQuestoes) -> ProxyOrdenacao:
    from PySide6.QtWidgets import QAbstractItemView, QHeaderView

    proxy = ProxyOrdenacao(tabela)
    proxy.setSourceModel(modelo)
    tabela.setModel(proxy)
    tabela.setSortingEnabled(True)
    tabela.sortByColumn(0, Qt.SortOrder.DescendingOrder)
    tabela.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    tabela.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    tabela.setAlternatingRowColors(True)
    tabela.verticalHeader().setVisible(False)
    tabela.verticalHeader().setDefaultSectionSize(tabela.fontMetrics().height() + 8)
    tabela.setWordWrap(False)
    cab = tabela.horizontalHeader()
    cab.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    cab.setStretchLastSection(False)
    larguras = [60, 120, 380, 180, 140, 40, 120, 50, 130]
    for i, w in enumerate(larguras):
        tabela.setColumnWidth(i, w)
    cab.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
    return proxy
