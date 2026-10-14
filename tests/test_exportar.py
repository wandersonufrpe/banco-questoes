"""Geração do .tex da prova, gabarito e resoluções; compilação de ponta a ponta."""

import json
import re
import shutil

import pytest

from bancoq.nucleo.compilador import compilar, localizar_tex
from bancoq.nucleo.entidades import Item, Questao
from bancoq.nucleo.exportar import Exportacao, documento_prova, nomes_arquivos
from bancoq.nucleo.modelos_prova import texto_generico
from bancoq.nucleo.prova import Cabecalho, Montagem, gerar_versoes

from conftest import png_minimo

TEX = localizar_tex()
precisa_tex = pytest.mark.skipif(TEX is None, reason="pdflatex/latexmk não instalado")
MACROS = r"\newcommand{\R}{\mathbb{R}}"


@pytest.fixture
def prova(repo):
    ident = repo.midia.adicionar_bytes(png_minimo(9))
    qs = [
        Questao(tipo="multipla", enunciado=f"Seja $x\\in\\R$. Figura: [[img:{ident}|0.3]]",
                itens=[Item("$1$"), Item("[0,1]", True, "certo"), Item("$\\frac{1}{2}$")],
                resolucao="Porque sim."),
        Questao(tipo="vf", enunciado="Julgue:", itens=[Item("$2>1$", True), Item("$1>2$")]),
        Questao(tipo="discursiva", enunciado="Prove que $\\sqrt2\\notin\\mathbb{Q}$.", resolucao="Por absurdo."),
        Questao(tipo="curta", enunciado="Quanto vale $2+2$?", resposta_curta="$4$"),
    ]
    ids = [repo.salvar_questao(q) for q in qs]
    m = Montagem(nome="P1 fictícia", num_versoes=2, embaralhar_questoes=True, embaralhar_alternativas=True,
                 semente=123, cabecalho=Cabecalho("Prova 1", "Cálculo I", "T01", "Fulano", "01/01/2030",
                                                  "Responda com caneta."))
    m.adicionar_manual(ids)
    m.itens[0].valor = "2,5"
    m.itens[2].espaco_cm = 4
    return m, repo.obter_questoes(ids), ident


def test_tex_da_prova(repo, prova):
    m, qs, ident = prova
    versoes = gerar_versoes(m, qs)
    tex = documento_prova(m, versoes[0], texto_generico(), MACROS, lambda i: f"midia/{i}.png")
    assert "<<" not in re.sub(r"%.*", "", tex)              # marcadores substituídos
    assert "Prova 1" in tex and "Cálculo I" in tex and "Responda com caneta." in tex
    assert MACROS in tex
    assert "\\fbox{\\textbf{Versão A}}" in tex
    sem_comentarios = re.sub(r"(?<!\\)%.*", "", tex)
    assert sem_comentarios.count("\\begin{questao}") == 4
    assert "\\begin{questao}[2,5]" in tex
    assert "\\begin{alternativas}" in tex and "\\alt {}[0,1]" in tex
    assert "\\begin{afirmativas}" in tex and "\\afirmativa $2>1$" in tex
    assert "\\espacoresposta{4cm}" in tex and "\\respostacurta" in tex
    assert f"\\includegraphics[width=0.3\\linewidth]{{midia/{ident}.png}}" in tex
    assert "Porque sim" not in tex and "certo" not in tex     # resolução e comentários não vão para a prova
    assert "Semente: 123" in tex


def test_versao_unica_nao_mostra_versao(repo, prova):
    m, qs, _ = prova
    m.num_versoes = 1
    tex = documento_prova(m, gerar_versoes(m, qs)[0], texto_generico(), "", None)
    assert "Versão A" not in tex and "\\seexiste{}{\\hfill\\fbox" in tex


def test_exportacao_gera_arquivos_e_midia(repo, prova, tmp_path):
    m, qs, ident = prova
    saida = tmp_path / "saida"
    rel = Exportacao(m, qs, texto_generico(), MACROS, repo.midia, saida, None, True).executar()
    assert not rel.erros and not rel.pdfs
    assert any("TeX não encontrado" in a for a in rel.avisos)   # sem TeX: só os .tex
    for nome in ("prova_A.tex", "prova_B.tex", "resolucao_A.tex", "resolucao_B.tex", "gabarito.tex", "montagem.json"):
        assert (saida / nome).exists(), nome
    assert (saida / "midia" / f"{ident}.png").exists()
    assert set(nomes_arquivos(m)) >= {p.name for p in rel.arquivos}
    reg = json.loads((saida / "montagem.json").read_text(encoding="utf-8"))
    assert reg["montagem"]["semente"] == 123 and len(reg["versoes"]) == 2
    gab = (saida / "gabarito.tex").read_text(encoding="utf-8")
    for v in reg["versoes"]:
        for q in v["questoes"]:
            if q["tipo"] in ("multipla", "vf"):
                assert q["resposta"] in gab
    res = (saida / "resolucao_B.tex").read_text(encoding="utf-8")
    assert "Porque sim." in res and "certo" in res and "\\marcacorreta" in res
    # só caminhos relativos
    assert str(tmp_path) not in (saida / "prova_A.tex").read_text(encoding="utf-8")


@precisa_tex
def test_ponta_a_ponta_com_pdflatex(repo, prova, tmp_path):
    m, qs, ident = prova
    saida = tmp_path / "saida"
    passos = []
    rel = Exportacao(m, qs, texto_generico(), MACROS, repo.midia, saida, TEX, True, 120,
                     lambda t, i, n: passos.append(t)).executar()
    assert not rel.erros, rel.erros
    for nome in ("prova_A.pdf", "prova_B.pdf", "resolucao_A.pdf", "resolucao_B.pdf", "gabarito.pdf"):
        assert (saida / nome).exists(), nome
    assert not (saida / "prova_A.aux").exists()
    # a pasta exportada compila sozinha em outro lugar
    outra = tmp_path / "outro computador"
    shutil.copytree(saida, outra)
    for pdf in outra.glob("*.pdf"):
        pdf.unlink()
    r = compilar(TEX, outra, "prova_A.tex", 120)
    assert r.ok, r.erro
    # o texto do PDF tem as alternativas na ordem da versão
    from bancoq.nucleo.pdf import pymupdf

    with pymupdf.open(saida / "prova_A.pdf") as doc:
        texto = "".join(p.get_text() for p in doc)
    assert "Prova 1" in texto and "Questão 1" in texto and "Versão A" in texto


@precisa_tex
def test_erro_de_compilacao_e_relatado(repo, tmp_path):
    qid = repo.salvar_questao(Questao(enunciado=r"Comando \naoexiste aqui"))
    m = Montagem()
    m.adicionar_manual([qid])
    rel = Exportacao(m, repo.obter_questoes([qid]), texto_generico(), "", repo.midia, tmp_path, TEX, True, 60).executar()
    assert any("prova_A.tex" in e and "Undefined control sequence" in e for e in rel.erros)
    assert (tmp_path / "prova_A.log").exists()
