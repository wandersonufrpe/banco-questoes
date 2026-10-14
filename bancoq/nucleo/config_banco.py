"""Configurações que pertencem ao banco (ficam dentro da pasta sincronizada)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path

ARQUIVO_CONFIG = "configuracoes.json"


@dataclass
class ConfigBanco:
    preambulo: str = ""              # pacotes e macros do usuário (\usepackage, \newcommand...)
    modelo_padrao: str = "generico.tex"
    limite_duplicadas: int = 85      # semelhança mínima (0–100) para avisar
    num_backups: int = 10
    checar_latex_ao_salvar: bool = True
    checar_duplicadas_ao_salvar: bool = True

    @classmethod
    def carregar(cls, pasta_banco: Path) -> "ConfigBanco":
        cfg = cls()
        try:
            dados = json.loads((Path(pasta_banco) / ARQUIVO_CONFIG).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cfg
        nomes = {f.name for f in fields(cls)}
        for chave, valor in dados.items():
            if chave in nomes:
                setattr(cfg, chave, valor)
        return cfg

    def salvar(self, pasta_banco: Path) -> None:
        destino = Path(pasta_banco) / ARQUIVO_CONFIG
        tmp = destino.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(destino)
