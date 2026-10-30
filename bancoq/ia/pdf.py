"""Leitura do PDF para a importação: onde está cada questão, figuras e recortes.

Tudo aqui é heurística para poupar trabalho (e leitura de imagens) do Claude:
ele confere os recortes e pode refazer qualquer um com ``recortar``.
Coordenadas sempre em pontos do PDF (1/72 de polegada), origem no canto
superior esquerdo da página; páginas numeradas a partir de 1.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from ..nucleo.pdf import pymupdf

Caixa = tuple[float, float, float, float]

ZONA_MARGEM = 0.065        # fração da altura considerada cabeçalho/rodapé
MARGEM_RECORTE = 4.0       # folga em volta dos recortes (pt)


@dataclass
class Linha:
    pagina: int            # 1, 2, ...
    caixa: Caixa
    texto: str
    fonte: str
    tamanho: float
    negrito: bool

    @property
    def x0(self) -> float:
        return self.caixa[0]

    @property
    def y0(self) -> float:
        return self.caixa[1]

    @property
    def x1(self) -> float:
        return self.caixa[2]

    @property
    def y1(self) -> float:
        return self.caixa[3]


@dataclass
class Parte:
    pagina: int
    caixa: Caixa

    def para_dict(self) -> dict:
        return {"pagina": self.pagina, "caixa": [round(v, 1) for v in self.caixa]}


@dataclass
class FiguraDetectada:
    numero: int
    pagina: int
    caixa: Caixa
    imagens: int = 0       # quantas imagens (bitmap) há no agrupamento
    desenhos: int = 0      # quantos traços vetoriais

    def para_dict(self) -> dict:
        return {"numero": self.numero, "pagina": self.pagina,
                "caixa": [round(v, 1) for v in self.caixa],
                "imagens": self.imagens, "desenhos": self.desenhos}


@dataclass
class RegiaoQuestao:
    ident: str
    numero: int
    pagina: int
    partes: list[Parte] = field(default_factory=list)
    figuras: list[FiguraDetectada] = field(default_factory=list)

    def para_dict(self) -> dict:
        return {"id": self.ident, "numero": self.numero, "pagina": self.pagina,
                "partes": [p.para_dict() for p in self.partes],
                "figuras": [f.para_dict() for f in self.figuras]}


# =====================================================================
# Texto
# =====================================================================
_ACENTOS = {"´": "́", "`": "̀", "ˆ": "̂", "^": "̂", "˜": "̃", "~": "̃",
            "¨": "̈"}


def normalizar_texto(texto: str) -> str:
    """Junta acentos soltos que o TeX deixa na camada de texto ("´e" -> "é", "c¸" -> "ç")."""
    t = re.sub(r"([cC])¸\s?", lambda m: "ç" if m.group(1) == "c" else "Ç", texto)
    t = re.sub(r"¸\s?([cC])", lambda m: "ç" if m.group(1) == "c" else "Ç", t)   # cedilha antes do c
    t = re.sub(r"([´`ˆ˜¨])\s?([A-Za-zıÍ])",
               lambda m: unicodedata.normalize("NFC", m.group(2).replace("ı", "i") + _ACENTOS[m.group(1)]),
               t)
    return unicodedata.normalize("NFC", t)


def _fonte_base(nome: str) -> str:
    return nome.split("+", 1)[-1]


def linhas_da_pagina(pagina, numero: int) -> list[Linha]:
    saida = []
    for bloco in pagina.get_text("dict")["blocks"]:
        if bloco.get("type") != 0:
            continue
        for ln in bloco["lines"]:
            spans = [s for s in ln["spans"] if s["text"].strip()]
            if not spans:
                continue
            texto = "".join(s["text"] for s in ln["spans"])
            s0 = spans[0]
            negrito = bool(s0["flags"] & 16) or "bold" in s0["font"].lower()
            saida.append(Linha(numero, tuple(ln["bbox"]), texto, _fonte_base(s0["font"]),
                               round(s0["size"], 1), negrito))
    return saida


# =====================================================================
# Cabeçalho, rodapé e colunas
# =====================================================================
def _assinatura(texto: str) -> str:
    return re.sub(r"\d+", "#", texto.strip().lower())


def linhas_de_margem(todas: list[list[Linha]], alturas: list[float]) -> set[int]:
    """ids (id(linha)) de cabeçalhos/rodapés: curtos perto da borda ou repetidos entre páginas."""
    fora: set[int] = set()
    repetidas = Counter()
    for linhas in todas:
        repetidas.update({(_assinatura(ln.texto), round(ln.y0 / 12)) for ln in linhas})
    n_pag = len(todas)
    for linhas, h in zip(todas, alturas):
        for ln in linhas:
            na_borda = ln.y1 < h * ZONA_MARGEM or ln.y0 > h * (1 - ZONA_MARGEM)
            perto = ln.y1 < h * 0.12 or ln.y0 > h * 0.88
            if RE_FORTE.match(ln.texto):
                continue                 # "QUESTÃO 12" no alto de cada página não é cabeçalho
            assinatura = _assinatura(ln.texto)
            repetida = (n_pag >= 3 and len(re.findall(r"[^\W\d_]", assinatura)) >= 3
                        and repetidas[(assinatura, round(ln.y0 / 12))] >= max(2, n_pag // 2))
            numero_pagina = re.fullmatch(r"\s*(p[áa]g(ina)?\.?\s*)?[-–]?\s*\d+(\s*/\s*\d+)?\s*[-–]?\s*",
                                         ln.texto, re.I) is not None
            if ((na_borda and len(ln.texto.strip()) <= 60) or (perto and repetida)
                    or (numero_pagina and (ln.y1 < h * 0.1 or ln.y0 > h * 0.9))):
                fora.add(id(ln))
    return fora


# =====================================================================
# Faixas e colunas
# =====================================================================
@dataclass
class Faixa:
    """Trecho horizontal da página com uma ou duas colunas."""

    y0: float
    y1: float
    duas_colunas: bool


def _cruza_meio(c: Caixa, meio: float) -> bool:
    return c[0] < meio - 6 and c[2] > meio + 6


def linhas_de_glifos(glifos: list[Caixa]) -> list[Caixa]:
    """Junta letras convertidas em curvas em linhas (mesma altura, vizinhas)."""
    linhas: list[list[float]] = []
    for g in sorted(glifos, key=lambda c: (round((c[1] + c[3]) / 4), c[0])):
        for ln in reversed(linhas[-6:]):
            sobrepoe = min(ln[3], g[3]) - max(ln[1], g[1]) >= 0.5 * min(ln[3] - ln[1], g[3] - g[1])
            if sobrepoe and -2 <= g[0] - ln[2] <= 8:
                ln[2] = max(ln[2], g[2])
                ln[1], ln[3] = min(ln[1], g[1]), max(ln[3], g[3])
                break
        else:
            linhas.append(list(g))
    return [tuple(ln) for ln in linhas]


def _alinhadas(caixas: list[Caixa]) -> int:
    """Quantas linhas começam no mesmo x (margem esquerda de uma coluna)."""
    xs = Counter(round(c[0] / 3) for c in caixas)
    return xs.most_common(1)[0][1] if xs else 0


def em_duas_colunas(caixas: list[Caixa], textos: list[Caixa], largura: float) -> bool:
    """Elementos de um trecho (linhas de texto e desenhos) estão em duas colunas?

    Cada elemento pesa a sua largura: em duas colunas quase nada atravessa o meio.
    Desenhos contam porque há PDFs com o texto convertido em curvas. Além disso,
    cada coluna precisa de linhas de texto alinhadas à esquerda (e a da direita
    começando perto do meio), para uma figura larga não parecer duas colunas.
    """
    meio = largura / 2
    esq = dir_ = cruza = 0.0
    for c in caixas:
        w = c[2] - c[0]
        if c[2] <= meio + 6:
            esq += w
        elif c[0] >= meio - 6:
            dir_ += w
        else:
            cruza += w
    lados = esq + dir_
    if not (lados > 0 and min(esq, dir_) >= 0.15 * lados and cruza <= 0.3 * lados):
        return False
    t_esq = [c for c in textos if c[2] <= meio + 6]
    t_dir = [c for c in textos if c[0] >= meio - 6]
    t_dir_inicio = [c for c in t_dir if c[0] <= meio + 0.15 * largura]
    largas = 0.35 * meio                 # linha de texto corrido, não célula de tabela

    def corridas(ts: list[Caixa]) -> int:
        return sum(1 for c in ts if c[2] - c[0] >= largas)

    return (_alinhadas(t_esq) >= 3 and _alinhadas(t_dir_inicio) >= 3
            and corridas(t_esq) >= 2 and corridas(t_dir) >= 2)


def faixas_da_pagina(caixas: list[Caixa], textos: list[Caixa], largura: float, altura: float) -> list[Faixa]:
    """Divide a página nas faixas separadas por elementos de largura total."""
    meio = largura / 2
    cruzam = sorted((c for c in caixas if _cruza_meio(c, meio) and c[3] - c[1] < altura * 0.5
                     and c[2] - c[0] >= 0.3 * largura), key=lambda c: c[1])
    blocos: list[list[float]] = []
    for c in cruzam:
        if blocos and c[1] <= blocos[-1][1] + 20:
            blocos[-1][1] = max(blocos[-1][1], c[3])
        else:
            blocos.append([c[1], c[3]])
    faixas: list[Faixa] = []
    y = 0.0
    for a, b in blocos:
        if a > y:
            faixas.append(Faixa(y, a, False))
        faixas.append(Faixa(max(a, y), b, False))
        y = max(y, b)
    if y < altura:
        faixas.append(Faixa(y, altura, False))
    for f in faixas:
        if f.y1 - f.y0 < 60:
            continue

        def na_faixa(c: Caixa) -> bool:
            return f.y0 <= (c[1] + c[3]) / 2 < f.y1 and not _cruza_meio(c, meio)

        dentro = [c for c in caixas if na_faixa(c)]
        if dentro:
            f.duas_colunas = em_duas_colunas(dentro, [c for c in textos if na_faixa(c)], largura)
    juntas: list[Faixa] = []
    for f in faixas:
        if juntas and juntas[-1].duas_colunas == f.duas_colunas:
            juntas[-1].y1 = f.y1
        else:
            juntas.append(f)
    return juntas


# =====================================================================
# Marcadores de questão
# =====================================================================
RE_FORTE = re.compile(
    r"^\s*(?:quest(?:ão|ao|ion)?|problema|exerc[íi]cio)\s*(?:n[º°o.]?\s*)?(\d{1,3})\b", re.I)
RE_FRACO = re.compile(r"^\s*\(?(\d{1,3})\s*[.)]\s*(?=\S|$)")


@dataclass
class Marcador:
    linha: Linha
    numero: int
    forte: bool
    lugar: tuple[int, int] = (0, 0)   # (faixa, coluna) na página

    @property
    def estilo(self) -> tuple:
        ln = self.linha
        return (self.forte, ln.fonte, round(ln.tamanho), ln.negrito)

    @property
    def posicao(self) -> tuple[int, int, int]:
        """(página, faixa, coluna): a "casa" onde o marcador está, em ordem de leitura."""
        return (self.linha.pagina, *self.lugar)


def _candidatos(linhas: list[Linha]) -> list[Marcador]:
    saida = []
    for ln in linhas:
        m = RE_FORTE.match(ln.texto)
        if m:
            saida.append(Marcador(ln, int(m.group(1)), True))
            continue
        m = RE_FRACO.match(ln.texto)
        if m and not re.match(r"^\s*\d+[.,]\d", ln.texto):
            saida.append(Marcador(ln, int(m.group(1)), False))
    return saida


def _maior_sequencia(marcadores: list[Marcador]) -> list[Marcador]:
    """Maior subsequência (na ordem de leitura) com números consecutivos n, n+1, n+2..."""
    melhor_fim: dict[int, tuple[int, int]] = {}   # número -> (tamanho, índice)
    anterior: list[int | None] = []
    tamanhos: list[int] = []
    for i, m in enumerate(marcadores):
        prev = melhor_fim.get(m.numero - 1)
        if prev:
            tamanhos.append(prev[0] + 1)
            anterior.append(prev[1])
        else:
            tamanhos.append(1)
            anterior.append(None)
        if tamanhos[i] > melhor_fim.get(m.numero, (0, -1))[0]:
            melhor_fim[m.numero] = (tamanhos[i], i)
    if not tamanhos:
        return []
    i: int | None = max(range(len(tamanhos)), key=lambda k: tamanhos[k])
    seq = []
    while i is not None:
        seq.append(marcadores[i])
        i = anterior[i]
    return seq[::-1]


def escolher_marcadores(candidatos: list[Marcador]) -> list[Marcador]:
    """Agrupa por estilo (fonte, tamanho, negrito, padrão) e fica com a melhor sequência."""
    por_estilo: dict[tuple, list[Marcador]] = {}
    for m in candidatos:
        por_estilo.setdefault(m.estilo, []).append(m)
    melhor: list[Marcador] = []
    melhor_nota: tuple = (0, 0, 0, 0)
    for estilo, lista in por_estilo.items():
        seq = _maior_sequencia(lista)
        forte, _fonte, tamanho, negrito = estilo
        nota = (len(seq) if (forte or len(seq) >= 2) else 0, int(forte), int(negrito), tamanho)
        if nota > melhor_nota:
            melhor, melhor_nota = seq, nota
    return melhor


# =====================================================================
# Análise do documento
# =====================================================================
@dataclass
class PaginaAnalisada:
    numero: int
    largura: float
    altura: float
    linhas: list[Linha]               # sem cabeçalho/rodapé
    graficos: list[tuple[Caixa, str]]  # desenhos e imagens do corpo
    faixas: list[Faixa]
    conteudo: Caixa | None            # área ocupada pelo corpo

    @property
    def caixas(self) -> list[Caixa]:
        return [ln.caixa for ln in self.linhas] + [g[0] for g in self.graficos]

    @property
    def duas_colunas(self) -> bool:
        return any(f.duas_colunas for f in self.faixas)

    def casas(self) -> list[tuple[int, int]]:
        """(faixa, coluna) em ordem de leitura."""
        return [(k, c) for k, f in enumerate(self.faixas) for c in range(2 if f.duas_colunas else 1)]

    def casa_de(self, x0: float, y0: float) -> tuple[int, int]:
        for k, f in enumerate(self.faixas):
            if f.y0 <= y0 < f.y1:
                return k, (1 if f.duas_colunas and x0 >= self.largura / 2 - 6 else 0)
        return len(self.faixas) - 1, 0

    def limites_casa(self, casa: tuple[int, int]) -> Caixa:
        """Retângulo da casa (faixa e coluna) ajustado ao conteúdo da página."""
        f = self.faixas[casa[0]]
        cx0, _, cx1, _ = self.conteudo or (0, 0, self.largura, self.altura)
        if f.duas_colunas:
            meio = self.largura / 2
            cx0, cx1 = (cx0, meio) if casa[1] == 0 else (meio, cx1)
        return (cx0, f.y0, cx1, f.y1)

    def ocupado(self, caixa: Caixa) -> Caixa | None:
        """Parte de ``caixa`` com conteúdo (elementos cujo centro está dentro dela)."""
        x0, y0, x1, y1 = caixa
        dentro = [c for c in self.caixas
                  if x0 - 1 <= (c[0] + c[2]) / 2 <= x1 + 1 and y0 - 1 <= (c[1] + c[3]) / 2 <= y1 + 1]
        return _uniao(dentro)


def _caixas_graficas(pagina) -> list[tuple[Caixa, str]]:
    """Desenhos vetoriais e imagens da página, sem fundos e tarjas de beirada."""
    r_pag = pagina.rect
    saida = []
    try:  # get_cdrawings é bem mais rápido e basta aqui (só caixas, tipo e preenchimento)
        desenhos = pagina.get_cdrawings() if hasattr(pagina, "get_cdrawings") else pagina.get_drawings()
    except Exception:  # noqa: BLE001
        desenhos = []

    def descartar(r) -> bool:
        if r.x0 < -2 or r.y0 < -2 or r.x1 > r_pag.width + 2 or r.y1 > r_pag.height + 2:
            return True                  # fora da folha (coordenadas não confiáveis)
        if r.width > r_pag.width * 0.9 and r.height > r_pag.height * 0.5:
            return True                  # fundo da página
        if r.x1 < 25 or r.x0 > r_pag.width - 25:
            return True                  # tarjas e marcas na beirada da folha
        if r.width < 2.5 and r.height > r_pag.height * 0.4:
            return True                  # fio entre colunas
        return False

    for d in desenhos:
        r = pymupdf.Rect(d["rect"]).normalize()
        if d.get("type") == "f" and all(v >= 0.97 for v in (d.get("fill") or (0,))):
            continue                     # preenchimento branco: invisível (máscaras, fundos)
        if not descartar(r):
            saida.append(((r.x0, r.y0, r.x1, r.y1), "glifo" if _e_glifo(d, r) else "desenho"))
    for info in pagina.get_image_info():
        r = pymupdf.Rect(info["bbox"]).normalize()
        if r.width * r.height >= 4 and not descartar(r):
            saida.append(((r.x0, r.y0, r.x1, r.y1), "imagem"))
    return saida


def _e_glifo(desenho: dict, r) -> bool:
    """Letra (ou linha de texto) convertida em curvas: preenchida, baixa e cheia de detalhes."""
    if desenho.get("type") != "f" or r.height > 14:
        return False
    return r.width <= 14 or len(desenho.get("items") or ()) >= r.width / 3


def _parecidas(a: Caixa, b: Caixa, tol: float = 5.0) -> bool:
    return all(abs(u - v) <= tol for u, v in zip(a, b))


def graficos_repetidos(todos: list[list[tuple[Caixa, str]]], alturas: list[float]) -> set[tuple[int, int]]:
    """(página, índice) de desenhos de cabeçalho/rodapé: repetidos em muitas páginas
    ou faixas largas encostadas no alto/pé da folha."""
    n_pag = len(todos)
    fora: set[tuple[int, int]] = set()
    for p, graficos in enumerate(todos):
        h = alturas[p]
        for k, (c, tipo) in enumerate(graficos):
            if c[3] < h * 0.09 or c[1] > h * 0.91:
                fora.add((p, k))
                continue
            if tipo == "glifo" or n_pag < 3 or (h * 0.15 < c[1] and c[3] < h * 0.85):
                continue
            outras = sum(1 for q, gs in enumerate(todos) if q != p
                         and any(_parecidas(c, c2) for c2, t2 in gs if t2 != "glifo"))
            if outras + 1 >= max(3, n_pag // 3):
                fora.add((p, k))
    return fora


def _uniao(caixas) -> Caixa | None:
    caixas = list(caixas)
    if not caixas:
        return None
    return (min(c[0] for c in caixas), min(c[1] for c in caixas),
            max(c[2] for c in caixas), max(c[3] for c in caixas))


def _dentro_corpo(c: Caixa, altura: float) -> bool:
    return c[3] > altura * ZONA_MARGEM and c[1] < altura * (1 - ZONA_MARGEM)


class Documento:
    """PDF aberto com as páginas analisadas (texto, faixas, colunas, desenhos)."""

    def __init__(self, caminho: Path | str):
        self.caminho = Path(caminho)
        self.doc = pymupdf.open(self.caminho)
        brutas = [linhas_da_pagina(p, i + 1) for i, p in enumerate(self.doc)]
        alturas = [p.rect.height for p in self.doc]
        fora = linhas_de_margem(brutas, alturas)
        graficos = [[g for g in _caixas_graficas(p) if _dentro_corpo(g[0], p.rect.height)]
                    for p in self.doc]
        repetidos = graficos_repetidos(graficos, alturas)
        self.paginas: list[PaginaAnalisada] = []
        for i, p in enumerate(self.doc):
            linhas = [ln for ln in brutas[i] if id(ln) not in fora]
            gs = [g for k, g in enumerate(graficos[i]) if (i, k) not in repetidos]
            caixas = [ln.caixa for ln in linhas] + [g[0] for g in gs]
            self.paginas.append(PaginaAnalisada(
                i + 1, p.rect.width, p.rect.height, linhas, gs,
                faixas_da_pagina(caixas, [ln.caixa for ln in linhas]
                                 + linhas_de_glifos([g[0] for g in gs if g[1] == "glifo"]),
                                 p.rect.width, p.rect.height),
                _uniao(caixas)))

    def fechar(self) -> None:
        self.doc.close()

    def __enter__(self) -> "Documento":
        return self

    def __exit__(self, *a) -> None:
        self.fechar()

    @property
    def num_paginas(self) -> int:
        return len(self.paginas)

    # ------------------------------------------------------------------
    def marcadores(self) -> list[Marcador]:
        candidatos = []
        for pag in self.paginas:
            cs = _candidatos(pag.linhas)
            for m in cs:
                m.lugar = pag.casa_de(m.linha.x0, m.linha.y0)
            cs.sort(key=lambda m: (m.lugar, m.linha.y0, m.linha.x0))
            candidatos.extend(cs)
        return escolher_marcadores(candidatos)

    def paginas_com(self, palavra: str) -> list[int]:
        alvo = palavra.lower()
        return [pag.numero for pag in self.paginas
                if any(alvo in normalizar_texto(ln.texto).lower() for ln in pag.linhas)]

    # ------------------------------------------------------------------
    def _casas_depois(self, pos: tuple[int, int, int]):
        """(página, faixa, coluna) seguintes, em ordem de leitura."""
        p, k, c = pos
        casas = self.paginas[p - 1].casas()
        i = casas.index((k, c)) + 1
        while True:
            if i >= len(casas):
                p += 1
                if p > self.num_paginas:
                    return
                casas = self.paginas[p - 1].casas()
                i = 0
            yield (p, *casas[i])
            i += 1

    def _parte(self, pagina: int, casa: tuple[int, int], de_y: float | None, ate_y: float | None) -> Parte | None:
        pag = self.paginas[pagina - 1]
        x0, y0, x1, y1 = pag.limites_casa(casa)
        if de_y is not None:
            y0 = max(y0, de_y)
        if ate_y is not None:
            y1 = min(y1, ate_y)
        ocupado = pag.ocupado((x0, y0, x1, y1))
        if ocupado is None:
            return None
        topo = y0 if de_y is not None else ocupado[1]   # no início da questão, desde o marcador
        fundo = min(y1, ocupado[3])
        if fundo - topo < 4:
            return None
        m = MARGEM_RECORTE
        esq, dir_ = max(x0 - m, ocupado[0] - m), min(x1 + m, ocupado[2] + m)
        return Parte(pagina, (max(0.0, esq), max(0.0, topo - m),
                              min(pag.largura, dir_), min(pag.altura, fundo + m)))

    def regioes(self, marcadores: list[Marcador] | None = None) -> list[RegiaoQuestao]:
        marcadores = self.marcadores() if marcadores is None else marcadores
        regioes = []
        usados: Counter = Counter()
        for k, m in enumerate(marcadores):
            ident = f"q{m.numero:03d}"
            usados[ident] += 1
            if usados[ident] > 1:
                ident += f"-{usados[ident]}"
            reg = RegiaoQuestao(ident, m.numero, m.linha.pagina)
            prox = marcadores[k + 1] if k + 1 < len(marcadores) else None
            ini = m.posicao
            if prox is not None and prox.posicao == ini:
                parte = self._parte(ini[0], m.lugar, m.linha.y0, prox.linha.y0 - 2)
                reg.partes = [parte] if parte else []
            else:
                parte = self._parte(ini[0], m.lugar, m.linha.y0, None)
                reg.partes = [parte] if parte else []
                # última questão: até o fim da página dela
                fim = prox.posicao if prox is not None else (ini[0], *self.paginas[ini[0] - 1].casas()[-1])
                for pos in self._casas_depois(ini):
                    if pos > fim:
                        break
                    ate = prox.linha.y0 - 2 if (prox is not None and pos == fim) else None
                    parte = self._parte(pos[0], pos[1:], None, ate)
                    if parte:
                        reg.partes.append(parte)
            reg.figuras = self.figuras_em(reg.partes, [(mm.linha.pagina, mm.linha.caixa) for mm in marcadores])
            regioes.append(reg)
        return regioes

    # ------------------------------------------------------------------
    def figuras_em(self, partes: list[Parte], evitar: list[tuple[int, Caixa]] = ()) -> list[FiguraDetectada]:
        """Agrupamentos de desenhos/imagens nas partes (sem fundos de marcadores e separadores)."""
        figuras = []
        for parte in partes:
            pag = self.paginas[parte.pagina - 1]
            x0, y0, x1, y1 = parte.caixa
            dentro = []
            glifos = [c for c, t in pag.graficos if t == "glifo"]
            for c, t in pag.graficos:
                if t == "glifo" or not (c[0] < x1 and c[2] > x0 and c[1] < y1 and c[3] > y0):
                    continue
                if any(p == parte.pagina and (_perto(c, e, 0) or (c[1] >= e[1] - 6 and c[3] <= e[3] + 6))
                       for p, e in evitar):
                    continue                     # fundo, fio ou moldura do "QUESTÃO 12"
                if _separador(c, parte.caixa):
                    continue
                dentro.append((c, t))
            for grupo in _agrupar(dentro):
                caixa = _uniao(c for c, _ in grupo)
                imagens = sum(1 for _, t in grupo if t == "imagem")
                if not _e_figura(caixa, imagens, parte.caixa):
                    continue
                caixa = _com_rotulos(caixa, pag.linhas, glifos)
                caixa = (max(caixa[0], x0), max(caixa[1], y0), min(caixa[2], x1), min(caixa[3], y1))
                figuras.append(FiguraDetectada(0, parte.pagina, caixa, imagens, len(grupo) - imagens))
        for n, f in enumerate(figuras, start=1):
            f.numero = n
        return figuras


def _separador(c: Caixa, regiao: Caixa) -> bool:
    """Fios que separam colunas ou questões (não são figura)."""
    larg, alt = c[2] - c[0], c[3] - c[1]
    rl, ra = regiao[2] - regiao[0], regiao[3] - regiao[1]
    if larg < 2.5 and alt > 0.5 * ra:
        return True
    if alt < 2.5 and larg > 0.85 * rl:
        return True
    return False


def _perto(a: Caixa, b: Caixa, folga: float) -> bool:
    return (a[0] - folga < b[2] and b[0] - folga < a[2]
            and a[1] - folga < b[3] and b[1] - folga < a[3])


def _agrupar(itens: list[tuple[Caixa, str]], folga: float = 8.0) -> list[list[tuple[Caixa, str]]]:
    grupos: list[list[tuple[Caixa, str]]] = []
    caixas: list[Caixa] = []
    for item in itens:
        juntar = [k for k, c in enumerate(caixas) if _perto(c, item[0], folga)]
        novo = [item]
        for k in sorted(juntar, reverse=True):
            novo.extend(grupos.pop(k))
            caixas.pop(k)
        grupos.append(novo)
        caixas.append(_uniao(c for c, _ in novo))
    # junções podem aproximar grupos que antes estavam longe
    mudou = True
    while mudou:
        mudou = False
        for i in range(len(grupos)):
            for j in range(i + 1, len(grupos)):
                if _perto(caixas[i], caixas[j], folga):
                    grupos[i].extend(grupos.pop(j))
                    caixas.pop(j)
                    caixas[i] = _uniao(c for c, _ in grupos[i])
                    mudou = True
                    break
            if mudou:
                break
    grupos.sort(key=lambda g: (round(_uniao(c for c, _ in g)[1] / 10), _uniao(c for c, _ in g)[0]))
    return grupos


def _e_figura(caixa: Caixa, imagens: int, regiao: Caixa) -> bool:
    larg, alt = caixa[2] - caixa[0], caixa[3] - caixa[1]
    if imagens:
        return larg * alt >= 100
    if larg < 12 or alt < 12:          # linhas soltas, traços de fração, sublinhados
        return False
    if larg * alt < 400:
        return False
    # moldura em volta da questão inteira
    rl, ra = regiao[2] - regiao[0], regiao[3] - regiao[1]
    if larg > 0.9 * rl and alt > 0.8 * ra:
        return False
    return True


def _com_rotulos(caixa: Caixa, linhas: list[Linha], glifos: list[Caixa] = (), folga: float = 10.0) -> Caixa:
    """Inclui rótulos curtos (A, B, 3 cm, 60°...) que ficam junto ou dentro da figura."""
    x0, y0, x1, y1 = caixa
    rotulos = [(ln.caixa, len(ln.texto.strip()) <= 8) for ln in linhas]
    rotulos += [(g, g[2] - g[0] <= 40) for g in glifos]
    for c, curto in rotulos:
        dentro = c[0] >= x0 - 1 and c[2] <= x1 + 1 and c[1] >= y0 - 1 and c[3] <= y1 + 1
        if dentro or (curto and _perto(caixa, c, folga)):
            x0, y0, x1, y1 = min(x0, c[0]), min(y0, c[1]), max(x1, c[2]), max(y1, c[3])
    return (x0 - 2, y0 - 2, x1 + 2, y1 + 2)


# =====================================================================
# Imagens
# =====================================================================
def recortar(doc, partes: list[Parte], destino: Path, dpi: int = 200, separacao: float = 6.0) -> Path:
    """PNG com as partes empilhadas (uma coluna continuando na outra, por exemplo)."""
    partes = [p for p in partes if p.caixa[2] > p.caixa[0] and p.caixa[3] > p.caixa[1]]
    if not partes:
        raise ValueError("nenhuma parte para recortar")
    largura = max(p.caixa[2] - p.caixa[0] for p in partes)
    altura = sum(p.caixa[3] - p.caixa[1] for p in partes) + separacao * (len(partes) - 1)
    saida = pymupdf.open()
    try:
        pagina = saida.new_page(width=largura, height=altura)
        y = 0.0
        for k, p in enumerate(partes):
            x0, y0, x1, y1 = p.caixa
            alvo = pymupdf.Rect(0, y, x1 - x0, y + (y1 - y0))
            pagina.show_pdf_page(alvo, doc, p.pagina - 1, clip=pymupdf.Rect(p.caixa))
            y += (y1 - y0)
            if k < len(partes) - 1:
                pagina.draw_line((0, y + separacao / 2), (largura, y + separacao / 2),
                                 color=(0.6, 0.6, 0.6), dashes="[3] 0", width=0.6)
                y += separacao
        destino = Path(destino)
        destino.parent.mkdir(parents=True, exist_ok=True)
        pagina.get_pixmap(dpi=dpi, alpha=False).save(destino)
    finally:
        saida.close()
    return destino


def texto_das_partes(doc, partes: list[Parte]) -> str:
    textos = []
    for p in partes:
        t = doc[p.pagina - 1].get_text("text", clip=pymupdf.Rect(p.caixa), sort=True)
        textos.append(normalizar_texto(t).strip())
    return "\n\n[continua]\n\n".join(t for t in textos if t)


def renderizar_pagina(doc, numero: int, destino: Path, dpi: int = 100, grade: float = 0) -> Path:
    """Página inteira em PNG; com ``grade`` desenha linhas a cada ``grade`` pontos, com rótulos."""
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    if not grade:
        doc[numero - 1].get_pixmap(dpi=dpi, alpha=False).save(destino)
        return destino
    copia = pymupdf.open()
    try:
        copia.insert_pdf(doc, from_page=numero - 1, to_page=numero - 1)
        pg = copia[0]
        r = pg.rect
        cor = (0.85, 0.2, 0.2)
        x = 0.0
        while x <= r.width:
            pg.draw_line((x, 0), (x, r.height), color=cor, width=0.3, stroke_opacity=0.5)
            pg.insert_text((x + 1, 8), f"{x:g}", fontsize=6, color=cor)
            x += grade
        y = grade
        while y <= r.height:
            pg.draw_line((0, y), (r.width, y), color=cor, width=0.3, stroke_opacity=0.5)
            pg.insert_text((1, y - 1), f"{y:g}", fontsize=6, color=cor)
            y += grade
        pg.get_pixmap(dpi=dpi, alpha=False).save(destino)
    finally:
        copia.close()
    return destino


def lado_a_lado(original: Path, desenhada: Path, destino: Path, altura: float = 260) -> Path:
    """Imagem de comparação: original do PDF à esquerda, redesenho à direita."""
    imgs = []
    for p in (original, desenhada):
        pix = pymupdf.Pixmap(str(p))
        imgs.append((p, pix.width, pix.height))
    escala = [altura / h for _, _, h in imgs]
    larguras = [w * e for (_, w, _), e in zip(imgs, escala)]
    margem, topo = 12.0, 18.0
    largura_total = sum(larguras) + margem * 3
    saida = pymupdf.open()
    try:
        pg = saida.new_page(width=largura_total, height=altura + topo + margem)
        x = margem
        for (arq, _, _), larg, rotulo in zip(imgs, larguras, ("Original (PDF)", "TikZ")):
            ret = pymupdf.Rect(x, topo, x + larg, topo + altura)
            pg.draw_rect(ret, color=(0.75, 0.75, 0.75), width=0.5)
            pg.insert_image(ret, filename=str(arq), keep_proportion=True)
            pg.insert_text((x, topo - 5), rotulo, fontsize=9, color=(0.2, 0.2, 0.2))
            x += larg + margem
        destino = Path(destino)
        destino.parent.mkdir(parents=True, exist_ok=True)
        pg.get_pixmap(dpi=144, alpha=False).save(destino)
    finally:
        saida.close()
    return destino
