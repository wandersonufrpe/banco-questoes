"""Padrão: questões como itens de um ``enumerate`` (alternativas numa lista aninhada)."""

from __future__ import annotations

from .base import (
    PadraoImportacao, QuestaoImportada, ambientes, analisar_bloco, dividir_por_comando, ler_opcional,
    registrar,
)


@registrar
class PadraoEnumerate(PadraoImportacao):
    nome = "Lista enumerate"
    descricao = "Cada \\item de um enumerate é uma questão; uma lista aninhada no fim vira alternativas"

    def _itens(self, corpo: str) -> list[str]:
        textos = []
        for _, _, ic, fc, _ in ambientes(corpo, ("enumerate",)):
            conteudo = corpo[ic:fc]
            _, j = ler_opcional(conteudo, 0)
            for cmd, _opt, texto in dividir_por_comando(conteudo[j:], ("item",)):
                if cmd:
                    textos.append(texto)
        return textos

    def pontuar(self, corpo: str) -> int:
        return 3 * len(self._itens(corpo))

    def separar(self, corpo: str) -> list[QuestaoImportada]:
        return [analisar_bloco(t) for t in self._itens(corpo)]
