"""Comandos de ``python -m bancoq.ia`` (cada um devolve um dicionário, impresso em JSON)."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path

from ..config_local import ConfigLocal
from ..nucleo.banco import Banco
from ..nucleo.checagem import interpretar_checagem, preparar_checagem
from ..nucleo.compilador import localizar_tex
from ..nucleo.config_banco import ConfigBanco
from ..nucleo.midia import GerenciadorMidia
from ..nucleo.modelos_prova import ler_modelo
from ..nucleo.tikz import compilar_figura, figuras_tikz, preambulo_figuras
from . import pdf as ferramentas_pdf
from .catalogo import catalogo, localizar_banco, pasta_trabalho
from .pacote import (
    SITUACAO_PRONTO,
    ErroPacote,
    Pacote,
    QuestaoPacote,
    listar_pacotes,
    nome_pacote,
    pasta_pacotes,
    tem_erro,
    validar_questao,
)

DPI_RECORTE = 200
DPI_FIGURA = 250


class ErroComando(Exception):
    pass


# =====================================================================
# Apoio
# =====================================================================
def _sha256(arquivo: Path) -> str:
    h = hashlib.sha256()
    with open(arquivo, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def abrir_pacote(ref: str, banco: str | None = None) -> Pacote:
    """``ref``: pasta do pacote ou só o nome (procurado em <banco>/entrada/pacotes)."""
    p = Path(ref).expanduser()
    if (p / "pacote.json").exists():
        return Pacote.abrir(p)
    alvo = pasta_pacotes(localizar_banco(banco)) / ref
    try:
        return Pacote.abrir(alvo)
    except ErroPacote:
        raise ErroComando(f"Pacote {ref!r} não encontrado (procurei em {alvo}).") from None


def pasta_trabalho_pacote(pacote: Pacote) -> Path:
    return pasta_trabalho() / pacote.nome


def rascunho(pacote: Pacote) -> Pacote:
    """Área de trabalho do Claude, com a mesma organização do pacote (questoes/,
    recortes/, figuras/), dentro do repositório: ali ele lê e escreve sem pedir
    licença. ``entregar`` copia para o pacote do banco o que estiver pronto."""
    return Pacote(pasta_trabalho_pacote(pacote), titulo=pacote.titulo, pdf=pacote.pdf)


def _banco_do_pacote(pacote: Pacote) -> Path:
    # <banco>/entrada/pacotes/<nome>
    return pacote.pasta.parent.parent.parent


def _rel(caminho: Path | None) -> str | None:
    return str(caminho) if caminho else None


def _ler_regioes(pacote: Pacote) -> dict:
    arq = pasta_trabalho_pacote(pacote) / "regioes.json"
    try:
        return json.loads(arq.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _gravar_regioes(pacote: Pacote, dados: dict) -> None:
    arq = pasta_trabalho_pacote(pacote) / "regioes.json"
    arq.parent.mkdir(parents=True, exist_ok=True)
    tmp = arq.with_suffix(".tmp")
    tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, arq)


def _pdf_do_pacote(pacote: Pacote) -> Path:
    regioes = _ler_regioes(pacote)
    caminho = Path(regioes.get("pdf_caminho", ""))
    if not caminho.is_file():
        raise ErroComando(
            f"Não achei o PDF original ({caminho or pacote.pdf}). Rode 'preparar' de novo com o PDF.")
    return caminho


def _tex():
    info = localizar_tex(ConfigLocal.carregar().caminho_tex)
    if info is None:
        raise ErroComando("TeX (pdflatex) não encontrado: instale o TeX Live ou o MiKTeX "
                          "ou indique o caminho nas Configurações do aplicativo.")
    return info


def _preambulo_figuras(pasta_banco: Path, q: QuestaoPacote | None) -> str:
    config = ConfigBanco.carregar(pasta_banco)
    try:
        modelo = ler_modelo(pasta_banco / "modelos", config.modelo_padrao)
    except Exception:  # noqa: BLE001
        modelo = ""
    extra = "\n".join(q.preambulo) if q is not None else ""
    return (preambulo_figuras(modelo, config.preambulo) + "\n" + extra).strip()


# =====================================================================
# banco / catalogo / pacotes
# =====================================================================
def cmd_banco(banco: str | None = None) -> dict:
    pasta = localizar_banco(banco)
    return {
        "banco": str(pasta),
        "pacotes": str(pasta_pacotes(pasta)),
        "trabalho": str(pasta_trabalho()),
    }


def cmd_catalogo(banco: str | None = None) -> dict:
    return catalogo(localizar_banco(banco))


def cmd_pacotes(banco: str | None = None) -> dict:
    pasta = localizar_banco(banco)
    saida = []
    for pac in listar_pacotes(pasta):
        decisoes = pac.decisoes()
        saida.append({
            "nome": pac.nome, "titulo": pac.titulo, "situacao": pac.situacao,
            "previstas": pac.previstas, "entregues": len(pac.ids()), "decididas": len(decisoes),
        })
    return {"banco": str(pasta), "pacotes": saida}


# =====================================================================
# preparar
# =====================================================================
def cmd_preparar(pdf: str, banco: str | None = None, nome: str | None = None,
                 titulo: str | None = None, refazer: bool = False) -> dict:
    """Cria (ou retoma) o pacote do PDF: regiões das questões, recortes, texto e figuras."""
    arq_pdf = Path(pdf).expanduser().resolve()
    if not arq_pdf.is_file():
        raise ErroComando(f"PDF não encontrado: {arq_pdf}")
    pasta_banco = localizar_banco(banco)
    nome = nome or nome_pacote(arq_pdf.name)
    pasta = pasta_pacotes(pasta_banco) / nome
    sha = _sha256(arq_pdf)
    if (pasta / "pacote.json").exists():
        pac = Pacote.abrir(pasta)
        if pac.sha256 and pac.sha256 != sha:
            raise ErroComando(f"Já existe o pacote {nome!r} de outro PDF. Use --nome para escolher outro nome.")
    else:
        pac = None
    with ferramentas_pdf.Documento(arq_pdf) as doc:
        if pac is None:
            pac = Pacote.criar(pasta, titulo=titulo or arq_pdf.stem, pdf=arq_pdf.name, sha256=sha,
                               paginas=doc.num_paginas)
        elif titulo:
            pac.titulo = titulo
        rasc = rascunho(pac)
        regioes = doc.regioes()
        pac.previstas = len(regioes) or pac.previstas
        pac.paginas = doc.num_paginas
        pac.salvar()
        questoes = []
        for reg in regioes:
            recorte = rasc.pasta_recortes / f"{reg.ident}.png"
            if reg.partes and (refazer or not recorte.exists()):
                ferramentas_pdf.recortar(doc.doc, reg.partes, recorte, DPI_RECORTE)
            texto = ferramentas_pdf.texto_das_partes(doc.doc, reg.partes)
            arq_texto = rasc.pasta / "texto" / f"{reg.ident}.txt"
            arq_texto.parent.mkdir(parents=True, exist_ok=True)
            arq_texto.write_text(texto + "\n", encoding="utf-8")
            figuras = []
            for fig in reg.figuras:
                destino = rasc.caminho_figura(reg.ident, fig.numero, "original")
                if refazer or not destino.exists():
                    ferramentas_pdf.recortar(doc.doc, [ferramentas_pdf.Parte(fig.pagina, fig.caixa)],
                                             destino, DPI_FIGURA)
                figuras.append({"numero": fig.numero, "arquivo": str(destino),
                                "imagens_no_pdf": fig.imagens})
            area = sum((p.caixa[2] - p.caixa[0]) * (p.caixa[3] - p.caixa[1]) for p in reg.partes) or 1
            questoes.append({
                "id": reg.ident, "numero": reg.numero, "pagina": reg.pagina,
                "recorte": str(recorte) if reg.partes else None,
                "texto": str(arq_texto),
                "texto_util": len(texto.strip()) * 1000 / area >= 2,
                "figuras": figuras,
                "escrita": rasc.arquivo_questao(reg.ident).exists(),
                "entregue": pac.arquivo_questao(reg.ident).exists(),
            })
        dados_regioes = {
            "pdf": arq_pdf.name, "pdf_caminho": str(arq_pdf), "paginas": doc.num_paginas,
            "questoes": [r.para_dict() for r in regioes],
        }
        gabarito = doc.paginas_com("gabarito")
    _gravar_regioes(pac, dados_regioes)
    avisos = []
    if not regioes:
        avisos.append("Nenhum marcador de questão encontrado: veja as páginas ('pagina --grade') e "
                      "recorte cada questão com 'recortar'.")
    if regioes and sum(1 for q in questoes if not q["texto_util"]) > len(questoes) / 2:
        avisos.append("A camada de texto do PDF quase não tem texto (texto em curvas): "
                      "leia as questões pelos recortes.")
    return {
        "pacote": str(pac.pasta), "nome": pac.nome, "titulo": pac.titulo,
        "trabalho": str(rasc.pasta), "escreva_as_questoes_em": str(rasc.pasta_questoes),
        "paginas": pac.paginas, "paginas_com_gabarito": gabarito,
        "questoes": questoes, "avisos": avisos,
    }


# =====================================================================
# pagina / recortar
# =====================================================================
def cmd_pagina(ref: str, numero: int, banco: str | None = None, grade: float = 0, dpi: int = 100) -> dict:
    pac = abrir_pacote(ref, banco)
    arq_pdf = _pdf_do_pacote(pac)
    sufixo = "-grade" if grade else ""
    destino = pasta_trabalho_pacote(pac) / "paginas" / f"p{numero:02d}{sufixo}.png"
    with ferramentas_pdf.pymupdf.open(arq_pdf) as doc:
        if not 1 <= numero <= doc.page_count:
            raise ErroComando(f"O PDF tem {doc.page_count} páginas.")
        ferramentas_pdf.renderizar_pagina(doc, numero, destino, dpi, grade)
        r = doc[numero - 1].rect
    return {"imagem": str(destino), "largura_pt": round(r.width, 1), "altura_pt": round(r.height, 1),
            "dpi": dpi, "grade_pt": grade or None}


def _ler_parte(texto: str) -> ferramentas_pdf.Parte:
    try:
        pagina, caixa = texto.split(":", 1)
        x0, y0, x1, y1 = (float(v) for v in caixa.split(","))
        return ferramentas_pdf.Parte(int(pagina), (x0, y0, x1, y1))
    except ValueError:
        raise ErroComando(f"Parte {texto!r} inválida: use PAGINA:x0,y0,x1,y1 (em pontos)") from None


def cmd_recortar(ref: str, ident: str, partes: list[str], banco: str | None = None,
                 figura: int | None = None) -> dict:
    """Refaz o recorte de uma questão (ou de uma figura dela) a partir de caixas dadas."""
    pac = abrir_pacote(ref, banco)
    rasc = rascunho(pac)
    arq_pdf = _pdf_do_pacote(pac)
    lista = [_ler_parte(p) for p in partes]
    if figura is None:
        destino = rasc.pasta_recortes / f"{ident}.png"
        dpi = DPI_RECORTE
    else:
        destino = rasc.caminho_figura(ident, figura, "original")
        dpi = DPI_FIGURA
    with ferramentas_pdf.pymupdf.open(arq_pdf) as doc:
        ferramentas_pdf.recortar(doc, lista, destino, dpi)
        texto = ferramentas_pdf.texto_das_partes(doc, lista) if figura is None else None
    regioes = _ler_regioes(pac)
    lista_reg = regioes.setdefault("questoes", [])
    reg = next((r for r in lista_reg if r.get("id") == ident), None)
    if reg is None:
        reg = {"id": ident, "numero": None, "pagina": lista[0].pagina, "partes": [], "figuras": []}
        lista_reg.append(reg)
    if figura is None:
        reg["partes"] = [p.para_dict() for p in lista]
        arq_texto = pasta_trabalho_pacote(pac) / "texto" / f"{ident}.txt"
        arq_texto.parent.mkdir(parents=True, exist_ok=True)
        arq_texto.write_text((texto or "") + "\n", encoding="utf-8")
    else:
        figs = [f for f in reg.get("figuras", []) if f.get("numero") != figura]
        figs.append({"numero": figura, "pagina": lista[0].pagina, "caixa": list(lista[0].caixa)})
        reg["figuras"] = sorted(figs, key=lambda f: f["numero"])
    _gravar_regioes(pac, regioes)
    saida = {"imagem": str(destino)}
    if figura is None:
        saida["texto"] = str(pasta_trabalho_pacote(pac) / "texto" / f"{ident}.txt")
    return saida


def cmd_remover_figura(ref: str, ident: str, figura: int, banco: str | None = None) -> dict:
    """Apaga o recorte de uma figura detectada por engano (e o desenho TikZ dela)."""
    rasc = rascunho(abrir_pacote(ref, banco))
    removidos = []
    for tipo in ("original", "tikz"):
        p = rasc.caminho_figura(ident, figura, tipo)
        if p.exists():
            p.unlink()
            removidos.append(str(p))
    return {"removidos": removidos}


# =====================================================================
# tikz
# =====================================================================
def _compilar(codigo: str, preambulo: str, cache: Path) -> dict:
    res = compilar_figura(codigo, preambulo, _tex(), cache)
    if res.ok:
        return {"ok": True, "png": str(res.png)}
    return {"ok": False, "erro": res.erro}


def cmd_tikz(ref: str, ident: str, banco: str | None = None, arquivo: str | None = None,
             figura: int | None = None) -> dict:
    """Compila as figuras TikZ de uma questão do pacote e gera a comparação com o original.

    Com ``arquivo``: compila só o TikZ desse arquivo (útil antes de escrever a questão) e
    compara com a figura ``figura`` do PDF.
    """
    pac = abrir_pacote(ref, banco)
    rasc = rascunho(pac)
    cache = rasc.pasta / "tikz"
    comparar = rasc.pasta / "comparar"
    q = rasc.questao(ident) if rasc.arquivo_questao(ident).exists() else None
    preambulo = _preambulo_figuras(_banco_do_pacote(pac), q)
    resultados = []

    def registrar(codigo: str, campo: str, numero: int | None, copiar: bool) -> None:
        r = {"campo": campo, "figura": numero, **_compilar(codigo, preambulo, cache)}
        if r["ok"] and numero is not None:
            original = rasc.figura_original(ident, numero)
            png = Path(r["png"])
            if copiar:
                destino = rasc.caminho_figura(ident, numero, "tikz")
                destino.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(png, destino)
                r["png"] = str(destino)
            if original:
                sufixo = "" if copiar else "-teste"
                r["comparacao"] = str(ferramentas_pdf.lado_a_lado(
                    original, png, comparar / f"{ident}-{numero}{sufixo}.png"))
            else:
                r["aviso"] = f"não há recorte original da figura {numero}"
        resultados.append(r)

    if arquivo:
        texto = Path(arquivo).read_text(encoding="utf-8")
        codigos = figuras_tikz(texto) or [texto]
        for k, codigo in enumerate(codigos):
            registrar(codigo, f"arquivo {Path(arquivo).name}", figura if k == 0 else None, False)
        return {"questao": ident, "figuras": resultados}
    if q is None:
        raise ErroComando(f"A questão {ident} ainda não foi escrita ({rasc.arquivo_questao(ident)}).")
    desenhadas = q.figuras_desenhadas()
    k = 0
    campos = [("enunciado", q.enunciado)] + [(f"item {i + 1}", it.texto) for i, it in enumerate(q.itens)]
    for campo, texto in campos:
        for codigo in figuras_tikz(texto):
            numero = desenhadas[k].numero if k < len(desenhadas) else None
            registrar(codigo, campo, numero, True)
            k += 1
    extras = [("resolução", q.resolucao)] + [(f"comentário {i + 1}", it.comentario)
                                            for i, it in enumerate(q.itens)]
    for campo, texto in extras:
        for codigo in figuras_tikz(texto):
            registrar(codigo, campo, None, False)
    return {"questao": ident, "figuras": resultados}


# =====================================================================
# validar / status / finalizar
# =====================================================================
def _checar_latex(pac: Pacote, q: QuestaoPacote, pasta_banco: Path, info) -> str | None:
    config = ConfigBanco.carregar(pasta_banco)
    modelo = ler_modelo(pasta_banco / "modelos", config.modelo_padrao)
    macros = (config.preambulo + "\n" + "\n".join(q.preambulo)).strip()
    temp = pasta_trabalho_pacote(pac) / "checagem"
    midia = GerenciadorMidia(Banco(pasta_banco, somente_leitura=True).pasta_midia, temp / "midia")
    comp, doc = preparar_checagem(q.para_questao(), modelo, macros, midia, info, 60, temp)
    try:
        r = interpretar_checagem(comp.executar(), doc)
    finally:
        shutil.rmtree(comp.pasta, ignore_errors=True)
    if r.ok:
        return None
    if r.tempo_esgotado:
        return "LaTeX: a compilação passou do tempo limite"
    if r.erro is None:
        return "LaTeX: a compilação falhou (veja o log)"
    msg = f"LaTeX em {r.campo_nome or 'algum campo'}: {r.erro.mensagem}"
    if r.erro.explicacao:
        msg += f" — {r.erro.explicacao}"
    if r.linha_tex:
        msg += f" (linha: {r.linha_tex.strip()[:80]})"
    return msg


def cmd_validar(ref: str, ids: list[str] | None = None, banco: str | None = None,
                compilar: bool = False) -> dict:
    """Confere as questões escritas no rascunho (as que o Claude ainda vai entregar)."""
    pac = abrir_pacote(ref, banco)
    rasc = rascunho(pac)
    pasta_banco = _banco_do_pacote(pac)
    info = _tex() if compilar else None
    saida = {}
    for ident in ids or rasc.ids():
        if not rasc.arquivo_questao(ident).exists():
            saida[ident] = {"erros": [f"{rasc.arquivo_questao(ident)} não existe"], "avisos": []}
            continue
        q = rasc.questao(ident)
        problemas = validar_questao(q, rasc)
        erros = [p.mensagem for p in problemas if p.gravidade == "erro"]
        avisos = [p.mensagem for p in problemas if p.gravidade == "aviso"]
        if compilar and not erros:
            e = _checar_latex(pac, q, pasta_banco, info)
            if e:
                erros.append(e)
        saida[ident] = {"erros": erros, "avisos": avisos}
    com_erro = [i for i, r in saida.items() if r["erros"]]
    return {"pacote": pac.nome, "questoes": saida, "total": len(saida), "com_erro": com_erro}


def _copiar(origem: Path, destino: Path) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_name(destino.name + ".tmp")
    shutil.copyfile(origem, tmp)
    os.replace(tmp, destino)


def cmd_entregar(ref: str, ids: list[str] | None = None, banco: str | None = None,
                 compilar: bool = False, forcar: bool = False) -> dict:
    """Copia para o pacote do banco (caixa de entrada do app) as questões sem erro.

    Primeiro as imagens, por último o texto: o app só vê a questão quando ela está
    completa. Questões já decididas no app não são reenviadas (com ``forcar``, uma
    questão rejeitada volta para a caixa de entrada).
    """
    pac = abrir_pacote(ref, banco)
    rasc = rascunho(pac)
    validacao = cmd_validar(ref, ids, banco, compilar)
    decisoes = pac.decisoes()
    entregues, puladas = [], {}
    for ident, r in validacao["questoes"].items():
        if r["erros"]:
            puladas[ident] = "tem erro: " + "; ".join(r["erros"])
            continue
        d = decisoes.get(ident)
        if d is not None and (d.situacao == "aprovada" or not forcar):
            puladas[ident] = f"já {d.situacao} no aplicativo"
            continue
        if pac.pasta_figuras.is_dir():
            for antigo in list(pac.pasta_figuras.glob(f"{ident}-*.png")):
                antigo.unlink()
        if rasc.recorte(ident):
            _copiar(rasc.recorte(ident), pac.pasta_recortes / f"{ident}.png")
        if rasc.pasta_figuras.is_dir():
            for fig in rasc.pasta_figuras.glob(f"{ident}-*.png"):
                _copiar(fig, pac.pasta_figuras / fig.name)
        _copiar(rasc.arquivo_questao(ident), pac.arquivo_questao(ident))
        if d is not None:
            pac.desfazer_decisao(ident)
        entregues.append(ident)
    return {"pacote": str(pac.pasta), "entregues": entregues, "puladas": puladas,
            "avisos": {i: r["avisos"] for i, r in validacao["questoes"].items()
                       if i in entregues and r["avisos"]}}


def cmd_status(ref: str, banco: str | None = None) -> dict:
    pac = abrir_pacote(ref, banco)
    rasc = rascunho(pac)
    regioes = _ler_regioes(pac).get("questoes", [])
    escritas = set(rasc.ids())
    entregues = set(pac.ids())
    previstas = [r["id"] for r in regioes]
    com_erro = [i for i in sorted(escritas) if tem_erro(validar_questao(rasc.questao(i), rasc))]
    alteradas = [i for i in sorted(escritas & entregues)
                 if rasc.arquivo_questao(i).read_bytes() != pac.arquivo_questao(i).read_bytes()]
    decisoes = pac.decisoes()
    return {
        "pacote": str(pac.pasta), "titulo": pac.titulo, "situacao": pac.situacao,
        "trabalho": str(rasc.pasta),
        "previstas": len(previstas) or pac.previstas,
        "escritas": len(escritas),
        "entregues": len(entregues),
        "faltando": [i for i in previstas if i not in escritas],
        "com_erro": com_erro,
        "nao_entregues": sorted(escritas - entregues),
        "alteradas_depois_de_entregar": alteradas,
        "aprovadas": sorted(i for i, d in decisoes.items() if d.situacao == "aprovada"),
        "rejeitadas": sorted(i for i, d in decisoes.items() if d.situacao == "rejeitada"),
    }


def cmd_finalizar(ref: str, banco: str | None = None, compilar: bool = True) -> dict:
    """Confere e entrega todas as questões e marca o pacote como pronto para revisão no app."""
    r = cmd_validar(ref, None, banco, compilar=compilar)
    if r["com_erro"]:
        return {"pronto": False, "motivo": "há questões com erro", "com_erro": r["com_erro"],
                "questoes": {i: r["questoes"][i] for i in r["com_erro"]}}
    e = cmd_entregar(ref, None, banco, compilar=False)
    pac = abrir_pacote(ref, banco)
    pac.situacao = SITUACAO_PRONTO
    pac.salvar()
    return {"pronto": True, "pacote": str(pac.pasta), "entregues_agora": e["entregues"],
            "no_pacote": len(pac.ids()), "faltando_no_pdf": cmd_status(ref, banco)["faltando"]}
