"""Padrão: divisão manual por linhas separadoras ``%%%`` (ou um bloco só)."""

from __future__ import annotations

from .base import SEPARADOR, PadraoImportacao, QuestaoImportada, analisar_bloco, registrar


@registrar
class PadraoManual(PadraoImportacao):
    nome = "Separador manual"
    descricao = "Questões separadas por linhas contendo só %%% (sem separador, tudo vira uma questão)"

    def pontuar(self, corpo: str) -> int:
        n = corpo.count(SEPARADOR)
        return 5 * n + 1 if n else 1

    def separar(self, corpo: str) -> list[QuestaoImportada]:
        blocos = [b for b in corpo.split(SEPARADOR) if b.strip()]
        return [analisar_bloco(b) for b in blocos]
