"""Montagem, sorteio, versões, semente e gabarito."""

import random

import pytest

from bancoq.nucleo.entidades import Item, Questao, letra
from bancoq.nucleo.prova import (
    ItemProva, Montagem, Regra, gerar_versoes, ressortear, sortear_regras, valor_total,
)


@pytest.fixture
def banco_fake(repo):
    """20 questões fictícias de vários tipos em duas categorias."""
    calc = repo.criar_categoria("Cálculo")
    alg = repo.criar_categoria("Álgebra")
    ids = []
    for i in range(20):
        tipo = ["multipla", "vf", "discursiva", "curta"][i % 4]
        q = Questao(tipo=tipo, enunciado=f"Questão fictícia {i}", categoria_id=calc if i < 12 else alg,
                    dificuldade=1 + i % 5, tags=["par" if i % 2 == 0 else "impar"],
                    resposta_curta=f"r{i}" if tipo == "curta" else "")
        if tipo == "multipla":
            q.itens = [Item(f"alt {k} da q{i}", correta=(k == i % 5)) for k in range(5)]
            q.nao_embaralhar = i == 4
        elif tipo == "vf":
            q.itens = [Item(f"afirm {k} da q{i}", correta=(k % 2 == 0)) for k in range(4)]
        ids.append(repo.salvar_questao(q))
    return {"repo": repo, "ids": ids, "calc": calc, "alg": alg}


def test_sorteio_por_regras_respeita_filtros(banco_fake):
    repo = banco_fake["repo"]
    m = Montagem()
    m.adicionar_manual([banco_fake["ids"][0]])
    m.regras = [Regra(n=3, categoria_id=banco_fake["calc"], tipo="multipla"),
                Regra(n=2, categoria_id=banco_fake["alg"], tags=["par"])]
    avisos = sortear_regras(repo, m, random.Random(1))
    assert len(m.itens) == 1 + 2 + 2           # só 3 múltiplas em Cálculo e 1 já está na prova
    assert any("só há 2" in a for a in avisos)
    assert m.itens[0].regra is None and m.itens[0].questao_id == banco_fake["ids"][0]
    assert len(set(m.ids())) == len(m.ids())   # sem repetição
    for it in m.itens[1:]:
        q = repo.obter_questao(it.questao_id)
        regra = m.regra(it.regra)
        if regra.tipo:
            assert q.tipo == "multipla" and q.categoria_id == banco_fake["calc"]
        else:
            assert "par" in q.tags and q.categoria_id == banco_fake["alg"]


def test_ressortear_troca_por_outra_da_mesma_regra(banco_fake):
    repo = banco_fake["repo"]
    m = Montagem(regras=[Regra(n=2, categoria_id=banco_fake["calc"])])
    sortear_regras(repo, m, random.Random(2))
    antes = m.ids()
    novo = ressortear(repo, m, 0, random.Random(3))
    assert novo is not None and novo not in antes
    assert m.itens[0].questao_id == novo and m.itens[1].questao_id == antes[1]
    assert repo.obter_questao(novo).categoria_id == banco_fake["calc"]
    m.itens.append(ItemProva(banco_fake["ids"][19]))
    assert ressortear(repo, m, 2) is None      # manual não ressorteia


def _montagem_completa(banco_fake, **kw):
    m = Montagem(num_versoes=4, embaralhar_questoes=True, embaralhar_alternativas=True, semente=424242, **kw)
    m.adicionar_manual(banco_fake["ids"][:12])
    return m


def test_versoes_reprodutiveis_com_a_mesma_semente(banco_fake):
    repo = banco_fake["repo"]
    m = _montagem_completa(banco_fake)
    qs = repo.obter_questoes(m.ids())
    v1 = gerar_versoes(m, qs)
    v2 = gerar_versoes(Montagem.de_dict(m.para_dict()), repo.obter_questoes(m.ids()))
    assert [[(qv.questao.id, qv.ordem_itens) for qv in v.questoes] for v in v1] == \
           [[(qv.questao.id, qv.ordem_itens) for qv in v.questoes] for v in v2]
    m.semente += 1
    v3 = gerar_versoes(m, qs)
    assert [[qv.questao.id for qv in v.questoes] for v in v1] != [[qv.questao.id for qv in v.questoes] for v in v3]


def test_versoes_diferentes_entre_si(banco_fake):
    m = _montagem_completa(banco_fake)
    versoes = gerar_versoes(m, banco_fake["repo"].obter_questoes(m.ids()))
    ordens = [tuple(qv.questao.id for qv in v.questoes) for v in versoes]
    assert len(set(ordens)) == 4
    assert [v.letra for v in versoes] == ["A", "B", "C", "D"]


def test_gabarito_corresponde_em_todas_as_versoes(banco_fake):
    """A letra do gabarito aponta, em cada versão, para a alternativa originalmente correta."""
    m = _montagem_completa(banco_fake)
    qs = banco_fake["repo"].obter_questoes(m.ids())
    versoes = gerar_versoes(m, qs)
    for v in versoes:
        assert sorted(qv.questao.id for qv in v.questoes) == sorted(m.ids())
        for qv in v.questoes:
            q = qs[qv.questao.id]
            assert sorted(qv.ordem_itens) == list(range(len(q.itens)))
            if q.tipo == "multipla":
                corretas_originais = [it.texto for it in q.itens if it.correta]
                letras = qv.letras_corretas()
                assert [q.itens[qv.ordem_itens[p]].texto for p in letras] == corretas_originais
                assert qv.resposta() == ", ".join(f"({letra(p)})" for p in letras)
            elif q.tipo == "vf":
                esperado = " ".join("V" if q.itens[i].correta else "F" for i in qv.ordem_itens)
                assert qv.resposta() == esperado
            elif q.tipo == "curta":
                assert qv.resposta() == q.resposta_curta


def test_nao_embaralhar_e_respeitado(banco_fake):
    m = _montagem_completa(banco_fake)
    qs = banco_fake["repo"].obter_questoes(m.ids())
    q4 = banco_fake["ids"][4]
    assert qs[q4].nao_embaralhar
    alguma_embaralhada = False
    for v in gerar_versoes(m, qs):
        for qv in v.questoes:
            if qv.questao.id == q4:
                assert qv.ordem_itens == list(range(5))
            elif qv.ordem_itens != sorted(qv.ordem_itens):
                alguma_embaralhada = True
    assert alguma_embaralhada


def test_sem_embaralhar_mantem_ordem(banco_fake):
    m = Montagem(num_versoes=2)
    m.adicionar_manual(banco_fake["ids"][:6])
    versoes = gerar_versoes(m, banco_fake["repo"].obter_questoes(m.ids()))
    for v in versoes:
        assert [qv.questao.id for qv in v.questoes] == banco_fake["ids"][:6]
        assert all(qv.ordem_itens == sorted(qv.ordem_itens) for qv in v.questoes)


def test_serializacao_e_valor_total():
    m = Montagem(nome="P1", regras=[Regra(n=2, tags=["a"])])
    m.itens = [ItemProva(1, "1,5"), ItemProva(2, "2", 4.0, m.regras[0].id)]
    m2 = Montagem.de_dict(m.para_dict())
    assert m2 == m
    assert valor_total(m) == 3.5
    m.remover_regra(m.regras[0].id)
    assert m.itens[1].regra is None
