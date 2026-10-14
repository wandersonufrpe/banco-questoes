"""Detecção de questões duplicadas (enunciados parecidos), com rapidfuzz."""

from __future__ import annotations

import hashlib
import re

from rapidfuzz import fuzz, process

from .banco import sem_acentos
from .latex_html import remover_comentarios
from .midia import RE_MARCADOR

TAMANHO_MINIMO = 12   # enunciados normalizados menores que isso não são comparados

_cache: dict[str, str] = {}


def _comando(m: re.Match) -> str:
    # \% \$ \& \# \_ \{ \} são caracteres; o resto (\textbf, \, \\ …) é formatação
    c = m.group(0)
    return c[1] if len(c) == 2 and c[1] in "%$&#_{}" else " "


def normalizar(texto: str) -> str:
    """Enunciado sem espaços, comandos de formatação, chaves, $ e acentos, em minúsculas."""
    t = remover_comentarios(texto or "")
    t = RE_MARCADOR.sub(" ", t)
    t = re.sub(r"\\(?:begin|end)\s*\{[^}]*\}", " ", t)
    t = re.sub(r"\\(?:[A-Za-z@]+\*?|.)", _comando, t)
    t = sem_acentos(t)
    t = re.sub(r"[\s{}$~&]+", "", t)
    return t


def _normalizado_cache(texto: str) -> str:
    chave = hashlib.md5(texto.encode("utf-8")).hexdigest()
    if chave not in _cache:
        if len(_cache) > 50000:
            _cache.clear()
        _cache[chave] = normalizar(texto)
    return _cache[chave]


def procurar_parecidas(enunciado: str, candidatos: list[tuple[int, str]], limite: float = 85,
                       excluir_id: int | None = None, maximo: int = 5) -> list[tuple[int, float]]:
    """Questões com semelhança >= ``limite`` (0–100), da mais parecida para a menos."""
    alvo = normalizar(enunciado)
    if len(alvo) < TAMANHO_MINIMO:
        return []
    escolhas = {qid: _normalizado_cache(t) for qid, t in candidatos if qid != excluir_id}
    escolhas = {k: v for k, v in escolhas.items() if v}
    achados = process.extract(alvo, escolhas, scorer=fuzz.ratio, score_cutoff=limite, limit=maximo)
    return [(chave, round(pontos, 1)) for _texto, pontos, chave in achados]
