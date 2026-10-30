"""Banco usado pela importação e o resumo dele que o Claude consulta (só leitura)."""

from __future__ import annotations

import os
from pathlib import Path

from ..config_local import ConfigLocal
from ..nucleo.banco import Banco
from ..nucleo.config_banco import ConfigBanco
from ..nucleo.midia import GerenciadorMidia
from ..nucleo.repositorio import Repositorio


class ErroCatalogo(Exception):
    pass


def localizar_banco(pasta: str | Path | None = None) -> Path:
    """Pasta do banco: a indicada, a da variável BANCOQ_BANCO ou a última aberta no app."""
    candidatos = [
        ("--banco", pasta),
        ("BANCOQ_BANCO", os.environ.get("BANCOQ_BANCO")),
        ("último banco aberto no aplicativo", ConfigLocal.carregar().ultimo_banco),
    ]
    for origem, valor in candidatos:
        if not valor:
            continue
        p = Path(valor).expanduser()
        if Banco.e_banco(p):
            return p.resolve()
        raise ErroCatalogo(f"{p} ({origem}) não é uma pasta de banco de questões.")
    raise ErroCatalogo(
        "Não sei qual banco usar: abra o banco no aplicativo uma vez ou informe --banco <pasta>.")


def pasta_trabalho() -> Path:
    """Rascunhos da importação (fora do banco): <repositório>/trabalho, ou BANCOQ_TRABALHO."""
    forcada = os.environ.get("BANCOQ_TRABALHO")
    if forcada:
        return Path(forcada)
    return Path(__file__).resolve().parents[2] / "trabalho"


def abrir_repositorio(pasta_banco: Path) -> Repositorio:
    banco = Banco(pasta_banco, somente_leitura=True)
    return Repositorio(banco, GerenciadorMidia(banco.pasta_midia, pasta_trabalho() / "midia-temp"))


def _sugestoes_pendentes(pasta_banco: Path, existentes: set[str], tags_existentes: set[str]) -> tuple[list, list]:
    """Categorias e tags novas usadas em questões ainda não aprovadas (caixa de entrada e
    rascunhos), para as importações seguintes usarem os mesmos nomes."""
    from collections import Counter

    from ..nucleo.banco import sem_acentos
    from .pacote import Pacote, listar_pacotes

    pacotes = listar_pacotes(pasta_banco)
    decididas = {(p.nome, i) for p in pacotes for i in p.decisoes()}   # já aprovadas ou rejeitadas
    pastas = [p.pasta_questoes for p in pacotes]
    trabalho = pasta_trabalho()
    if trabalho.is_dir():
        pastas += [d / "questoes" for d in trabalho.iterdir() if (d / "questoes").is_dir()]
    cats, tags = Counter(), Counter()
    vistos: set[tuple[str, str]] = set()
    for pasta in pastas:
        pac = Pacote(pasta.parent)
        for ident in pac.ids():
            q = pac.questao(ident)
            chave = (pac.nome, ident)          # rascunho e entregue contam uma vez
            if chave in vistos or chave in decididas:
                continue
            vistos.add(chave)
            caminho = " > ".join(q.categoria)
            if caminho and sem_acentos(caminho) not in existentes:
                cats[caminho] += 1
            for t in q.tags:
                if sem_acentos(t) not in tags_existentes:
                    tags[t] += 1
    return ([{"caminho": c, "questoes": n} for c, n in sorted(cats.items())],
            [{"nome": t, "questoes": n} for t, n in sorted(tags.items())])


def catalogo(pasta_banco: Path) -> dict:
    """O que o Claude precisa saber do banco para preencher os metadados."""
    from ..nucleo.banco import sem_acentos

    repo = abrir_repositorio(pasta_banco)
    caminhos = repo.caminhos_categorias()
    contagem = repo.contagem_por_categoria()
    config = ConfigBanco.carregar(pasta_banco)
    tags = repo.tags()
    novas_cat, novas_tags = _sugestoes_pendentes(
        pasta_banco, {sem_acentos(c) for c in caminhos.values()}, {sem_acentos(t.nome) for t in tags})
    return {
        "banco": str(pasta_banco),
        "questoes": repo.contar_questoes(),
        "categorias": [
            {"caminho": caminho, "questoes": contagem.get(cid, 0)}
            for cid, caminho in sorted(caminhos.items(), key=lambda x: x[1].lower())
        ],
        "tags": [{"nome": t.nome, "questoes": t.quantidade} for t in tags],
        "fontes": repo.fontes(),
        "preambulo": config.preambulo,
        "categorias_novas_em_uso": novas_cat,
        "tags_novas_em_uso": novas_tags,
    }
