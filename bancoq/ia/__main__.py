"""Ferramentas da importação de PDFs com o Claude: ``python -m bancoq.ia <comando>``.

Saída sempre em JSON (UTF-8). Código de saída 0 = certo, 1 = há questões com erro
(validar/finalizar), 2 = o comando não pôde ser feito.
"""

from __future__ import annotations

import argparse
import json
import sys

from . import comandos
from .catalogo import ErroCatalogo
from .pacote import ErroPacote


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m bancoq.ia",
        description="Ferramentas para importar provas em PDF para o Banco de Questões.")
    p.add_argument("--banco", help="pasta do banco (padrão: o último aberto no aplicativo)")
    sub = p.add_subparsers(dest="comando", required=True, metavar="comando")

    sub.add_parser("banco", help="pasta do banco, dos pacotes e do trabalho")
    sub.add_parser("catalogo", help="categorias, tags, fontes e preâmbulo do banco")
    sub.add_parser("pacotes", help="pacotes da caixa de entrada")

    s = sub.add_parser("preparar", help="cria/retoma o pacote de um PDF: recortes, texto e figuras")
    s.add_argument("pdf")
    s.add_argument("--nome", help="nome da pasta do pacote (padrão: nome do PDF)")
    s.add_argument("--titulo", help="título do pacote (ex.: OBMEP 2025 — Nível 3, 1ª fase)")
    s.add_argument("--refazer", action="store_true", help="refaz os recortes que já existem")

    s = sub.add_parser("pagina", help="página inteira em PNG (com --grade, linhas a cada N pontos)")
    s.add_argument("pacote")
    s.add_argument("numero", type=int)
    s.add_argument("--grade", type=float, default=0)
    s.add_argument("--dpi", type=int, default=100)

    s = sub.add_parser("recortar", help="refaz o recorte de uma questão ou figura")
    s.add_argument("pacote")
    s.add_argument("questao")
    s.add_argument("--parte", action="append", required=True,
                   help="PAGINA:x0,y0,x1,y1 em pontos; repita para juntar partes")
    s.add_argument("--figura", type=int, help="número da figura (sem isto, recorta a questão)")

    s = sub.add_parser("remover-figura", help="apaga uma figura detectada por engano")
    s.add_argument("pacote")
    s.add_argument("questao")
    s.add_argument("figura", type=int)

    s = sub.add_parser("tikz", help="compila as figuras TikZ e compara com o original")
    s.add_argument("pacote")
    s.add_argument("questao")
    s.add_argument("--arquivo", help="compila só o TikZ deste arquivo (teste antes de escrever)")
    s.add_argument("--figura", type=int, help="com --arquivo: figura do PDF para comparar")

    s = sub.add_parser("validar", help="confere as questões escritas no rascunho (trabalho/)")
    s.add_argument("pacote")
    s.add_argument("questoes", nargs="*")
    s.add_argument("--compilar", action="store_true", help="também compila o LaTeX de cada questão")

    s = sub.add_parser("entregar", help="copia as questões sem erro para a caixa de entrada do app")
    s.add_argument("pacote")
    s.add_argument("questoes", nargs="*")
    s.add_argument("--compilar", action="store_true", help="compila o LaTeX antes de entregar")
    s.add_argument("--forcar", action="store_true", help="reenvia questões rejeitadas no app")

    s = sub.add_parser("status", help="o que já foi feito e o que falta no pacote")
    s.add_argument("pacote")

    s = sub.add_parser("finalizar", help="confere e entrega tudo e marca o pacote como pronto")
    s.add_argument("pacote")
    s.add_argument("--sem-compilar", action="store_true")
    return p


def executar(argv: list[str] | None = None) -> tuple[dict, int]:
    a = _parser().parse_args(argv)
    c = a.comando
    if c == "banco":
        r = comandos.cmd_banco(a.banco)
    elif c == "catalogo":
        r = comandos.cmd_catalogo(a.banco)
    elif c == "pacotes":
        r = comandos.cmd_pacotes(a.banco)
    elif c == "preparar":
        r = comandos.cmd_preparar(a.pdf, a.banco, a.nome, a.titulo, a.refazer)
    elif c == "pagina":
        r = comandos.cmd_pagina(a.pacote, a.numero, a.banco, a.grade, a.dpi)
    elif c == "recortar":
        r = comandos.cmd_recortar(a.pacote, a.questao, a.parte, a.banco, a.figura)
    elif c == "remover-figura":
        r = comandos.cmd_remover_figura(a.pacote, a.questao, a.figura, a.banco)
    elif c == "tikz":
        r = comandos.cmd_tikz(a.pacote, a.questao, a.banco, a.arquivo, a.figura)
    elif c == "validar":
        r = comandos.cmd_validar(a.pacote, a.questoes or None, a.banco, a.compilar)
        return r, 1 if r["com_erro"] else 0
    elif c == "entregar":
        r = comandos.cmd_entregar(a.pacote, a.questoes or None, a.banco, a.compilar, a.forcar)
        return r, 1 if r["puladas"] and not r["entregues"] else 0
    elif c == "status":
        r = comandos.cmd_status(a.pacote, a.banco)
    elif c == "finalizar":
        r = comandos.cmd_finalizar(a.pacote, a.banco, not a.sem_compilar)
        return r, 0 if r["pronto"] else 1
    else:  # pragma: no cover - o argparse já recusa
        raise comandos.ErroComando(f"comando desconhecido: {c}")
    return r, 0


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    try:
        resultado, codigo = executar(argv)
    except (comandos.ErroComando, ErroCatalogo, ErroPacote) as e:
        resultado, codigo = {"erro": str(e)}, 2
    except Exception as e:  # noqa: BLE001 - falha inesperada: detalhes no stderr
        import traceback

        traceback.print_exc()
        resultado, codigo = {"erro": f"falha inesperada ({type(e).__name__}: {e})"}, 2
    print(json.dumps(resultado, ensure_ascii=False, indent=1))
    return codigo


if __name__ == "__main__":
    sys.exit(main())
