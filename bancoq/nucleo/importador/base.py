"""Base do importador de .tex.

Cada padrão de prova antiga é uma subclasse de ``PadraoImportacao`` registrada
com ``@registrar``. Para reconhecer um formato novo, basta criar um módulo em
``bancoq/nucleo/importador/`` com uma classe que implemente ``pontuar`` e
``separar`` e importá-lo em ``__init__.py``.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from ..entidades import Item, Questao
from ..latex_html import remover_comentarios
from ..midia import ErroMidia, GerenciadorMidia, marcador


@dataclass
class QuestaoImportada:
    tipo: str = "discursiva"
    enunciado: str = ""
    itens: list[Item] = field(default_factory=list)
    resposta_curta: str = ""
    resolucao: str = ""
    avisos: list[str] = field(default_factory=list)

    def para_questao(self) -> Questao:
        return Questao(tipo=self.tipo, enunciado=self.enunciado.strip(), itens=list(self.itens),
                       resposta_curta=self.resposta_curta.strip(), resolucao=self.resolucao.strip())


@dataclass
class ResultadoImportacao:
    questoes: list[QuestaoImportada]
    padrao: str
    preambulo: str = ""
    avisos: list[str] = field(default_factory=list)


class PadraoImportacao(ABC):
    nome: str = ""
    descricao: str = ""

    @abstractmethod
    def pontuar(self, corpo: str) -> int:
        """Quanto este padrão parece se aplicar ao texto (0 = não se aplica)."""

    @abstractmethod
    def separar(self, corpo: str) -> list[QuestaoImportada]:
        """Divide o corpo do documento em questões."""


_REGISTRO: list[PadraoImportacao] = []


def registrar(cls):
    _REGISTRO.append(cls())
    return cls


def padroes() -> list[PadraoImportacao]:
    return list(_REGISTRO)


def padrao_por_nome(nome: str) -> PadraoImportacao | None:
    return next((p for p in _REGISTRO if p.nome == nome), None)


# =============================================================================
# utilidades de varredura de LaTeX
# =============================================================================
def separar_documento(texto: str) -> tuple[str, str]:
    """(preâmbulo, corpo). Sem \\begin{document}, tudo é corpo."""
    m = re.search(r"\\begin\{document\}", texto)
    if not m:
        return "", texto
    fim = re.search(r"\\end\{document\}", texto[m.end():])
    corpo = texto[m.end(): m.end() + fim.start()] if fim else texto[m.end():]
    return texto[: m.start()], corpo


def pular_grupo(s: str, i: int) -> int:
    """Com s[i] == '{', devolve a posição logo após a chave que fecha."""
    nivel = 0
    while i < len(s):
        ch = s[i]
        if ch == "\\":
            i += 2
            continue
        if ch == "{":
            nivel += 1
        elif ch == "}":
            nivel -= 1
            if nivel == 0:
                return i + 1
        i += 1
    return len(s)


def ler_opcional(s: str, i: int) -> tuple[str | None, int]:
    """Lê ``[...]`` em s[i:] (pulando espaços); devolve (conteúdo, nova posição)."""
    j = i
    while j < len(s) and s[j] in " \t":
        j += 1
    if j >= len(s) or s[j] != "[":
        return None, i
    nivel = 0
    k = j + 1
    while k < len(s):
        ch = s[k]
        if ch == "\\":
            k += 2
            continue
        if ch == "{":
            nivel += 1
        elif ch == "}":
            nivel -= 1
        elif ch == "]" and nivel == 0:
            return s[j + 1:k], k + 1
        k += 1
    return None, i


def ler_grupo(s: str, i: int) -> tuple[str | None, int]:
    j = i
    while j < len(s) and s[j] in " \t\n":
        j += 1
    if j >= len(s) or s[j] != "{":
        return None, i
    fim = pular_grupo(s, j)
    return s[j + 1: fim - 1], fim


RE_BEGIN_END = re.compile(r"\\(begin|end)\s*\{([^}]*)\}")


def fim_ambiente(s: str, inicio: int, nome: str) -> tuple[int, int]:
    """A partir de ``inicio`` (logo após \\begin{nome}), acha o \\end{nome} correspondente.

    Devolve (posição do \\end, posição logo após o \\end{nome}); (-1, -1) se não achar.
    """
    nivel = 1
    for m in RE_BEGIN_END.finditer(s, inicio):
        if m.group(2) != nome:
            continue
        nivel += 1 if m.group(1) == "begin" else -1
        if nivel == 0:
            return m.start(), m.end()
    return -1, -1


def ambientes(s: str, nomes: tuple[str, ...]) -> list[tuple[str, int, int, int, int]]:
    """Ambientes de primeiro nível com esses nomes: (nome, ini_begin, ini_conteudo, fim_conteudo, fim_end)."""
    achados = []
    pos = 0
    while True:
        m = None
        for mm in RE_BEGIN_END.finditer(s, pos):
            if mm.group(1) == "begin" and mm.group(2) in nomes:
                m = mm
                break
        if m is None:
            return achados
        nome = m.group(2)
        a, b = fim_ambiente(s, m.end(), nome)
        if a < 0:
            achados.append((nome, m.start(), m.end(), len(s), len(s)))
            return achados
        achados.append((nome, m.start(), m.end(), a, b))
        pos = b


def dividir_por_comando(s: str, comandos: tuple[str, ...]) -> list[tuple[str, str | None, str]]:
    """Divide ``s`` nos comandos dados (ex.: \\item) que estejam no primeiro nível.

    Ignora ocorrências dentro de ambientes aninhados ou de chaves.
    Devolve [(comando, argumento_opcional, texto)]; o texto antes do primeiro
    comando vem com comando "".
    """
    partes: list[tuple[str, str | None, str]] = []
    nivel_amb = 0
    nivel_chave = 0
    atual_cmd, atual_opt, inicio = "", None, 0
    i = 0
    padrao = re.compile(r"\\(" + "|".join(re.escape(c) for c in comandos) + r")(?![A-Za-z@])")
    while i < len(s):
        ch = s[i]
        if ch == "\\":
            m = RE_BEGIN_END.match(s, i)
            if m:
                nivel_amb += 1 if m.group(1) == "begin" else -1
                i = m.end()
                continue
            m = padrao.match(s, i)
            if m and nivel_amb == 0 and nivel_chave == 0:
                partes.append((atual_cmd, atual_opt, s[inicio:i]))
                atual_cmd = m.group(1)
                opt, j = ler_opcional(s, m.end())
                atual_opt = opt
                inicio = j
                i = j
                continue
            i += 2
            continue
        if ch == "{":
            nivel_chave += 1
        elif ch == "}":
            nivel_chave = max(0, nivel_chave - 1)
        i += 1
    partes.append((atual_cmd, atual_opt, s[inicio:]))
    return partes


def limpar_texto(t: str) -> str:
    """Tira espaços sobrando e comandos de espaçamento do fim do texto."""
    t = t.strip()
    lixo = re.compile(
        r"(\\(?:vspace\*?\s*\{[^}]*\}|vfill|newpage|clearpage|pagebreak|bigskip|medskip|smallskip|"
        r"hfill|par|noindent|vskip\s*[^\\\s]*|makeemptybox\s*\{[^}]*\}|fillwithlines\s*\{[^}]*\}|"
        r"fillwithdottedlines\s*\{[^}]*\})\s*)+$"
    )
    anterior = None
    while anterior != t:
        anterior = t
        t = lixo.sub("", t).rstrip()
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


# =============================================================================
# imagens
# =============================================================================
RE_INCLUDEGRAPHICS = re.compile(r"\\includegraphics\s*(\[[^\]]*\])?\s*\{([^}]*)\}")


def largura_de_opcoes(opcoes: str) -> float:
    m = re.search(r"width\s*=\s*([0-9.]*)\s*\\(?:linewidth|textwidth|columnwidth|hsize)", opcoes or "")
    if m:
        try:
            return max(0.05, min(1.0, float(m.group(1) or 1)))
        except ValueError:
            return 0.6
    m = re.search(r"width\s*=\s*([0-9.]+)\s*(cm|mm|in|pt)", opcoes or "")
    if m:
        valor = float(m.group(1))
        cm = {"cm": valor, "mm": valor / 10, "in": valor * 2.54, "pt": valor / 28.45}[m.group(2)]
        return max(0.05, min(1.0, round(cm / 16, 2)))
    return 0.6


def importar_imagens(texto: str, pasta_base: Path | None, midia: GerenciadorMidia | None,
                     avisos: list[str]) -> str:
    """Troca \\includegraphics{arquivo} por marcadores [[img:ID]] (imagens ficam pendentes)."""
    if midia is None:
        return texto

    def troca(m: re.Match) -> str:
        nome = m.group(2).strip()
        candidatos = []
        base = Path(pasta_base) if pasta_base else None
        for ext in ("", ".pdf", ".png", ".jpg", ".jpeg", ".PDF", ".PNG", ".JPG"):
            p = Path(nome + ext)
            if not p.is_absolute() and base is not None:
                p = base / p
            candidatos.append(p)
        for p in candidatos:
            if p.is_file():
                try:
                    ident = midia.adicionar_arquivo(p)
                except ErroMidia as e:
                    avisos.append(f"Imagem {nome}: {e}")
                    return m.group(0)
                return marcador(ident, largura_de_opcoes(m.group(1) or ""))
        avisos.append(f"Imagem não encontrada: {nome}")
        return m.group(0)

    return RE_INCLUDEGRAPHICS.sub(troca, texto)


def desembrulhar_figuras(texto: str) -> str:
    """Remove \\begin{figure}…\\end{figure} (mantém o conteúdo) e \\caption/\\label."""
    texto = re.sub(r"\\begin\{figure\*?\}(\[[^\]]*\])?", "", texto)
    texto = re.sub(r"\\end\{figure\*?\}", "", texto)
    texto = re.sub(r"\\label\{[^}]*\}", "", texto)
    return texto


# =============================================================================
# análise de um bloco (enunciado + alternativas + resolução)
# =============================================================================
AMB_RESOLUCAO = ("solution", "solutionorbox", "solutionorlines", "solutionordottedlines", "solutionorgrid",
                 "solucao", "resolucao", "resolução", "solução", "proof", "resposta", "gabarito")
RE_TITULO_RESOLUCAO = re.compile(
    r"(?:^|\n)\s*(?:\\textbf\{|\\emph\{|\\textit\{)?\s*(?:Resolução|Resolucao|Solução|Solucao|Resposta|Gabarito)"
    r"\s*[:.]?\s*\}?\s*[:.]?", re.IGNORECASE,
)
MARCAS_CORRETA = (r"\correta", r"\certa", r"\CorrectChoice", r"\checkmark", r"(correta)", r"(certa)",
                  r"\correct")
RE_VF = re.compile(r"^\s*\(\s*(V|F|\\quad|\\,|~|\s*)\s*\)\s*")


def _tirar_marca_correta(texto: str, rotulo: str | None) -> tuple[str, bool]:
    correta = False
    for marca in MARCAS_CORRETA:
        if marca in texto:
            texto = texto.replace(marca, "")
            correta = True
    if rotulo and any(m in rotulo for m in (r"\checkmark", "*", "x", "X", r"\correta")):
        correta = True
    return texto.strip(), correta


def separar_resolucao(texto: str) -> tuple[str, str]:
    """Separa a resolução (ambiente solution/resolucao ou parágrafo "Resolução:")."""
    resolucoes = []
    for nome, ini, ic, fc, fim in reversed(ambientes(texto, AMB_RESOLUCAO)):
        conteudo = texto[ic:fc]
        if nome.startswith("solution"):
            _, j = ler_opcional(conteudo, 0)
            conteudo = conteudo[j:]
        resolucoes.insert(0, conteudo.strip())
        texto = texto[:ini] + texto[fim:]
    m = RE_TITULO_RESOLUCAO.search(texto)
    if m and m.start() > 0:
        resolucoes.append(texto[m.end():].strip())
        texto = texto[: m.start()]
    return texto, "\n\n".join(r for r in resolucoes if r)


def analisar_bloco(texto: str) -> QuestaoImportada:
    """Reconhece alternativas (lista no fim do bloco) e resolução em um bloco de texto."""
    q = QuestaoImportada()
    texto, q.resolucao = separar_resolucao(texto)
    listas = ambientes(texto, ("enumerate", "itemize", "alternativas", "choices", "oneparchoices",
                               "checkboxes", "oneparcheckboxes", "afirmativas", "description"))
    if listas:
        nome, ini, ic, fc, fim = listas[-1]
        depois = limpar_texto(texto[fim:])
        conteudo = texto[ic:fc]
        opcao, j = ler_opcional(conteudo, 0)
        conteudo = conteudo[j:]
        partes = dividir_por_comando(conteudo, ("item", "alt", "choice", "CorrectChoice", "afirmativa"))
        itens_brutos = [(cmd, opt, t) for cmd, opt, t in partes if cmd]
        rotulos_letra = bool(opcao) and bool(re.search(r"\\alph|\\Alph|\(a\)|a\)|\ba\b", opcao))
        curtos = all(len(t.strip()) < 400 and "\\begin{" not in t for _, _, t in itens_brutos)
        e_alternativas = (
            len(itens_brutos) >= 2 and not depois
            and (nome in ("alternativas", "choices", "oneparchoices", "checkboxes", "oneparcheckboxes", "afirmativas")
                 or rotulos_letra or (curtos and nome in ("enumerate", "itemize")))
        )
        if e_alternativas:
            itens = []
            vf = 0
            for cmd, opt, t in itens_brutos:
                t, correta = _tirar_marca_correta(t, opt)
                if cmd == "CorrectChoice":
                    correta = True
                mvf = RE_VF.match(t)
                if mvf:
                    vf += 1
                    marca = mvf.group(1).strip()
                    if marca in ("V", "F"):
                        correta = marca == "V"
                    t = t[mvf.end():]
                itens.append(Item(limpar_texto(t), correta))
            q.itens = itens
            q.enunciado = limpar_texto(texto[:ini])
            enun_vf = re.search(r"verdadeir[oa]s?\s+ou\s+fals[oa]s?|\bV\s+ou\s+F\b|\(V\)\s*ou\s*\(F\)",
                                q.enunciado, re.IGNORECASE)
            if nome == "afirmativas" or vf == len(itens) or (enun_vf and vf > 0):
                q.tipo = "vf"
            else:
                q.tipo = "multipla"
                if not any(i.correta for i in itens):
                    q.avisos.append("Nenhuma alternativa marcada como correta.")
            return q
    q.enunciado = limpar_texto(texto)
    return q


SEPARADOR = "\\SEPARADORDEQUESTOES"
RE_LINHA_SEPARADORA = re.compile(r"(?m)^[ \t]*%{3,}.*$")


def preparar_texto(texto: str) -> str:
    """Normaliza quebras, marca as linhas separadoras "%%%" e remove os comentários."""
    texto = texto.replace("\r\n", "\n").replace("\r", "\n")
    texto = RE_LINHA_SEPARADORA.sub(lambda _m: "\n" + SEPARADOR + "\n", texto)
    texto = remover_comentarios(texto)
    return desembrulhar_figuras(texto)


def importar(texto: str, padrao: PadraoImportacao | None = None, pasta_base: Path | None = None,
             midia: GerenciadorMidia | None = None) -> ResultadoImportacao:
    """Separa as questões de um .tex (o padrão é detectado se não for dado)."""
    from . import padroes_disponiveis  # noqa: F401 - garante o registro dos padrões

    preambulo, corpo = separar_documento(texto.replace("\r\n", "\n"))
    corpo = preparar_texto(corpo)
    avisos: list[str] = []
    if padrao is None:
        candidatos = sorted(padroes(), key=lambda p: p.pontuar(corpo), reverse=True)
        padrao = candidatos[0] if candidatos and candidatos[0].pontuar(corpo) > 0 else padrao_por_nome("Separador manual")
    if padrao.nome != "Separador manual":
        corpo = corpo.replace(SEPARADOR, "\n")
    questoes = padrao.separar(corpo)
    for q in questoes:
        q.enunciado = importar_imagens(q.enunciado, pasta_base, midia, q.avisos)
        q.resolucao = importar_imagens(q.resolucao, pasta_base, midia, q.avisos)
        for it in q.itens:
            it.texto = importar_imagens(it.texto, pasta_base, midia, q.avisos)
    questoes = [q for q in questoes if q.enunciado.strip() or q.itens]
    if not questoes:
        avisos.append("Nenhuma questão encontrada. Tente outro padrão ou divida manualmente.")
    return ResultadoImportacao(questoes, padrao.nome, preambulo, avisos)


RE_DEFINICAO = re.compile(r"\\(?:newcommand|renewcommand|providecommand|DeclareMathOperator|def)(?![A-Za-z@])")


def definicoes_do_preambulo(preambulo: str) -> list[str]:
    """Definições (\\newcommand, \\DeclareMathOperator, \\def…) do preâmbulo importado."""
    s = remover_comentarios(preambulo or "")
    achadas = []
    pos = 0
    while True:
        m = RE_DEFINICAO.search(s, pos)
        if not m:
            break
        i = m.end()
        if i < len(s) and s[i] == "*":
            i += 1
        while i < len(s) and s[i] in " \t\n":
            i += 1
        # nome: {\\nome} ou \\nome
        if i < len(s) and s[i] == "{":
            i = pular_grupo(s, i)
        else:
            mm = re.compile(r"\\(?:[A-Za-z@]+|.)").match(s, i)
            i = mm.end() if mm else i
        # argumentos opcionais, parâmetros #1#2 e o corpo
        while i < len(s):
            while i < len(s) and s[i] in " \t\n":
                i += 1
            if i < len(s) and s[i] == "[":
                _, j = ler_opcional(s, i)
                if j == i:
                    break
                i = j
            elif i < len(s) and s[i] == "#":
                i += 2
            else:
                break
        if i < len(s) and s[i] == "{":
            fim = pular_grupo(s, i)
            achadas.append(s[m.start():fim].strip())
            pos = fim
        else:
            pos = m.end()
    return achadas
