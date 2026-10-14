"""Padrão: classe ``exam`` (\\question, \\choice, \\CorrectChoice, solution)."""

from __future__ import annotations

import re

from .base import (
    PadraoImportacao, QuestaoImportada, ambientes, analisar_bloco, dividir_por_comando, ler_grupo,
    ler_opcional, limpar_texto, registrar,
)

RE_QUESTION = re.compile(r"\\(?:question|titledquestion)(?![A-Za-z@])")
RE_FILLIN = re.compile(r"\\fillin(?![A-Za-z@])")

ROTULOS_PARTES = {"parts": r"(\alph*)", "subparts": r"\roman*.", "subsubparts": r"\greek*."}


def converter_partes(texto: str) -> str:
    """\\begin{parts}\\part … → enumerate (o ambiente parts só existe na classe exam)."""
    for amb, comando in (("subsubparts", "subsubpart"), ("subparts", "subpart"), ("parts", "part")):
        rotulo = ROTULOS_PARTES[amb].replace(r"\greek*", r"\arabic*")
        texto = re.sub(r"\\begin\{" + amb + r"\}", r"\\begin{enumerate}[label=" + rotulo.replace("\\", "\\\\") + "]", texto)
        texto = re.sub(r"\\end\{" + amb + r"\}", r"\\end{enumerate}", texto)
        texto = re.sub(r"\\" + comando + r"(?![A-Za-z@])\s*(\[[^\]]*\])?", r"\\item ", texto)
    return texto


def extrair_fillin(texto: str) -> tuple[str, str]:
    """\\fillin[resposta][largura] vira uma linha em branco; devolve (texto, resposta)."""
    respostas = []
    saida = []
    pos = 0
    for m in RE_FILLIN.finditer(texto):
        saida.append(texto[pos:m.start()])
        resp, j = ler_opcional(texto, m.end())
        _, j = ler_opcional(texto, j)
        if resp:
            respostas.append(resp.strip())
        saida.append(r"\underline{\hspace{3cm}}")
        pos = j
    saida.append(texto[pos:])
    return "".join(saida), "; ".join(respostas)


@registrar
class PadraoExam(PadraoImportacao):
    nome = "Classe exam"
    descricao = "\\question, \\choice, \\CorrectChoice e solution (classe exam)"

    def pontuar(self, corpo: str) -> int:
        return 10 * len(RE_QUESTION.findall(corpo))

    def separar(self, corpo: str) -> list[QuestaoImportada]:
        regioes = [corpo[ic:fc] for _, _, ic, fc, _ in ambientes(corpo, ("questions",))] or [corpo]
        questoes = []
        for regiao in regioes:
            for cmd, _pontos, texto in dividir_por_comando(regiao, ("question", "titledquestion")):
                if not cmd:
                    continue
                prefixo = ""
                if cmd == "titledquestion":
                    titulo, j = ler_grupo(texto, 0)
                    _, j = ler_opcional(texto, j)
                    texto = texto[j:]
                    if titulo:
                        prefixo = f"\\textbf{{{titulo.strip()}}}\n\n"
                texto, resposta = extrair_fillin(texto)
                q = analisar_bloco(texto)
                # "parts" é convertido depois da análise para não virar alternativas
                q.enunciado = limpar_texto(prefixo + converter_partes(q.enunciado))
                q.resolucao = converter_partes(q.resolucao)
                if resposta and q.tipo == "discursiva":
                    q.tipo = "curta"
                    q.resposta_curta = resposta
                questoes.append(q)
        return questoes
