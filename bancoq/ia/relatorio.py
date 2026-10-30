"""Relatório de conferência de uma questão do pacote (aba "Conferência" do app).

HTML simples, no subconjunto que o QTextBrowser entende (tabelas, cores, imagens).
"""

from __future__ import annotations

import html
from pathlib import Path

from .pacote import (
    FIGURA_AJUSTAR,
    FIGURA_TEXTO,
    Decisao,
    Pacote,
    Problema,
    QuestaoPacote,
    respostas_concordam,
)

VERDE, VERMELHO, LARANJA, CINZA = "#1f7a3a", "#b3261e", "#a34a00", "#666666"


def _e(texto) -> str:
    return html.escape(str(texto or ""))


def _img(caminho: Path | None, largura: int) -> str:
    if caminho is None:
        return f'<span style="color:{CINZA}">(sem imagem)</span>'
    return f'<img src="{caminho.resolve().as_uri()}" width="{largura}">'


def precisa_atencao(qp: QuestaoPacote, problemas: list[Problema]) -> list[str]:
    """Motivos curtos para destacar a questão na lista (vazio = nada a destacar)."""
    motivos = []
    if any(p.gravidade == "erro" for p in problemas):
        motivos.append("tem erro")
    principal = qp.resposta or qp.resposta_da_chave()
    if qp.resposta_independente and principal and not respostas_concordam(principal, qp.resposta_independente):
        motivos.append("resoluções discordam")
    if qp.gabarito_pdf and principal and not respostas_concordam(principal, qp.gabarito_pdf):
        motivos.append("diverge do gabarito")
    if qp.confianca == "baixa":
        motivos.append("confiança baixa")
    if any(f.situacao == FIGURA_AJUSTAR for f in qp.figuras):
        motivos.append("figura para ajustar")
    if qp.avisos:
        motivos.append("aviso do Claude")
    return motivos


def relatorio_html(qp: QuestaoPacote, pacote: Pacote, problemas: list[Problema], *,
                   decisao: Decisao | None = None, categoria: str = "", categoria_nova: bool = False,
                   tags_novas: list[str] = (), preambulo_faltando: list[str] = (),
                   parecidas: list[tuple[int, float]] = (), largura_imagem: int = 260) -> str:
    p: list[str] = []
    titulo = f"Questão {qp.numero}" if qp.numero else qp.ident
    if qp.pagina:
        titulo += f" · página {qp.pagina}"
    p.append(f"<h3>{_e(titulo)}</h3>")

    if decisao is not None:
        if decisao.situacao == "aprovada":
            p.append(f'<p style="color:{VERDE}"><b>Aprovada</b> em {_e(decisao.em)}'
                     + (f" — questão nº {decisao.questao_id} no banco" if decisao.questao_id else "") + "</p>")
        else:
            p.append(f'<p style="color:{CINZA}"><b>Rejeitada</b> em {_e(decisao.em)}'
                     + (f" — {_e(decisao.motivo)}" if decisao.motivo else "") + "</p>")

    # --- resposta
    principal = qp.resposta or qp.resposta_da_chave()
    linhas = []

    def linha(nome: str, valor: str, comparar: bool = True) -> None:
        if not valor:
            marca, cor, valor_txt = "—", CINZA, "não informado"
        elif not comparar or not principal:
            marca, cor, valor_txt = "", "black", valor
        elif respostas_concordam(principal, valor):
            marca, cor, valor_txt = "✔", VERDE, valor
        else:
            marca, cor, valor_txt = "✖", VERMELHO, valor
        linhas.append(f'<tr><td>{_e(nome)}</td><td style="color:{cor}"><b>{_e(valor_txt)}</b> {marca}</td></tr>')

    linha("Resolução principal", principal, comparar=False)
    linha("Segunda resolução (independente)", qp.resposta_independente)
    linha("Gabarito do PDF", qp.gabarito_pdf)
    linhas.append(f"<tr><td>SymPy</td><td>{_e(qp.sympy) or '—'}</td></tr>")
    cor_conf = {"alta": VERDE, "média": LARANJA, "baixa": VERMELHO}.get(qp.confianca, CINZA)
    linhas.append(f'<tr><td>Confiança</td><td style="color:{cor_conf}"><b>{_e(qp.confianca) or "—"}</b></td></tr>')
    p.append('<table cellspacing="0" cellpadding="3" border="0">' + "".join(linhas) + "</table>")

    # --- avisos e problemas
    itens = [f'<li style="color:{LARANJA}">{_e(a)}</li>' for a in qp.avisos]
    for pr in problemas:
        cor = VERMELHO if pr.gravidade == "erro" else LARANJA
        itens.append(f'<li style="color:{cor}">{_e(pr.mensagem)}</li>')
    for qid, pontos in parecidas:
        itens.append(f'<li style="color:{VERMELHO}">parecida com a questão nº {qid} do banco ({pontos:g}%)</li>')
    if itens:
        p.append("<h4>Atenção</h4><ul>" + "".join(itens) + "</ul>")

    # --- metadados novos
    meta = []
    if categoria:
        meta.append(f"Categoria: <b>{_e(categoria)}</b>"
                    + (f' <span style="color:{LARANJA}">(nova: será criada ao aprovar)</span>' if categoria_nova else ""))
    if tags_novas:
        meta.append(f"Tags novas: <b>{_e(', '.join(tags_novas))}</b>")
    if qp.preambulo:
        partes = []
        for ln in qp.preambulo:
            falta = ln in preambulo_faltando
            partes.append(f"<code>{_e(ln)}</code>"
                          + (f' <span style="color:{LARANJA}">(falta no preâmbulo do banco)</span>' if falta else ""))
        meta.append("Preâmbulo: " + "; ".join(partes))
    if meta:
        p.append("<h4>Metadados</h4><p>" + "<br>".join(meta) + "</p>")

    # --- figuras
    numeros = sorted({f.numero for f in qp.figuras} | {
        int(o.stem.split("-")[-2]) for o in pacote.figuras_originais(qp.ident)})
    if numeros:
        p.append("<h4>Figuras</h4>")
        por_numero = {f.numero: f for f in qp.figuras}
        for n in numeros:
            f = por_numero.get(n)
            if f is None:
                situacao, cor = "sem @figura (o Claude não tratou esta figura)", LARANJA
            elif f.situacao == FIGURA_AJUSTAR:
                situacao, cor = "precisa de ajuste" + (f": {f.nota}" if f.nota else ""), LARANJA
            elif f.situacao == FIGURA_TEXTO:
                situacao, cor = "virou texto/tabela", CINZA
            else:
                situacao, cor = "redesenhada em TikZ", VERDE
            p.append(f'<p><b>Figura {n}</b> — <span style="color:{cor}">{_e(situacao)}</span></p>')
            p.append('<table cellspacing="6"><tr><td>Original (PDF)</td><td>TikZ</td></tr><tr>'
                     f"<td>{_img(pacote.figura_original(qp.ident, n), largura_imagem)}</td>"
                     f"<td>{_img(pacote.figura_tikz(qp.ident, n), largura_imagem)}</td></tr></table>")

    # --- relatório do Claude
    if qp.verificacao.strip():
        texto = _e(qp.verificacao.strip()).replace("\n", "<br>")
        p.append(f"<h4>Relatório da conferência</h4><p>{texto}</p>")
    return "".join(p)
