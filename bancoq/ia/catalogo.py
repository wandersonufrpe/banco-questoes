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


def catalogo(pasta_banco: Path) -> dict:
    """O que o Claude precisa saber do banco para preencher os metadados."""
    repo = abrir_repositorio(pasta_banco)
    caminhos = repo.caminhos_categorias()
    contagem = repo.contagem_por_categoria()
    config = ConfigBanco.carregar(pasta_banco)
    return {
        "banco": str(pasta_banco),
        "questoes": repo.contar_questoes(),
        "categorias": [
            {"caminho": caminho, "questoes": contagem.get(cid, 0)}
            for cid, caminho in sorted(caminhos.items(), key=lambda x: x[1].lower())
        ],
        "tags": [{"nome": t.nome, "questoes": t.quantidade} for t in repo.tags()],
        "fontes": repo.fontes(),
        "preambulo": config.preambulo,
    }
