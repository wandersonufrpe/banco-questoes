"""Conversão de um subconjunto do LaTeX para HTML (prévia rápida).

A matemática é repassada ao MathJax com os delimitadores ``\\( \\)`` e
``\\[ \\]``; o texto em volta é convertido aqui: parágrafos, ``\\textbf``,
``\\emph``, ``itemize``, ``enumerate``, ``tabular`` simples e alguns símbolos.
O que não é suportado (TikZ, por exemplo) vira o aviso
"[use a prévia exata]".
"""

from __future__ import annotations

import html
import re
import unicodedata
from typing import Callable

from .midia import RE_MARCADOR, largura_de

AVISO = "[use a prévia exata]"

AMBIENTES_MATEMATICOS = {
    "equation", "equation*", "align", "align*", "gather", "gather*", "multline",
    "multline*", "flalign", "flalign*", "alignat", "alignat*", "eqnarray", "eqnarray*",
    "displaymath", "math",
}

# comandos de texto com um argumento -> (abre, fecha)
FORMATOS = {
    "textbf": ("<b>", "</b>"),
    "textit": ("<i>", "</i>"),
    "emph": ("<em>", "</em>"),
    "textsl": ("<i>", "</i>"),
    "underline": ("<u>", "</u>"),
    "texttt": ("<code>", "</code>"),
    "textsc": ('<span style="font-variant:small-caps">', "</span>"),
    "textrm": ("", ""),
    "textsf": ('<span style="font-family:sans-serif">', "</span>"),
    "textup": ("", ""),
    "textnormal": ("", ""),
    "text": ("", ""),
    "mbox": ("", ""),
    "makebox": ("", ""),
    "fbox": ('<span class="fbox">', "</span>"),
    "framebox": ('<span class="fbox">', "</span>"),
    "footnote": ('<sup class="nota">(', ")</sup>"),
    "url": ("<code>", "</code>"),
    "enquote": ("“", "”"),
}

# comandos que mudam o estilo até o fim do grupo: {\bf ...}
SELETORES = {
    "bf": ("<b>", "</b>"), "bfseries": ("<b>", "</b>"),
    "it": ("<i>", "</i>"), "itshape": ("<i>", "</i>"),
    "em": ("<em>", "</em>"), "sl": ("<i>", "</i>"), "slshape": ("<i>", "</i>"),
    "tt": ("<code>", "</code>"), "ttfamily": ("<code>", "</code>"),
    "sc": ('<span style="font-variant:small-caps">', "</span>"),
    "scshape": ('<span style="font-variant:small-caps">', "</span>"),
    "rm": ("", ""), "rmfamily": ("", ""), "upshape": ("", ""), "normalfont": ("", ""),
    "sffamily": ('<span style="font-family:sans-serif">', "</span>"),
    "tiny": ('<span style="font-size:60%">', "</span>"),
    "scriptsize": ('<span style="font-size:70%">', "</span>"),
    "footnotesize": ('<span style="font-size:80%">', "</span>"),
    "small": ('<span style="font-size:90%">', "</span>"),
    "normalsize": ("", ""),
    "large": ('<span style="font-size:120%">', "</span>"),
    "Large": ('<span style="font-size:144%">', "</span>"),
    "LARGE": ('<span style="font-size:173%">', "</span>"),
    "huge": ('<span style="font-size:207%">', "</span>"),
    "Huge": ('<span style="font-size:249%">', "</span>"),
    "centering": ('<div style="text-align:center">', "</div>"),
    "raggedright": ("", ""), "raggedleft": ('<div style="text-align:right">', "</div>"),
}

SIMBOLOS = {
    "%": "%", "$": "$", "&": "&amp;", "#": "#", "_": "_", "{": "{", "}": "}",
    " ": " ", ",": "\u2009", ";": "\u2005", ":": "\u2005", "!": "", "-": "", "/": "",
    "@": "", "\\": "<br>", "textbackslash": "\\", "ldots": "…", "dots": "…",
    "textellipsis": "…", "quad": "\u2003", "qquad": "\u2003\u2003", "S": "§", "P": "¶",
    "textdegree": "°", "degree": "°", "copyright": "©", "textregistered": "®",
    "LaTeX": "L<sup>A</sup>T<sub>E</sub>X", "TeX": "T<sub>E</sub>X", "newline": "<br>",
    "linebreak": "<br>", "textendash": "–", "textemdash": "—", "textasciitilde": "~",
    "textasciicircum": "^", "textbar": "|", "textless": "&lt;", "textgreater": "&gt;",
    "ss": "ß", "o": "ø", "O": "Ø", "ae": "æ", "AE": "Æ", "oe": "œ", "OE": "Œ",
    "i": "ı", "j": "ȷ", "l": "ł", "L": "Ł", "aa": "å", "AA": "Å", "dag": "†", "ddag": "‡",
    "textquotedblleft": "“", "textquotedblright": "”", "guillemotleft": "«",
    "guillemotright": "»", "euro": "€", "hfill": " ", "hfil": " ", "dotfill": " … ",
    "enspace": "\u2002", "thinspace": "\u2009", "ordm": "º", "ordf": "ª",
    "textordmasculine": "º", "textordfeminine": "ª",
}

# comandos ignorados (sem argumentos)
IGNORADOS = {
    "noindent", "indent", "smallskip", "medskip", "bigskip", "vfill", "newpage",
    "clearpage", "pagebreak", "nopagebreak", "allowbreak", "protect", "relax", "null",
    "displaystyle", "textstyle", "leavevmode", "nobreak", "break", "cleardoublepage",
    "maketitle", "tableofcontents", "hline", "toprule", "midrule", "bottomrule",
    "selectfont", "ignorespaces", "unskip", "strut", "phantomsection",
}

# comandos ignorados junto com seus argumentos (quantos obrigatórios)
IGNORADOS_COM_ARGS = {
    "vspace": 1, "hspace": 1, "label": 1, "index": 1, "addvspace": 1, "vskip": 0,
    "setlength": 2, "addtolength": 2, "setcounter": 2, "addtocounter": 2, "pagestyle": 1,
    "thispagestyle": 1, "linespread": 1, "cline": 1, "newpage": 0, "color": 1, "fontsize": 2,
    "rule": 2, "phantom": 1, "hphantom": 1, "vphantom": 1, "cmidrule": 1,
}

ACENTOS = {
    "'": "\u0301", "`": "\u0300", "^": "\u0302", "~": "\u0303", '"': "\u0308",
    "=": "\u0304", ".": "\u0307", "c": "\u0327", "v": "\u030c", "u": "\u0306",
    "H": "\u030b", "k": "\u0328", "r": "\u030a", "d": "\u0323", "b": "\u0331",
}

_ITEM = "\x00ITEM\x00"
_CELULA = "\x00CEL\x00"
_LINHA = "\x00LIN\x00"
_PARAGRAFO = "\x00PAR\x00"


def _interno(s: str) -> str:
    """Conteúdo que vai dentro de um elemento HTML: parágrafos viram quebras."""
    return s.replace(_PARAGRAFO, "<br>")


def remover_comentarios(texto: str) -> str:
    """Remove comentários ``%`` (respeitando ``\\%``) como o TeX faz."""
    saida = []
    linhas = texto.split("\n")
    for n, linha in enumerate(linhas):
        i = 0
        corte = None
        while i < len(linha):
            ch = linha[i]
            if ch == "\\":
                i += 2
                continue
            if ch == "%":
                corte = i
                break
            i += 1
        if corte is None:
            saida.append(linha + ("\n" if n < len(linhas) - 1 else ""))
        else:
            # o comentário "come" a quebra de linha e os espaços do início da próxima
            saida.append(linha[:corte])
            if n + 1 < len(linhas):
                linhas[n + 1] = linhas[n + 1].lstrip(" \t")
    return "".join(saida)


class _Conversor:
    def __init__(self, texto: str, resolver_imagem: Callable[[str], str | None] | None):
        self.s = texto
        self.i = 0
        self.resolver = resolver_imagem
        self.n = len(texto)

    # -- leitura básica ---------------------------------------------------------
    def _pular_espacos(self, incluir_quebra: bool = True) -> None:
        while self.i < self.n and self.s[self.i] in (" \t\n\r" if incluir_quebra else " \t"):
            self.i += 1

    def _ler_nome_comando(self) -> str:
        """Lê o nome após a barra invertida (self.i aponta para depois da barra)."""
        if self.i >= self.n:
            return ""
        if self.s[self.i].isalpha() or self.s[self.i] == "@":
            j = self.i
            while j < self.n and (self.s[j].isalpha() or self.s[j] == "@"):
                j += 1
            nome = self.s[self.i:j]
            self.i = j
            if self.i < self.n and self.s[self.i] == "*" and nome not in ("item",):
                nome += "*"
                self.i += 1
            return nome
        nome = self.s[self.i]
        self.i += 1
        return nome

    def _ler_grupo_bruto(self) -> str | None:
        """Lê ``{...}`` balanceado e devolve o conteúdo sem as chaves."""
        self._pular_espacos()
        if self.i >= self.n or self.s[self.i] != "{":
            return None
        nivel = 0
        inicio = self.i + 1
        while self.i < self.n:
            ch = self.s[self.i]
            if ch == "\\":
                self.i += 2
                continue
            if ch == "{":
                nivel += 1
            elif ch == "}":
                nivel -= 1
                if nivel == 0:
                    conteudo = self.s[inicio:self.i]
                    self.i += 1
                    return conteudo
            self.i += 1
        conteudo = self.s[inicio:]
        self.i = self.n
        return conteudo

    def _ler_opcional_bruto(self) -> str | None:
        j = self.i
        while j < self.n and self.s[j] in " \t":
            j += 1
        if j >= self.n or self.s[j] != "[":
            return None
        nivel = 0
        k = j
        while k < self.n:
            ch = self.s[k]
            if ch == "\\":
                k += 2
                continue
            if ch == "{":
                nivel += 1
            elif ch == "}":
                nivel -= 1
            elif ch == "]" and nivel == 0:
                self.i = k + 1
                return self.s[j + 1:k]
            k += 1
        return None

    def _ler_argumento(self) -> str:
        """Argumento obrigatório: grupo entre chaves ou um único token."""
        self._pular_espacos()
        if self.i >= self.n:
            return ""
        if self.s[self.i] == "{":
            return self._ler_grupo_bruto() or ""
        if self.s[self.i] == "\\":
            self.i += 1
            return "\\" + self._ler_nome_comando()
        ch = self.s[self.i]
        self.i += 1
        return ch

    def _sub(self, texto: str) -> str:
        return _Conversor(texto, self.resolver).converter()

    # -- matemática -----------------------------------------------------------------
    def _ler_ate(self, fim: str) -> str:
        j = self.i
        while j < self.n:
            if self.s.startswith(fim, j):
                conteudo = self.s[self.i:j]
                self.i = j + len(fim)
                return conteudo
            if self.s[j] == "\\":
                j += 2
                continue
            j += 1
        conteudo = self.s[self.i:]
        self.i = self.n
        return conteudo

    def _ler_ambiente_bruto(self, nome: str) -> str:
        """Conteúdo até o \\end{nome} correspondente (considera aninhamento)."""
        abre = "\\begin{" + nome + "}"
        fecha = "\\end{" + nome + "}"
        nivel = 1
        j = self.i
        while j < self.n:
            if self.s.startswith(abre, j):
                nivel += 1
                j += len(abre)
                continue
            if self.s.startswith(fecha, j):
                nivel -= 1
                if nivel == 0:
                    conteudo = self.s[self.i:j]
                    self.i = j + len(fecha)
                    return conteudo
                j += len(fecha)
                continue
            if self.s[j] == "\\":
                j += 2
                continue
            j += 1
        conteudo = self.s[self.i:]
        self.i = self.n
        return conteudo

    @staticmethod
    def _mat(conteudo: str, display: bool) -> str:
        c = html.escape(conteudo, quote=False)
        if display:
            return f'<div class="mat">\\[{c}\\]</div>'
        return f"\\({c}\\)"

    # -- conversão principal ---------------------------------------------------------------
    def converter(self) -> str:
        partes: list[str] = []
        while self.i < self.n:
            ch = self.s[self.i]
            if ch == "\\":
                partes.append(self._comando())
            elif ch == "$":
                if self.s.startswith("$$", self.i):
                    self.i += 2
                    partes.append(self._mat(self._ler_ate("$$"), True))
                else:
                    self.i += 1
                    partes.append(self._mat(self._ler_ate("$"), False))
            elif ch == "{":
                grupo = self._ler_grupo_bruto() or ""
                partes.append(self._sub(grupo))
            elif ch == "}":
                self.i += 1
            elif ch == "\n":
                j = self.i + 1
                while j < self.n and self.s[j] in " \t\r":
                    j += 1
                if j < self.n and self.s[j] == "\n":
                    while j < self.n and self.s[j] in " \t\r\n":
                        j += 1
                    partes.append(_PARAGRAFO)
                    self.i = j
                else:
                    partes.append(" ")
                    self.i += 1
            elif ch == "~":
                partes.append("&nbsp;")
                self.i += 1
            elif ch == "&":
                partes.append(_CELULA)
                self.i += 1
            elif ch == "[" and self.s.startswith("[[img:", self.i):
                m = RE_MARCADOR.match(self.s, self.i)
                if m:
                    partes.append(self._imagem(m))
                    self.i = m.end()
                else:
                    partes.append("[")
                    self.i += 1
            elif ch == "-" and self.s.startswith("---", self.i):
                partes.append("—")
                self.i += 3
            elif ch == "-" and self.s.startswith("--", self.i):
                partes.append("–")
                self.i += 2
            elif ch == "`" and self.s.startswith("``", self.i):
                partes.append("“")
                self.i += 2
            elif ch == "'" and self.s.startswith("''", self.i):
                partes.append("”")
                self.i += 2
            elif ch in "<>&\"":
                partes.append(html.escape(ch))
                self.i += 1
            else:
                j = self.i
                while j < self.n and self.s[j] not in "\\${}\n~&[-`'<>\"":
                    j += 1
                if j == self.i:
                    j += 1
                partes.append(html.escape(self.s[self.i:j], quote=False))
                self.i = j
        return "".join(partes)

    def _imagem(self, m: re.Match) -> str:
        ident = m.group(1).lower()
        url = self.resolver(ident) if self.resolver else None
        largura = largura_de(m) * 100
        if url is None:
            return f'<span class="aviso">[imagem não encontrada: {html.escape(ident)}]</span>'
        return f'<img class="img" src="{html.escape(url)}" style="width:{largura:.0f}%">'

    def _comando(self) -> str:
        self.i += 1  # barra
        nome = self._ler_nome_comando()
        if not nome:
            return "\\"
        if nome == "(":
            return self._mat(self._ler_ate("\\)"), False)
        if nome == "[":
            return self._mat(self._ler_ate("\\]"), True)
        if nome == "begin":
            return self._ambiente()
        if nome == "end":
            self._ler_argumento()
            return ""
        if nome == "item":
            rotulo = self._ler_opcional_bruto()
            if rotulo is not None:
                return _ITEM + "\x01" + self._sub(rotulo) + "\x02"
            return _ITEM
        if nome == "\\":
            self._ler_opcional_bruto()
            if self.i < self.n and self.s[self.i] == "*":
                self.i += 1
            return _LINHA
        if nome == "par":
            return _PARAGRAFO
        if nome in ACENTOS:
            arg = self._ler_argumento()
            if arg and arg[0].isalpha():
                base = "i" if arg == "\\i" else arg[0]
                return html.escape(unicodedata.normalize("NFC", base + ACENTOS[nome]) + arg[1:])
            return html.escape(arg)
        if nome in FORMATOS:
            abre, fecha = FORMATOS[nome]
            if nome in ("makebox", "framebox"):
                self._ler_opcional_bruto()
                self._ler_opcional_bruto()
            return abre + _interno(self._sub(self._ler_argumento())) + fecha
        if nome == "textcolor":
            cor = self._ler_argumento()
            return f'<span style="color:{html.escape(cor)}">' + self._sub(self._ler_argumento()) + "</span>"
        if nome == "href":
            self._ler_argumento()
            return "<u>" + self._sub(self._ler_argumento()) + "</u>"
        if nome in ("ref", "eqref", "pageref", "cite"):
            self._ler_opcional_bruto()
            self._ler_argumento()
            return "[?]"
        if nome in SELETORES:
            abre, fecha = SELETORES[nome]
            self._pular_espacos(incluir_quebra=False)
            resto = self.s[self.i:]
            self.i = self.n
            return abre + _interno(self._sub(resto)) + fecha
        if nome in SIMBOLOS:
            if nome[0].isalpha():
                self._pular_espacos(incluir_quebra=False)
            return SIMBOLOS[nome]
        base = nome.rstrip("*")
        if base in IGNORADOS:
            self._pular_espacos(incluir_quebra=False)
            return ""
        if base in IGNORADOS_COM_ARGS:
            self._ler_opcional_bruto()
            for _ in range(IGNORADOS_COM_ARGS[base]):
                self._ler_argumento()
            return ""
        if base in ("includegraphics",):
            self._ler_opcional_bruto()
            self._ler_argumento()
            return self._aviso("\\includegraphics (use o botão de imagem)")
        return self._aviso("\\" + nome)

    @staticmethod
    def _aviso(o_que: str) -> str:
        return f'<span class="aviso" title="{html.escape(o_que)}">{AVISO}</span>'

    def _ambiente(self) -> str:
        nome = self._ler_argumento().strip()
        if nome in AMBIENTES_MATEMATICOS:
            conteudo = self._ler_ambiente_bruto(nome)
            c = html.escape(conteudo, quote=False)
            return f'<div class="mat">\\begin{{{nome}}}{c}\\end{{{nome}}}</div>'
        if nome in ("itemize", "enumerate", "description"):
            opcao = self._ler_opcional_bruto() or ""
            conteudo = self._ler_ambiente_bruto(nome)
            return self._lista(nome, opcao, self._sub(conteudo))
        if nome in ("center", "flushleft", "flushright", "quote", "quotation", "minipage", "small",
                    "footnotesize", "large", "samepage", "multicols", "proof", "solucao", "resolucao"):
            if nome == "minipage":
                self._ler_opcional_bruto()
                self._ler_argumento()
            if nome == "multicols":
                self._ler_argumento()
            conteudo = _interno(self._sub(self._ler_ambiente_bruto(nome)))
            if nome == "center":
                return f'<div style="text-align:center">{conteudo}</div>'
            if nome == "flushright":
                return f'<div style="text-align:right">{conteudo}</div>'
            if nome in ("quote", "quotation"):
                return f"<blockquote>{conteudo}</blockquote>"
            if nome == "proof":
                return f"<div><i>Demonstração.</i> {conteudo} ∎</div>"
            return f"<div>{conteudo}</div>"
        if nome in ("tabular", "tabular*", "tabularx", "array"):
            if nome in ("tabular*", "tabularx"):
                self._ler_argumento()
            self._ler_opcional_bruto()
            self._ler_argumento()  # especificação das colunas
            conteudo = self._sub(self._ler_ambiente_bruto(nome))
            return self._tabela(conteudo)
        # ambiente não suportado: pula o conteúdo e avisa
        self._ler_ambiente_bruto(nome)
        return self._aviso(f"ambiente {nome}")

    @staticmethod
    def _lista(nome: str, opcao: str, conteudo: str) -> str:
        pedacos = conteudo.split(_ITEM)
        itens = pedacos[1:] if len(pedacos) > 1 else pedacos
        if nome == "enumerate":
            tipo = "1"
            if "\\alph" in opcao or re.search(r"(^|[^\\\w])a([^\w]|$)", opcao):
                tipo = "a"
            elif "\\Alph" in opcao or re.search(r"(^|[^\\\w])A([^\w]|$)", opcao):
                tipo = "A"
            elif "\\roman" in opcao or re.search(r"(^|[^\\\w])i([^\w]|$)", opcao):
                tipo = "i"
            elif "\\Roman" in opcao or re.search(r"(^|[^\\\w])I([^\w]|$)", opcao):
                tipo = "I"
            abre, fecha = f'<ol type="{tipo}">', "</ol>"
        else:
            abre, fecha = "<ul>", "</ul>"
        lis = []
        for item in itens:
            item = _interno(item)
            rotulo = ""
            if item.startswith("\x01"):
                fim = item.find("\x02")
                rotulo, item = item[1:fim], item[fim + 1:]
            if rotulo:
                lis.append(f'<li class="rotulado"><b>{rotulo}</b> {item}</li>')
            else:
                lis.append(f"<li>{item}</li>")
        return abre + "".join(lis) + fecha

    @staticmethod
    def _tabela(conteudo: str) -> str:
        linhas = [ln for ln in conteudo.split(_LINHA)]
        if linhas and not linhas[-1].strip():
            linhas.pop()
        trs = []
        for ln in linhas:
            celulas = _interno(ln).split(_CELULA)
            trs.append("<tr>" + "".join(f"<td>{c.strip()}</td>" for c in celulas) + "</tr>")
        return '<table class="tab">' + "".join(trs) + "</table>"


def _finalizar(html_bruto: str) -> str:
    texto = html_bruto.replace(_LINHA, "<br>").replace(_CELULA, "&amp;")
    texto = texto.replace(_ITEM, "")
    texto = re.sub("\x01([^\x02]*)\x02", r"\1", texto)
    paragrafos = [p.strip() for p in texto.split(_PARAGRAFO)]
    return "".join(f'<div class="p">{p}</div>' for p in paragrafos if p)


def latex_para_html(texto: str, resolver_imagem: Callable[[str], str | None] | None = None) -> str:
    """Converte um campo LaTeX em HTML para a prévia (matemática fica para o MathJax)."""
    if not texto or not texto.strip():
        return ""
    limpo = remover_comentarios(texto.replace("\r\n", "\n"))
    return _finalizar(_Conversor(limpo, resolver_imagem).converter())


def texto_simples(texto: str, limite: int = 160) -> str:
    """Resumo de uma linha do LaTeX (para listas)."""
    t = remover_comentarios(texto or "")
    t = RE_MARCADOR.sub("[imagem]", t)
    t = re.sub(r"\\(?:textbf|emph|textit|underline|text|mathrm)\{([^{}]*)\}", r"\1", t)
    t = re.sub(r"\\(begin|end)\{[^}]*\}", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) > limite:
        t = t[: limite - 1].rstrip() + "…"
    return t
