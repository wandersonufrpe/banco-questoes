"""Modelos de prova: arquivos .tex com marcadores ``<<nome>>``.

Os modelos de um banco ficam em ``<banco>/modelos``. O modelo genérico
embutido no aplicativo é copiado para lá quando o banco é criado e serve de
reserva se a pasta estiver vazia.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from ..caminhos import recurso

MARCADORES = (
    "titulo", "disciplina", "turma", "professor", "data",
    "versao", "instrucoes", "macros", "questoes",
)
RE_MARCADOR = re.compile(r"<<([A-Za-z_]+)>>")
NOME_GENERICO = "generico.tex"

# ambientes e comandos que o aplicativo usa ao escrever as questões
AMBIENTES_USADOS = ("questao", "alternativas", "afirmativas")
COMANDOS_USADOS = ("alt", "afirmativa", "espacoresposta", "respostacurta")


def texto_generico() -> str:
    return recurso("modelos", NOME_GENERICO).read_text(encoding="utf-8")


def copiar_modelo_generico(pasta_modelos: Path) -> None:
    pasta_modelos = Path(pasta_modelos)
    pasta_modelos.mkdir(parents=True, exist_ok=True)
    destino = pasta_modelos / NOME_GENERICO
    if not destino.exists():
        shutil.copyfile(recurso("modelos", NOME_GENERICO), destino)


def listar_modelos(pasta_modelos: Path) -> list[str]:
    pasta_modelos = Path(pasta_modelos)
    nomes = sorted(p.name for p in pasta_modelos.glob("*.tex")) if pasta_modelos.exists() else []
    return nomes or [NOME_GENERICO]


def ler_modelo(pasta_modelos: Path, nome: str) -> str:
    p = Path(pasta_modelos) / nome
    if p.is_file():
        return p.read_text(encoding="utf-8")
    return texto_generico()


def nome_arquivo_valido(nome: str) -> str:
    nome = re.sub(r"[^\w\-. ]", "_", nome.strip()).strip(". ")
    if not nome:
        raise ValueError("Nome de modelo inválido.")
    if not nome.lower().endswith(".tex"):
        nome += ".tex"
    return nome


def _inicio_comentario(linha: str) -> int:
    i = 0
    while i < len(linha):
        if linha[i] == "\\":
            i += 2
            continue
        if linha[i] == "%":
            return i
        i += 1
    return len(linha)


def preencher(modelo: str, valores: dict[str, str]) -> str:
    """Substitui os marcadores; marcadores sem valor viram texto vazio.

    Marcadores dentro de comentários (depois de ``%``) são deixados como estão.
    """
    saida = []
    for linha in modelo.split("\n"):
        corte = _inicio_comentario(linha)
        codigo, comentario = linha[:corte], linha[corte:]
        codigo = RE_MARCADOR.sub(lambda m: valores.get(m.group(1), ""), codigo)
        saida.append(codigo + comentario)
    return "\n".join(saida)


def marcadores_usados(modelo: str) -> set[str]:
    """Marcadores presentes fora de comentários."""
    usados = set()
    for linha in modelo.split("\n"):
        usados |= {m.group(1) for m in RE_MARCADOR.finditer(linha[:_inicio_comentario(linha)])}
    return usados


def posicao_begin_document(modelo: str) -> int:
    """Posição do primeiro \\begin{document} fora de comentários (-1 se não houver)."""
    pos = 0
    for linha in modelo.split("\n"):
        j = linha.find("\\begin{document}")
        if 0 <= j < _inicio_comentario(linha):
            return pos + j
        pos += len(linha) + 1
    return -1


def preambulo(modelo: str, macros: str) -> str:
    """Parte do modelo antes de \\begin{document}, com as macros do usuário."""
    i = posicao_begin_document(modelo)
    cabeca = modelo if i < 0 else modelo[:i]
    if "macros" not in marcadores_usados(cabeca):
        cabeca += "\n" + macros + "\n"
    return preencher(cabeca, {"macros": macros})


def validar_modelo(texto: str) -> list[str]:
    """Problemas encontrados no modelo (lista vazia = parece correto)."""
    avisos = []
    if "\\documentclass" not in texto:
        avisos.append("Falta \\documentclass.")
    if "\\begin{document}" not in texto or "\\end{document}" not in texto:
        avisos.append("Falta \\begin{document} ou \\end{document}.")
    usados = marcadores_usados(texto)
    if "questoes" not in usados:
        avisos.append("Falta o marcador <<questoes>> (onde as questões entram).")
    if "macros" not in usados:
        avisos.append("Falta o marcador <<macros>> (suas macros serão postas antes de \\begin{document}).")
    for amb in AMBIENTES_USADOS:
        if not re.search(r"\\(?:new|renew|provide)environment\*?\s*\{" + amb + r"\}", texto):
            avisos.append(f"O ambiente “{amb}” não está definido no modelo.")
    for cmd in COMANDOS_USADOS:
        if not re.search(r"\\(?:(?:new|renew|provide)command\*?\s*\{?\s*|def\s*|let\s*)\\" + cmd + r"(?![A-Za-z])", texto):
            avisos.append(f"O comando \\{cmd} não está definido no modelo.")
    desconhecidos = sorted(usados - set(MARCADORES) - {"semente"})
    for d in desconhecidos:
        avisos.append(f"Marcador desconhecido: <<{d}>> (ficará vazio).")
    return avisos
