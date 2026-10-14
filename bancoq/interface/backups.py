"""Diálogos de trava e de backups."""

from __future__ import annotations

import html
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFileDialog, QLabel, QListWidget, QListWidgetItem, QMessageBox,
    QPushButton, QVBoxLayout,
)

from ..nucleo.backup import criar_backup, escrever_zip, listar_backups
from ..nucleo.trava import InfoTrava

ABRIR_LEITURA, ABRIR_ASSIM_MESMO, CANCELAR = "leitura", "assim_mesmo", "cancelar"


def perguntar_trava(info: InfoTrava, pasta: Path, parent=None, mesmo_computador: bool = False) -> str:
    caixa = QMessageBox(parent)
    caixa.setWindowTitle("Banco em uso")
    caixa.setIcon(QMessageBox.Icon.Warning)
    if mesmo_computador:
        texto = ("Este banco já está aberto em outra janela do aplicativo <b>neste computador</b>.")
    else:
        quem = html.escape(info.computador) + (f" (usuário {html.escape(info.usuario)})" if info.usuario else "")
        quando = html.escape(info.horario_legivel()) if info.horario else "horário desconhecido"
        texto = (f"O banco em <code>{html.escape(str(pasta))}</code> parece estar aberto no computador "
                 f"<b>{quem}</b>, desde {quando}.")
    caixa.setText(texto)
    caixa.setInformativeText(
        "Se os dois computadores gravarem no banco, a sincronização pode perder alterações. "
        "Se o outro computador já fechou o aplicativo (ou travou), espere a sincronização terminar "
        "e abra assim mesmo."
    )
    leitura = caixa.addButton("Abrir só para leitura", QMessageBox.ButtonRole.AcceptRole)
    assim = caixa.addButton("Abrir assim mesmo", QMessageBox.ButtonRole.DestructiveRole)
    caixa.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
    caixa.setDefaultButton(leitura)
    caixa.exec()
    if caixa.clickedButton() is leitura:
        return ABRIR_LEITURA
    if caixa.clickedButton() is assim:
        return ABRIR_ASSIM_MESMO
    return CANCELAR


class DialogoBackups(QDialog):
    """Lista os backups e permite fazer um agora ou restaurar um deles."""

    def __init__(self, ctx, aplicativo, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.aplicativo = aplicativo
        self.setWindowTitle("Backups do banco")
        self.resize(620, 440)
        lay = QVBoxLayout(self)
        nota = QLabel(
            f"Um backup (banco, mídia, modelos e configurações num .zip) é feito automaticamente sempre que o "
            f"banco é aberto. São mantidos os últimos <b>{ctx.config.num_backups}</b> (altere em Configurações > Banco). "
            f"Pasta: <code>{html.escape(str(ctx.banco.pasta_backups))}</code>"
        )
        nota.setWordWrap(True)
        lay.addWidget(nota)
        self.lista = QListWidget()
        lay.addWidget(self.lista, 1)
        botoes = QDialogButtonBox()
        self.b_agora = botoes.addButton("Fazer backup agora", QDialogButtonBox.ButtonRole.ActionRole)
        self.b_restaurar = botoes.addButton("Restaurar…", QDialogButtonBox.ButtonRole.ActionRole)
        b_pasta = botoes.addButton("Abrir pasta", QDialogButtonBox.ButtonRole.ActionRole)
        botoes.addButton("Fechar", QDialogButtonBox.ButtonRole.RejectRole)
        botoes.rejected.connect(self.reject)
        self.b_agora.clicked.connect(self._agora)
        self.b_restaurar.clicked.connect(self._restaurar)
        b_pasta.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(ctx.banco.pasta_backups))))
        if ctx.somente_leitura:
            self.b_agora.setEnabled(False)
            self.b_restaurar.setEnabled(False)
        lay.addWidget(botoes)
        self._carregar()

    def _carregar(self) -> None:
        self.lista.clear()
        for b in listar_backups(self.ctx.banco):
            it = QListWidgetItem(b.descricao + ("   (antes de restaurar)" if "antes-de-restaurar" in b.caminho.name else ""))
            it.setData(Qt.ItemDataRole.UserRole, str(b.caminho))
            self.lista.addItem(it)
        if self.lista.count():
            self.lista.setCurrentRow(0)

    def _agora(self) -> None:
        try:
            criar_backup(self.ctx.banco, self.ctx.config.num_backups)
        except OSError as e:
            QMessageBox.critical(self, "Backup", f"Não foi possível criar o backup: {e}")
        self._carregar()

    def _restaurar(self) -> None:
        it = self.lista.currentItem()
        if it is None:
            return
        r = QMessageBox.question(
            self, "Restaurar backup",
            f"Restaurar o backup de {it.text().split(' — ')[0]}?\n\n"
            "O banco atual será substituído (antes disso, é feito um backup do estado atual). "
            "As telas serão recarregadas.",
        )
        if r != QMessageBox.StandardButton.Yes:
            return
        self.accept()
        self.aplicativo.restaurar_backup(Path(it.data(Qt.ItemDataRole.UserRole)))


def exportar_banco(ctx, parent=None) -> None:
    sugestao = str(Path.home() / f"{ctx.banco.nome}.zip")
    arq, _ = QFileDialog.getSaveFileName(parent, "Exportar banco inteiro", sugestao, "Arquivo zip (*.zip)")
    if not arq:
        return
    if not arq.lower().endswith(".zip"):
        arq += ".zip"
    try:
        escrever_zip(ctx.banco, Path(arq))
    except OSError as e:
        QMessageBox.critical(parent, "Exportar banco", f"Erro: {e}")
        return
    QMessageBox.information(parent, "Exportar banco", f"Banco exportado para\n{arq}")
