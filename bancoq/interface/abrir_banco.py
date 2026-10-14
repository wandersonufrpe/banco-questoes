"""Diálogo inicial: criar ou abrir um banco de questões."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMessageBox,
    QPushButton, QVBoxLayout,
)

from ..nucleo.banco import Banco


def escolher_pasta_novo_banco(parent) -> Path | None:
    pasta = QFileDialog.getExistingDirectory(
        parent, "Pasta do novo banco (de preferência dentro da pasta sincronizada)"
    )
    if not pasta:
        return None
    p = Path(pasta)
    if Banco.e_banco(p):
        QMessageBox.information(parent, "Novo banco", "Esta pasta já contém um banco. Ele será aberto.")
        return p
    if any(p.iterdir()):
        caixa = QMessageBox(parent)
        caixa.setWindowTitle("Novo banco")
        caixa.setIcon(QMessageBox.Icon.Question)
        caixa.setText(
            f"A pasta “{p.name}” não está vazia.\n\n"
            "Criar uma subpasta “BancoQuestoes” dentro dela para o novo banco?"
        )
        sub = caixa.addButton("Criar subpasta", QMessageBox.ButtonRole.AcceptRole)
        aqui = caixa.addButton("Usar esta pasta", QMessageBox.ButtonRole.DestructiveRole)
        caixa.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
        caixa.exec()
        if caixa.clickedButton() is sub:
            return p / "BancoQuestoes"
        if caixa.clickedButton() is not aqui:
            return None
    return p


def escolher_pasta_banco_existente(parent) -> Path | None:
    pasta = QFileDialog.getExistingDirectory(parent, "Pasta do banco de questões")
    if not pasta:
        return None
    p = Path(pasta)
    if not Banco.e_banco(p):
        QMessageBox.warning(parent, "Abrir banco", f"A pasta “{p}” não contém um banco de questões (banco.sqlite3).")
        return None
    return p


class DialogoAbrirBanco(QDialog):
    """Resultado: ``self.pasta`` e ``self.criar`` (True = criar banco novo)."""

    def __init__(self, recentes: list[str], parent=None, mensagem: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Banco de Questões")
        self.resize(560, 380)
        self.pasta: Path | None = None
        self.criar = False
        lay = QVBoxLayout(self)
        titulo = QLabel("<h2>Banco de Questões</h2>")
        lay.addWidget(titulo)
        texto = QLabel(
            mensagem or
            "Escolha a pasta do banco de questões. Para usar em mais de um computador, "
            "crie o banco dentro da pasta sincronizada com o Google Drive."
        )
        texto.setWordWrap(True)
        lay.addWidget(texto)

        existentes = [r for r in recentes if Banco.e_banco(r)]
        if existentes:
            lay.addWidget(QLabel("Bancos recentes (clique duas vezes para abrir):"))
            self.lista = QListWidget()
            for r in existentes:
                it = QListWidgetItem(r)
                it.setData(Qt.ItemDataRole.UserRole, r)
                self.lista.addItem(it)
            self.lista.itemDoubleClicked.connect(self._recente)
            lay.addWidget(self.lista, 1)
        else:
            lay.addStretch(1)

        botoes = QHBoxLayout()
        b_novo = QPushButton("Criar novo banco…")
        b_abrir = QPushButton("Abrir banco existente…")
        b_sair = QPushButton("Sair")
        b_novo.clicked.connect(self._novo)
        b_abrir.clicked.connect(self._abrir)
        b_sair.clicked.connect(self.reject)
        botoes.addWidget(b_novo)
        botoes.addWidget(b_abrir)
        botoes.addStretch(1)
        botoes.addWidget(b_sair)
        lay.addLayout(botoes)

    def _recente(self, item: QListWidgetItem) -> None:
        self.pasta = Path(item.data(Qt.ItemDataRole.UserRole))
        self.criar = False
        self.accept()

    def _novo(self) -> None:
        p = escolher_pasta_novo_banco(self)
        if p is not None:
            self.pasta = p
            self.criar = not Banco.e_banco(p)
            self.accept()

    def _abrir(self) -> None:
        p = escolher_pasta_banco_existente(self)
        if p is not None:
            self.pasta = p
            self.criar = False
            self.accept()
