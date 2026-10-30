"""Importação com IA: formato do pacote, análise do PDF, TikZ e linha de comando.

Os PDFs usados aqui são fictícios e gerados na hora com o PyMuPDF.
"""

import json
import shutil

import pytest

from bancoq.ia import pdf as ferramentas_pdf
from bancoq.ia.__main__ import main
from bancoq.ia.pacote import (
    APROVADA,
    FIGURA_AJUSTAR,
    FIGURA_TEXTO,
    REJEITADA,
    Pacote,
    QuestaoPacote,
    faltando_no_preambulo,
    ler_questao,
    listar_pacotes,
    nome_pacote,
    normalizar_resposta,
    pasta_concluidos,
    pasta_pacotes,
    problemas_latex,
    resolver_categoria,
    tem_erro,
    validar_questao,
)
from bancoq.nucleo.compilador import localizar_tex
from bancoq.nucleo.latex_html import AVISO, latex_para_html
from bancoq.nucleo.pdf import pymupdf
from bancoq.nucleo.repositorio import CategoriaNova
from bancoq.nucleo.tikz import (
    chave_figura,
    compilar_figura,
    documento_figura,
    figuras_tikz,
    preambulo_figuras,
    usa_pgfplots,
)

TEX = localizar_tex()
precisa_tex = pytest.mark.skipif(TEX is None, reason="pdflatex/latexmk não instalado")

QUESTAO_OK = r"""@numero: 4
@pagina: 2
@tipo: multipla
@dificuldade: 2
@fonte: Olimpíada Fictícia 2024 — Nível 1, questão 4
@ano: 2024
@categoria: Aritmética > Frações
@tags: frações; soma
@resposta: B
@resposta_independente: (B)
@gabarito_pdf: b
@sympy: 1/2 + 1/3 = 5/6 conferido
@confianca: alta
@figura: 1 | ok
@preambulo: \usepackage{tikz}

@@enunciado
Quanto vale $\frac{1}{2}+\frac{1}{3}$? Veja a figura.
\begin{center}
\begin{tikzpicture}
\draw (0,0) rectangle (2,1);
\end{tikzpicture}
\end{center}

@@alternativa
$\frac{2}{5}$
@@comentario
Somou numeradores e denominadores.

@@alternativa correta
$\frac{5}{6}$
@@comentario
Correta: $\frac{3}{6}+\frac{2}{6}$.

@@alternativa
$\frac{1}{6}$
@@comentario
Multiplicou as frações.

@@resolucao
Com denominador $6$: $\frac{3}{6}+\frac{2}{6}=\frac{5}{6}$.

@@observacoes
Questão fictícia.

@@verificacao
Duas resoluções independentes deram $\frac56$.
"""


# =====================================================================
# Formato de seções
# =====================================================================
def test_ler_questao_completa():
    q = ler_questao(QUESTAO_OK, "q004")
    assert not q.problemas_leitura
    assert q.tipo == "multipla" and q.numero == "4" and q.pagina == 2
    assert q.enunciado.startswith(r"Quanto vale $\frac{1}{2}")      # sem escapes
    assert [i.correta for i in q.itens] == [False, True, False]
    assert q.itens[1].comentario.startswith("Correta")
    assert q.categoria == ["Aritmética", "Frações"] and q.tags == ["frações", "soma"]
    assert q.ano == 2024 and q.dificuldade == 2 and q.confianca == "alta"
    assert q.figuras[0].numero == 1 and q.preambulo == [r"\usepackage{tikz}"]
    assert q.resolucao.endswith(r"=\frac{5}{6}$.") and q.observacoes == "Questão fictícia."
    assert "Duas resoluções" in q.verificacao


def test_ida_e_volta_do_texto():
    q = ler_questao(QUESTAO_OK, "q004")
    q2 = ler_questao(q.para_texto(), "q004")
    for campo in ("tipo", "enunciado", "resolucao", "observacoes", "fonte", "ano", "categoria", "tags",
                  "resposta", "resposta_independente", "gabarito_pdf", "confianca", "verificacao",
                  "preambulo"):
        assert getattr(q2, campo) == getattr(q, campo), campo
    assert [(i.texto, i.correta, i.comentario) for i in q2.itens] == \
           [(i.texto, i.correta, i.comentario) for i in q.itens]


def test_vf_curta_e_problemas_de_leitura():
    vf = ler_questao("@tipo: verdadeiro ou falso\n@@enunciado\nJulgue.\n@@afirmativa V\n$1<2$\n"
                     "@@afirmativa falsa\n$2<1$\n@@resolucao\nok")
    assert vf.tipo == "vf" and [i.correta for i in vf.itens] == [True, False]
    assert vf.resposta_da_chave() == "VF"
    curta = ler_questao("@tipo: curta\n@@enunciado\nQuanto?\n@@resposta_esperada\n$12$\n@@resolucao\nok")
    assert curta.resposta_esperada == "$12$"
    ruim = ler_questao("texto solto\n@tipo: múltipla\n@@enunciado\nx\n@@comentario\nsem item\n"
                       "@@afirmativa talvez\ny\n@@secao\nz\n@campo_estranho: 1")
    msgs = " | ".join(p.mensagem for p in ruim.problemas_leitura)
    assert "fora de seção" in msgs and "sem alternativa" in msgs
    assert "verdadeira" in msgs and "seção desconhecida" in msgs


def test_validar_questao():
    q = ler_questao(QUESTAO_OK, "q004")
    assert not tem_erro(validar_questao(q))
    # resposta que não bate com a alternativa marcada
    q.resposta = "C"
    assert any("não bate" in p.mensagem for p in validar_questao(q))
    q.resposta = "B"
    q.resposta_independente = "A"
    q.gabarito_pdf = "C"
    msgs = [p.mensagem for p in validar_questao(q)]
    assert any("discordam" in m for m in msgs) and any("gabarito do PDF" in m for m in msgs)
    q.itens[0].correta = True
    assert any("exatamente 1" in p.mensagem for p in validar_questao(q) if p.gravidade == "erro")
    q.itens[0].correta = False
    q.figuras[0].situacao = FIGURA_AJUSTAR
    assert any("precisa de ajuste" in p.mensagem for p in validar_questao(q))
    q.enunciado = q.enunciado.replace(r"\begin{tikzpicture}", "").replace(r"\end{tikzpicture}", "")
    assert any("tikzpicture" in p.mensagem for p in validar_questao(q) if p.gravidade == "erro")
    q.figuras[0].situacao = FIGURA_TEXTO          # virou tabela: não precisa de TikZ
    assert not tem_erro(validar_questao(q))
    q.resolucao = ""
    assert tem_erro(validar_questao(q))


def test_problemas_latex_e_respostas():
    assert problemas_latex(r"$\frac{1}{2}$ e \{ ok \} 50\%") == []
    assert "chaves" in problemas_latex(r"\textbf{x")[0]
    assert "ímpar de $" in problemas_latex("custa $5")[0]
    assert "sem \\end" in problemas_latex(r"\begin{center}x")[0]
    assert "TikZ" in problemas_latex(r"\includegraphics{a.png}")[0]
    assert normalizar_resposta("Alternativa (C)") == "c" == normalizar_resposta("c)")
    assert normalizar_resposta("$12$") == normalizar_resposta("12")
    assert nome_pacote("Prova ÁGIL 2025 (1ª fase).pdf") == "prova-agil-2025-1a-fase"


# =====================================================================
# Pacote e decisões
# =====================================================================
def test_pacote_decisoes_e_concluidos(banco):
    pasta = pasta_pacotes(banco.pasta) / "ficticia"
    pac = Pacote.criar(pasta, titulo="Prova fictícia", pdf="ficticia.pdf", paginas=2)
    q = ler_questao(QUESTAO_OK, "q004")
    pac.gravar_questao(q)
    pac.gravar_questao(QuestaoPacote(ident="q005", tipo="discursiva", enunciado="Explique.",
                                     resolucao="Assim."))
    reaberto = Pacote.abrir(pasta)
    assert reaberto.titulo == "Prova fictícia" and reaberto.ids() == ["q004", "q005"]
    assert reaberto.questao("q004").itens[1].correta
    assert reaberto.pendentes() == ["q004", "q005"]
    reaberto.registrar_decisao("q004", APROVADA, questao_id=7)
    reaberto.registrar_decisao("q005", REJEITADA, motivo="repetida")
    d = Pacote.abrir(pasta).decisoes()
    assert d["q004"].questao_id == 7 and d["q005"].motivo == "repetida"
    reaberto.desfazer_decisao("q005")
    assert reaberto.pendentes() == ["q005"]
    assert reaberto.preambulo_necessario() == [r"\usepackage{tikz}"]
    assert faltando_no_preambulo([r"\usepackage{tikz}", r"\usepackage{xcolor}"],
                                 "\\usepackage{ tikz }\n") == [r"\usepackage{xcolor}"]
    assert [p.nome for p in listar_pacotes(banco.pasta)] == ["ficticia"]
    destino = reaberto.mover_para_concluidos(banco.pasta)
    assert destino.parent == pasta_concluidos(banco.pasta) and not pasta.exists()
    assert listar_pacotes(banco.pasta) == [] and len(listar_pacotes(banco.pasta, concluidos=True)) == 1


def test_resolver_categoria_e_gravar_no_banco(repo):
    alg = repo.criar_categoria("Álgebra")
    repo.criar_categoria("Equações", alg)
    assert resolver_categoria(repo, ["álgebra", "Equações"]) == (repo.caminho_para_ids(["Álgebra", "Equações"]), None)
    cid, nova = resolver_categoria(repo, ["Álgebra", "Inequações", "Modulares"])
    assert cid is None and nova == CategoriaNova(alg, ["Inequações", "Modulares"])
    assert resolver_categoria(repo, ["Geometria"]) == (None, CategoriaNova(None, ["Geometria"]))
    assert resolver_categoria(repo, []) == (None, None)

    q = ler_questao(QUESTAO_OK, "q004")
    questao = q.para_questao()
    questao.categoria_id, nova = resolver_categoria(repo, q.categoria)
    qid = repo.salvar_questao(questao, nova)
    salva = repo.obter_questao(qid)
    assert repo.caminhos_categorias()[salva.categoria_id] == "Aritmética > Frações"
    assert salva.tags == ["frações", "soma"] and salva.fonte.startswith("Olimpíada")
    assert [i.correta for i in salva.itens] == [False, True, False]
    assert salva.itens[2].comentario == "Multiplicou as frações."


# =====================================================================
# PDF fictício
# =====================================================================
LINHAS = [
    "Texto corrido da questão para ocupar a linha",
    "inteira da coluna, como num caderno de prova",
    "com duas colunas de texto bem alinhadas aqui.",
]


def _questao_na_coluna(pag, x, y, numero, marcador="QUESTÃO {n}", linhas=LINHAS, alternativas=True):
    pag.insert_text((x, y), marcador.format(n=numero), fontname="hebo", fontsize=11)
    y += 18
    for t in linhas:
        pag.insert_text((x, y), t, fontname="helv", fontsize=9)
        y += 13
    if alternativas:
        for letra in "ABCD":
            pag.insert_text((x, y), f"({letra}) {numero * 10 + ord(letra) - 64}", fontname="helv", fontsize=9)
            y += 13
    return y


def pdf_duas_colunas(caminho):
    doc = pymupdf.open()
    p1 = doc.new_page(width=595, height=842)
    p1.insert_text((50, 30), "Prova Fictícia de Matemática", fontname="helv", fontsize=8)
    p1.insert_text((290, 825), "1", fontname="helv", fontsize=8)
    _questao_na_coluna(p1, 50, 90, 1)
    y = _questao_na_coluna(p1, 50, 400, 2)
    p1.draw_rect(pymupdf.Rect(70, y, 230, y + 90), color=(0, 0, 0), width=1)   # figura
    p1.draw_circle((150, y + 45), 30, color=(0, 0, 0), width=1)
    p1.insert_text((62, y + 100), "A", fontname="helv", fontsize=9)
    p1.insert_text((232, y + 100), "B", fontname="helv", fontsize=9)
    _questao_na_coluna(p1, 315, 90, 3)
    _questao_na_coluna(p1, 315, 560, 4, alternativas=False)
    p2 = doc.new_page(width=595, height=842)
    p2.insert_text((50, 30), "Prova Fictícia de Matemática", fontname="helv", fontsize=8)
    p2.insert_text((290, 825), "2", fontname="helv", fontsize=8)
    y = 80
    for letra in "ABCD":   # continuação da questão 4 no alto da página 2
        p2.insert_text((50, y), f"({letra}) continuação {letra} da questão quatro", fontname="helv", fontsize=9)
        y += 13
    _questao_na_coluna(p2, 50, 300, 5)
    _questao_na_coluna(p2, 315, 300, 6)
    doc.save(caminho)
    doc.close()
    return caminho


def pdf_uma_coluna(caminho):
    doc = pymupdf.open()
    p = doc.new_page(width=595, height=842)
    y = 70
    for n, t in enumerate(["Leia com atenção.", "Use caneta.", "Não converse."], start=1):
        p.insert_text((50, y), f"{n}. {t}", fontname="hebo", fontsize=8)
        y += 12
    largas = ["Uma linha bem longa que atravessa o meio da página de um lado a outro, de verdade."] * 3
    y = 140
    for n in range(1, 5):
        y = _questao_na_coluna(p, 50, y, n, marcador="{n}.", linhas=largas) + 30
    doc.save(caminho)
    doc.close()
    return caminho


def test_regioes_duas_colunas(tmp_path):
    with ferramentas_pdf.Documento(pdf_duas_colunas(tmp_path / "duas.pdf")) as doc:
        assert doc.paginas[0].duas_colunas
        regioes = doc.regioes()
    assert [r.ident for r in regioes] == ["q001", "q002", "q003", "q004", "q005", "q006"]
    por_id = {r.ident: r for r in regioes}
    assert por_id["q001"].partes[0].caixa[2] < 300          # coluna da esquerda
    assert por_id["q003"].partes[0].caixa[0] > 290          # coluna da direita
    # a questão 4 continua no alto da página 2, antes da questão 5
    partes4 = por_id["q004"].partes
    assert [p.pagina for p in partes4] == [1, 2]
    assert partes4[1].caixa[1] > 50 and partes4[1].caixa[3] < 300   # sem o cabeçalho
    assert len(por_id["q002"].figuras) == 1 and not por_id["q001"].figuras
    fig = por_id["q002"].figuras[0].caixa
    assert fig[0] <= 62 and fig[2] >= 238                      # inclui os rótulos A e B


def test_regioes_uma_coluna_ignora_instrucoes(tmp_path):
    with ferramentas_pdf.Documento(pdf_uma_coluna(tmp_path / "uma.pdf")) as doc:
        assert not doc.paginas[0].duas_colunas
        regioes = doc.regioes()
    assert [r.numero for r in regioes] == [1, 2, 3, 4]
    assert all(r.partes[0].caixa[1] > 110 for r in regioes)   # não pegou as instruções


def test_normalizar_texto():
    assert ferramentas_pdf.normalizar_texto("qual ´e a soluc¸˜ao? ˆangulo") == "qual é a solução? ângulo"


def test_recortes_e_comparacao(tmp_path):
    arq = pdf_duas_colunas(tmp_path / "duas.pdf")
    with ferramentas_pdf.Documento(arq) as doc:
        q4 = next(r for r in doc.regioes() if r.ident == "q004")
        png = ferramentas_pdf.recortar(doc.doc, q4.partes, tmp_path / "q4.png", dpi=72)
        texto = ferramentas_pdf.texto_das_partes(doc.doc, q4.partes)
        grade = ferramentas_pdf.renderizar_pagina(doc.doc, 1, tmp_path / "p1.png", dpi=50, grade=50)
    assert "QUESTÃO 4" in texto and "continuação D" in texto and "[continua]" in texto
    pix = pymupdf.Pixmap(str(png))
    assert pix.height > pix.width * 0.5
    assert grade.exists()
    comp = ferramentas_pdf.lado_a_lado(png, grade, tmp_path / "comp.png", altura=100)
    assert pymupdf.Pixmap(str(comp)).width > 0


# =====================================================================
# TikZ
# =====================================================================
FIGURA = r"\begin{tikzpicture}\draw (0,0) -- (1,1);\end{tikzpicture}"


def test_tikz_documento_e_preambulo():
    assert figuras_tikz(f"a {FIGURA} b {FIGURA}") == [FIGURA, FIGURA]
    doc = documento_figura(FIGURA, r"\newcommand{\R}{\mathbb{R}}")
    assert r"\usepackage{tikz}" in doc and r"\usetikzlibrary{" in doc and r"\newcommand{\R}" in doc
    assert "pgfplots" not in doc
    plot = r"\begin{tikzpicture}\begin{axis}\addplot {x};\end{axis}\end{tikzpicture}"
    assert usa_pgfplots(plot) and r"\usepackage{pgfplots}" in documento_figura(plot)
    assert chave_figura(FIGURA, "") != chave_figura(FIGURA, "x")
    modelo = "\\documentclass{article}\n\\usepackage{tikz}\n\\usetikzlibrary{3d}\n\\usepackage{geometry}\n" \
             "\\begin{document}\n\\usetikzlibrary{depois}\n\\end{document}\n"
    assert preambulo_figuras(modelo, "% macros") == "\\usepackage{tikz}\n\\usetikzlibrary{3d}\n% macros"


def test_previa_rapida_com_tikz():
    estados = {"ok": ("ok", "file:///fig.png"), "pendente": ("pendente", ""), "erro": ("erro", "Undefined control")}
    for estado, resposta in estados.items():
        vistos = []

        def resolver(codigo, resposta=resposta, vistos=vistos):
            vistos.append(codigo)
            return resposta

        h = latex_para_html(r"Veja: \begin{center}" + FIGURA + r"\end{center} fim", resolver_tikz=resolver)
        assert vistos == [FIGURA] and "fim" in h
        if estado == "ok":
            assert '<img class="tikz" src="file:///fig.png">' in h
        elif estado == "pendente":
            assert "desenhando" in h
        else:
            assert "não compilou" in h and "Undefined control" in h
    assert AVISO in latex_para_html(FIGURA)          # sem quem compile: aviso de sempre


@precisa_tex
def test_compilar_figura_com_cache(tmp_path):
    r = compilar_figura(FIGURA, "", TEX, tmp_path / "cache", dpi=72)
    assert r.ok and r.png.exists()
    (tmp_path / "cache" / r.png.name).touch()
    assert compilar_figura(FIGURA, "", TEX, tmp_path / "cache").png == r.png   # do cache
    ruim = compilar_figura(r"\begin{tikzpicture}\desenhar (0,0);\end{tikzpicture}", "", TEX,
                           tmp_path / "cache", dpi=72)
    assert not ruim.ok and "desenhar" in ruim.erro


# =====================================================================
# Linha de comando
# =====================================================================
def _rodar(capsys, *args):
    codigo = main(list(args))
    return codigo, json.loads(capsys.readouterr().out)


def test_cli_fluxo_completo(banco, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("BANCOQ_TRABALHO", str(tmp_path / "trabalho"))
    b = str(banco.pasta)
    arq = pdf_duas_colunas(tmp_path / "Prova Fictícia.pdf")

    codigo, r = _rodar(capsys, "--banco", b, "banco")
    assert codigo == 0 and r["banco"] == str(banco.pasta.resolve())

    codigo, r = _rodar(capsys, "--banco", b, "preparar", str(arq), "--titulo", "Prova Fictícia 2024")
    assert codigo == 0 and r["nome"] == "prova-ficticia"
    assert [q["id"] for q in r["questoes"]] == ["q001", "q002", "q003", "q004", "q005", "q006"]
    q2 = next(q for q in r["questoes"] if q["id"] == "q002")
    assert len(q2["figuras"]) == 1 and q2["texto_util"]
    pac = Pacote.abrir(r["pacote"])
    assert pac.previstas == 6 and pac.recorte("q001") and pac.figura_original("q002", 1)

    codigo, r = _rodar(capsys, "--banco", b, "status", "prova-ficticia")
    assert r["escritas"] == 0 and len(r["faltando"]) == 6

    # o Claude escreve uma questão boa e uma com erro
    texto_ok = QUESTAO_OK.replace("@figura: 1 | ok\n", "")
    texto_ok = texto_ok.replace(r"\begin{tikzpicture}", "").replace(r"\end{tikzpicture}", "")
    texto_ok = texto_ok.replace(r"\draw (0,0) rectangle (2,1);", "")
    (pac.pasta_questoes / "q001.txt").write_text(texto_ok, encoding="utf-8")
    (pac.pasta_questoes / "q003.txt").write_text("@tipo: multipla\n@@enunciado\n$x\n", encoding="utf-8")
    codigo, r = _rodar(capsys, "--banco", b, "validar", "prova-ficticia")
    assert codigo == 1 and r["com_erro"] == ["q003"] and not r["questoes"]["q001"]["erros"]
    codigo, r = _rodar(capsys, "--banco", b, "finalizar", "prova-ficticia", "--sem-compilar")
    assert codigo == 1 and r["com_erro"] == ["q003"]
    (pac.pasta_questoes / "q003.txt").unlink()
    codigo, r = _rodar(capsys, "--banco", b, "finalizar", "prova-ficticia", "--sem-compilar")
    assert codigo == 0 and r["pronto"] and "q002" in r["faltando_no_pdf"]
    assert Pacote.abrir(pac.pasta).situacao == "pronto"

    # recorte refeito à mão, página com grade e figura removida
    codigo, r = _rodar(capsys, "--banco", b, "recortar", "prova-ficticia", "q001",
                       "--parte", "1:40,70,290,200", "--parte", "1:300,70,560,120")
    assert codigo == 0 and "QUESTÃO 1" in open(r["texto"], encoding="utf-8").read()
    codigo, r = _rodar(capsys, "--banco", b, "pagina", "prova-ficticia", "2", "--grade", "50")
    assert codigo == 0 and r["imagem"].endswith("p02-grade.png") and r["altura_pt"] == 842
    codigo, r = _rodar(capsys, "--banco", b, "remover-figura", "prova-ficticia", "q002", "1")
    assert len(r["removidos"]) == 1 and not pac.figura_original("q002", 1)

    codigo, r = _rodar(capsys, "--banco", b, "pacotes")
    assert r["pacotes"][0]["escritas"] == 1 and r["pacotes"][0]["situacao"] == "pronto"
    codigo, r = _rodar(capsys, "--banco", b, "catalogo")
    assert r["questoes"] == 0 and r["categorias"] == []

    # erros viram JSON com código 2
    codigo, r = _rodar(capsys, "--banco", b, "status", "nao-existe")
    assert codigo == 2 and "não encontrado" in r["erro"]
    codigo, r = _rodar(capsys, "--banco", str(tmp_path), "banco")
    assert codigo == 2 and "não é uma pasta de banco" in r["erro"]


def test_cli_banco_padrao_e_ausente(banco, monkeypatch, capsys):
    from bancoq.config_local import ConfigLocal

    monkeypatch.delenv("BANCOQ_BANCO", raising=False)
    codigo, r = _rodar(capsys, "banco")
    assert codigo == 2 and "--banco" in r["erro"]
    cfg = ConfigLocal()
    cfg.registrar_banco(str(banco.pasta))
    cfg.salvar()
    codigo, r = _rodar(capsys, "banco")
    assert codigo == 0 and r["banco"] == str(banco.pasta.resolve())


@precisa_tex
def test_cli_tikz_e_validar_compilando(banco, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("BANCOQ_TRABALHO", str(tmp_path / "trabalho"))
    b = str(banco.pasta)
    arq = pdf_duas_colunas(tmp_path / "ficticia.pdf")
    _rodar(capsys, "--banco", b, "preparar", str(arq))
    pac = Pacote.abrir(pasta_pacotes(banco.pasta) / "ficticia")
    (pac.pasta_questoes / "q002.txt").write_text(QUESTAO_OK, encoding="utf-8")
    codigo, r = _rodar(capsys, "--banco", b, "tikz", "ficticia", "q002")
    assert codigo == 0 and r["figuras"][0]["ok"] and r["figuras"][0]["figura"] == 1
    assert pac.figura_tikz("q002", 1) and r["figuras"][0]["comparacao"].endswith("q002-1.png")
    teste = tmp_path / "teste.tex"
    teste.write_text(FIGURA, encoding="utf-8")
    codigo, r = _rodar(capsys, "--banco", b, "tikz", "ficticia", "q002", "--arquivo", str(teste),
                       "--figura", "1")
    assert r["figuras"][0]["comparacao"].endswith("q002-1-teste.png")
    codigo, r = _rodar(capsys, "--banco", b, "validar", "ficticia", "q002", "--compilar")
    assert codigo == 0, r
    (pac.pasta_questoes / "q002.txt").write_text(
        QUESTAO_OK.replace(r"Com denominador", r"\comandoinexistente Com denominador"), encoding="utf-8")
    codigo, r = _rodar(capsys, "--banco", b, "validar", "ficticia", "q002", "--compilar")
    assert codigo == 1 and "Resolução" in r["questoes"]["q002"]["erros"][0]
    shutil.rmtree(tmp_path / "trabalho")
