"""Configurações desta máquina (caminho do TeX, último banco aberto etc.).

Ficam fora da pasta sincronizada, em ~/.config/BancoQuestoes (Linux) ou
%APPDATA%\\BancoQuestoes (Windows).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from .caminhos import pasta_config_local


@dataclass
class ConfigLocal:
    ultimo_banco: str = ""
    bancos_recentes: list[str] = field(default_factory=list)
    caminho_tex: str = ""            # pdflatex ou latexmk; vazio = procurar no PATH
    tempo_limite_previa: int = 30    # segundos
    tempo_limite_prova: int = 180    # segundos
    ultima_pasta_saida: str = ""
    ultima_pasta_imagens: str = ""
    geometria: dict = field(default_factory=dict)

    @staticmethod
    def arquivo() -> Path:
        return pasta_config_local() / "config.json"

    @classmethod
    def carregar(cls) -> "ConfigLocal":
        cfg = cls()
        try:
            dados = json.loads(cls.arquivo().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cfg
        nomes = {f.name for f in fields(cls)}
        for chave, valor in dados.items():
            if chave in nomes:
                setattr(cfg, chave, valor)
        return cfg

    def salvar(self) -> None:
        destino = self.arquivo()
        destino.parent.mkdir(parents=True, exist_ok=True)
        tmp = destino.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(destino)

    def registrar_banco(self, pasta: str) -> None:
        self.ultimo_banco = pasta
        recentes = [p for p in self.bancos_recentes if p != pasta]
        self.bancos_recentes = [pasta] + recentes[:7]
