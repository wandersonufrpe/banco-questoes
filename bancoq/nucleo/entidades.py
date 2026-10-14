"""Estruturas de dados do banco de questões."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

TIPOS: dict[str, str] = {
    "discursiva": "Discursiva",
    "multipla": "Múltipla escolha",
    "vf": "Verdadeiro ou falso",
    "curta": "Resposta curta",
}

TIPOS_COM_ITENS = ("multipla", "vf")


def nome_tipo(tipo: str) -> str:
    return TIPOS.get(tipo, tipo)


@dataclass
class Item:
    """Alternativa (múltipla escolha) ou afirmativa (verdadeiro ou falso).

    Em múltipla escolha, ``correta`` marca a alternativa correta.
    Em verdadeiro ou falso, ``correta`` significa "verdadeira".
    """

    texto: str = ""
    correta: bool = False
    comentario: str = ""
    id: int | None = None


@dataclass
class Questao:
    id: int | None = None
    tipo: str = "discursiva"
    enunciado: str = ""
    itens: list[Item] = field(default_factory=list)
    resposta_curta: str = ""
    resolucao: str = ""
    observacoes: str = ""
    dificuldade: int = 3
    fonte: str = ""
    ano: int | None = None
    categoria_id: int | None = None
    tags: list[str] = field(default_factory=list)
    nao_embaralhar: bool = False
    criada_em: str = ""
    alterada_em: str = ""

    @property
    def usa_itens(self) -> bool:
        return self.tipo in TIPOS_COM_ITENS

    def itens_validos(self) -> list[Item]:
        """Itens que pertencem ao tipo atual (vazio para discursiva/curta)."""
        return list(self.itens) if self.usa_itens else []

    def copia(self) -> "Questao":
        return copy.deepcopy(self)

    def campos_latex(self) -> list[tuple[str, str]]:
        """Pares (nome legível do campo, texto) de todos os campos em LaTeX."""
        campos = [("Enunciado", self.enunciado)]
        rotulo = "Alternativa" if self.tipo == "multipla" else "Afirmativa"
        for i, item in enumerate(self.itens_validos()):
            nome = f"{rotulo} {letra(i) if self.tipo == 'multipla' else i + 1}"
            campos.append((nome, item.texto))
            if item.comentario.strip():
                campos.append((f"Comentário da {nome.lower()}", item.comentario))
        if self.tipo == "curta":
            campos.append(("Resposta esperada", self.resposta_curta))
        campos.append(("Resolução", self.resolucao))
        return campos


@dataclass
class Categoria:
    id: int
    nome: str
    pai_id: int | None = None


@dataclass
class Tag:
    id: int
    nome: str
    quantidade: int = 0


@dataclass
class ResumoQuestao:
    """Linha da lista de questões (sem itens nem textos longos)."""

    id: int
    tipo: str
    enunciado: str
    dificuldade: int
    fonte: str
    ano: int | None
    categoria_id: int | None
    tags: list[str]
    alterada_em: str


def letra(indice: int) -> str:
    """0 -> a, 1 -> b, ..., 25 -> z, 26 -> aa ..."""
    s = ""
    indice += 1
    while indice > 0:
        indice, resto = divmod(indice - 1, 26)
        s = chr(ord("a") + resto) + s
    return s


def letra_versao(indice: int) -> str:
    return letra(indice).upper()
