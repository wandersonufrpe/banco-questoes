from bancoq.nucleo.latex_html import AVISO, latex_para_html, remover_comentarios, texto_simples
from bancoq.nucleo.macros import extrair_macros


def test_matematica_vai_para_o_mathjax():
    h = latex_para_html(r"Seja $x<1$ e \[ y = \frac{1}{2} \]")
    assert r"\(x&lt;1\)" in h
    assert r"\[ y = \frac{1}{2} \]" in h


def test_formatacao_paragrafos_e_listas():
    h = latex_para_html("\\textbf{a} \\emph{b}\n\nnovo\n\\begin{enumerate}[label=(\\alph*)]\\item um\\item dois\\end{enumerate}")
    assert "<b>a</b>" in h and "<em>b</em>" in h
    assert h.count('<div class="p">') == 2
    assert '<ol type="a">' in h and h.count("<li>") == 2


def test_itemize_aninhado():
    h = latex_para_html(r"\begin{itemize}\item a \begin{itemize}\item b\end{itemize}\item c\end{itemize}")
    assert h.count("<ul>") == 2
    assert h.count("<li>") == 3


def test_nao_suportado_avisa():
    h = latex_para_html(r"Figura: \begin{tikzpicture}\draw (0,0)--(1,1);\end{tikzpicture} fim")
    assert AVISO in h and "draw" not in h and "fim" in h


def test_simbolos_e_comentarios():
    h = latex_para_html("50\\% de R\\$ 10 % comentário\nok -- sim")
    assert "50% de R$ 10" in h and "comentário" not in h and "–" in h


def test_math_com_dolar_escapado():
    h = latex_para_html(r"custa \$3 e $a+b$")
    assert "custa $3 e \\(a+b\\)" in h


def test_imagem():
    h = latex_para_html("x [[img:0123456789abcdef|0.3]] y", lambda i: f"file:///m/{i}.png")
    assert 'src="file:///m/0123456789abcdef.png"' in h and "width:30%" in h
    h2 = latex_para_html("[[img:0123456789abcdef]]", lambda i: None)
    assert "imagem não encontrada" in h2


def test_acentos_antigos():
    assert "ação" in latex_para_html(r"a\c{c}\~ao")


def test_remover_comentarios_respeita_escape():
    assert remover_comentarios("a\\% b % c\nd") == "a\\% b d"


def test_texto_simples():
    assert texto_simples("\\textbf{Calcule}  $x$\n\n[[img:abcdefabcdef1234]]") == "Calcule $x$ [imagem]"


def test_macros():
    m = extrair_macros(r"""
\usepackage{amsmath}
\newcommand{\R}{\mathbb{R}}  % reais
\newcommand*\abs[1]{\left|#1\right|}
\renewcommand{\v}[2][x]{#2_{#1}}
\DeclareMathOperator{\sen}{sen}
\DeclareMathOperator*{\argmax}{arg\,max}
\def\N{\mathbb{N}}
""")
    assert m["R"] == r"\mathbb{R}"
    assert m["abs"] == [r"\left|#1\right|", 1]
    assert m["v"] == ["#2_{#1}", 2, "x"]
    assert m["sen"] == r"\operatorname{sen}"
    assert m["argmax"] == r"\operatorname*{arg\,max}"
    assert m["N"] == r"\mathbb{N}"
