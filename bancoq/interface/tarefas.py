"""Execução de funções demoradas em segundo plano (sem travar a interface)."""

from __future__ import annotations

import traceback
from typing import Any, Callable

from PySide6.QtCore import QThread, Signal

_ativas: set["Tarefa"] = set()


class Tarefa(QThread):
    concluida = Signal(object)
    falhou = Signal(str)

    def __init__(self, funcao: Callable[[], Any], parent=None):
        super().__init__(parent)
        self.funcao = funcao
        _ativas.add(self)
        self.finished.connect(self._fim)

    def run(self) -> None:
        try:
            resultado = self.funcao()
        except Exception:  # noqa: BLE001
            self.falhou.emit(traceback.format_exc())
            return
        self.concluida.emit(resultado)

    def _fim(self) -> None:
        _ativas.discard(self)
        self.deleteLater()


def executar(funcao: Callable[[], Any], ao_concluir: Callable[[Any], None],
             ao_falhar: Callable[[str], None] | None = None, parent=None) -> Tarefa:
    t = Tarefa(funcao, parent)
    t.concluida.connect(ao_concluir)
    if ao_falhar is not None:
        t.falhou.connect(ao_falhar)
    t.start()
    return t


def aguardar_todas(ms: int = 3000) -> None:
    for t in list(_ativas):
        t.wait(ms)
