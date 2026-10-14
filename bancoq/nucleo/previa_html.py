"""HTML de uma questão inteira para a prévia rápida (usa latex_html)."""

from __future__ import annotations

import html
from typing import Callable

from .entidades import Questao, letra
from .latex_html import latex_para_html


def html_questao(
    q: Questao,
    resolver_imagem: Callable[[str], str | None] | None = None,
    mostrar_respostas: bool = True,
    mostrar_observacoes: bool = True,
    numero: str | None = None,
) -> str:
    def conv(t: str) -> str:
        return latex_para_html(t, resolver_imagem)

    partes = ['<div class="questao">']
    if numero:
        partes.append(f'<div class="numero">Questão {html.escape(numero)}</div>')
    enun = conv(q.enunciado)
    partes.append(f'<div class="enunciado">{enun or "<span class=vazio>(enunciado vazio)</span>"}</div>')

    if q.tipo == "multipla":
        partes.append('<ol class="alternativas">')
        for i, item in enumerate(q.itens):
            classe = "correta" if (item.correta and mostrar_respostas) else ""
            marca = '<span class="marca">✔</span>' if classe else ""
            com = ""
            if mostrar_respostas and item.comentario.strip():
                com = f'<div class="comentario">{conv(item.comentario)}</div>'
            partes.append(
                f'<li class="{classe}"><span class="rotulo">({letra(i)})</span>'
                f'<div class="texto-item">{conv(item.texto)}{com}</div>{marca}</li>'
            )
        partes.append("</ol>")
        if q.nao_embaralhar and mostrar_respostas:
            partes.append('<div class="info">Alternativas não serão embaralhadas.</div>')
    elif q.tipo == "vf":
        partes.append('<ol class="alternativas afirmativas">')
        for i, item in enumerate(q.itens):
            vf = ("V" if item.correta else "F") if mostrar_respostas else " "
            com = ""
            if mostrar_respostas and item.comentario.strip():
                com = f'<div class="comentario">{conv(item.comentario)}</div>'
            partes.append(
                f'<li><span class="rotulo vf">({vf})</span>'
                f'<div class="texto-item">{conv(item.texto)}{com}</div></li>'
            )
        partes.append("</ol>")
    elif q.tipo == "curta" and mostrar_respostas and q.resposta_curta.strip():
        partes.append(
            f'<div class="resposta"><span class="titulo">Resposta esperada:</span> {conv(q.resposta_curta)}</div>'
        )

    if mostrar_respostas and q.resolucao.strip():
        partes.append(
            f'<div class="resolucao"><div class="titulo">Resolução</div>{conv(q.resolucao)}</div>'
        )
    if mostrar_observacoes and q.observacoes.strip():
        obs = html.escape(q.observacoes).replace("\n", "<br>")
        partes.append(
            f'<div class="observacoes"><div class="titulo">Observações (não vão para a prova)</div>{obs}</div>'
        )
    partes.append("</div>")
    return "".join(partes)
