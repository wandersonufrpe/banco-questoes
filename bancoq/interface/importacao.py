"""Importação de .tex com tela de revisão (nada é gravado até confirmar)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFrame, QGridLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QScrollArea, QSpinBox, QSplitter, QVBoxLayout, QWidget,
)

from ..contexto import Contexto
from ..nucleo.duplicadas import procurar_parecidas
from ..nucleo.entidades import TIPOS, Item, Questao
from ..nucleo.importador import definicoes_do_preambulo, importar, padrao_por_nome, padroes
from ..nucleo.latex_html import texto_simples
from ..nucleo.macros import extrair_macros
from ..nucleo.previa_html import html_questao
from ..nucleo.repositorio import CategoriaNova
from .cadastro import NOMES_DIFICULDADE, titulo_secao
from .categorias import SeletorCategoria
from .editor_latex import EditorLatex
from .itens import EditorItens
from .previa import PreviaWeb, resolvedor_imagens
from .tags import CampoTags, separar_tags

ABREV = {"discursiva": "D", "multipla": "ME", "vf": "VF", "curta": "RC"}


@dataclass
class Entrada:
    questao: Questao
    categoria_nova: CategoriaNova | None = None
    incluir: bool = True
    avisos: list[str] = field(default_factory=list)


class DialogoColar(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Colar LaTeX")
        self.resize(760, 560)
        lay = QVBoxLayout(self)
        nota = QLabel("Cole o trecho em LaTeX. Para dividir à mão, separe as questões com uma linha contendo só "
                      "<code>%%%</code>; ou divida depois na revisão com “Dividir no cursor”.")
        nota.setWordWrap(True)
        lay.addWidget(nota)
        self.editor = EditorLatex(linhas_min=20, linhas_max=10000, aceita_imagens=False)
        lay.addWidget(self.editor, 1)
        botoes = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        ok = botoes.addButton("Separar questões", QDialogButtonBox.ButtonRole.AcceptRole)
        ok.clicked.connect(self.accept)
        botoes.rejected.connect(self.reject)
        lay.addWidget(botoes)


class TelaImportacao(QWidget):
    def __init__(self, ctx: Contexto, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.entradas: list[Entrada] = []
        self.atual: int | None = None
        self._carregando = False
        self._texto_origem = ""
        self._pasta_origem: Path | None = None
        self._fonte_padrao = ""
        self._definicoes: list[str] = []

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(6, 6, 6, 6)
        topo = QHBoxLayout()
        b_abrir = QPushButton("Abrir arquivo .tex…")
        b_colar = QPushButton("Colar LaTeX…")
        topo.addWidget(b_abrir)
        topo.addWidget(b_colar)
        topo.addSpacing(20)
        topo.addWidget(QLabel("Padrão:"))
        self.c_padrao = QComboBox()
        self.c_padrao.addItem("Automático", None)
        for p in padroes():
            self.c_padrao.addItem(p.nome, p.nome)
            self.c_padrao.setItemData(self.c_padrao.count() - 1, p.descricao, Qt.ItemDataRole.ToolTipRole)
        topo.addWidget(self.c_padrao)
        self.b_reprocessar = QPushButton("Separar de novo")
        self.b_reprocessar.setToolTip("Separa o texto original de novo com o padrão escolhido (desfaz os ajustes)")
        self.b_reprocessar.setEnabled(False)
        topo.addWidget(self.b_reprocessar)
        self.l_status = QLabel("Abra um .tex ou cole um trecho de LaTeX para começar.")
        self.l_status.setStyleSheet("color: gray;")
        topo.addWidget(self.l_status, 1)
        raiz.addLayout(topo)

        self.faixa_macros = QFrame()
        self.faixa_macros.setStyleSheet("QFrame { background: #fff6e0; border-radius: 4px; }")
        fm = QHBoxLayout(self.faixa_macros)
        fm.setContentsMargins(8, 4, 8, 4)
        self.l_macros = QLabel()
        self.l_macros.setWordWrap(True)
        b_macros = QPushButton("Ver e adicionar às minhas macros…")
        fm.addWidget(self.l_macros, 1)
        fm.addWidget(b_macros)
        self.faixa_macros.setVisible(False)
        raiz.addWidget(self.faixa_macros)

        divisor = QSplitter(Qt.Orientation.Horizontal)
        raiz.addWidget(divisor, 1)

        # ---- esquerda: lista e ações em lote -------------------------------------------------
        esq = QWidget()
        le = QVBoxLayout(esq)
        le.setContentsMargins(0, 0, 0, 0)
        le.addWidget(QLabel("<b>Questões encontradas</b> (desmarque para não importar)"))
        self.lista = QListWidget()
        self.lista.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        le.addWidget(self.lista, 1)
        h = QHBoxLayout()
        self.b_juntar = QPushButton("Juntar com a próxima")
        self.b_dividir = QPushButton("Dividir no cursor")
        self.b_dividir.setToolTip("Divide o enunciado na posição do cursor: o que vem depois vira outra questão")
        self.b_excluir = QPushButton("Excluir")
        for b in (self.b_juntar, self.b_dividir, self.b_excluir):
            h.addWidget(b)
        le.addLayout(h)

        lote = QGroupBox("Aplicar às selecionadas")
        g = QGridLayout(lote)
        self.ch_cat = QCheckBox("Categoria")
        self.sel_cat = SeletorCategoria(ctx.repo)
        self.ch_tags = QCheckBox("Acrescentar tags")
        self.e_tags = CampoTags()
        self.ch_fonte = QCheckBox("Fonte")
        self.e_fonte = QLineEdit()
        self.ch_ano = QCheckBox("Ano")
        self.s_ano = QSpinBox()
        self.s_ano.setRange(0, 2100)
        self.s_ano.setSpecialValueText("—")
        self.ch_dif = QCheckBox("Dificuldade")
        self.c_dif = QComboBox()
        self.c_dif.addItems(NOMES_DIFICULDADE)
        self.c_dif.setCurrentIndex(2)
        for i, (ch, w) in enumerate(((self.ch_cat, self.sel_cat), (self.ch_tags, self.e_tags),
                                     (self.ch_fonte, self.e_fonte), (self.ch_ano, self.s_ano),
                                     (self.ch_dif, self.c_dif))):
            g.addWidget(ch, i, 0)
            g.addWidget(w, i, 1)
        self.sel_cat.alterado.connect(lambda: self.ch_cat.setChecked(True))
        self.e_tags.textEdited.connect(lambda _t: self.ch_tags.setChecked(True))
        self.e_fonte.textEdited.connect(lambda _t: self.ch_fonte.setChecked(True))
        self.s_ano.valueChanged.connect(lambda _v: self.ch_ano.setChecked(True))
        self.c_dif.activated.connect(lambda _i: self.ch_dif.setChecked(True))
        self.b_aplicar = QPushButton("Aplicar às selecionadas")
        g.addWidget(self.b_aplicar, 5, 1, alignment=Qt.AlignmentFlag.AlignRight)
        le.addWidget(lote)
        divisor.addWidget(esq)

        # ---- meio: edição ----------------------------------------------------------------------------
        rolagem = QScrollArea()
        rolagem.setWidgetResizable(True)
        meio = QWidget()
        rolagem.setWidget(meio)
        lm = QVBoxLayout(meio)
        h = QHBoxLayout()
        h.addWidget(QLabel("Tipo:"))
        self.c_tipo = QComboBox()
        for k, v in TIPOS.items():
            self.c_tipo.addItem(v, k)
        h.addWidget(self.c_tipo)
        h.addStretch(1)
        lm.addLayout(h)
        self.l_info = QLabel()
        self.l_info.setWordWrap(True)
        self.l_info.setStyleSheet("color: #555;")
        lm.addWidget(self.l_info)
        lm.addWidget(titulo_secao("Enunciado"))
        self.enunciado = EditorLatex(linhas_min=6, linhas_max=30)
        lm.addWidget(self.enunciado)
        self.l_itens = titulo_secao("Alternativas")
        lm.addWidget(self.l_itens)
        self.itens = EditorItens()
        lm.addWidget(self.itens)
        self.l_resposta = titulo_secao("Resposta esperada")
        lm.addWidget(self.l_resposta)
        self.resposta = EditorLatex(linhas_min=1, linhas_max=6)
        lm.addWidget(self.resposta)
        lm.addWidget(titulo_secao("Resolução"))
        self.resolucao = EditorLatex(linhas_min=3, linhas_max=20)
        lm.addWidget(self.resolucao)
        lm.addStretch(1)
        for e in (self.enunciado, self.resposta, self.resolucao):
            e.midia = ctx.midia
        self.itens.definir_midia(ctx.midia)
        self.editor_area = meio
        divisor.addWidget(rolagem)

        self.previa = PreviaWeb()
        divisor.addWidget(self.previa)
        divisor.setSizes([360, 560, 420])

        # ---- rodapé ---------------------------------------------------------------------------------------
        baixo = QHBoxLayout()
        self.b_descartar = QPushButton("Descartar tudo")
        baixo.addWidget(self.b_descartar)
        baixo.addStretch(1)
        aviso = QLabel("Nada é gravado no banco até você confirmar.")
        aviso.setStyleSheet("color: gray;")
        baixo.addWidget(aviso)
        self.b_gravar = QPushButton("Gravar no banco")
        f = self.b_gravar.font()
        f.setBold(True)
        self.b_gravar.setFont(f)
        baixo.addWidget(self.b_gravar)
        raiz.addLayout(baixo)

        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self._atualizar_previa)

        b_abrir.clicked.connect(self.abrir_arquivo)
        b_colar.clicked.connect(self.colar)
        self.b_reprocessar.clicked.connect(self._reprocessar)
        b_macros.clicked.connect(self._adicionar_macros)
        self.lista.currentRowChanged.connect(self._selecionar)
        self.lista.itemChanged.connect(self._marcacao_mudou)
        self.b_juntar.clicked.connect(self._juntar)
        self.b_dividir.clicked.connect(self._dividir)
        self.b_excluir.clicked.connect(self._excluir)
        self.b_aplicar.clicked.connect(self._aplicar_lote)
        self.b_descartar.clicked.connect(self._descartar)
        self.b_gravar.clicked.connect(self.gravar)
        self.c_tipo.currentIndexChanged.connect(self._tipo_mudou)
        for s in (self.enunciado.textChanged, self.resposta.textChanged, self.resolucao.textChanged,
                  self.itens.alterado):
            s.connect(self._editou)
        ctx.sinais.config_alterada.connect(lambda: self.previa.definir_macros(extrair_macros(ctx.config.preambulo)))
        self.previa.definir_macros(extrair_macros(ctx.config.preambulo))
        self._atualizar_estado()

    # =========================================================================
    # entrada de texto
    # =========================================================================
    def pode_descartar(self) -> bool:
        if not self.entradas:
            return True
        r = QMessageBox.question(
            self, "Importação", "Há questões importadas ainda não gravadas no banco. Descartá-las?",
            QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        return r == QMessageBox.StandardButton.Discard

    def abrir_arquivo(self) -> None:
        if not self.pode_descartar():
            return
        arq, _ = QFileDialog.getOpenFileName(self, "Importar prova em LaTeX", "", "LaTeX (*.tex);;Todos (*)")
        if not arq:
            return
        dados = Path(arq).read_bytes()
        try:
            texto = dados.decode("utf-8")
        except UnicodeDecodeError:
            texto = dados.decode("latin-1")
        self.carregar_texto(texto, Path(arq).parent, Path(arq).stem)

    def colar(self) -> None:
        if not self.pode_descartar():
            return
        d = DialogoColar(self)
        if d.exec() and d.editor.toPlainText().strip():
            self.carregar_texto(d.editor.toPlainText(), None, "")

    def carregar_texto(self, texto: str, pasta: Path | None, fonte: str) -> None:
        self._texto_origem = texto
        self._pasta_origem = pasta
        self._fonte_padrao = fonte
        self.b_reprocessar.setEnabled(True)
        self._reprocessar(confirmar=False)

    def _reprocessar(self, confirmar: bool = True) -> None:
        if confirmar is True and self.entradas:
            r = QMessageBox.question(self, "Separar de novo", "Os ajustes feitos na revisão serão perdidos. Continuar?")
            if r != QMessageBox.StandardButton.Yes:
                return
        nome = self.c_padrao.currentData()
        res = importar(self._texto_origem, padrao_por_nome(nome) if nome else None,
                       self._pasta_origem, self.ctx.midia)
        self.entradas = []
        existentes = self.ctx.repo.enunciados()
        for qi in res.questoes:
            q = qi.para_questao()
            q.fonte = self._fonte_padrao
            avisos = list(qi.avisos)
            achadas = procurar_parecidas(q.enunciado, existentes, self.ctx.config.limite_duplicadas, maximo=1)
            if achadas:
                avisos.append(f"Possível duplicada da questão nº {achadas[0][0]} do banco ({achadas[0][1]:g}%).")
            self.entradas.append(Entrada(q, avisos=avisos))
        self.e_fonte.setText(self._fonte_padrao)
        texto = f"{len(self.entradas)} questão(ões) encontrada(s) — padrão: {res.padrao}"
        if res.avisos:
            texto += " — " + " ".join(res.avisos)
        self.l_status.setText(texto)
        self.l_status.setStyleSheet("")
        meu = self.ctx.config.preambulo
        self._definicoes = [d for d in definicoes_do_preambulo(res.preambulo) if d not in meu]
        if self._definicoes:
            self.l_macros.setText(f"O arquivo define {len(self._definicoes)} macro(s) que não estão no seu preâmbulo "
                                  "(ex.: " + ", ".join(d.split("}")[0] + "}" for d in self._definicoes[:3]) + ").")
        self.faixa_macros.setVisible(bool(self._definicoes))
        self._recarregar_lista(0 if self.entradas else None)

    def _adicionar_macros(self) -> None:
        if not self._definicoes:
            return
        texto = "\n".join(self._definicoes)
        caixa = QMessageBox(self)
        caixa.setWindowTitle("Macros do arquivo importado")
        caixa.setText("Estas definições serão acrescentadas ao fim de Configurações > Preâmbulo e macros:")
        caixa.setDetailedText(texto)
        caixa.setInformativeText(texto[:600] + ("…" if len(texto) > 600 else ""))
        adicionar = caixa.addButton("Adicionar e salvar", QMessageBox.ButtonRole.AcceptRole)
        caixa.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
        if self.ctx.somente_leitura:
            adicionar.setEnabled(False)
        caixa.exec()
        if caixa.clickedButton() is adicionar:
            atual = self.ctx.config.preambulo.rstrip()
            self.ctx.config.preambulo = (atual + "\n\n" if atual else "") + "% importadas\n" + texto + "\n"
            self.ctx.salvar_config()
            self._definicoes = []
            self.faixa_macros.setVisible(False)

    # =========================================================================
    # lista
    # =========================================================================
    def _texto_item(self, i: int, e: Entrada) -> str:
        q = e.questao
        txt = f"{i + 1}. [{ABREV.get(q.tipo, '?')}] {texto_simples(q.enunciado, 90) or '(vazio)'}"
        if e.avisos:
            txt = "⚠ " + txt
        return txt

    def _recarregar_lista(self, selecionar: int | None = None) -> None:
        self._carregando = True
        self.lista.clear()
        for i, e in enumerate(self.entradas):
            it = QListWidgetItem(self._texto_item(i, e))
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked if e.incluir else Qt.CheckState.Unchecked)
            if e.avisos:
                it.setToolTip("\n".join(e.avisos))
            self.lista.addItem(it)
        self._carregando = False
        self.atual = None
        if selecionar is not None and self.entradas:
            self.lista.setCurrentRow(min(selecionar, len(self.entradas) - 1))
        else:
            self._carregar_editor(None)
        self._atualizar_estado()

    def _atualizar_estado(self) -> None:
        n = sum(1 for e in self.entradas if e.incluir)
        self.b_gravar.setText(f"Gravar {n} questão(ões) no banco")
        tem = bool(self.entradas)
        for w in (self.b_gravar, self.b_descartar, self.b_juntar, self.b_dividir, self.b_excluir, self.b_aplicar):
            w.setEnabled(tem)
        self.b_gravar.setEnabled(n > 0 and not self.ctx.somente_leitura)
        self.editor_area.setEnabled(self.atual is not None)

    def _marcacao_mudou(self, it: QListWidgetItem) -> None:
        if self._carregando:
            return
        i = self.lista.row(it)
        self.entradas[i].incluir = it.checkState() == Qt.CheckState.Checked
        self._atualizar_estado()

    def _selecionados(self) -> list[int]:
        return sorted(self.lista.row(it) for it in self.lista.selectedItems())

    def _selecionar(self, linha: int) -> None:
        if self._carregando:
            return
        self._carregar_editor(linha if 0 <= linha < len(self.entradas) else None)

    # =========================================================================
    # edição
    # =========================================================================
    def _carregar_editor(self, i: int | None) -> None:
        self.atual = i
        self._carregando = True
        try:
            if i is None:
                for e in (self.enunciado, self.resposta, self.resolucao):
                    e.clear()
                self.itens.definir_itens([])
                self.l_info.clear()
                self.previa.mostrar_vazio("Selecione uma questão importada para revisar.")
            else:
                q = self.entradas[i].questao
                self.c_tipo.setCurrentIndex(max(0, self.c_tipo.findData(q.tipo)))
                self.enunciado.setPlainText(q.enunciado)
                self.itens.definir_tipo(q.tipo)
                self.itens.definir_itens(q.itens)
                self.resposta.setPlainText(q.resposta_curta)
                self.resolucao.setPlainText(q.resolucao)
                self._mostrar_tipo(q.tipo)
                self._atualizar_info()
        finally:
            self._carregando = False
        self._atualizar_estado()
        if i is not None:
            self._atualizar_previa()

    def _atualizar_info(self) -> None:
        if self.atual is None:
            return
        e = self.entradas[self.atual]
        q = e.questao
        if e.categoria_nova is not None:
            cat = " > ".join(e.categoria_nova.nomes) + " (nova)"
            if e.categoria_nova.pai_id is not None:
                cat = self.ctx.repo.caminhos_categorias().get(e.categoria_nova.pai_id, "") + " > " + cat
        else:
            cat = self.ctx.repo.caminhos_categorias().get(q.categoria_id, "sem categoria") if q.categoria_id else "sem categoria"
        partes = [f"Categoria: {cat}", f"Tags: {', '.join(q.tags) or '—'}", f"Fonte: {q.fonte or '—'}",
                  f"Ano: {q.ano or '—'}", f"Dificuldade: {q.dificuldade}"]
        texto = " · ".join(partes)
        if e.avisos:
            texto += "\n⚠ " + " ".join(e.avisos)
        self.l_info.setText(texto)

    def _mostrar_tipo(self, tipo: str) -> None:
        com_itens = tipo in ("multipla", "vf")
        self.itens.setVisible(com_itens)
        self.l_itens.setVisible(com_itens)
        self.l_itens.setText("Afirmativas" if tipo == "vf" else "Alternativas")
        self.resposta.setVisible(tipo == "curta")
        self.l_resposta.setVisible(tipo == "curta")

    def _tipo_mudou(self) -> None:
        tipo = self.c_tipo.currentData()
        self.itens.definir_tipo(tipo)
        self._mostrar_tipo(tipo)
        if not self._carregando and tipo in ("multipla", "vf") and not self.itens.linhas:
            self.itens.garantir_minimo(4)
        self._editou()

    def _editou(self, *_a) -> None:
        if self._carregando or self.atual is None:
            return
        e = self.entradas[self.atual]
        q = e.questao
        q.tipo = self.c_tipo.currentData()
        q.enunciado = self.enunciado.toPlainText()
        q.itens = self.itens.itens()
        q.resposta_curta = self.resposta.toPlainText()
        q.resolucao = self.resolucao.toPlainText()
        it = self.lista.item(self.atual)
        if it is not None:
            self._carregando = True
            it.setText(self._texto_item(self.atual, e))
            self._carregando = False
        self.timer.start()

    def _atualizar_previa(self) -> None:
        if self.atual is None:
            return
        q = self.entradas[self.atual].questao
        self.previa.mostrar(html_questao(q, resolvedor_imagens(self.ctx.midia)))

    # =========================================================================
    # ajustes das divisões
    # =========================================================================
    def _juntar(self) -> None:
        i = self.atual
        if i is None or i + 1 >= len(self.entradas):
            return
        a, b = self.entradas[i].questao, self.entradas[i + 1].questao
        a.enunciado = (a.enunciado.rstrip() + "\n\n" + b.enunciado.lstrip()).strip()
        if b.itens:
            a.itens = a.itens + b.itens
            if a.tipo == "discursiva":
                a.tipo = b.tipo
        a.resolucao = "\n\n".join(t for t in (a.resolucao.strip(), b.resolucao.strip()) if t)
        a.resposta_curta = a.resposta_curta or b.resposta_curta
        self.entradas[i].avisos += self.entradas[i + 1].avisos
        del self.entradas[i + 1]
        self._recarregar_lista(i)

    def _dividir(self) -> None:
        i = self.atual
        if i is None:
            return
        pos = self.enunciado.textCursor().position()
        texto = self.enunciado.toPlainText()
        antes, depois = texto[:pos].rstrip(), texto[pos:].lstrip()
        if not antes or not depois:
            QMessageBox.information(self, "Dividir", "Ponha o cursor do enunciado no ponto em que a próxima questão começa.")
            return
        atual = self.entradas[i]
        q = atual.questao
        nova = Questao(tipo=q.tipo, enunciado=depois, itens=q.itens, resposta_curta=q.resposta_curta,
                       resolucao=q.resolucao, dificuldade=q.dificuldade, fonte=q.fonte, ano=q.ano,
                       categoria_id=q.categoria_id, tags=list(q.tags))
        q.enunciado = antes
        q.tipo = "discursiva"
        q.itens = []
        q.resposta_curta = ""
        q.resolucao = ""
        self.entradas.insert(i + 1, Entrada(nova, atual.categoria_nova, True, []))
        self._recarregar_lista(i)

    def _excluir(self) -> None:
        sel = self._selecionados()
        if not sel:
            return
        if len(sel) > 1:
            r = QMessageBox.question(self, "Excluir", f"Tirar {len(sel)} questões da importação?")
            if r != QMessageBox.StandardButton.Yes:
                return
        for i in reversed(sel):
            del self.entradas[i]
        self._recarregar_lista(sel[0])

    def _aplicar_lote(self) -> None:
        sel = self._selecionados()
        if not sel:
            QMessageBox.information(self, "Aplicar", "Selecione uma ou mais questões na lista (Ctrl+clique ou Shift+clique).")
            return
        if not any(c.isChecked() for c in (self.ch_cat, self.ch_tags, self.ch_fonte, self.ch_ano, self.ch_dif)):
            QMessageBox.information(self, "Aplicar", "Marque o que deve ser aplicado (categoria, tags, fonte, ano ou dificuldade).")
            return
        novas_tags = separar_tags(self.e_tags.text())
        for i in sel:
            e = self.entradas[i]
            q = e.questao
            if self.ch_cat.isChecked():
                q.categoria_id = self.sel_cat.categoria_id
                e.categoria_nova = self.sel_cat.nova
            if self.ch_tags.isChecked():
                for t in novas_tags:
                    if t.casefold() not in {x.casefold() for x in q.tags}:
                        q.tags.append(t)
            if self.ch_fonte.isChecked():
                q.fonte = self.e_fonte.text().strip()
            if self.ch_ano.isChecked():
                q.ano = self.s_ano.value() or None
            if self.ch_dif.isChecked():
                q.dificuldade = self.c_dif.currentIndex() + 1
        self._atualizar_info()
        self.l_status.setText(f"Aplicado a {len(sel)} questão(ões).")

    def _descartar(self) -> None:
        if self.pode_descartar():
            self.entradas = []
            self._texto_origem = ""
            self.b_reprocessar.setEnabled(False)
            self.faixa_macros.setVisible(False)
            self.l_status.setText("Importação descartada.")
            self._recarregar_lista(None)

    # =========================================================================
    # gravar
    # =========================================================================
    def gravar(self) -> None:
        escolhidas = [e for e in self.entradas if e.incluir]
        if not escolhidas:
            return
        vazias = [i + 1 for i, e in enumerate(self.entradas) if e.incluir and not e.questao.enunciado.strip()]
        if vazias:
            QMessageBox.warning(self, "Gravar", f"Questões com enunciado vazio: {', '.join(map(str, vazias))}. "
                                "Corrija ou desmarque antes de gravar.")
            return
        r = QMessageBox.question(self, "Gravar no banco", f"Gravar {len(escolhidas)} questão(ões) no banco?")
        if r != QMessageBox.StandardButton.Yes:
            return
        lista = []
        for e in escolhidas:
            q = e.questao
            q.itens = [i for i in q.itens if i.texto.strip() or i.comentario.strip() or i.correta]
            lista.append((q, e.categoria_nova))
        try:
            ids = self.ctx.repo.salvar_questoes(lista)
        except Exception as ex:  # noqa: BLE001
            QMessageBox.critical(self, "Gravar", f"Nada foi gravado por causa de um erro:\n{ex}")
            return
        self.ctx.sinais.questoes_alteradas.emit()
        self.ctx.sinais.tags_alteradas.emit()
        self.ctx.sinais.categorias_alteradas.emit()
        self.entradas = [e for e in self.entradas if not e.incluir]
        self._recarregar_lista(0 if self.entradas else None)
        self.l_status.setText(f"{len(ids)} questão(ões) gravada(s) no banco (nº {min(ids)} a {max(ids)}).")
        self.l_status.setStyleSheet("color: #1f7a3a;")
