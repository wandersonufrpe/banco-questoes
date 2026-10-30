"""Formato do pacote de importação: o que o Claude entrega e o app revisa.

Pasta do pacote: ``<banco>/entrada/pacotes/<nome>/``::

    pacote.json                     dados do PDF (gravado pelas ferramentas)
    questoes/<id>.txt               uma questão por arquivo, no formato de seções
    recortes/<id>.png               a questão recortada do PDF
    figuras/<id>-<n>-original.png   figura n recortada do PDF
    figuras/<id>-<n>-tikz.png       a mesma figura redesenhada em TikZ
    decisoes.json                   aprovações e rejeições (gravado só pelo app)

Formato de seções: LaTeX puro, sem escapes (``\\frac`` dentro de JSON viraria
"form feed" + "rac" sem dar erro). Cabeçalho com ``@campo: valor`` e depois as
seções, cada uma começando numa linha ``@@nome``::

    @numero: 4
    @tipo: multipla
    @dificuldade: 3
    @fonte: OBMEP 2025 — Nível 3, 1ª fase, questão 4
    @ano: 2025
    @categoria: Geometria > Triângulos
    @tags: semelhança; área
    @resposta: C
    @resposta_independente: C
    @gabarito_pdf: C
    @confianca: alta
    @figura: 1 | ok
    @@enunciado
    Texto da questão em LaTeX.
    @@alternativa
    $12$
    @@comentario
    Por que está errada.
    @@alternativa correta
    ...
    @@resolucao
    ...
    @@verificacao
    Relatório da conferência (texto livre).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from ..nucleo.banco import agora_iso, sem_acentos
from ..nucleo.entidades import TIPOS, Item, Questao, letra
from ..nucleo.repositorio import CategoriaNova, Repositorio

FORMATO = 1
PASTA_ENTRADA = "entrada"
PASTA_PACOTES = "pacotes"
PASTA_CONCLUIDOS = "concluidos"
ARQUIVO_PACOTE = "pacote.json"
ARQUIVO_DECISOES = "decisoes.json"

APROVADA = "aprovada"
REJEITADA = "rejeitada"

SITUACAO_ANDAMENTO = "em preparação"
SITUACAO_PRONTO = "pronto"

FIGURA_OK = "ok"              # redesenhada em TikZ e conferida
FIGURA_AJUSTAR = "ajustar"    # redesenhada, mas o professor precisa conferir/ajustar
FIGURA_TEXTO = "texto"        # não era desenho (tabela, quadro de texto): virou LaTeX comum
SITUACOES_FIGURA = (FIGURA_OK, FIGURA_AJUSTAR, FIGURA_TEXTO)

CONFIANCAS = ("alta", "média", "baixa")

SEP_CATEGORIA = ">"


class ErroPacote(Exception):
    pass


# =====================================================================
# Caminhos
# =====================================================================
def pasta_entrada(pasta_banco: Path | str) -> Path:
    return Path(pasta_banco) / PASTA_ENTRADA


def pasta_pacotes(pasta_banco: Path | str) -> Path:
    return pasta_entrada(pasta_banco) / PASTA_PACOTES


def pasta_concluidos(pasta_banco: Path | str) -> Path:
    return pasta_entrada(pasta_banco) / PASTA_CONCLUIDOS


def nome_pacote(texto: str) -> str:
    """Nome de pasta seguro a partir do nome do PDF (minúsculas, sem acentos)."""
    t = unicodedata.normalize("NFKD", Path(texto).stem)
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return t[:60] or "pacote"


def _chave(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto.strip())
    return "".join(c for c in t if not unicodedata.combining(c)).lower()


def _gravar_json(destino: Path, dados: dict) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_name(destino.name + ".tmp")
    tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, destino)


# =====================================================================
# Questão do pacote
# =====================================================================
@dataclass
class FiguraPacote:
    numero: int
    situacao: str = FIGURA_OK      # ok | ajustar
    nota: str = ""


@dataclass
class Problema:
    gravidade: str                 # "erro" ou "aviso"
    mensagem: str

    def __str__(self) -> str:
        return f"{self.gravidade}: {self.mensagem}"


@dataclass
class QuestaoPacote:
    ident: str
    numero: str = ""
    pagina: int | None = None
    tipo: str = "multipla"
    enunciado: str = ""
    itens: list[Item] = field(default_factory=list)
    resposta_esperada: str = ""
    resolucao: str = ""
    observacoes: str = ""
    dificuldade: int = 3
    fonte: str = ""
    ano: int | None = None
    categoria: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    nao_embaralhar: bool = False
    # verificação
    resposta: str = ""
    resposta_independente: str = ""
    gabarito_pdf: str = ""
    sympy: str = ""
    confianca: str = ""
    verificacao: str = ""
    # extras
    figuras: list[FiguraPacote] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    preambulo: list[str] = field(default_factory=list)
    problemas_leitura: list[Problema] = field(default_factory=list)
    arquivo: Path | None = None

    # ------------------------------------------------------------------
    def para_questao(self) -> Questao:
        """Questão do banco (sem categoria: veja ``resolver_categoria``)."""
        return Questao(
            tipo=self.tipo if self.tipo in TIPOS else "discursiva",
            enunciado=self.enunciado,
            itens=[Item(i.texto, i.correta, i.comentario) for i in self.itens],
            resposta_curta=self.resposta_esperada,
            resolucao=self.resolucao,
            observacoes=self.observacoes,
            dificuldade=min(5, max(1, self.dificuldade)),
            fonte=self.fonte,
            ano=self.ano,
            tags=list(self.tags),
            nao_embaralhar=self.nao_embaralhar,
        )

    def textos_com_figuras(self) -> list[str]:
        """Campos cujas figuras correspondem às do PDF (enunciado e itens, nessa ordem)."""
        return [self.enunciado] + [i.texto for i in self.itens]

    def figuras_desenhadas(self) -> list[FiguraPacote]:
        """Figuras do PDF redesenhadas em TikZ, na ordem: a k-ésima tikzpicture do
        enunciado/itens corresponde à k-ésima desta lista."""
        return sorted((f for f in self.figuras if f.situacao != FIGURA_TEXTO), key=lambda f: f.numero)

    def resposta_da_chave(self) -> str:
        """Resposta segundo as alternativas/afirmativas marcadas (para comparar)."""
        if self.tipo == "multipla":
            corretas = [letra(i) for i, it in enumerate(self.itens) if it.correta]
            return ",".join(corretas)
        if self.tipo == "vf":
            return "".join("V" if it.correta else "F" for it in self.itens)
        return self.resposta

    # ------------------------------------------------------------------
    def para_texto(self) -> str:
        cab = []

        def c(nome: str, valor) -> None:
            if valor not in (None, "", []):
                cab.append(f"@{nome}: {valor}")

        c("numero", self.numero)
        c("pagina", self.pagina)
        c("tipo", self.tipo)
        c("dificuldade", self.dificuldade)
        c("fonte", self.fonte)
        c("ano", self.ano)
        c("categoria", f" {SEP_CATEGORIA} ".join(self.categoria))
        c("tags", "; ".join(self.tags))
        if self.nao_embaralhar:
            c("nao_embaralhar", "sim")
        c("resposta", self.resposta)
        c("resposta_independente", self.resposta_independente)
        c("gabarito_pdf", self.gabarito_pdf)
        c("sympy", self.sympy)
        c("confianca", self.confianca)
        for f in self.figuras:
            c("figura", f"{f.numero} | {f.situacao}" + (f" | {f.nota}" if f.nota else ""))
        for a in self.avisos:
            c("aviso", a)
        for p in self.preambulo:
            c("preambulo", p)
        sec = []

        def s(cabecalho: str, texto: str) -> None:
            sec.append(f"@@{cabecalho}\n{texto.strip()}" if texto.strip() else f"@@{cabecalho}")

        s("enunciado", self.enunciado)
        for it in self.itens:
            if self.tipo == "vf":
                s("afirmativa " + ("verdadeira" if it.correta else "falsa"), it.texto)
            else:
                s("alternativa" + (" correta" if it.correta else ""), it.texto)
            if it.comentario.strip():
                s("comentario", it.comentario)
        if self.resposta_esperada.strip():
            s("resposta_esperada", self.resposta_esperada)
        s("resolucao", self.resolucao)
        if self.observacoes.strip():
            s("observacoes", self.observacoes)
        if self.verificacao.strip():
            s("verificacao", self.verificacao)
        return "\n".join(cab) + "\n\n" + "\n\n".join(sec) + "\n"


TIPOS_ACEITOS = {
    "multipla": "multipla", "multipla escolha": "multipla", "objetiva": "multipla",
    "vf": "vf", "verdadeiro ou falso": "vf", "v ou f": "vf", "verdadeiro/falso": "vf",
    "curta": "curta", "resposta curta": "curta", "numerica": "curta",
    "discursiva": "discursiva", "aberta": "discursiva", "dissertativa": "discursiva",
}

CAMPOS_REPETIVEIS = ("figura", "aviso", "preambulo")
CAMPOS_CABECALHO = (
    "numero", "pagina", "tipo", "dificuldade", "fonte", "ano", "categoria", "tags",
    "nao_embaralhar", "resposta", "resposta_independente", "gabarito_pdf", "sympy",
    "confianca",
) + CAMPOS_REPETIVEIS

RE_CABECALHO = re.compile(r"^@([A-Za-z_çãéíóú]+)\s*:\s?(.*)$")
RE_SECAO = re.compile(r"^@@\s*(.*?)\s*$")


def _sim(valor: str) -> bool:
    return _chave(valor) in ("sim", "s", "true", "verdadeiro", "1", "yes")


def _limpar(linhas: list[str]) -> str:
    while linhas and not linhas[0].strip():
        linhas.pop(0)
    while linhas and not linhas[-1].strip():
        linhas.pop()
    return "\n".join(linhas)


def separar_tags(valor: str) -> list[str]:
    sep = ";" if ";" in valor else ","
    vistas: list[str] = []
    for t in valor.split(sep):
        t = t.strip()
        if t and t.lower() not in (v.lower() for v in vistas):
            vistas.append(t)
    return vistas


def separar_categoria(valor: str) -> list[str]:
    return [p.strip() for p in valor.split(SEP_CATEGORIA) if p.strip()]


def ler_questao(texto: str, ident: str = "", arquivo: Path | None = None) -> QuestaoPacote:
    """Lê o formato de seções. Problemas viram ``problemas_leitura`` (nunca exceção)."""
    q = QuestaoPacote(ident=ident, arquivo=arquivo)
    p = q.problemas_leitura
    linhas = texto.replace("\r\n", "\n").replace("\ufeff", "").split("\n")
    i = 0
    vistos: set[str] = set()
    # --- cabeçalho
    while i < len(linhas) and not linhas[i].startswith("@@"):
        linha = linhas[i]
        i += 1
        if not linha.strip() or linha.lstrip().startswith("#"):
            continue
        m = RE_CABECALHO.match(linha.strip())
        if not m:
            p.append(Problema("erro", f"linha {i} fora de seção: {linha.strip()[:60]!r}"))
            continue
        nome, valor = _chave(m.group(1)), m.group(2).strip()
        if nome not in CAMPOS_CABECALHO:
            p.append(Problema("aviso", f"campo desconhecido @{m.group(1)} (linha {i})"))
            continue
        if nome in vistos and nome not in CAMPOS_REPETIVEIS:
            p.append(Problema("aviso", f"@{nome} aparece mais de uma vez; vale o último"))
        vistos.add(nome)
        _campo_cabecalho(q, nome, valor, i)
    # --- seções
    atual: str | None = None
    detalhe = ""
    corpo: list[str] = []
    item_atual: Item | None = None

    def fechar() -> None:
        nonlocal item_atual
        if atual is None:
            return
        conteudo = _limpar(corpo)
        if atual == "enunciado":
            if q.enunciado:
                p.append(Problema("erro", "mais de uma seção @@enunciado"))
            q.enunciado = conteudo
        elif atual in ("alternativa", "afirmativa"):
            item_atual = Item(conteudo, _correta(atual, detalhe))
            q.itens.append(item_atual)
        elif atual == "comentario":
            if item_atual is None:
                p.append(Problema("erro", "@@comentario sem alternativa/afirmativa antes"))
            elif item_atual.comentario:
                p.append(Problema("erro", "dois @@comentario seguidos para o mesmo item"))
            else:
                item_atual.comentario = conteudo
        elif atual in ("resposta_esperada", "resposta"):
            q.resposta_esperada = conteudo
        elif atual == "resolucao":
            q.resolucao = conteudo
        elif atual == "observacoes":
            q.observacoes = conteudo
        elif atual == "verificacao":
            q.verificacao = conteudo

    def _correta(tipo_item: str, det: str) -> bool:
        d = _chave(det)
        if tipo_item == "alternativa":
            if d not in ("", "correta", "certa"):
                p.append(Problema("erro", f"@@alternativa {det}: use '@@alternativa' ou '@@alternativa correta'"))
            return d in ("correta", "certa")
        if d in ("verdadeira", "v", "verdadeiro"):
            return True
        if d not in ("falsa", "f", "falso"):
            p.append(Problema("erro", f"@@afirmativa {det or '(sem V/F)'}: use 'verdadeira' ou 'falsa'"))
        return False

    secoes_validas = ("enunciado", "alternativa", "afirmativa", "comentario", "resposta_esperada",
                      "resposta", "resolucao", "observacoes", "verificacao")
    while i < len(linhas):
        linha = linhas[i]
        i += 1
        m = RE_SECAO.match(linha) if linha.startswith("@@") else None
        if m:
            fechar()
            partes = m.group(1).split(None, 1)
            nome = _chave(partes[0]) if partes else ""
            detalhe = partes[1] if len(partes) > 1 else ""
            if nome not in secoes_validas:
                p.append(Problema("erro", f"seção desconhecida @@{m.group(1)} (linha {i})"))
                atual = None
            else:
                atual = nome
            corpo = []
            continue
        if atual is None:
            if linha.strip():
                p.append(Problema("erro", f"linha {i} fora de seção: {linha.strip()[:60]!r}"))
            continue
        corpo.append(linha)
    fechar()
    return q


def _campo_cabecalho(q: QuestaoPacote, nome: str, valor: str, linha: int) -> None:
    p = q.problemas_leitura
    if nome == "numero":
        q.numero = valor
    elif nome == "pagina":
        m = re.match(r"\d+", valor)
        q.pagina = int(m.group()) if m else None
    elif nome == "tipo":
        tipo = TIPOS_ACEITOS.get(_chave(valor))
        if tipo is None:
            p.append(Problema("erro", f"@tipo {valor!r} desconhecido (use multipla, vf, curta ou discursiva)"))
        else:
            q.tipo = tipo
    elif nome == "dificuldade":
        try:
            q.dificuldade = int(valor)
        except ValueError:
            p.append(Problema("erro", f"@dificuldade {valor!r} não é um número de 1 a 5"))
    elif nome == "fonte":
        q.fonte = valor
    elif nome == "ano":
        if valor:
            try:
                q.ano = int(valor)
            except ValueError:
                p.append(Problema("erro", f"@ano {valor!r} não é um número"))
    elif nome == "categoria":
        q.categoria = separar_categoria(valor)
    elif nome == "tags":
        q.tags = separar_tags(valor)
    elif nome == "nao_embaralhar":
        q.nao_embaralhar = _sim(valor)
    elif nome in ("resposta", "resposta_independente", "gabarito_pdf", "sympy"):
        setattr(q, nome, valor)
    elif nome == "confianca":
        c = _chave(valor)
        q.confianca = {"alta": "alta", "media": "média", "baixa": "baixa"}.get(c, valor)
        if c not in ("alta", "media", "baixa", ""):
            p.append(Problema("aviso", f"@confianca {valor!r}: use alta, média ou baixa"))
    elif nome == "figura":
        partes = [x.strip() for x in valor.split("|")]
        try:
            numero = int(partes[0])
        except ValueError:
            p.append(Problema("erro", f"@figura {valor!r}: comece com o número da figura (ex.: '1 | ok')"))
            return
        situacao = _chave(partes[1]) if len(partes) > 1 and partes[1] else FIGURA_OK
        if situacao not in SITUACOES_FIGURA:
            p.append(Problema("aviso", f"@figura {numero}: situação {partes[1]!r} (use ok, ajustar ou texto)"))
            situacao = FIGURA_AJUSTAR
        q.figuras.append(FiguraPacote(numero, situacao, " | ".join(partes[2:])))
    elif nome == "aviso":
        if valor:
            q.avisos.append(valor)
    elif nome == "preambulo":
        if valor:
            q.preambulo.append(valor)


# =====================================================================
# Validação (sem TeX; a compilação fica nas ferramentas e no app)
# =====================================================================
def normalizar_resposta(texto: str) -> str:
    t = _chave(texto or "")
    t = re.sub(r"^(alternativa|letra|item|opcao|resposta)\s+", "", t)
    t = t.replace("$", "").replace("\\,", "").replace("\\ ", "")
    t = re.sub(r"[\s()\[\]{}]", "", t)
    t = t.rstrip(".)")
    return t


def respostas_concordam(a: str, b: str) -> bool:
    return normalizar_resposta(a) == normalizar_resposta(b)


def _sem_escapados(texto: str) -> str:
    return re.sub(r"\\[\\{}$%]", "", texto)


def problemas_latex(texto: str) -> list[str]:
    """Erros de estrutura fáceis de ver sem compilar: chaves, $ e ambientes."""
    erros = []
    linhas = []
    for ln in texto.split("\n"):  # ignora comentários
        m = re.search(r"(?<!\\)%", ln)
        linhas.append(ln[: m.start()] if m else ln)
    t = _sem_escapados("\n".join(linhas))
    nivel = 0
    for ch in t:
        if ch == "{":
            nivel += 1
        elif ch == "}":
            nivel -= 1
            if nivel < 0:
                break
    if nivel != 0:
        erros.append("chaves { } desbalanceadas")
    sem_duplo = t.replace("$$", "")
    if sem_duplo.count("$") % 2:
        erros.append("número ímpar de $ (fórmula sem fechar)")
    pilha: list[str] = []
    for m in re.finditer(r"\\(begin|end)\s*\{([^}]*)\}", t):
        if m.group(1) == "begin":
            pilha.append(m.group(2))
        elif not pilha or pilha.pop() != m.group(2):
            erros.append(f"\\end{{{m.group(2)}}} sem o \\begin correspondente")
            break
    else:
        if pilha:
            erros.append(f"\\begin{{{pilha[-1]}}} sem \\end")
    if "[[img:" in t:
        erros.append("marcador de imagem do banco: redesenhe a figura em TikZ")
    if "\\includegraphics" in t:
        erros.append("\\includegraphics: redesenhe a figura em TikZ")
    return erros


RE_FORMULA = re.compile(r"\\\[.*?\\\]|\$\$.*?\$\$|(?<!\\)\$.*?(?<!\\)\$|\\\(.*?\\\)", re.S)


def tikz_em_formula(texto: str) -> bool:
    """tikzpicture dentro de $...$ ou \\[...\\]: compila, mas a prévia rápida não mostra."""
    return any("tikzpicture" in m.group() for m in RE_FORMULA.finditer(texto or ""))


def validar_questao(q: QuestaoPacote, pacote: "Pacote | None" = None) -> list[Problema]:
    pr = list(q.problemas_leitura)

    def erro(m: str) -> None:
        pr.append(Problema("erro", m))

    def aviso(m: str) -> None:
        pr.append(Problema("aviso", m))

    if not q.enunciado.strip():
        erro("enunciado vazio")
    if q.tipo in ("multipla", "vf"):
        nome = "alternativa" if q.tipo == "multipla" else "afirmativa"
        if q.tipo == "multipla" and len(q.itens) < 2:
            erro("múltipla escolha precisa de pelo menos 2 alternativas")
        if q.tipo == "vf" and not q.itens:
            erro("verdadeiro ou falso precisa de pelo menos 1 afirmativa")
        if q.tipo == "multipla":
            n = sum(1 for i in q.itens if i.correta)
            if n != 1:
                erro(f"marque exatamente 1 alternativa correta (há {n})")
        for k, it in enumerate(q.itens):
            rotulo = f"{nome} {letra(k) if q.tipo == 'multipla' else k + 1}"
            if not it.texto.strip():
                erro(f"{rotulo} vazia")
            if not it.comentario.strip():
                aviso(f"{rotulo} sem @@comentario")
    elif q.itens:
        erro(f"questão do tipo {q.tipo} não deve ter alternativas/afirmativas")
    if q.tipo == "curta" and not q.resposta_esperada.strip():
        erro("resposta curta sem @@resposta_esperada")
    if not q.resolucao.strip():
        erro("falta a @@resolucao")
    if not 1 <= q.dificuldade <= 5:
        erro("@dificuldade deve ir de 1 a 5")
    if q.ano is not None and not 1900 <= q.ano <= 2100:
        erro(f"@ano {q.ano} fora do intervalo esperado")
    if not q.fonte.strip():
        aviso("sem @fonte")
    if not q.categoria:
        aviso("sem @categoria")
    if not q.tags:
        aviso("sem @tags")

    # respostas
    chave = q.resposta_da_chave()
    if q.tipo in ("multipla", "vf") and q.resposta and chave and not respostas_concordam(q.resposta, chave):
        erro(f"@resposta {q.resposta} não bate com o item marcado ({chave.upper()})")
    principal = q.resposta or chave
    if not q.resposta_independente.strip():
        aviso("sem @resposta_independente (segunda resolução)")
    elif principal and not respostas_concordam(principal, q.resposta_independente):
        aviso(f"as resoluções discordam: {principal} × {q.resposta_independente}")
    if q.gabarito_pdf.strip() and principal and not respostas_concordam(principal, q.gabarito_pdf):
        aviso(f"diverge do gabarito do PDF: {principal} × {q.gabarito_pdf}")

    # LaTeX
    campos = [("enunciado", q.enunciado), ("resolução", q.resolucao),
              ("resposta esperada", q.resposta_esperada)]
    for k, it in enumerate(q.itens):
        campos.append((f"item {k + 1}", it.texto))
        campos.append((f"comentário do item {k + 1}", it.comentario))
    for nome, texto in campos:
        for e in problemas_latex(texto):
            erro(f"{nome}: {e}")
        if tikz_em_formula(texto):
            erro(f"{nome}: tikzpicture dentro de fórmula ($...$ ou \\[...\\]); feche a fórmula "
                 "antes da figura (a prévia rápida do app não mostra figura dentro de fórmula)")

    # figuras
    from ..nucleo.tikz import figuras_tikz

    n_tikz = sum(len(figuras_tikz(t)) for t in q.textos_com_figuras())
    numeros = [f.numero for f in q.figuras]
    if len(set(numeros)) != len(numeros):
        erro("@figura repetida")
    desenhadas = q.figuras_desenhadas()
    if n_tikz < len(desenhadas):
        erro(f"há {len(desenhadas)} @figura desenhada(s), mas só {n_tikz} tikzpicture no enunciado/itens")
    for f in q.figuras:
        if f.situacao == FIGURA_AJUSTAR:
            aviso(f"figura {f.numero} precisa de ajuste" + (f": {f.nota}" if f.nota else ""))
    if pacote is not None:
        if not pacote.recorte(q.ident):
            aviso("sem recorte do PDF (recortes/" + q.ident + ".png)")
        for f in q.figuras:
            if not pacote.figura_original(q.ident, f.numero):
                aviso(f"figura {f.numero}: falta o recorte original")
        originais = pacote.figuras_originais(q.ident)
        if len(originais) > len(q.figuras):
            aviso(f"o PDF tem {len(originais)} figura(s) recortada(s), mas só {len(q.figuras)} @figura")
    return pr


def tem_erro(problemas: list[Problema]) -> bool:
    return any(p.gravidade == "erro" for p in problemas)


# =====================================================================
# Pacote
# =====================================================================
@dataclass
class Decisao:
    situacao: str                  # aprovada | rejeitada
    em: str = ""
    questao_id: int | None = None
    motivo: str = ""


@dataclass
class Pacote:
    pasta: Path
    titulo: str = ""
    pdf: str = ""
    sha256: str = ""
    paginas: int = 0
    criado_em: str = ""
    atualizado_em: str = ""
    situacao: str = SITUACAO_ANDAMENTO
    previstas: int | None = None   # questões encontradas no PDF
    observacoes: str = ""

    @property
    def nome(self) -> str:
        return self.pasta.name

    @property
    def pasta_questoes(self) -> Path:
        return self.pasta / "questoes"

    @property
    def pasta_recortes(self) -> Path:
        return self.pasta / "recortes"

    @property
    def pasta_figuras(self) -> Path:
        return self.pasta / "figuras"

    # ------------------------------------------------------------------
    @classmethod
    def criar(cls, pasta: Path, **dados) -> "Pacote":
        pasta = Path(pasta)
        pasta.mkdir(parents=True, exist_ok=True)
        for sub in ("questoes", "recortes", "figuras"):
            (pasta / sub).mkdir(exist_ok=True)
        pac = cls(pasta, criado_em=agora_iso(), **dados)
        pac.salvar()
        return pac

    @classmethod
    def abrir(cls, pasta: Path | str) -> "Pacote":
        pasta = Path(pasta)
        try:
            dados = json.loads((pasta / ARQUIVO_PACOTE).read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise ErroPacote(f"{pasta} não é um pacote (falta {ARQUIVO_PACOTE})") from None
        except (OSError, ValueError) as e:
            raise ErroPacote(f"não foi possível ler {pasta / ARQUIVO_PACOTE}: {e}") from None
        pac = cls(pasta)
        for chave in ("titulo", "pdf", "sha256", "paginas", "criado_em", "atualizado_em",
                      "situacao", "previstas", "observacoes"):
            if chave in dados:
                setattr(pac, chave, dados[chave])
        return pac

    def salvar(self) -> None:
        self.atualizado_em = agora_iso()
        _gravar_json(self.pasta / ARQUIVO_PACOTE, {
            "formato": FORMATO,
            "titulo": self.titulo,
            "pdf": self.pdf,
            "sha256": self.sha256,
            "paginas": self.paginas,
            "criado_em": self.criado_em,
            "atualizado_em": self.atualizado_em,
            "situacao": self.situacao,
            "previstas": self.previstas,
            "observacoes": self.observacoes,
        })

    # ------------------------------------------------------------------
    def arquivo_questao(self, ident: str) -> Path:
        return self.pasta_questoes / f"{ident}.txt"

    def ids(self) -> list[str]:
        if not self.pasta_questoes.is_dir():
            return []
        return sorted(p.stem for p in self.pasta_questoes.glob("*.txt"))

    def questao(self, ident: str) -> QuestaoPacote:
        arq = self.arquivo_questao(ident)
        try:
            texto = arq.read_text(encoding="utf-8")
        except OSError as e:
            q = QuestaoPacote(ident=ident, arquivo=arq)
            q.problemas_leitura.append(Problema("erro", f"não foi possível ler {arq.name}: {e}"))
            return q
        except UnicodeDecodeError:
            q = QuestaoPacote(ident=ident, arquivo=arq)
            q.problemas_leitura.append(Problema("erro", f"{arq.name} não está em UTF-8"))
            return q
        return ler_questao(texto, ident, arq)

    def questoes(self) -> list[QuestaoPacote]:
        return [self.questao(i) for i in self.ids()]

    def gravar_questao(self, q: QuestaoPacote) -> Path:
        arq = self.arquivo_questao(q.ident)
        arq.parent.mkdir(parents=True, exist_ok=True)
        tmp = arq.with_name(arq.name + ".tmp")
        tmp.write_text(q.para_texto(), encoding="utf-8")
        os.replace(tmp, arq)
        return arq

    # ------------------------------------------------------------------
    def recorte(self, ident: str) -> Path | None:
        p = self.pasta_recortes / f"{ident}.png"
        return p if p.exists() else None

    def caminho_figura(self, ident: str, numero: int, tipo: str = "original") -> Path:
        return self.pasta_figuras / f"{ident}-{numero}-{tipo}.png"

    def figura_original(self, ident: str, numero: int) -> Path | None:
        p = self.caminho_figura(ident, numero, "original")
        return p if p.exists() else None

    def figura_tikz(self, ident: str, numero: int) -> Path | None:
        p = self.caminho_figura(ident, numero, "tikz")
        return p if p.exists() else None

    def figuras_originais(self, ident: str) -> list[Path]:
        if not self.pasta_figuras.is_dir():
            return []
        achadas = []
        for p in self.pasta_figuras.glob(f"{ident}-*-original.png"):
            m = re.fullmatch(re.escape(ident) + r"-(\d+)-original", p.stem)
            if m:
                achadas.append((int(m.group(1)), p))
        return [p for _, p in sorted(achadas)]

    # ------------------------------------------------------------------
    def decisoes(self) -> dict[str, Decisao]:
        try:
            dados = json.loads((self.pasta / ARQUIVO_DECISOES).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        saida = {}
        for ident, d in (dados.get("questoes") or {}).items():
            if isinstance(d, dict) and d.get("situacao") in (APROVADA, REJEITADA):
                saida[ident] = Decisao(d["situacao"], d.get("em", ""), d.get("questao_id"), d.get("motivo", ""))
        return saida

    def registrar_decisao(self, ident: str, situacao: str, questao_id: int | None = None,
                          motivo: str = "") -> None:
        if situacao not in (APROVADA, REJEITADA):
            raise ValueError(situacao)
        atuais = self.decisoes()
        atuais[ident] = Decisao(situacao, agora_iso(), questao_id, motivo)
        self._gravar_decisoes(atuais)

    def desfazer_decisao(self, ident: str) -> None:
        atuais = self.decisoes()
        if atuais.pop(ident, None) is not None:
            self._gravar_decisoes(atuais)

    def _gravar_decisoes(self, decisoes: dict[str, Decisao]) -> None:
        _gravar_json(self.pasta / ARQUIVO_DECISOES, {
            "formato": FORMATO,
            "questoes": {
                k: {kk: vv for kk, vv in d.__dict__.items() if vv not in (None, "")}
                for k, d in sorted(decisoes.items())
            },
        })

    def pendentes(self) -> list[str]:
        decididas = self.decisoes()
        return [i for i in self.ids() if i not in decididas]

    def preambulo_necessario(self, ids: list[str] | None = None) -> list[str]:
        """Linhas de @preambulo das questões (sem repetição, na ordem)."""
        linhas: list[str] = []
        for q in self.questoes():
            if ids is not None and q.ident not in ids:
                continue
            for ln in q.preambulo:
                if ln not in linhas:
                    linhas.append(ln)
        return linhas

    def mover_para_concluidos(self, pasta_banco: Path | str) -> Path:
        destino_base = pasta_concluidos(pasta_banco)
        destino_base.mkdir(parents=True, exist_ok=True)
        destino = destino_base / self.nome
        n = 2
        while destino.exists():
            destino = destino_base / f"{self.nome}-{n}"
            n += 1
        shutil.move(str(self.pasta), str(destino))
        self.pasta = destino
        return destino


def listar_pacotes(pasta_banco: Path | str, concluidos: bool = False) -> list[Pacote]:
    base = pasta_concluidos(pasta_banco) if concluidos else pasta_pacotes(pasta_banco)
    if not base.is_dir():
        return []
    pacotes = []
    for pasta in sorted(base.iterdir()):
        if (pasta / ARQUIVO_PACOTE).exists():
            try:
                pacotes.append(Pacote.abrir(pasta))
            except ErroPacote:
                continue
    return pacotes


def faltando_no_preambulo(linhas: list[str], preambulo: str) -> list[str]:
    """Linhas pedidas pelas questões que ainda não estão no preâmbulo do banco."""
    atual = "".join((preambulo or "").split())
    return [ln for ln in linhas if "".join(ln.split()) not in atual]


# =====================================================================
# Categoria: caminho de nomes -> id existente ou CategoriaNova
# =====================================================================
def resolver_categoria(repo: Repositorio, nomes: list[str]) -> tuple[int | None, CategoriaNova | None]:
    """Usa as categorias que já existem e cria (ao salvar) só o que faltar.

    A comparação ignora maiúsculas e acentos ("algebra" acha "Álgebra").
    """
    nomes = [n.strip() for n in nomes if n.strip()]
    if not nomes:
        return None, None
    filhos: dict[int | None, dict[str, int]] = {}
    for cat in repo.categorias():
        filhos.setdefault(cat.pai_id, {}).setdefault(sem_acentos(cat.nome.strip()), cat.id)
    pai: int | None = None
    for k, nome in enumerate(nomes):
        cid = filhos.get(pai, {}).get(sem_acentos(nome))
        if cid is None:
            return None, CategoriaNova(pai, nomes[k:])
        pai = cid
    return pai, None
