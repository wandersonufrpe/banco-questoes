"""Geração do LaTeX das questões, da prévia exata e do documento de checagem.

Convenção usada com os modelos (definida no próprio modelo):

* ``\\begin{questao}[valor] … \\end{questao}`` (valor opcional);
* ``\\begin{alternativas} \\alt … \\end{alternativas}``;
* ``\\begin{afirmativas} \\afirmativa … \\end{afirmativas}``;
* ``\\espacoresposta{5cm}`` e ``\\respostacurta``.

Nos documentos de resolução e na prévia exata também são usados
``\\marcacorreta``, ``\\marcavf{V}``, ``\\comentario{…}``, ``\\respostaesperada{…}``
e o ambiente ``resolucao``, definidos com ``\\providecommand`` (podem ser
redefinidos nas macros do usuário).
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .entidades import Questao, letra
from .midia import RE_MARCADOR, GerenciadorMidia, formatar_largura, largura_de
from .modelos_prova import preambulo

ResolverImagem = Callable[[str], "str | None"]

DEFINICOES_RESOLUCAO = r"""
% ---- comandos usados nas resoluções (podem ser redefinidos nas macros) ----
\providecommand{\marcacorreta}{\hfill\textbf{(correta)}}
\providecommand{\marcavf}[1]{\textbf{(#1)}~}
\providecommand{\comentario}[1]{\par{\small\itshape #1\par}}
\providecommand{\respostaesperada}[1]{\par\smallskip\noindent\textbf{Resposta:} #1\par}
\providecommand{\respostaalternativa}[1]{\par\smallskip\noindent\textbf{Resposta:} #1\par}
\providecommand{\semresolucao}{\par\smallskip\noindent\textit{(sem resolução cadastrada)}\par}
\makeatletter
\@ifundefined{resolucao}{%
  \newenvironment{resolucao}{\par\smallskip\noindent\textbf{Resolução.}\ }{\par}}{}
\makeatother
"""


class ColetorImagens:
    """Resolve marcadores para caminhos relativos e lembra quais arquivos copiar."""

    def __init__(self, midia: GerenciadorMidia | None, subpasta: str = "midia"):
        self.midia = midia
        self.subpasta = subpasta
        self.arquivos: dict[str, Path] = {}
        self.faltando: set[str] = set()

    def __call__(self, ident: str) -> str | None:
        p = self.midia.caminho(ident) if self.midia else None
        if p is None:
            self.faltando.add(ident)
            return None
        self.arquivos[p.name] = p
        return f"{self.subpasta}/{p.name}"

    def copiar_para(self, pasta: Path) -> None:
        if not self.arquivos:
            return
        destino = Path(pasta) / self.subpasta
        destino.mkdir(parents=True, exist_ok=True)
        for nome, origem in self.arquivos.items():
            alvo = destino / nome
            if not alvo.exists():
                shutil.copyfile(origem, alvo)


def substituir_imagens(texto: str, resolver: ResolverImagem | None) -> str:
    def troca(m):
        caminho = resolver(m.group(1).lower()) if resolver else None
        if caminho is None:
            return r"\fbox{\texttt{[imagem não encontrada]}}"
        return f"\\includegraphics[width={formatar_largura(largura_de(m))}\\linewidth]{{{caminho}}}"

    return RE_MARCADOR.sub(troca, texto or "")


def campo(texto: str, resolver: ResolverImagem | None) -> str:
    """Texto de um campo pronto para entrar no .tex (sempre seguido de quebra)."""
    t = substituir_imagens(texto, resolver).strip("\n").rstrip()
    return t


def _protege_colchete(t: str) -> str:
    # evita que um texto começado por "[" vire argumento opcional de \item/\begin
    return "{}" + t if t.lstrip().startswith("[") else t


def formatar_valor(valor) -> str:
    if valor in (None, ""):
        return ""
    if isinstance(valor, (int, float)):
        return f"{valor:g}".replace(".", ",")
    return str(valor).strip()


def latex_questao_prova(q: Questao, resolver: ResolverImagem | None, ordem: list[int] | None = None,
                        valor: str = "", espaco_cm: float = 0.0) -> str:
    """Questão como aparece na prova (sem respostas)."""
    itens = q.itens_validos()
    ordem = list(range(len(itens))) if ordem is None else ordem
    v = formatar_valor(valor)
    linhas = [f"\\begin{{questao}}[{v}]" if v else "\\begin{questao}"]
    linhas.append(_protege_colchete(campo(q.enunciado, resolver)))
    if q.tipo == "multipla" and itens:
        linhas.append("\\begin{alternativas}")
        for i in ordem:
            linhas.append("\\alt " + _protege_colchete(campo(itens[i].texto, resolver)))
        linhas.append("\\end{alternativas}")
    elif q.tipo == "vf" and itens:
        linhas.append("\\begin{afirmativas}")
        for i in ordem:
            linhas.append("\\afirmativa " + _protege_colchete(campo(itens[i].texto, resolver)))
        linhas.append("\\end{afirmativas}")
    elif q.tipo == "curta":
        linhas.append("\\respostacurta")
    if espaco_cm and espaco_cm > 0:
        linhas.append(f"\\espacoresposta{{{espaco_cm:g}cm}}")
    linhas.append("\\end{questao}")
    return "\n".join(linhas) + "\n"


def resposta_curta_gabarito(q: Questao, ordem: list[int] | None = None) -> str:
    """Resposta da questão para a tabela do gabarito (já na ordem da versão)."""
    itens = q.itens_validos()
    ordem = list(range(len(itens))) if ordem is None else ordem
    if q.tipo == "multipla":
        letras = [letra(pos) for pos, i in enumerate(ordem) if itens[i].correta]
        return ", ".join(f"({l})" for l in letras) if letras else "—"
    if q.tipo == "vf":
        return " ".join("V" if itens[i].correta else "F" for i in ordem) or "—"
    if q.tipo == "curta":
        return q.resposta_curta.strip() or "—"
    return "discursiva"


def latex_questao_resolucao(q: Questao, resolver: ResolverImagem | None, ordem: list[int] | None = None,
                            valor: str = "") -> str:
    """Questão com a resposta, os comentários de cada alternativa e a resolução."""
    itens = q.itens_validos()
    ordem = list(range(len(itens))) if ordem is None else ordem
    v = formatar_valor(valor)
    linhas = [f"\\begin{{questao}}[{v}]" if v else "\\begin{questao}"]
    linhas.append(_protege_colchete(campo(q.enunciado, resolver)))
    if q.tipo == "multipla" and itens:
        linhas.append("\\begin{alternativas}")
        for i in ordem:
            it = itens[i]
            linhas.append("\\alt " + _protege_colchete(campo(it.texto, resolver)))
            if it.correta:
                linhas.append("\\marcacorreta")
            if it.comentario.strip():
                linhas.append("\\comentario{" + campo(it.comentario, resolver) + "\n}")
        linhas.append("\\end{alternativas}")
        linhas.append("\\respostaalternativa{" + resposta_curta_gabarito(q, ordem) + "}")
    elif q.tipo == "vf" and itens:
        linhas.append("\\begin{afirmativas}")
        for i in ordem:
            it = itens[i]
            linhas.append("\\afirmativa \\marcavf{" + ("V" if it.correta else "F") + "}"
                          + campo(it.texto, resolver))
            if it.comentario.strip():
                linhas.append("\\comentario{" + campo(it.comentario, resolver) + "\n}")
        linhas.append("\\end{afirmativas}")
        linhas.append("\\respostaalternativa{" + resposta_curta_gabarito(q, ordem) + "}")
    elif q.tipo == "curta":
        linhas.append("\\respostaesperada{" + campo(q.resposta_curta, resolver) + "\n}")
    if q.resolucao.strip():
        linhas.append("\\begin{resolucao}")
        linhas.append(campo(q.resolucao, resolver))
        linhas.append("\\end{resolucao}")
    else:
        linhas.append("\\semresolucao")
    linhas.append("\\end{questao}")
    return "\n".join(linhas) + "\n"


def latex_respostas_questao(q: Questao, resolver: ResolverImagem | None,
                            ordem: list[int] | None = None) -> str:
    """Só a resposta, os comentários das alternativas e a resolução (sem o enunciado)."""
    itens = q.itens_validos()
    ordem = list(range(len(itens))) if ordem is None else ordem
    linhas = []
    if q.tipo in ("multipla", "vf") and itens:
        linhas.append("\\respostaalternativa{" + resposta_curta_gabarito(q, ordem) + "}")
        for pos, i in enumerate(ordem):
            it = itens[i]
            if it.comentario.strip():
                rot = f"({letra(pos)})" if q.tipo == "multipla" else f"{pos + 1}."
                linhas.append("\\comentario{\\textbf{" + rot + "} " + campo(it.comentario, resolver) + "\n}")
    elif q.tipo == "curta":
        linhas.append("\\respostaesperada{" + campo(q.resposta_curta, resolver) + "\n}")
    if q.resolucao.strip():
        linhas += ["\\begin{resolucao}", campo(q.resolucao, resolver), "\\end{resolucao}"]
    else:
        linhas.append("\\semresolucao")
    return "\n".join(linhas) + "\n"


# =============================================================================
# prévia exata
# =============================================================================
def documento_previa_exata(q: Questao, modelo: str, macros: str, resolver: ResolverImagem | None) -> str:
    partes = [
        preambulo(modelo, macros),
        DEFINICOES_RESOLUCAO,
        "\\begin{document}\n\\pagestyle{empty}\n",
        "% ---- como aparece na prova ----\n",
        latex_questao_prova(q, resolver),
        "\n\\bigskip\\hrule\\medskip\n\\noindent{\\small\\textsf{GABARITO E RESOLUÇÃO}}\\par\n",
        latex_respostas_questao(q, resolver),
        "\n\\end{document}\n",
    ]
    return "".join(partes)


# =============================================================================
# checagem ao salvar
# =============================================================================
@dataclass
class DocumentoChecagem:
    texto: str
    trechos: list[tuple[int, int, str, str]] = field(default_factory=list)  # (ini, fim, chave, nome)
    inicio_corpo: int = 0

    def campo_da_linha(self, linha: int | None) -> tuple[str, str] | None:
        """(chave, nome) do campo que contém a linha, ou o último antes dela."""
        if linha is None:
            return None
        if linha < self.inicio_corpo:
            return ("preambulo", "Preâmbulo e macros (Configurações)")
        anterior = None
        for ini, fim, chave, nome in self.trechos:
            if ini <= linha <= fim:
                return chave, nome
            if ini <= linha:
                anterior = (chave, nome)
        return anterior


class _Escritor:
    def __init__(self):
        self.linhas: list[str] = []

    @property
    def proxima(self) -> int:
        return len(self.linhas) + 1

    def add(self, texto: str) -> tuple[int, int]:
        ini = self.proxima
        partes = texto.split("\n")
        self.linhas.extend(partes)
        return ini, self.proxima - 1


def documento_checagem(q: Questao, modelo: str, macros: str, resolver: ResolverImagem | None) -> DocumentoChecagem:
    """Documento com todos os campos LaTeX da questão, cada um em linhas conhecidas."""
    e = _Escritor()
    e.add(preambulo(modelo, macros).rstrip("\n"))
    e.add(DEFINICOES_RESOLUCAO.strip("\n"))
    e.add("\\begin{document}")
    doc = DocumentoChecagem("")
    doc.inicio_corpo = e.proxima
    trechos = doc.trechos

    def campo_em_linhas(prefixo: str, texto: str, chave: str, nome: str, sufixo: str = "") -> None:
        if prefixo:
            e.add(prefixo)
        ini, fim = e.add(_protege_colchete(campo(texto, resolver)) or "~")
        trechos.append((ini, fim, chave, nome))
        if sufixo:
            e.add(sufixo)

    e.add("\\begin{questao}")
    campo_em_linhas("", q.enunciado, "enunciado", "Enunciado")
    itens = q.itens_validos()
    if q.tipo in ("multipla", "vf") and itens:
        amb, cmd = ("alternativas", "\\alt") if q.tipo == "multipla" else ("afirmativas", "\\afirmativa")
        e.add(f"\\begin{{{amb}}}")
        for i, it in enumerate(itens):
            rot = f"Alternativa ({letra(i)})" if q.tipo == "multipla" else f"Afirmativa {i + 1}"
            campo_em_linhas(cmd, it.texto, f"item:{i}:texto", rot)
        e.add(f"\\end{{{amb}}}")
    elif q.tipo == "curta":
        e.add("\\respostacurta")
    e.add("\\end{questao}")
    for i, it in enumerate(itens):
        if it.comentario.strip():
            rot = f"Comentário da alternativa ({letra(i)})" if q.tipo == "multipla" else f"Comentário da afirmativa {i + 1}"
            campo_em_linhas("\\comentario{", it.comentario, f"item:{i}:comentario", rot, "}")
    if q.tipo == "curta" and q.resposta_curta.strip():
        campo_em_linhas("\\respostaesperada{", q.resposta_curta, "resposta", "Resposta esperada", "}")
    if q.resolucao.strip():
        campo_em_linhas("\\begin{resolucao}", q.resolucao, "resolucao", "Resolução", "\\end{resolucao}")
    e.add("\\end{document}")
    doc.texto = "\n".join(e.linhas) + "\n"
    return doc
