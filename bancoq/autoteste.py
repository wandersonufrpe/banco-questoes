"""Autoteste do executável: ``BancoQuestoes --autoteste [--relatorio arquivo.txt]``.

Confere se as partes empacotadas funcionam: SQLite com FTS5, PyMuPDF, rapidfuzz,
traduções do Qt, MathJax local no QtWebEngine (sem rede) e, se houver TeX, a
compilação de uma prova. Tudo acontece numa pasta temporária, que é apagada no
fim; nenhum banco do usuário é tocado.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path


def executar_autoteste(app) -> int:
    from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer

    resultados: list[tuple[str, bool, str]] = []

    def checar(nome: str, func) -> None:
        try:
            detalhe = func() or ""
            resultados.append((nome, True, str(detalhe)))
        except Exception as e:  # noqa: BLE001
            resultados.append((nome, False, f"{type(e).__name__}: {e}"))

    tmp = Path(tempfile.mkdtemp(prefix="bancoq-autoteste-"))
    os.environ["BANCOQ_CONFIG"] = str(tmp / "config")
    contexto = {}

    def banco():
        from .nucleo.banco import Banco, fts5_disponivel
        from .nucleo.entidades import Item, Questao
        from .nucleo.midia import GerenciadorMidia
        from .nucleo.repositorio import Filtro, Repositorio

        b = Banco.criar(tmp / "banco")
        repo = Repositorio(b, GerenciadorMidia(b.pasta_midia, tmp / "temp"))
        qid = repo.salvar_questao(Questao(tipo="multipla", enunciado="Autoteste: quanto vale $1+1$?",
                                          itens=[Item("$1$"), Item("$2$", True)]))
        assert repo.buscar(Filtro(texto="autoteste"))[0].id == qid
        contexto["repo"] = repo
        return f"FTS5={'sim' if fts5_disponivel() else 'não (usa LIKE)'}"

    def pymupdf():
        from .nucleo.pdf import pymupdf as fitz

        doc = fitz.open()
        doc.new_page().insert_text((72, 72), "autoteste")
        dados = doc.tobytes()
        with fitz.open(stream=dados, filetype="pdf") as d:
            assert d.page_count == 1
            return f"versão {fitz.VersionBind}"

    def rapidfuzz():
        from .nucleo.duplicadas import procurar_parecidas

        r = procurar_parecidas("Calcule a derivada de x ao quadrado", [(1, "calcule a derivada de x ao quadrado.")])
        assert r and r[0][1] > 90
        return "ok"

    def recursos():
        from .caminhos import recurso

        mj = recurso("mathjax", "tex-svg-full.js")
        assert mj.stat().st_size > 1_000_000, "MathJax ausente"
        assert recurso("modelos", "generico.tex").exists()
        assert recurso("previa.html").exists()
        return str(mj.parent)

    def traducoes():
        from PySide6.QtWidgets import QDialogButtonBox

        caixa = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        texto = caixa.button(QDialogButtonBox.StandardButton.Cancel).text().replace("&", "")
        assert texto == "Cancelar", f"botão aparece como “{texto}”"
        return texto

    def mathjax():
        from .interface.previa import PreviaWeb

        v = PreviaWeb()
        v.resize(500, 200)
        v.show()
        v.mostrar(r"<p>\(\int_0^1 x^2\,dx\)</p>")
        resultado = {}
        laco = QEventLoop()

        def consultar():
            v.page().runJavaScript(
                "document.querySelectorAll('mjx-container').length + '|' + (window.MathJax ? MathJax.version : '')",
                0, lambda r: (resultado.setdefault("r", r), laco.quit()),
            )

        inicio = time.monotonic()
        while time.monotonic() - inicio < 30:
            QTimer.singleShot(700, consultar)
            QTimer.singleShot(5000, laco.quit)
            laco.exec()
            r = resultado.pop("r", None)
            if r and not str(r).startswith("0|"):
                v.close()
                v.deleteLater()
                QCoreApplication.processEvents()
                return f"MathJax {str(r).split('|')[1]} renderizou {str(r).split('|')[0]} fórmula(s)"
        v.close()
        raise RuntimeError("o MathJax não renderizou a fórmula em 30 s")

    def tex():
        from .nucleo.compilador import localizar_tex
        from .nucleo.exportar import Exportacao
        from .nucleo.modelos_prova import texto_generico
        from .nucleo.prova import Montagem

        info = localizar_tex()
        if info is None:
            return "TeX não encontrado (a prévia exata e o PDF ficam desativados; isso não é erro)"
        repo = contexto["repo"]
        m = Montagem(num_versoes=2, embaralhar_alternativas=True)
        m.adicionar_manual([r.id for r in repo.buscar()])
        rel = Exportacao(m, repo.obter_questoes(m.ids()), texto_generico(), "", repo.midia, tmp / "saida",
                         info, True, 120).executar()
        assert not rel.erros, rel.erros
        return f"{info.descricao()} — {len(rel.pdfs)} PDF(s)"

    for nome, func in (("Recursos empacotados", recursos), ("SQLite/banco", banco), ("PyMuPDF", pymupdf),
                       ("rapidfuzz", rapidfuzz), ("Traduções do Qt", traducoes), ("Prévia (QtWebEngine + MathJax)", mathjax),
                       ("TeX", tex)):
        checar(nome, func)

    from . import __version__

    linhas = [f"Banco de Questões {__version__} — autoteste", f"Python {sys.version.split()[0]}, {sys.platform}"]
    for nome, ok, detalhe in resultados:
        linhas.append(f"[{'OK' if ok else 'FALHOU'}] {nome}: {detalhe}")
    falhas = sum(1 for _, ok, _ in resultados if not ok)
    linhas.append("RESULTADO: " + ("tudo certo" if not falhas else f"{falhas} falha(s)"))
    relatorio = "\n".join(linhas)
    print(relatorio, flush=True)
    destino = None
    if "--relatorio" in sys.argv:
        i = sys.argv.index("--relatorio")
        if i + 1 < len(sys.argv):
            destino = Path(sys.argv[i + 1])
    if destino is not None:
        destino.write_text(relatorio + "\n", encoding="utf-8")
    from .app import encerrar_qt

    encerrar_qt(app)
    shutil.rmtree(tmp, ignore_errors=True)
    return 1 if falhas else 0
