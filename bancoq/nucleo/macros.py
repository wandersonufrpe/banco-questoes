"""Leitura das macros do preâmbulo do usuário para a configuração do MathJax.

Reconhece ``\\newcommand``, ``\\renewcommand``, ``\\providecommand`` (com ou
sem ``*``, com número de argumentos e valor padrão), ``\\DeclareMathOperator``
e ``\\def`` simples. O resto do preâmbulo (``\\usepackage`` etc.) é ignorado
na prévia rápida, mas vale na prévia exata e na exportação.
"""

from __future__ import annotations

import re

from .latex_html import remover_comentarios


class _Leitor:
    def __init__(self, s: str):
        self.s = s
        self.i = 0

    def espacos(self) -> None:
        while self.i < len(self.s) and self.s[self.i] in " \t\r\n":
            self.i += 1

    def grupo(self) -> str | None:
        self.espacos()
        if self.i >= len(self.s) or self.s[self.i] != "{":
            return None
        nivel = 0
        inicio = self.i + 1
        while self.i < len(self.s):
            ch = self.s[self.i]
            if ch == "\\":
                self.i += 2
                continue
            if ch == "{":
                nivel += 1
            elif ch == "}":
                nivel -= 1
                if nivel == 0:
                    self.i += 1
                    return self.s[inicio:self.i - 1]
            self.i += 1
        return None

    def opcional(self) -> str | None:
        self.espacos()
        if self.i >= len(self.s) or self.s[self.i] != "[":
            return None
        nivel = 0
        j = self.i + 1
        while j < len(self.s):
            ch = self.s[j]
            if ch == "{":
                nivel += 1
            elif ch == "}":
                nivel -= 1
            elif ch == "]" and nivel == 0:
                conteudo = self.s[self.i + 1:j]
                self.i = j + 1
                return conteudo
            j += 1
        return None

    def nome_comando(self) -> str | None:
        """Lê ``\\nome`` ou ``{\\nome}`` e devolve ``nome``."""
        self.espacos()
        if self.s.startswith("{", self.i):
            g = self.grupo()
            if g is None:
                return None
            m = re.fullmatch(r"\s*\\([A-Za-z@]+|.)\s*", g)
            return m.group(1) if m else None
        m = re.compile(r"\\([A-Za-z@]+|.)").match(self.s, self.i)
        if not m:
            return None
        self.i = m.end()
        return m.group(1)


RE_INICIO = re.compile(
    r"\\(newcommand|renewcommand|providecommand|DeclareMathOperator|DeclareRobustCommand|def)(\*?)"
)


def extrair_macros(preambulo: str) -> dict[str, object]:
    """Devolve o dicionário ``macros`` no formato da configuração do MathJax."""
    texto = remover_comentarios(preambulo or "")
    macros: dict[str, object] = {}
    pos = 0
    while True:
        m = RE_INICIO.search(texto, pos)
        if not m:
            break
        leitor = _Leitor(texto)
        leitor.i = m.end()
        tipo, estrela = m.group(1), m.group(2)
        try:
            if tipo == "def":
                nome = leitor.nome_comando()
                params = re.compile(r"(?:#\d)*").match(texto, leitor.i)
                n_args = len(params.group(0)) // 2 if params else 0
                leitor.i = params.end() if params else leitor.i
                corpo = leitor.grupo()
                if nome and corpo is not None:
                    macros[nome] = [corpo, n_args] if n_args else corpo
            elif tipo == "DeclareMathOperator":
                nome = leitor.nome_comando()
                corpo = leitor.grupo()
                if nome and corpo is not None:
                    op = "\\operatorname*" if estrela else "\\operatorname"
                    macros[nome] = f"{op}{{{corpo}}}"
            else:
                nome = leitor.nome_comando()
                n = leitor.opcional()
                padrao = leitor.opcional()
                corpo = leitor.grupo()
                if nome and corpo is not None:
                    n_args = int(n) if n and n.strip().isdigit() else 0
                    if tipo == "providecommand" and nome in macros:
                        pass
                    elif padrao is not None and n_args:
                        macros[nome] = [corpo, n_args, padrao]
                    elif n_args:
                        macros[nome] = [corpo, n_args]
                    else:
                        macros[nome] = corpo
        except (ValueError, IndexError):
            pass
        pos = max(leitor.i, m.end())
    return macros
