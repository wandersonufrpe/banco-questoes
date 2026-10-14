"""Importador de .tex: classe exam, enumerate aninhado, títulos e divisão manual."""

from pathlib import Path

from bancoq.nucleo.importador import definicoes_do_preambulo, importar, padrao_por_nome, padroes
from bancoq.nucleo.importador.base import PadraoImportacao, QuestaoImportada, registrar
from bancoq.nucleo.midia import GerenciadorMidia, ids_no_texto

from conftest import DADOS, png_minimo


def ler(nome):
    return (DADOS / nome).read_text(encoding="utf-8")


def test_classe_exam():
    r = importar(ler("prova_exam.tex"))
    assert r.padrao == "Classe exam"
    assert len(r.questoes) == 4                          # a questão comentada não entra
    q1, q2, q3, q4 = r.questoes
    assert q1.tipo == "multipla" and [i.correta for i in q1.itens] == [False, True, False, False]
    assert q1.itens[1].texto == "$1$"
    assert q1.resolucao == "Limite fundamental trigonométrico."
    assert q2.tipo == "discursiva" and "\\begin{enumerate}" in q2.enunciado and "\\item Calcule" in q2.enunciado
    assert "\\part" not in q2.enunciado and q2.resolucao.startswith("$f'(x) = 2x$")
    assert q3.tipo == "curta" and q3.resposta_curta == "$4$" and "\\textbf{Bônus}" in q3.enunciado
    assert q4.tipo == "multipla" and q4.itens[0].correta and not q4.itens[1].correta
    assert "vspace" not in q4.enunciado


def test_macros_do_preambulo():
    r = importar(ler("prova_exam.tex"))
    assert definicoes_do_preambulo(r.preambulo) == [
        r"\newcommand{\R}{\mathbb{R}}", r"\DeclareMathOperator{\sen}{sen}",
        r"\newcommand{\abs}[1]{\left|#1\right|}",
    ]


def test_enumerate_aninhado(tmp_path):
    (tmp_path / "figura_teste.png").write_bytes(png_minimo(5))
    midia = GerenciadorMidia(tmp_path / "midia", tmp_path / "temp")
    texto = ler("prova_enumerate.tex")
    r = importar(texto, pasta_base=tmp_path, midia=midia)
    assert r.padrao == "Lista enumerate"
    assert len(r.questoes) == 4                          # instruções fora do enumerate ficam de fora
    q1, q2, q3, q4 = r.questoes
    assert q1.tipo == "multipla" and [i.correta for i in q1.itens] == [False, True, False]
    assert "\\correta" not in q1.itens[1].texto
    assert q2.tipo == "discursiva" and q2.resolucao.startswith("Suponha")
    assert "Resolução" not in q2.enunciado
    assert q3.tipo == "vf" and [i.correta for i in q3.itens] == [True, False]
    assert q3.itens[0].texto.startswith("Todo número")
    assert q4.tipo == "discursiva"                       # lista no meio do texto não é alternativa
    ids = ids_no_texto(q4.enunciado)
    assert len(ids) == 1 and midia.e_pendente(ids[0])   # imagem importada só como pendente
    assert "|0.4]]" in q4.enunciado
    assert not (tmp_path / "midia").exists()


def test_titulos_questao_n():
    r = importar(ler("prova_titulos.tex"))
    assert r.padrao == "Títulos “Questão N”"
    assert [q.tipo for q in r.questoes] == ["discursiva", "multipla", "discursiva"]
    assert r.questoes[1].itens[0].correta


def test_divisao_manual_por_separador():
    texto = "Primeira questão $x$.\n%%%\nSegunda questão.\n\\begin{enumerate}\\item a\\item b\\end{enumerate}\n%%%%\n\nTerceira."
    r = importar(texto)
    assert r.padrao == "Separador manual"
    assert [q.enunciado for q in r.questoes] == ["Primeira questão $x$.", "Segunda questão.", "Terceira."]
    assert r.questoes[1].tipo == "multipla"


def test_texto_sem_estrutura_vira_uma_questao():
    r = importar("Só um parágrafo com $x^2$.")
    assert len(r.questoes) == 1 and r.questoes[0].enunciado == "Só um parágrafo com $x^2$."


def test_padrao_escolhido_manualmente():
    r = importar(ler("prova_exam.tex"), padrao=padrao_por_nome("Separador manual"))
    assert r.padrao == "Separador manual" and len(r.questoes) == 1


def test_novo_padrao_pode_ser_registrado():
    @registrar
    class PadraoPontoEVirgula(PadraoImportacao):
        nome = "Teste ;;"
        descricao = "separa por ;;"

        def pontuar(self, corpo):
            return 1000 if ";;" in corpo else 0

        def separar(self, corpo):
            return [QuestaoImportada(enunciado=t.strip()) for t in corpo.split(";;")]

    try:
        r = importar("a ;; b ;; c")
        assert r.padrao == "Teste ;;" and len(r.questoes) == 3
    finally:
        from bancoq.nucleo.importador import base

        base._REGISTRO[:] = [p for p in base._REGISTRO if p.nome != "Teste ;;"]
    assert "Teste ;;" not in [p.nome for p in padroes()]
