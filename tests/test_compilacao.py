"""Compilação com pdflatex (os testes que precisam do TeX são pulados sem ele)."""

import pytest

from bancoq.nucleo.checagem import interpretar_checagem, preparar_checagem, preparar_previa_exata
from bancoq.nucleo.compilador import comando, InfoTex, ler_erro_log, localizar_tex
from bancoq.nucleo.entidades import Item, Questao
from bancoq.nucleo.midia import GerenciadorMidia
from bancoq.nucleo.modelos_prova import texto_generico

TEX = localizar_tex()
precisa_tex = pytest.mark.skipif(TEX is None, reason="pdflatex/latexmk não instalado")


def test_comando_nunca_usa_shell_escape():
    for info in (InfoTex("pdflatex", "pdflatex"), InfoTex("pdflatex", "pdflatex", miktex=True),
                 InfoTex("latexmk", "latexmk"), InfoTex("latexmk", "latexmk", miktex=True)):
        cmd = comando(info, "a.tex")
        assert "-interaction=nonstopmode" in cmd and "-halt-on-error" in cmd
        assert not any(c in ("-shell-escape", "--shell-escape", "--enable-write18") for c in cmd)
        assert any("no-shell-escape" in c or "disable-write18" in c for c in cmd)


LOG_EXEMPLO = r"""
This is pdfTeX, Version 3.141592653-2.6-1.40.25 (TeX Live 2023/Debian)
(./checagem.tex
! Undefined control sequence.
l.42 Seja $x \in \R
                   $.
Here is how much of TeX's memory you used:
"""


def test_ler_erro_log():
    e = ler_erro_log(LOG_EXEMPLO)
    assert e.linha == 42
    assert "Undefined control sequence" in e.mensagem and "\\R" in e.mensagem
    assert "Comando não definido" in e.explicacao
    assert "erro aqui" in e.trecho


def test_ler_erro_log_pacote_faltando():
    e = ler_erro_log("! LaTeX Error: File `naoexiste.sty' not found.\n\nType X to quit\nl.5 \\begin")
    assert "naoexiste.sty" in e.explicacao


def _q():
    return Questao(tipo="multipla", enunciado=r"Seja $x \in \R$.",
                   itens=[Item("$1$"), Item(r"$\frac{1}{2$", True), Item("[0,1]")],
                   resolucao="Basta ver que $x=1$.")


@precisa_tex
def test_checagem_aponta_o_campo(tmp_path):
    midia = GerenciadorMidia(tmp_path / "m", tmp_path)
    q = _q()
    comp, doc = preparar_checagem(q, texto_generico(), "", midia, TEX, 60, tmp_path)
    r = interpretar_checagem(comp.executar(), doc)
    assert not r.ok and r.campo_nome == "Enunciado"
    comp, doc = preparar_checagem(q, texto_generico(), r"\newcommand{\R}{\mathbb{R}}", midia, TEX, 60, tmp_path)
    r = interpretar_checagem(comp.executar(), doc)
    assert not r.ok and r.campo_chave == "item:1:texto"
    q.itens[1].texto = r"$\frac{1}{2}$"
    comp, doc = preparar_checagem(q, texto_generico(), r"\newcommand{\R}{\mathbb{R}}", midia, TEX, 60, tmp_path)
    assert interpretar_checagem(comp.executar(), doc).ok
    q.resolucao = r"\begin{itemize}\item sem fim"
    comp, doc = preparar_checagem(q, texto_generico(), r"\newcommand{\R}{\mathbb{R}}", midia, TEX, 60, tmp_path)
    r = interpretar_checagem(comp.executar(), doc)
    assert not r.ok and r.campo_chave == "resolucao"


@precisa_tex
def test_erro_no_preambulo(tmp_path):
    midia = GerenciadorMidia(tmp_path / "m", tmp_path)
    q = Questao(enunciado="ok")
    comp, doc = preparar_checagem(q, texto_generico(), r"\usepackage{pacoteinexistentexyz}", midia, TEX, 60, tmp_path)
    r = interpretar_checagem(comp.executar(), doc)
    assert not r.ok and r.campo_chave == "preambulo"


@precisa_tex
def test_tempo_limite(tmp_path):
    midia = GerenciadorMidia(tmp_path / "m", tmp_path)
    q = Questao(enunciado=r"\def\laco{\laco}\laco")
    comp, doc = preparar_checagem(q, texto_generico(), "", midia, TEX, 3, tmp_path)
    r = interpretar_checagem(comp.executar(), doc)
    assert not r.ok and r.tempo_esgotado


@precisa_tex
def test_previa_exata_gera_pdf_e_imagem(tmp_path):
    from bancoq.nucleo.pdf import paginas_png
    from conftest import png_minimo

    midia = GerenciadorMidia(tmp_path / "m", tmp_path)
    ident = midia.adicionar_bytes(png_minimo(3))
    q = _q()
    q.itens[1].texto = r"$\frac{1}{2}$"
    q.enunciado = f"Seja $x \\in \\R$. [[img:{ident}|0.2]]"
    comp = preparar_previa_exata(q, texto_generico(), r"\newcommand{\R}{\mathbb{R}}", midia, TEX, 60, tmp_path)
    res = comp.executar()
    assert res.ok, res.erro
    imgs = paginas_png(res.pdf)
    assert imgs and imgs[0].startswith(b"\x89PNG")
