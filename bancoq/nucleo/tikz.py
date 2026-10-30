"""Figuras TikZ: localizar no texto e compilar cada uma sozinha (com cache).

Usado pela prévia rápida (a figura vira imagem) e pelas ferramentas de importação
com IA (conferir o redesenho contra o original do PDF).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from .compilador import Compilacao, InfoTex

RE_TIKZ = re.compile(r"\\begin\{tikzpicture\}.*?\\end\{tikzpicture\}", re.S)

# bibliotecas carregadas sempre na compilação isolada de uma figura
BIBLIOTECAS_PADRAO = (
    "arrows.meta,calc,patterns,angles,quotes,positioning,"
    "decorations.pathreplacing,decorations.markings,intersections,shapes.geometric"
)


@dataclass
class ResultadoFigura:
    ok: bool
    png: Path | None = None
    erro: str = ""
    log: str = ""


def figuras_tikz(texto: str) -> list[str]:
    """Ambientes tikzpicture completos presentes no texto, na ordem."""
    return RE_TIKZ.findall(texto or "")


def usa_pgfplots(codigo: str) -> bool:
    return "\\begin{axis}" in codigo or "\\addplot" in codigo or "pgfplots" in codigo


def chave_figura(codigo: str, preambulo: str) -> str:
    h = hashlib.sha256()
    h.update(codigo.strip().encode("utf-8"))
    h.update(b"\0")
    h.update((preambulo or "").encode("utf-8"))
    return h.hexdigest()[:20]


RE_LINHA_TIKZ = re.compile(r"^\s*\\(usepackage(\[[^\]]*\])?\{[^}]*(tikz|pgfplots)[^}]*\}|usetikzlibrary|usepgfplotslibrary|pgfplotsset|tikzset)")


def preambulo_figuras(modelo: str, macros: str) -> str:
    """Preâmbulo das figuras isoladas: linhas de TikZ/pgfplots do modelo + macros do banco."""
    from .modelos_prova import posicao_begin_document

    i = posicao_begin_document(modelo or "")
    cabeca = (modelo or "")[: i if i >= 0 else len(modelo or "")]
    linhas = [ln for ln in cabeca.splitlines() if RE_LINHA_TIKZ.match(ln)]
    return "\n".join(linhas + [macros or ""]).strip()


def documento_figura(codigo: str, preambulo: str = "") -> str:
    """Documento standalone com a figura e o preâmbulo do banco."""
    pre = preambulo or ""
    linhas = [
        "\\documentclass[border=4pt]{standalone}",
        "\\usepackage[utf8]{inputenc}",
        "\\usepackage[T1]{fontenc}",
        "\\usepackage{amsmath,amssymb}",
    ]
    # TikZ antes de tudo (repetir \usepackage depois não faz mal) para as bibliotecas
    # e para macros do usuário que usem \tikzset
    linhas.append("\\usepackage{tikz}")
    linhas.append(f"\\usetikzlibrary{{{BIBLIOTECAS_PADRAO}}}")
    if usa_pgfplots(codigo) and "pgfplots" not in pre:
        linhas.append("\\usepackage{pgfplots}")
        linhas.append("\\pgfplotsset{compat=1.17}")
    linhas.append(pre)
    linhas.append("\\begin{document}")
    linhas.append(codigo.strip())
    linhas.append("\\end{document}")
    return "\n".join(linhas) + "\n"


def compilar_figura(codigo: str, preambulo: str, info: InfoTex, pasta_cache: Path,
                    tempo_limite: float = 60, dpi: int = 200) -> ResultadoFigura:
    """Compila a figura (ou devolve o PNG do cache) e gera o PNG."""
    from .pdf import pymupdf

    pasta_cache = Path(pasta_cache)
    pasta_cache.mkdir(parents=True, exist_ok=True)
    chave = chave_figura(codigo, preambulo)
    png = pasta_cache / f"tikz-{chave}.png"
    if png.exists():
        return ResultadoFigura(True, png)
    trabalho = pasta_cache / f"tikz-{chave}"
    trabalho.mkdir(exist_ok=True)
    (trabalho / "figura.tex").write_text(documento_figura(codigo, preambulo), encoding="utf-8")
    res = Compilacao(info, trabalho, "figura.tex", tempo_limite, passadas=1).executar()
    if not res.ok or res.pdf is None:
        if res.tempo_esgotado:
            erro = f"tempo limite de {tempo_limite:g} s esgotado"
        elif res.erro is not None:
            erro = res.erro.mensagem + (f" — {res.erro.explicacao}" if res.erro.explicacao else "")
            if res.erro.trecho:
                erro += f" (perto de: {res.erro.trecho})"
        else:
            erro = "falha na compilação"
        return ResultadoFigura(False, None, erro, res.log)
    with pymupdf.open(res.pdf) as doc:
        doc[0].get_pixmap(dpi=dpi, alpha=False).save(png)
    return ResultadoFigura(True, png, "", res.log)
