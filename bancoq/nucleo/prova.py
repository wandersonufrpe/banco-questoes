"""Montagem de prova: seleção manual, sorteio por regras, versões e gabarito."""

from __future__ import annotations

import random
import uuid
from dataclasses import asdict, dataclass, field

from .entidades import Questao, letra_versao, nome_tipo
from .latex_gerar import resposta_curta_gabarito
from .repositorio import Filtro, Repositorio

MAX_VERSOES = 26


def nova_semente() -> int:
    return random.SystemRandom().randint(100000, 999999)


@dataclass
class Cabecalho:
    titulo: str = ""
    disciplina: str = ""
    turma: str = ""
    professor: str = ""
    data: str = ""
    instrucoes: str = ""


@dataclass
class Regra:
    """ "N questões de [categoria] com [tags], dificuldade [faixa], tipo [x]"."""

    n: int = 1
    categoria_id: int | None = None
    incluir_subcategorias: bool = True
    tags: list[str] = field(default_factory=list)
    tags_modo: str = "todas"
    dif_min: int = 1
    dif_max: int = 5
    tipo: str | None = None
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])

    def filtro(self, excluir: list[int] | None = None) -> Filtro:
        return Filtro(
            categoria_id=self.categoria_id, incluir_subcategorias=self.incluir_subcategorias,
            tags=list(self.tags), tags_modo=self.tags_modo, tipos=[self.tipo] if self.tipo else [],
            dif_min=min(self.dif_min, self.dif_max), dif_max=max(self.dif_min, self.dif_max),
            excluir_ids=list(excluir or []),
        )

    def descricao(self, caminhos: dict[int, str]) -> str:
        inicio = f"{self.n} {'questão' if self.n == 1 else 'questões'}"
        if self.categoria_id is not None:
            inicio += (f" de {caminhos.get(self.categoria_id, '(categoria excluída)')}"
                       + ("" if self.incluir_subcategorias else " (sem subcategorias)"))
        partes = [inicio]
        if self.tags:
            junta = " e " if self.tags_modo == "todas" else " ou "
            partes.append("com " + junta.join(self.tags))
        if (self.dif_min, self.dif_max) != (1, 5):
            a, b = sorted((self.dif_min, self.dif_max))
            partes.append(f"dificuldade {a}" if a == b else f"dificuldade {a} a {b}")
        if self.tipo:
            partes.append(f"tipo {nome_tipo(self.tipo).lower()}")
        return ", ".join(partes)


@dataclass
class ItemProva:
    questao_id: int
    valor: str = ""            # texto livre, ex.: "1,5"
    espaco_cm: float = 0.0     # espaço para resposta (discursivas)
    regra: str | None = None   # id da regra que sorteou; None = escolha manual


@dataclass
class Montagem:
    nome: str = ""
    cabecalho: Cabecalho = field(default_factory=Cabecalho)
    itens: list[ItemProva] = field(default_factory=list)
    regras: list[Regra] = field(default_factory=list)
    num_versoes: int = 1
    embaralhar_questoes: bool = False
    embaralhar_alternativas: bool = False
    semente: int = field(default_factory=nova_semente)
    modelo: str = ""

    # -- (des)serialização -------------------------------------------------------------
    def para_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def de_dict(cls, d: dict) -> "Montagem":
        m = cls()
        m.nome = d.get("nome", "")
        m.cabecalho = Cabecalho(**{k: v for k, v in d.get("cabecalho", {}).items()
                                   if k in Cabecalho.__dataclass_fields__})
        m.itens = [ItemProva(**{k: v for k, v in i.items() if k in ItemProva.__dataclass_fields__})
                   for i in d.get("itens", [])]
        m.regras = [Regra(**{k: v for k, v in r.items() if k in Regra.__dataclass_fields__})
                    for r in d.get("regras", [])]
        m.num_versoes = max(1, min(MAX_VERSOES, int(d.get("num_versoes", 1))))
        m.embaralhar_questoes = bool(d.get("embaralhar_questoes", False))
        m.embaralhar_alternativas = bool(d.get("embaralhar_alternativas", False))
        m.semente = int(d.get("semente", nova_semente()))
        m.modelo = d.get("modelo", "")
        return m

    # -- consultas -----------------------------------------------------------------------
    def ids(self) -> list[int]:
        return [i.questao_id for i in self.itens]

    def regra(self, rid: str | None) -> Regra | None:
        return next((r for r in self.regras if r.id == rid), None)

    def adicionar_manual(self, ids: list[int]) -> int:
        existentes = set(self.ids())
        n = 0
        for qid in ids:
            if qid not in existentes:
                self.itens.append(ItemProva(qid))
                existentes.add(qid)
                n += 1
        return n

    def remover_regra(self, rid: str) -> None:
        self.regras = [r for r in self.regras if r.id != rid]
        for it in self.itens:
            if it.regra == rid:
                it.regra = None


# =============================================================================
# sorteio
# =============================================================================
def sortear_regras(repo: Repositorio, m: Montagem, rng: random.Random | None = None) -> list[str]:
    """Refaz o sorteio de todas as regras. Questões escolhidas à mão ficam.

    Devolve avisos (por exemplo, regra com menos questões disponíveis que o pedido).
    """
    rng = rng or random.Random()
    m.itens = [i for i in m.itens if i.regra is None or m.regra(i.regra) is None]
    for it in m.itens:
        it.regra = None if m.regra(it.regra) is None else it.regra
    avisos = []
    caminhos = repo.caminhos_categorias()
    for regra in m.regras:
        candidatos = repo.ids_filtrados(regra.filtro(excluir=m.ids()))
        if len(candidatos) < regra.n:
            avisos.append(f"Regra “{regra.descricao(caminhos)}”: só há {len(candidatos)} questão(ões) disponível(is).")
        escolhidos = rng.sample(candidatos, min(regra.n, len(candidatos)))
        for qid in escolhidos:
            m.itens.append(ItemProva(qid, regra=regra.id))
    return avisos


def ressortear(repo: Repositorio, m: Montagem, indice: int, rng: random.Random | None = None) -> int | None:
    """Troca a questão ``indice`` por outra da mesma regra. Devolve o novo id ou None."""
    rng = rng or random.Random()
    item = m.itens[indice]
    regra = m.regra(item.regra)
    if regra is None:
        return None
    candidatos = repo.ids_filtrados(regra.filtro(excluir=m.ids()))
    if not candidatos:
        return None
    novo = rng.choice(candidatos)
    m.itens[indice] = ItemProva(novo, valor=item.valor, espaco_cm=item.espaco_cm, regra=regra.id)
    return novo


def contar_disponiveis(repo: Repositorio, regra: Regra, excluir: list[int] | None = None) -> int:
    return len(repo.ids_filtrados(regra.filtro(excluir=excluir)))


# =============================================================================
# versões
# =============================================================================
@dataclass
class QuestaoVersao:
    numero: int                 # 1, 2, 3… na versão
    item: ItemProva
    questao: Questao
    ordem_itens: list[int]      # índices das alternativas originais, na ordem da versão

    def resposta(self) -> str:
        return resposta_curta_gabarito(self.questao, self.ordem_itens)

    def letras_corretas(self) -> list[int]:
        """Posições (0 = a) das alternativas corretas nesta versão."""
        itens = self.questao.itens_validos()
        return [pos for pos, i in enumerate(self.ordem_itens) if itens[i].correta]


@dataclass
class Versao:
    indice: int
    letra: str
    questoes: list[QuestaoVersao]


def gerar_versoes(m: Montagem, questoes: dict[int, Questao]) -> list[Versao]:
    """Gera as versões de forma determinística a partir da semente.

    A mesma montagem (mesmas questões, mesma ordem, mesmas opções e mesma
    semente) produz sempre as mesmas versões.
    """
    itens = [it for it in m.itens if it.questao_id in questoes]
    versoes: list[Versao] = []
    ordens_usadas: list[list[int]] = []
    for v in range(max(1, min(MAX_VERSOES, m.num_versoes))):
        rng = random.Random(f"bancoq:{m.semente}:{v}")
        ordem = list(range(len(itens)))
        if m.embaralhar_questoes and len(itens) > 1:
            for _ in range(30):  # tenta não repetir a ordem de outra versão
                rng.shuffle(ordem)
                if ordem not in ordens_usadas:
                    break
        ordens_usadas.append(list(ordem))
        lista = []
        for numero, k in enumerate(ordem, start=1):
            it = itens[k]
            q = questoes[it.questao_id]
            oi = list(range(len(q.itens_validos())))
            if m.embaralhar_alternativas and not q.nao_embaralhar and len(oi) > 1:
                rng.shuffle(oi)
            lista.append(QuestaoVersao(numero, it, q, oi))
        versoes.append(Versao(v, letra_versao(v), lista))
    return versoes


def valor_numerico(valor: str) -> float | None:
    t = (valor or "").strip().replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def valor_total(m: Montagem) -> float | None:
    valores = [valor_numerico(i.valor) for i in m.itens if (i.valor or "").strip()]
    if not valores or any(v is None for v in valores):
        return None
    return sum(valores)
