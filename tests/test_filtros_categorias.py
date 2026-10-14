import pytest

from bancoq.nucleo.banco import ErroBanco
from bancoq.nucleo.entidades import Item, Questao
from bancoq.nucleo.repositorio import Filtro


@pytest.fixture
def povoado(repo):
    """Banco fictício: Cálculo > Integrais > Substituição, Cálculo > Limites, Álgebra."""
    calc = repo.criar_categoria("Cálculo")
    integ = repo.criar_categoria("Integrais", calc)
    subst = repo.criar_categoria("Substituição", integ)
    lim = repo.criar_categoria("Limites", calc)
    alg = repo.criar_categoria("Álgebra")
    dados = [
        ("Calcule a integral $\\int x\\,dx$.", subst, ["integral", "básica"], 2, "multipla", "Lista 1", 2021),
        ("Integral por partes de $x e^x$.", integ, ["integral"], 4, "discursiva", "Stewart", 2022),
        ("Calcule o limite fundamental trigonométrico.", lim, ["limite", "básica"], 3, "curta", "Lista 2", 2023),
        ("Determine o núcleo da transformação linear.", alg, ["matriz"], 5, "vf", "Prova antiga", 2020),
        ("Questão sem categoria sobre funções.", None, [], 1, "discursiva", "", None),
    ]
    ids = {}
    for enun, cat, tags, dif, tipo, fonte, ano in dados:
        q = Questao(tipo=tipo, enunciado=enun, categoria_id=cat, tags=tags, dificuldade=dif, fonte=fonte, ano=ano,
                    resolucao="Resolução detalhada com substituição." if "ntegral" in enun else "",
                    observacoes="usada na turma noturna" if dif == 5 else "")
        if tipo in ("multipla", "vf"):
            q.itens = [Item("alternativa trigonométrica", True), Item("outra")]
        ids[enun.split()[0] + str(dif)] = repo.salvar_questao(q)
    return {"calc": calc, "integ": integ, "subst": subst, "lim": lim, "alg": alg, "ids": ids}


def ids(repo, **kw):
    return sorted(r.id for r in repo.buscar(Filtro(**kw)))


def test_categoria_com_e_sem_subcategorias(repo, povoado):
    assert len(ids(repo, categoria_id=povoado["calc"])) == 3
    assert ids(repo, categoria_id=povoado["calc"], incluir_subcategorias=False) == []
    assert len(ids(repo, categoria_id=povoado["integ"])) == 2
    assert len(ids(repo, sem_categoria=True)) == 1


def test_tags_todas_ou_qualquer(repo, povoado):
    assert len(ids(repo, tags=["integral", "básica"])) == 1
    assert len(ids(repo, tags=["integral", "básica"], tags_modo="qualquer")) == 3
    assert ids(repo, tags=["inexistente"]) == []
    assert len(ids(repo, tags=["INTEGRAL"])) == 2


def test_tipo_dificuldade_fonte_ano(repo, povoado):
    assert len(ids(repo, tipos=["discursiva"])) == 2
    assert len(ids(repo, dif_min=3, dif_max=5)) == 3
    assert len(ids(repo, fonte="lista")) == 2
    assert len(ids(repo, ano_min=2021, ano_max=2022)) == 2


def test_busca_textual_sem_acentos_e_em_todos_os_campos(repo, povoado):
    assert len(ids(repo, texto="integral")) == 2           # enunciado
    assert len(ids(repo, texto="nucleo")) == 1             # sem acento
    assert len(ids(repo, texto="trigonometric")) == 3      # alternativas + enunciado (prefixo)
    assert len(ids(repo, texto="substituicao")) == 2       # resolução
    assert len(ids(repo, texto="noturna")) == 1            # observações
    assert len(ids(repo, texto="calc")) == 2               # prefixo


def test_filtros_combinados(repo, povoado):
    assert len(ids(repo, categoria_id=povoado["calc"], texto="calcule", dif_max=2)) == 1


def test_busca_sem_fts_usa_like(repo, povoado):
    repo.banco._usar_fts = False
    assert len(ids(repo, texto="nucleo")) == 1
    assert len(ids(repo, texto="trigonometric")) == 3


def test_renomear_mover_mesclar_excluir_categoria(repo, povoado):
    repo.renomear_categoria(povoado["lim"], "Limites e continuidade")
    assert "Cálculo > Limites e continuidade" in repo.caminhos_categorias().values()
    with pytest.raises(ErroBanco):
        repo.renomear_categoria(povoado["lim"], "integrais")
    with pytest.raises(ErroBanco):
        repo.mover_categoria(povoado["calc"], povoado["subst"])
    repo.mover_categoria(povoado["alg"], povoado["calc"])
    assert repo.caminhos_categorias()[povoado["alg"]] == "Cálculo > Álgebra"
    # mesclar Integrais em Limites: questões e subcategorias vão junto
    repo.mesclar_categorias(povoado["integ"], povoado["lim"])
    assert povoado["integ"] not in repo.caminhos_categorias()
    assert repo.caminhos_categorias()[povoado["subst"]] == "Cálculo > Limites e continuidade > Substituição"
    assert len(ids(repo, categoria_id=povoado["lim"])) == 3
    # excluir: tudo sobe para a mãe
    repo.excluir_categoria(povoado["lim"])
    assert repo.caminhos_categorias()[povoado["subst"]] == "Cálculo > Substituição"
    assert len(ids(repo, categoria_id=povoado["calc"], incluir_subcategorias=False)) == 2
    assert repo.contar_questoes() == 5


def test_mesclar_com_nomes_iguais_junta_subcategorias(repo):
    a = repo.criar_categoria("A")
    b = repo.criar_categoria("B")
    xa = repo.criar_categoria("X", a)
    xb = repo.criar_categoria("X", b)
    qid = repo.salvar_questao(Questao(enunciado="q", categoria_id=xa))
    repo.mesclar_categorias(a, b)
    assert repo.obter_questao(qid).categoria_id == xb
    assert sorted(repo.caminhos_categorias().values()) == ["B", "B > X"]


def test_renomear_mesclar_excluir_tags(repo, povoado):
    tags = {t.nome: t.id for t in repo.tags()}
    repo.renomear_tag(tags["matriz"], "matrizes")
    with pytest.raises(ErroBanco):
        repo.renomear_tag(tags["limite"], "Integral")
    repo.mesclar_tags([tags["limite"], tags["básica"]], tags["básica"])
    nomes = {t.nome: t.quantidade for t in repo.tags()}
    assert "limite" not in nomes and nomes["básica"] == 2
    repo.excluir_tag(tags["integral"])
    assert len(ids(repo, tags=["integral"])) == 0
    assert repo.contar_questoes() == 5
