"""Árvore de categorias: seletor (cadastro/filtros) e gerenciador."""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMessageBox,
    QPushButton, QToolButton, QTreeWidget, QTreeWidgetItem, QTreeWidgetItemIterator, QVBoxLayout,
    QWidget,
)

from ..nucleo.banco import ErroBanco
from ..nucleo.entidades import Categoria
from ..nucleo.repositorio import CategoriaNova, Repositorio

PAPEL_ID = Qt.ItemDataRole.UserRole
PAPEL_NOVA = Qt.ItemDataRole.UserRole + 1


def preencher_arvore(arvore: QTreeWidget, categorias: list[Categoria],
                     contagem: dict | None = None) -> dict[int, QTreeWidgetItem]:
    arvore.clear()
    por_pai: dict[int | None, list[Categoria]] = {}
    ids = {c.id for c in categorias}
    for c in categorias:
        pai = c.pai_id if c.pai_id in ids else None
        por_pai.setdefault(pai, []).append(c)
    itens: dict[int, QTreeWidgetItem] = {}

    def adicionar(pai_item, pai_id):
        for c in sorted(por_pai.get(pai_id, []), key=lambda c: c.nome.casefold()):
            if c.id in itens:
                continue
            it = QTreeWidgetItem([c.nome])
            it.setData(0, PAPEL_ID, c.id)
            if contagem is not None:
                it.setText(1, str(contagem.get(c.id, 0)))
                it.setTextAlignment(1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if pai_item is None:
                arvore.addTopLevelItem(it)
            else:
                pai_item.addChild(it)
            itens[c.id] = it
            adicionar(it, c.id)

    adicionar(None, None)
    return itens


def filtrar_arvore(arvore: QTreeWidget, texto: str) -> None:
    texto = texto.strip().casefold()

    def visitar(item: QTreeWidgetItem) -> bool:
        visivel_filho = False
        for i in range(item.childCount()):
            visivel_filho |= visitar(item.child(i))
        casa = not texto or texto in item.text(0).casefold()
        item.setHidden(not (casa or visivel_filho))
        if texto and visivel_filho:
            item.setExpanded(True)
        return casa or visivel_filho

    for i in range(arvore.topLevelItemCount()):
        visitar(arvore.topLevelItem(i))


class DialogoEscolherCategoria(QDialog):
    """Escolhe uma categoria; permite criar novas (só gravadas ao salvar a questão)."""

    def __init__(self, repo: Repositorio, atual_id: int | None, atual_nova: CategoriaNova | None,
                 parent=None, permitir_criar: bool = True, titulo: str = "Escolher categoria"):
        super().__init__(parent)
        self.setWindowTitle(titulo)
        self.resize(420, 520)
        self.repo = repo
        self.resultado_id: int | None = None
        self.resultado_nova: CategoriaNova | None = None

        lay = QVBoxLayout(self)
        self.busca = QLineEdit()
        self.busca.setPlaceholderText("Procurar categoria…")
        self.busca.setClearButtonEnabled(True)
        lay.addWidget(self.busca)
        self.arvore = QTreeWidget()
        self.arvore.setHeaderHidden(True)
        lay.addWidget(self.arvore, 1)
        self.itens = preencher_arvore(self.arvore, repo.categorias())
        self.busca.textChanged.connect(lambda t: filtrar_arvore(self.arvore, t))

        if permitir_criar:
            linha = QHBoxLayout()
            b1 = QPushButton("Nova categoria")
            b1.setToolTip("Cria uma categoria no nível principal")
            b1.clicked.connect(lambda: self._nova(raiz=True))
            b2 = QPushButton("Nova subcategoria")
            b2.setToolTip("Cria uma subcategoria dentro da categoria selecionada")
            b2.clicked.connect(lambda: self._nova(raiz=False))
            linha.addWidget(b1)
            linha.addWidget(b2)
            lay.addLayout(linha)
            nota = QLabel("Categorias novas aparecem em itálico e só são gravadas quando a questão for salva.")
            nota.setWordWrap(True)
            nota.setStyleSheet("color: gray; font-size: 9pt;")
            lay.addWidget(nota)

        botoes = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.b_sem = botoes.addButton("Sem categoria", QDialogButtonBox.ButtonRole.ResetRole)
        botoes.accepted.connect(self._aceitar)
        botoes.rejected.connect(self.reject)
        self.b_sem.clicked.connect(self._sem_categoria)
        lay.addWidget(botoes)
        self.arvore.itemDoubleClicked.connect(lambda *_: self._aceitar())

        # restaura a seleção atual
        if atual_nova is not None:
            pai = self.itens.get(atual_nova.pai_id) if atual_nova.pai_id is not None else None
            it = None
            for nome in atual_nova.nomes:
                it = self._criar_item_novo(pai, nome)
                pai = it
            if it is not None:
                self.arvore.setCurrentItem(it)
        elif atual_id is not None and atual_id in self.itens:
            self.arvore.setCurrentItem(self.itens[atual_id])
        self.busca.setFocus()

    def _criar_item_novo(self, pai: QTreeWidgetItem | None, nome: str) -> QTreeWidgetItem:
        # reaproveita item com o mesmo nome no mesmo nível
        filhos = [pai.child(i) for i in range(pai.childCount())] if pai else [
            self.arvore.topLevelItem(i) for i in range(self.arvore.topLevelItemCount())
        ]
        for f in filhos:
            if f.text(0).casefold() == nome.casefold():
                return f
        it = QTreeWidgetItem([nome])
        it.setData(0, PAPEL_NOVA, True)
        fonte = QFont(it.font(0))
        fonte.setItalic(True)
        it.setFont(0, fonte)
        it.setToolTip(0, "Categoria nova (será criada ao salvar a questão)")
        if pai is None:
            self.arvore.addTopLevelItem(it)
        else:
            pai.addChild(it)
            pai.setExpanded(True)
        return it

    def _nova(self, raiz: bool) -> None:
        pai = None if raiz else self.arvore.currentItem()
        if not raiz and pai is None:
            QMessageBox.information(self, "Nova subcategoria", "Selecione primeiro a categoria-mãe.")
            return
        nome, ok = QInputDialog.getText(self, "Nova categoria", "Nome:")
        if ok and nome.strip():
            it = self._criar_item_novo(pai, nome.strip())
            self.busca.clear()
            self.arvore.setCurrentItem(it)

    def _sem_categoria(self) -> None:
        self.resultado_id = None
        self.resultado_nova = None
        self.accept()

    def _aceitar(self) -> None:
        it = self.arvore.currentItem()
        if it is None:
            self._sem_categoria()
            return
        if it.data(0, PAPEL_NOVA):
            nomes = []
            atual = it
            while atual is not None and atual.data(0, PAPEL_NOVA):
                nomes.insert(0, atual.text(0))
                atual = atual.parent()
            pai_id = atual.data(0, PAPEL_ID) if atual is not None else None
            self.resultado_id = None
            self.resultado_nova = CategoriaNova(pai_id, nomes)
        else:
            self.resultado_id = it.data(0, PAPEL_ID)
            self.resultado_nova = None
        self.accept()


class SeletorCategoria(QWidget):
    """Mostra a categoria escolhida e abre a árvore para trocar."""

    alterado = Signal()

    def __init__(self, repo: Repositorio, parent=None, permitir_criar: bool = True,
                 texto_vazio: str = "(sem categoria)"):
        super().__init__(parent)
        self.repo = repo
        self.permitir_criar = permitir_criar
        self.texto_vazio = texto_vazio
        self.categoria_id: int | None = None
        self.nova: CategoriaNova | None = None
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.campo = QLineEdit()
        self.campo.setReadOnly(True)
        self.campo.setPlaceholderText(texto_vazio)
        self.campo.setToolTip("Clique para escolher a categoria")
        self.campo.installEventFilter(self)
        lay.addWidget(self.campo, 1)
        b = QToolButton()
        b.setText("Escolher…")
        b.clicked.connect(self.escolher)
        lay.addWidget(b)
        self.b_limpar = QToolButton()
        self.b_limpar.setText("✕")
        self.b_limpar.setToolTip("Sem categoria")
        self.b_limpar.clicked.connect(lambda: self.definir(None))
        lay.addWidget(self.b_limpar)

    def eventFilter(self, obj, ev) -> bool:  # noqa: N802
        if obj is self.campo and ev.type() == QEvent.Type.MouseButtonRelease and self.isEnabled():
            self.escolher()
            return True
        return super().eventFilter(obj, ev)

    def escolher(self) -> None:
        d = DialogoEscolherCategoria(self.repo, self.categoria_id, self.nova, self, self.permitir_criar)
        if d.exec():
            self.categoria_id, self.nova = d.resultado_id, d.resultado_nova
            self._atualizar_texto()
            self.alterado.emit()

    def definir(self, categoria_id: int | None, nova: CategoriaNova | None = None) -> None:
        self.categoria_id, self.nova = categoria_id, nova
        self._atualizar_texto()
        self.alterado.emit()

    def _atualizar_texto(self) -> None:
        if self.nova is not None:
            base = ""
            if self.nova.pai_id is not None:
                base = self.repo.caminhos_categorias().get(self.nova.pai_id, "") + " > "
            self.campo.setText(base + " > ".join(self.nova.nomes) + "  (nova)")
        elif self.categoria_id is not None:
            self.campo.setText(self.repo.caminhos_categorias().get(self.categoria_id, "(categoria excluída)"))
        else:
            self.campo.clear()

    def recarregar(self) -> None:
        if self.categoria_id is not None and self.categoria_id not in self.repo.caminhos_categorias():
            self.categoria_id = None
        self._atualizar_texto()

    def estado(self) -> tuple:
        return (self.categoria_id, tuple(self.nova.nomes) if self.nova else None,
                self.nova.pai_id if self.nova else None)


class GerenciadorCategorias(QDialog):
    """Renomear, mover, mesclar e excluir categorias (cada ação pede confirmação)."""

    alterou = Signal()

    def __init__(self, repo: Repositorio, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.setWindowTitle("Categorias")
        self.resize(520, 560)
        lay = QVBoxLayout(self)
        self.busca = QLineEdit()
        self.busca.setPlaceholderText("Procurar…")
        self.busca.setClearButtonEnabled(True)
        lay.addWidget(self.busca)
        self.arvore = QTreeWidget()
        self.arvore.setHeaderLabels(["Categoria", "Questões"])
        self.arvore.setColumnWidth(0, 360)
        lay.addWidget(self.arvore, 1)
        self.busca.textChanged.connect(lambda t: filtrar_arvore(self.arvore, t))

        linha = QHBoxLayout()
        for texto, func in (
            ("Nova…", self._nova), ("Nova subcategoria…", self._nova_sub), ("Renomear…", self._renomear),
            ("Mover para…", self._mover), ("Mesclar com…", self._mesclar), ("Excluir", self._excluir),
        ):
            b = QPushButton(texto)
            b.clicked.connect(func)
            b.setEnabled(not repo.somente_leitura)
            linha.addWidget(b)
        lay.addLayout(linha)
        nota = QLabel(
            "Excluir uma categoria não apaga questões: elas e as subcategorias passam para a categoria-mãe."
        )
        nota.setWordWrap(True)
        nota.setStyleSheet("color: gray;")
        lay.addWidget(nota)
        fechar = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        fechar.rejected.connect(self.reject)
        lay.addWidget(fechar)
        self._recarregar()

    def _recarregar(self, selecionar: int | None = None) -> None:
        itens = preencher_arvore(self.arvore, self.repo.categorias(), self.repo.contagem_por_categoria())
        self.arvore.expandToDepth(0)
        if selecionar in itens:
            self.arvore.setCurrentItem(itens[selecionar])
        filtrar_arvore(self.arvore, self.busca.text())

    def _atual(self) -> int | None:
        it = self.arvore.currentItem()
        return it.data(0, PAPEL_ID) if it else None

    def _executar(self, func, *args, selecionar=None) -> None:
        try:
            r = func(*args)
        except ErroBanco as e:
            QMessageBox.warning(self, "Categorias", str(e))
            return
        self._recarregar(selecionar if selecionar is not None else (r if isinstance(r, int) else None))
        self.alterou.emit()

    def _nova(self, pai: int | None = None) -> None:
        nome, ok = QInputDialog.getText(self, "Nova categoria", "Nome:")
        if ok and nome.strip():
            self._executar(self.repo.criar_categoria, nome, pai)

    def _nova_sub(self) -> None:
        cid = self._atual()
        if cid is None:
            QMessageBox.information(self, "Categorias", "Selecione a categoria-mãe.")
            return
        self._nova(cid)

    def _renomear(self) -> None:
        cid = self._atual()
        if cid is None:
            return
        nome, ok = QInputDialog.getText(self, "Renomear", "Novo nome:", text=self.arvore.currentItem().text(0))
        if ok and nome.strip():
            self._executar(self.repo.renomear_categoria, cid, nome, selecionar=cid)

    def _escolher_destino(self, titulo: str, excluir: int) -> tuple[bool, int | None]:
        d = DialogoEscolherCategoria(self.repo, None, None, self, permitir_criar=False, titulo=titulo)
        d.b_sem.setText("Nível principal")
        if not d.exec():
            return False, None
        if d.resultado_id == excluir:
            return False, None
        return True, d.resultado_id

    def _mover(self) -> None:
        cid = self._atual()
        if cid is None:
            return
        ok, destino = self._escolher_destino("Mover para dentro de…", cid)
        if ok:
            self._executar(self.repo.mover_categoria, cid, destino, selecionar=cid)

    def _mesclar(self) -> None:
        cid = self._atual()
        if cid is None:
            return
        ok, destino = self._escolher_destino("Mesclar com (destino)…", cid)
        if not ok or destino is None:
            return
        caminhos = self.repo.caminhos_categorias()
        r = QMessageBox.question(
            self, "Mesclar categorias",
            f"Todas as questões e subcategorias de\n“{caminhos.get(cid)}”\nirão para\n“{caminhos.get(destino)}”,"
            " e a primeira será excluída. Continuar?",
        )
        if r == QMessageBox.StandardButton.Yes:
            self._executar(self.repo.mesclar_categorias, cid, destino, selecionar=destino)

    def _excluir(self) -> None:
        cid = self._atual()
        if cid is None:
            return
        caminho = self.repo.caminhos_categorias().get(cid)
        r = QMessageBox.question(
            self, "Excluir categoria",
            f"Excluir “{caminho}”?\nAs questões e subcategorias dela passarão para a categoria-mãe.",
        )
        if r == QMessageBox.StandardButton.Yes:
            self._executar(self.repo.excluir_categoria, cid)
