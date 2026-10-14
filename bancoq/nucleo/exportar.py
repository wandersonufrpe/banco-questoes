"""Exportação de uma montagem: .tex e PDF de cada versão, gabarito e resoluções.

Estrutura da pasta de saída::

    prova_A.tex / prova_A.pdf          (uma por versão)
    resolucao_A.tex / resolucao_A.pdf  (resolução e comentários, por versão)
    gabarito.tex / gabarito.pdf        (tabela de respostas de cada versão)
    midia/                             (imagens usadas, caminhos relativos)
    montagem.json                      (semente, ordem das questões e respostas)

A pasta compila sozinha em outro computador (só precisa do TeX).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from .compilador import Compilacao, InfoTex
from .entidades import Questao
from .latex_gerar import (
    DEFINICOES_RESOLUCAO, ColetorImagens, campo, latex_questao_prova, latex_questao_resolucao,
)
from .midia import GerenciadorMidia
from .modelos_prova import preambulo, preencher
from .prova import Montagem, Versao, gerar_versoes, valor_numerico

EXTENSOES_AUXILIARES = (".aux", ".out", ".toc", ".fls", ".fdb_latexmk", ".synctex.gz", ".nav", ".snm")


@dataclass
class RelatorioExportacao:
    pasta: Path
    arquivos: list[Path] = field(default_factory=list)
    erros: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    pdfs: list[Path] = field(default_factory=list)
    cancelado: bool = False


def nomes_arquivos(m: Montagem) -> list[str]:
    nomes = ["gabarito.tex", "gabarito.pdf", "montagem.json"]
    for v in range(m.num_versoes):
        letra = chr(ord("A") + v)
        nomes += [f"prova_{letra}.tex", f"prova_{letra}.pdf", f"resolucao_{letra}.tex", f"resolucao_{letra}.pdf"]
    return nomes


def valores_cabecalho(m: Montagem, versao: Versao | None) -> dict[str, str]:
    c = m.cabecalho
    return {
        "titulo": c.titulo, "disciplina": c.disciplina, "turma": c.turma, "professor": c.professor,
        "data": c.data, "instrucoes": c.instrucoes.strip(),
        "versao": versao.letra if (versao is not None and m.num_versoes > 1) else "",
        "semente": str(m.semente),
    }


def _comentario_topo(m: Montagem, versao: Versao | None, o_que: str) -> str:
    agora = datetime.now().strftime("%d/%m/%Y %H:%M")
    linhas = [f"% {o_que} gerado(a) pelo Banco de Questões em {agora}."]
    nome = m.nome or m.cabecalho.titulo
    if nome:
        linhas.append(f"% Montagem: {nome}")
    linhas.append(f"% Semente: {m.semente} — versões: {m.num_versoes} — embaralhar questões: "
                  f"{'sim' if m.embaralhar_questoes else 'não'} — embaralhar alternativas: "
                  f"{'sim' if m.embaralhar_alternativas else 'não'}")
    if versao is not None:
        ids = ", ".join(str(qv.questao.id) for qv in versao.questoes)
        if m.num_versoes > 1:
            linhas.append(f"% Versão {versao.letra}. Questões (nº no banco, na ordem desta versão): {ids}")
        else:
            linhas.append(f"% Questões (nº no banco, nesta ordem): {ids}")
    return "\n".join(linhas) + "\n"


def documento_prova(m: Montagem, versao: Versao, modelo: str, macros: str, resolver) -> str:
    corpo = "\n".join(
        latex_questao_prova(
            qv.questao, resolver, qv.ordem_itens, qv.item.valor,
            qv.item.espaco_cm if qv.questao.tipo == "discursiva" else 0.0,
        )
        for qv in versao.questoes
    )
    valores = valores_cabecalho(m, versao) | {"macros": macros, "questoes": corpo}
    return _comentario_topo(m, versao, "Prova") + preencher(modelo, valores)


def _titulo_documento(m: Montagem, titulo: str, versao: Versao | None) -> str:
    c = m.cabecalho
    linhas = ["\\begin{center}", f"{{\\Large\\bfseries {titulo}}}\\par"]
    if c.titulo.strip():
        linhas.append(f"{{\\large {c.titulo}}}\\par")
    detalhes = [x for x in (c.disciplina, c.turma and f"Turma {c.turma}", c.data) if x and x.strip()]
    if detalhes:
        linhas.append(" \\textperiodcentered{} ".join(detalhes) + "\\par")
    if versao is not None and m.num_versoes > 1:
        linhas.append(f"\\fbox{{\\textbf{{Versão {versao.letra}}}}}\\par")
    linhas.append("\\end{center}")
    return "\n".join(linhas) + "\n"


def documento_resolucao(m: Montagem, versao: Versao, modelo: str, macros: str, resolver) -> str:
    valores = valores_cabecalho(m, versao)
    partes = [
        _comentario_topo(m, versao, "Resolução"),
        preambulo(modelo, macros, valores),
        DEFINICOES_RESOLUCAO,
        "\\begin{document}\n",
        _titulo_documento(m, "Resolução", versao),
        "\\medskip\n",
    ]
    for qv in versao.questoes:
        partes.append(latex_questao_resolucao(qv.questao, resolver, qv.ordem_itens, qv.item.valor))
        partes.append("\n")
    partes.append("\\end{document}\n")
    return "".join(partes)


def _celula(texto: str) -> str:
    return texto.replace("\n", " ").strip() or "—"


def documento_gabarito(m: Montagem, versoes: list[Versao], modelo: str, macros: str, resolver) -> str:
    valores = valores_cabecalho(m, None)
    partes = [
        _comentario_topo(m, None, "Gabarito"),
        preambulo(modelo, macros, valores),
        "\n\\usepackage{longtable}\n",
        DEFINICOES_RESOLUCAO,
        "\\begin{document}\n",
        _titulo_documento(m, "Gabarito", None),
        f"\\noindent{{\\small Semente do embaralhamento: {m.semente}. "
        f"Versões: {m.num_versoes}.}}\\par\\medskip\n",
    ]
    if len(versoes) > 1:
        partes.append("\\noindent\\textbf{Resumo (múltipla escolha e V/F)}\\par\\smallskip\n")
        cols = "|c|" + "c|" * len(versoes)
        partes.append(f"\\begin{{longtable}}{{{cols}}}\n\\hline\n\\textbf{{Nº}}")
        for v in versoes:
            partes.append(f" & \\textbf{{{v.letra}}}")
        partes.append(" \\\\ \\hline\n\\endhead\n")
        for i in range(len(versoes[0].questoes)):
            partes.append(str(i + 1))
            for v in versoes:
                qv = v.questoes[i]
                if qv.questao.tipo in ("multipla", "vf"):
                    partes.append(" & " + qv.resposta())
                elif qv.questao.tipo == "curta":
                    partes.append(" & \\textit{curta}")
                else:
                    partes.append(" & \\textit{disc.}")
            partes.append(" \\\\ \\hline\n")
        partes.append("\\end{longtable}\n\\medskip\n")
    for v in versoes:
        titulo = f"Versão {v.letra}" if len(versoes) > 1 else "Respostas"
        partes.append(f"\\par\\bigskip\\noindent{{\\large\\bfseries {titulo}}}\\par\\smallskip\n")
        partes.append("\\begin{longtable}{|c|c|p{0.55\\linewidth}|c|}\n\\hline\n"
                      "\\textbf{Nº} & \\textbf{Nº no banco} & \\textbf{Resposta} & \\textbf{Valor} \\\\ \\hline\n"
                      "\\endhead\n")
        for qv in v.questoes:
            q = qv.questao
            if q.tipo == "curta":
                resp = _celula(campo(q.resposta_curta, resolver))
            elif q.tipo == "discursiva":
                resp = "\\textit{discursiva — ver resolução}"
            else:
                resp = qv.resposta()
            partes.append(f"{qv.numero} & {q.id} & {resp} & {_celula(qv.item.valor)} \\\\ \\hline\n")
        partes.append("\\end{longtable}\n")
    partes.append("\\end{document}\n")
    return "".join(partes)


def registro_json(m: Montagem, versoes: list[Versao]) -> dict:
    return {
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "montagem": m.para_dict(),
        "versoes": [
            {
                "versao": v.letra,
                "questoes": [
                    {"numero": qv.numero, "questao_id": qv.questao.id, "tipo": qv.questao.tipo,
                     "ordem_alternativas": qv.ordem_itens, "resposta": qv.resposta(), "valor": qv.item.valor}
                    for qv in v.questoes
                ],
            }
            for v in versoes
        ],
    }


class Exportacao:
    """Executa a exportação (pode rodar numa thread e ser cancelada)."""

    def __init__(self, m: Montagem, questoes: dict[int, Questao], modelo: str, macros: str,
                 midia: GerenciadorMidia, pasta: Path, info_tex: InfoTex | None, gerar_pdf: bool,
                 tempo_limite: float = 180,
                 progresso: Callable[[str, int, int], None] | None = None):
        self.m = m
        self.questoes = questoes
        self.modelo = modelo
        self.macros = macros
        self.midia = midia
        self.pasta = Path(pasta)
        self.info = info_tex
        self.gerar_pdf = gerar_pdf and info_tex is not None
        self.tempo_limite = tempo_limite
        self.progresso = progresso or (lambda texto, i, n: None)
        self._cancelado = False
        self._comp: Compilacao | None = None

    def cancelar(self) -> None:
        self._cancelado = True
        if self._comp is not None:
            self._comp.cancelar()

    def executar(self) -> RelatorioExportacao:
        rel = RelatorioExportacao(self.pasta)
        self.pasta.mkdir(parents=True, exist_ok=True)
        faltando = [i.questao_id for i in self.m.itens if i.questao_id not in self.questoes]
        if faltando:
            rel.avisos.append(f"Questões não encontradas no banco (ignoradas): {', '.join(map(str, faltando))}")
        versoes = gerar_versoes(self.m, self.questoes)
        coletor = ColetorImagens(self.midia)

        documentos: list[tuple[str, str]] = []
        for v in versoes:
            documentos.append((f"prova_{v.letra}.tex", documento_prova(self.m, v, self.modelo, self.macros, coletor)))
        for v in versoes:
            documentos.append((f"resolucao_{v.letra}.tex",
                               documento_resolucao(self.m, v, self.modelo, self.macros, coletor)))
        documentos.append(("gabarito.tex", documento_gabarito(self.m, versoes, self.modelo, self.macros, coletor)))

        for nome, texto in documentos:
            destino = self.pasta / nome
            destino.write_text(texto, encoding="utf-8")
            rel.arquivos.append(destino)
        coletor.copiar_para(self.pasta)
        if coletor.faltando:
            rel.avisos.append("Imagens não encontradas: " + ", ".join(sorted(coletor.faltando)))
        json_path = self.pasta / "montagem.json"
        json_path.write_text(json.dumps(registro_json(self.m, versoes), ensure_ascii=False, indent=2),
                             encoding="utf-8")
        rel.arquivos.append(json_path)

        if not self.gerar_pdf:
            if self.info is None:
                rel.avisos.append("TeX não encontrado: foram gerados só os arquivos .tex.")
            return rel

        total = len(documentos)
        for i, (nome, _) in enumerate(documentos):
            if self._cancelado:
                rel.cancelado = True
                break
            self.progresso(f"Compilando {nome}…", i, total)
            self._comp = Compilacao(self.info, self.pasta, nome, self.tempo_limite, passadas=2)
            res = self._comp.executar()
            self._comp = None
            if res.cancelado:
                rel.cancelado = True
                break
            if res.ok and res.pdf:
                rel.pdfs.append(res.pdf)
                self._limpar_auxiliares(nome, manter_log=False)
            elif res.tempo_esgotado:
                rel.erros.append(f"{nome}: tempo limite ({self.tempo_limite:g} s) esgotado.")
            else:
                msg = res.erro.mensagem if res.erro else "falha sem mensagem"
                linha = f" (linha {res.erro.linha} do .tex)" if res.erro and res.erro.linha else ""
                expl = f" {res.erro.explicacao}" if res.erro and res.erro.explicacao else ""
                rel.erros.append(f"{nome}: {msg}{linha}.{expl} Veja {Path(nome).stem}.log.")
                self._limpar_auxiliares(nome, manter_log=True)
        self.progresso("Concluído.", total, total)
        return rel

    def _limpar_auxiliares(self, nome_tex: str, manter_log: bool) -> None:
        base = self.pasta / Path(nome_tex).stem
        extensoes = list(EXTENSOES_AUXILIARES) + ([] if manter_log else [".log"])
        for ext in extensoes:
            try:
                Path(str(base) + ext).unlink()
            except OSError:
                pass


def exportar(*args, **kwargs) -> RelatorioExportacao:
    return Exportacao(*args, **kwargs).executar()


def soma_valores(versao: Versao) -> float | None:
    vals = [valor_numerico(qv.item.valor) for qv in versao.questoes if qv.item.valor.strip()]
    if not vals or any(v is None for v in vals):
        return None
    return sum(vals)
