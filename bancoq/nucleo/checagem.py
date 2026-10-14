"""Checagem de LaTeX ao salvar e prévia exata (compilação de uma questão sozinha)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from .compilador import Compilacao, ErroLatex, InfoTex, ResultadoCompilacao
from .entidades import Questao
from .latex_gerar import ColetorImagens, DocumentoChecagem, documento_checagem, documento_previa_exata
from .midia import GerenciadorMidia


def nova_pasta_compilacao(base: Path) -> Path:
    pasta = Path(base) / "compilacao" / uuid.uuid4().hex[:10]
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


@dataclass
class ResultadoChecagem:
    ok: bool
    erro: ErroLatex | None = None
    campo_chave: str | None = None
    campo_nome: str | None = None
    log: str = ""
    tempo_esgotado: bool = False
    cancelado: bool = False
    linha_tex: str = ""


def preparar_checagem(q: Questao, modelo: str, macros: str, midia: GerenciadorMidia, info: InfoTex,
                      tempo_limite: float, pasta_temp: Path) -> tuple[Compilacao, DocumentoChecagem]:
    pasta = nova_pasta_compilacao(pasta_temp)
    coletor = ColetorImagens(midia)
    doc = documento_checagem(q, modelo, macros, coletor)
    (pasta / "checagem.tex").write_text(doc.texto, encoding="utf-8")
    coletor.copiar_para(pasta)
    return Compilacao(info, pasta, "checagem.tex", tempo_limite, passadas=1), doc


def interpretar_checagem(res: ResultadoCompilacao, doc: DocumentoChecagem) -> ResultadoChecagem:
    if res.ok:
        return ResultadoChecagem(True, log=res.log)
    r = ResultadoChecagem(False, erro=res.erro, log=res.log or res.saida,
                          tempo_esgotado=res.tempo_esgotado, cancelado=res.cancelado)
    if res.erro is not None:
        if res.erro.linha is None and res.erro.trecho:
            res.erro.linha = _procurar_trecho(doc.texto, res.erro.trecho, doc.inicio_corpo)
        achado = doc.campo_da_linha(res.erro.linha)
        if achado:
            r.campo_chave, r.campo_nome = achado
        if res.erro.linha:
            linhas = doc.texto.splitlines()
            if 0 < res.erro.linha <= len(linhas):
                r.linha_tex = linhas[res.erro.linha - 1]
    return r


def _procurar_trecho(texto: str, trecho: str, a_partir: int) -> int | None:
    """Linha do documento onde começa o trecho citado pelo TeX (ex.: "Runaway argument")."""
    alvo = "".join(trecho.split())
    linhas = ["".join(ln.split()) for ln in texto.splitlines()]
    for tamanho in (24, 16, 10, 6, 3):
        pedaco = alvo[:tamanho]
        if len(pedaco) < min(tamanho, 3):
            continue
        for n, linha in enumerate(linhas, start=1):
            if n >= a_partir and pedaco in linha:
                return n
    return None


def preparar_previa_exata(q: Questao, modelo: str, macros: str, midia: GerenciadorMidia, info: InfoTex,
                          tempo_limite: float, pasta_temp: Path) -> Compilacao:
    pasta = nova_pasta_compilacao(pasta_temp)
    coletor = ColetorImagens(midia)
    texto = documento_previa_exata(q, modelo, macros, coletor)
    (pasta / "previa.tex").write_text(texto, encoding="utf-8")
    coletor.copiar_para(pasta)
    return Compilacao(info, pasta, "previa.tex", tempo_limite, passadas=1)
