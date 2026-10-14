"""Campo de tags com autocompletar e gerenciador de tags."""

from __future__ import annotations

from PySide6.QtCore import QStringListModel, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QCompleter, QDialog, QDialogButtonBox, QHBoxLayout, QInputDialog, QLabel,
    QLineEdit, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from ..nucleo.banco import ErroBanco
from ..nucleo.repositorio import Repositorio


def separar_tags(texto: str) -> list[str]:
    vistas: list[str] = []
    for t in texto.replace(";", ",").split(","):
        t = " ".join(t.split())
        if t and t.casefold() not in {v.casefold() for v in vistas}:
            vistas.append(t)
    return vistas


class _CompletarUltima(QCompleter):
    """Completa só a última tag da lista separada por vírgulas."""

    def splitPath(self, caminho: str) -> list[str]:  # noqa: N802
        return [caminho.split(",")[-1].strip()]

    def pathFromIndex(self, indice) -> str:  # noqa: N802
        completada = super().pathFromIndex(indice)
        campo = self.widget()
        partes = campo.text().split(",")[:-1] if campo else []
        partes = [p.strip() for p in partes if p.strip()]
        return ", ".join(partes + [completada]) + ", "


class CampoTags(QLineEdit):
    alterado = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPlaceholderText("tags separadas por vírgula (Enter ou vírgula para a próxima)")
        self.modelo = QStringListModel(self)
        self.completar = _CompletarUltima(self.modelo, self)
        self.completar.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completar.setFilterMode(Qt.MatchFlag.MatchContains)
        self.setCompleter(self.completar)
        self.textChanged.connect(self.alterado)

    def definir_sugestoes(self, nomes: list[str]) -> None:
        self.modelo.setStringList(sorted(nomes, key=str.casefold))

    def tags(self) -> list[str]:
        return separar_tags(self.text())

    def definir_tags(self, tags: list[str]) -> None:
        self.setText(", ".join(tags))


class GerenciadorTags(QDialog):
    """Renomear, mesclar e excluir tags (cada ação pede confirmação)."""

    alterou = Signal()

    def __init__(self, repo: Repositorio, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.setWindowTitle("Tags")
        self.resize(460, 520)
        lay = QVBoxLayout(self)
        self.busca = QLineEdit()
        self.busca.setPlaceholderText("Procurar…")
        self.busca.setClearButtonEnabled(True)
        self.busca.textChanged.connect(self._filtrar)
        lay.addWidget(self.busca)
        self.tabela = QTableWidget(0, 2)
        self.tabela.setHorizontalHeaderLabels(["Tag", "Questões"])
        self.tabela.horizontalHeader().setStretchLastSection(False)
        self.tabela.setColumnWidth(0, 300)
        self.tabela.verticalHeader().setVisible(False)
        self.tabela.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabela.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabela.setSortingEnabled(True)
        lay.addWidget(self.tabela, 1)
        linha = QHBoxLayout()
        for texto, func in (("Renomear…", self._renomear), ("Mesclar selecionadas…", self._mesclar),
                            ("Excluir selecionadas", self._excluir)):
            b = QPushButton(texto)
            b.clicked.connect(func)
            b.setEnabled(not repo.somente_leitura)
            linha.addWidget(b)
        lay.addLayout(linha)
        nota = QLabel("Para mesclar, selecione várias tags (Ctrl+clique) e escolha a que vai ficar.")
        nota.setWordWrap(True)
        nota.setStyleSheet("color: gray;")
        lay.addWidget(nota)
        fechar = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        fechar.rejected.connect(self.reject)
        lay.addWidget(fechar)
        self._recarregar()

    def _recarregar(self) -> None:
        self.tabela.setSortingEnabled(False)
        tags = self.repo.tags()
        self.tabela.setRowCount(len(tags))
        for i, t in enumerate(tags):
            it = QTableWidgetItem(t.nome)
            it.setData(Qt.ItemDataRole.UserRole, t.id)
            self.tabela.setItem(i, 0, it)
            n = QTableWidgetItem()
            n.setData(Qt.ItemDataRole.DisplayRole, t.quantidade)
            self.tabela.setItem(i, 1, n)
        self.tabela.setSortingEnabled(True)
        self._filtrar(self.busca.text())

    def _filtrar(self, texto: str) -> None:
        texto = texto.strip().casefold()
        for i in range(self.tabela.rowCount()):
            it = self.tabela.item(i, 0)
            self.tabela.setRowHidden(i, bool(texto) and texto not in it.text().casefold())

    def _selecionadas(self) -> list[tuple[int, str]]:
        linhas = sorted({i.row() for i in self.tabela.selectedIndexes()})
        return [(self.tabela.item(r, 0).data(Qt.ItemDataRole.UserRole), self.tabela.item(r, 0).text())
                for r in linhas]

    def _executar(self, func, *args) -> None:
        try:
            func(*args)
        except ErroBanco as e:
            QMessageBox.warning(self, "Tags", str(e))
            return
        self._recarregar()
        self.alterou.emit()

    def _renomear(self) -> None:
        sel = self._selecionadas()
        if len(sel) != 1:
            QMessageBox.information(self, "Tags", "Selecione uma tag.")
            return
        tid, nome = sel[0]
        novo, ok = QInputDialog.getText(self, "Renomear tag", "Novo nome:", text=nome)
        if ok and novo.strip() and novo.strip() != nome:
            self._executar(self.repo.renomear_tag, tid, novo)

    def _mesclar(self) -> None:
        sel = self._selecionadas()
        if len(sel) < 2:
            QMessageBox.information(self, "Tags", "Selecione duas ou mais tags para mesclar.")
            return
        nomes = [n for _, n in sel]
        destino, ok = QInputDialog.getItem(self, "Mesclar tags", "Tag que vai ficar:", nomes, 0, False)
        if not ok:
            return
        destino_id = next(t for t, n in sel if n == destino)
        outras = [n for n in nomes if n != destino]
        r = QMessageBox.question(
            self, "Mesclar tags",
            f"As questões com {', '.join(outras)} passarão a ter “{destino}”, e essas tags serão excluídas. Continuar?",
        )
        if r == QMessageBox.StandardButton.Yes:
            self._executar(self.repo.mesclar_tags, [t for t, _ in sel], destino_id)

    def _excluir(self) -> None:
        sel = self._selecionadas()
        if not sel:
            return
        r = QMessageBox.question(
            self, "Excluir tags",
            f"Excluir {len(sel)} tag(s)? As questões continuam no banco, só perdem essas tags.",
        )
        if r == QMessageBox.StandardButton.Yes:
            def excluir_todas():
                for tid, _ in sel:
                    self.repo.excluir_tag(tid)
            self._executar(excluir_todas)
