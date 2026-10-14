import sqlite3

import pytest

from bancoq.nucleo.banco import ARQUIVO_DB, Banco, ErroBanco, ErroSomenteLeitura
from bancoq.nucleo.entidades import Item, Questao
from bancoq.nucleo.repositorio import CategoriaNova, Filtro, Repositorio

from conftest import png_minimo


def q_multipla(enunciado="Quanto é $1+1$?", **kw):
    return Questao(
        tipo="multipla", enunciado=enunciado,
        itens=[Item("$1$"), Item("$2$", True, "certo"), Item("$3$")], **kw,
    )


def test_banco_comeca_vazio_e_com_estrutura(banco, repo):
    assert repo.contar_questoes() == 0
    assert repo.categorias() == []
    assert repo.tags() == []
    for sub in ("midia", "modelos", "backups"):
        assert (banco.pasta / sub).is_dir()
    assert (banco.pasta / "modelos" / "generico.tex").exists()
    assert (banco.pasta / "configuracoes.json").exists()


def test_sem_wal_e_sem_arquivos_auxiliares(banco, repo):
    repo.salvar_questao(q_multipla())
    with banco.conectar() as c:
        assert c.execute("PRAGMA journal_mode").fetchone()[0].lower() == "delete"
    nomes = {p.name for p in banco.pasta.iterdir()}
    assert not any(n.endswith(("-wal", "-shm", "-journal")) for n in nomes)


def test_criar_banco_duas_vezes_falha(banco):
    with pytest.raises(ErroBanco):
        Banco.criar(banco.pasta)


def test_salvar_e_ler_questao(repo):
    q = q_multipla(dificuldade=4, fonte="Lista 2", ano=2023, tags=["limites", "Fácil", "limites"],
                   resolucao="Basta somar.", observacoes="usei em 2023", nao_embaralhar=True)
    qid = repo.salvar_questao(q)
    lida = repo.obter_questao(qid)
    assert lida.tipo == "multipla"
    assert [i.texto for i in lida.itens] == ["$1$", "$2$", "$3$"]
    assert [i.correta for i in lida.itens] == [False, True, False]
    assert lida.itens[1].comentario == "certo"
    assert sorted(lida.tags) == ["Fácil", "limites"]
    assert lida.dificuldade == 4 and lida.fonte == "Lista 2" and lida.ano == 2023
    assert lida.nao_embaralhar
    assert lida.criada_em and lida.alterada_em


def test_atualizar_questao_troca_itens_e_tags(repo):
    qid = repo.salvar_questao(q_multipla(tags=["a", "b"]))
    q = repo.obter_questao(qid)
    q.itens = [Item("x", True), Item("y")]
    q.tags = ["b", "c"]
    repo.salvar_questao(q)
    lida = repo.obter_questao(qid)
    assert [i.texto for i in lida.itens] == ["x", "y"]
    assert lida.tags == ["b", "c"]
    assert repo.contar_questoes() == 1


def test_discursiva_descarta_itens(repo):
    q = q_multipla()
    q.tipo = "discursiva"
    qid = repo.salvar_questao(q)
    assert repo.obter_questao(qid).itens == []


def test_tags_sem_diferenciar_maiusculas(repo):
    repo.salvar_questao(q_multipla(tags=["Limites"]))
    repo.salvar_questao(q_multipla(tags=["limites"]))
    assert [t.nome for t in repo.tags()] == ["Limites"]
    assert repo.tags()[0].quantidade == 2


def test_excluir_questao(repo):
    qid = repo.salvar_questao(q_multipla())
    repo.excluir_questao(qid)
    assert repo.obter_questao(qid) is None
    assert repo.buscar(Filtro(texto="quanto")) == []


def test_categoria_nova_so_e_criada_ao_salvar(repo):
    raiz = repo.criar_categoria("Cálculo")
    nova = CategoriaNova(raiz, ["Integrais", "Substituição"])
    assert len(repo.categorias()) == 1
    qid = repo.salvar_questao(q_multipla(), nova)
    caminhos = repo.caminhos_categorias()
    q = repo.obter_questao(qid)
    assert caminhos[q.categoria_id] == "Cálculo > Integrais > Substituição"
    # salvar outra com o mesmo caminho reaproveita
    repo.salvar_questao(q_multipla(), CategoriaNova(raiz, ["integrais", "Substituição"]))
    assert len(repo.categorias()) == 3


def test_imagens_vao_para_midia_so_ao_salvar(repo, banco):
    dados = png_minimo(7)
    ident = repo.midia.adicionar_bytes(dados)
    assert repo.midia.e_pendente(ident)
    assert not any(banco.pasta_midia.iterdir())
    q = q_multipla(enunciado=f"Veja [[img:{ident}|0.5]]")
    q.itens[0].texto = f"[[img:{ident}]]"
    qid = repo.salvar_questao(q)
    arquivos = list(banco.pasta_midia.iterdir())
    assert [p.name for p in arquivos] == [f"{ident}.png"]
    assert len(ident) == 16
    ligacoes = repo.imagens_da_questao(qid)
    assert (None, f"{ident}.png") in ligacoes
    item_id = repo.obter_questao(qid).itens[0].id
    assert (item_id, f"{ident}.png") in ligacoes


def test_somente_leitura(banco, tmp_path):
    from bancoq.nucleo.midia import GerenciadorMidia

    ro = Repositorio(Banco(banco.pasta, somente_leitura=True), GerenciadorMidia(banco.pasta_midia, tmp_path))
    assert ro.contar_questoes() == 0
    with pytest.raises(ErroSomenteLeitura):
        ro.salvar_questao(q_multipla())


def test_montagens(repo):
    mid = repo.salvar_montagem("P1", {"x": 1})
    assert repo.obter_montagem(mid) == ("P1", {"x": 1})
    repo.salvar_montagem("P1 v2", {"x": 2}, mid)
    assert repo.listar_montagens()[0][1] == "P1 v2"
    repo.excluir_montagem(mid)
    assert repo.listar_montagens() == []
