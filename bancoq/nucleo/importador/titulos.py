"""Padrão: questões precedidas de um título "Questão 1", "Questão 2"…"""

from __future__ import annotations

import re

from .base import PadraoImportacao, QuestaoImportada, analisar_bloco, registrar

RE_TITULO = re.compile(
    r"(?:^|\n)[ \t]*(?:"
    r"\\(?:sub)*section\*?\s*\{\s*Quest[ãa]o[^}]*\}"
    r"|\\(?:textbf|paragraph\*?|noindent\s*\\textbf)\s*\{\s*Quest[ãa]o\s*\d+[^}]*\}"
    r"|Quest[ãa]o\s+\d+\s*(?:[.:)\-–—]|\n)"
    r")",
    re.IGNORECASE,
)


@registrar
class PadraoTitulos(PadraoImportacao):
    nome = "Títulos “Questão N”"
    descricao = "Cada questão começa com um título como \\textbf{Questão 1} ou \\section*{Questão 2}"

    def pontuar(self, corpo: str) -> int:
        n = len(RE_TITULO.findall(corpo))
        return 4 * n if n >= 2 else 0

    def separar(self, corpo: str) -> list[QuestaoImportada]:
        marcas = list(RE_TITULO.finditer(corpo))
        questoes = []
        for k, m in enumerate(marcas):
            fim = marcas[k + 1].start() if k + 1 < len(marcas) else len(corpo)
            questoes.append(analisar_bloco(corpo[m.end():fim]))
        return questoes
