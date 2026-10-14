"""Tela de cadastro de questões (aba inicial)."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QCompleter, QFormLayout, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QScrollArea, QSizePolicy, QSpinBox, QSplitter,
    QTabWidget, QVBoxLayout, QWidget,
)

from ..contexto import Contexto
from ..nucleo.entidades import TIPOS, Item, Questao
from ..nucleo.previa_html import html_questao
from ..nucleo.macros import extrair_macros
from ..nucleo.repositorio import CategoriaNova
from .categorias import SeletorCategoria
from .editor_latex import EditorLatex
from .itens import EditorItens
from .previa import PreviaWeb, resolvedor_imagens
from .tags import CampoTags

NOMES_DIFICULDADE = ["1 — muito fácil", "2 — fácil", "3 — média", "4 — difícil", "5 — muito difícil"]
ITENS_INICIAIS = {"multipla": 5, "vf": 4}


def titulo_secao(texto: str) -> QLabel:
    rotulo = QLabel(texto)
    f = rotulo.font()
    f.setBold(True)
    rotulo.setFont(f)
    return rotulo


def item_vazio(item: Item) -> bool:
    return not item.texto.strip() and not item.comentario.strip()


class TelaCadastro(QWidget):
    questao_salva = Signal(int)
    estado_mudou = Signal()

    def __init__(self, ctx: Contexto, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.questao_id: int | None = None
        self.questao_carregada: Questao | None = None
        self._base: tuple | None = None
        self._carregando = False
        self._salvando = False

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(6, 6, 6, 6)

        # -- barra de estado da questão ----------------------------------------------
        topo = QHBoxLayout()
        self.l_titulo = QLabel()
        f = self.l_titulo.font()
        f.setPointSize(f.pointSize() + 2)
        f.setBold(True)
        self.l_titulo.setFont(f)
        topo.addWidget(self.l_titulo)
        self.l_datas = QLabel()
        self.l_datas.setStyleSheet("color: gray;")
        topo.addWidget(self.l_datas)
        topo.addStretch(1)
        self.l_modificado = QLabel("● alterações não salvas")
        self.l_modificado.setStyleSheet("color: #c25e00; font-weight: bold;")
        self.l_modificado.setVisible(False)
        topo.addWidget(self.l_modificado)
        raiz.addLayout(topo)

        divisor = QSplitter(Qt.Orientation.Horizontal)
        raiz.addWidget(divisor, 1)

        # -- formulário ---------------------------------------------------------------------
        rolagem = QScrollArea()
        rolagem.setWidgetResizable(True)
        rolagem.setFrameShape(QFrame.Shape.NoFrame)
        form = QWidget()
        rolagem.setWidget(form)
        lf = QVBoxLayout(form)
        lf.setContentsMargins(2, 2, 8, 2)

        grade = QGridLayout()
        grade.setHorizontalSpacing(8)
        self.c_tipo = QComboBox()
        for chave, nome in TIPOS.items():
            self.c_tipo.addItem(nome, chave)
        self.c_dificuldade = QComboBox()
        self.c_dificuldade.addItems(NOMES_DIFICULDADE)
        self.c_dificuldade.setCurrentIndex(2)
        self.s_ano = QSpinBox()
        self.s_ano.setRange(0, 2100)
        self.s_ano.setSpecialValueText("—")
        self.s_ano.setToolTip("Ano (deixe em — se não souber)")
        self.e_fonte = QLineEdit()
        self.e_fonte.setPlaceholderText("ex.: Lista 3, Stewart cap. 5, P1 2023.1")
        self.completar_fonte = QCompleter([], self)
        self.completar_fonte.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completar_fonte.setFilterMode(Qt.MatchFlag.MatchContains)
        self.e_fonte.setCompleter(self.completar_fonte)
        self.categoria = SeletorCategoria(ctx.repo)
        self.tags = CampoTags()
        self.ch_nao_embaralhar = QCheckBox("Não embaralhar alternativas")
        self.ch_nao_embaralhar.setToolTip('Use em casos como "todas as anteriores"')

        grade.addWidget(QLabel("Tipo:"), 0, 0)
        grade.addWidget(self.c_tipo, 0, 1)
        grade.addWidget(QLabel("Dificuldade:"), 0, 2)
        grade.addWidget(self.c_dificuldade, 0, 3)
        grade.addWidget(QLabel("Ano:"), 0, 4)
        grade.addWidget(self.s_ano, 0, 5)
        grade.addWidget(QLabel("Categoria:"), 1, 0)
        grade.addWidget(self.categoria, 1, 1, 1, 5)
        grade.addWidget(QLabel("Tags:"), 2, 0)
        grade.addWidget(self.tags, 2, 1, 1, 5)
        grade.addWidget(QLabel("Fonte:"), 3, 0)
        grade.addWidget(self.e_fonte, 3, 1, 1, 3)
        grade.addWidget(self.ch_nao_embaralhar, 3, 4, 1, 2)
        grade.setColumnStretch(1, 2)
        grade.setColumnStretch(3, 1)
        lf.addLayout(grade)

        # enunciado
        lin = QHBoxLayout()
        lin.addWidget(titulo_secao("Enunciado"))
        lin.addStretch(1)
        self.b_img_enunciado = QPushButton("Inserir imagem…")
        self.b_img_enunciado.setToolTip("Também é possível arrastar um arquivo ou colar (Ctrl+V) uma imagem")
        lin.addWidget(self.b_img_enunciado)
        lf.addLayout(lin)
        self.enunciado = EditorLatex(linhas_min=6, linhas_max=24)
        self.enunciado.setPlaceholderText("Enunciado em LaTeX. Ex.: Calcule $\\int_0^1 x^2\\,dx$.")
        lf.addWidget(self.enunciado)

        # alternativas / afirmativas
        self.l_itens = titulo_secao("Alternativas")
        lf.addWidget(self.l_itens)
        self.itens = EditorItens()
        lf.addWidget(self.itens)

        # resposta curta
        self.l_resposta = titulo_secao("Resposta esperada")
        lf.addWidget(self.l_resposta)
        self.resposta = EditorLatex(linhas_min=1, linhas_max=6)
        self.resposta.setPlaceholderText("Resposta curta esperada (LaTeX)")
        lf.addWidget(self.resposta)

        # resolução
        lin = QHBoxLayout()
        lin.addWidget(titulo_secao("Resolução"))
        lin.addStretch(1)
        self.b_img_resolucao = QPushButton("Inserir imagem…")
        lin.addWidget(self.b_img_resolucao)
        lf.addLayout(lin)
        self.resolucao = EditorLatex(linhas_min=4, linhas_max=24)
        self.resolucao.setPlaceholderText("Resolução em LaTeX (vai para o documento de resoluções, não para a prova)")
        lf.addWidget(self.resolucao)

        lf.addWidget(titulo_secao("Observações (nunca vão para a prova)"))
        self.observacoes = EditorLatex(linhas_min=2, linhas_max=10, aceita_imagens=False, latex=False)
        self.observacoes.setPlaceholderText("Texto livre")
        lf.addWidget(self.observacoes)
        lf.addStretch(1)

        divisor.addWidget(rolagem)

        # -- prévia -------------------------------------------------------------------------------
        self.abas_previa = QTabWidget()
        self.previa = PreviaWeb()
        self.abas_previa.addTab(self.previa, "Prévia rápida")
        divisor.addWidget(self.abas_previa)
        divisor.setStretchFactor(0, 3)
        divisor.setStretchFactor(1, 2)
        divisor.setSizes([700, 500])

        # -- botões ---------------------------------------------------------------------------------
        baixo = QHBoxLayout()
        self.b_limpar = QPushButton("Limpar")
        self.b_limpar.setToolTip("Começa uma questão em branco")
        baixo.addWidget(self.b_limpar)
        baixo.addStretch(1)
        self.l_status = QLabel()
        self.l_status.setStyleSheet("color: #1f7a3a;")
        baixo.addWidget(self.l_status)
        self.b_salvar_nova = QPushButton("Salvar e nova")
        self.b_salvar_nova.setToolTip("Salva e abre uma questão em branco mantendo tipo, categoria, tags, fonte e ano")
        self.b_salvar = QPushButton("Salvar no banco")
        self.b_salvar.setToolTip("Salvar no banco (Ctrl+S)")
        self.b_salvar.setDefault(True)
        f = self.b_salvar.font()
        f.setBold(True)
        self.b_salvar.setFont(f)
        baixo.addWidget(self.b_salvar_nova)
        baixo.addWidget(self.b_salvar)
        raiz.addLayout(baixo)

        # -- ligações -------------------------------------------------------------------------------
        for editor in (self.enunciado, self.resolucao, self.resposta):
            editor.midia = ctx.midia
            editor.erro.connect(self._erro_imagem)
        self.itens.definir_midia(ctx.midia)
        self.itens.erro_imagem.connect(self._erro_imagem)
        self.itens.pasta_imagem_usada.connect(self._lembrar_pasta_imagem)
        self.itens.pasta_inicial = ctx.local.ultima_pasta_imagens

        self.timer_previa = QTimer(self)
        self.timer_previa.setSingleShot(True)
        self.timer_previa.setInterval(500)
        self.timer_previa.timeout.connect(self.atualizar_previa)

        self.c_tipo.currentIndexChanged.connect(self._tipo_mudou)
        for sinal in (
            self.enunciado.textChanged, self.resolucao.textChanged, self.resposta.textChanged,
            self.observacoes.textChanged, self.itens.alterado, self.c_dificuldade.currentIndexChanged,
            self.s_ano.valueChanged, self.e_fonte.textChanged, self.categoria.alterado, self.tags.alterado,
            self.ch_nao_embaralhar.toggled,
        ):
            sinal.connect(self._alterou)

        self.b_img_enunciado.clicked.connect(lambda: self._inserir_imagem(self.enunciado))
        self.b_img_resolucao.clicked.connect(lambda: self._inserir_imagem(self.resolucao))
        self.b_salvar.clicked.connect(lambda: self.salvar(e_nova=False))
        self.b_salvar_nova.clicked.connect(lambda: self.salvar(e_nova=True))
        self.b_limpar.clicked.connect(self._limpar_clicado)
        atalho = QShortcut(QKeySequence.StandardKey.Save, self)
        atalho.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        atalho.activated.connect(lambda: self.salvar(e_nova=False))

        ctx.sinais.config_alterada.connect(self.aplicar_config)
        ctx.sinais.categorias_alteradas.connect(self.categoria.recarregar)
        ctx.sinais.tags_alteradas.connect(self._recarregar_sugestoes)
        ctx.sinais.questoes_alteradas.connect(self._recarregar_sugestoes)

        if ctx.somente_leitura:
            for b in (self.b_salvar, self.b_salvar_nova):
                b.setEnabled(False)
                b.setToolTip("Banco aberto somente para leitura")

        self.aplicar_config()
        self._recarregar_sugestoes()
        self.nova_questao()

    # =========================================================================
    # estado do formulário
    # =========================================================================
    def tipo(self) -> str:
        return self.c_tipo.currentData()

    def questao_do_formulario(self) -> tuple[Questao, CategoriaNova | None]:
        tipo = self.tipo()
        itens = self.itens.itens() if tipo in ("multipla", "vf") else []
        q = Questao(
            id=self.questao_id,
            tipo=tipo,
            enunciado=self.enunciado.toPlainText(),
            itens=itens,
            resposta_curta=self.resposta.toPlainText() if tipo == "curta" else "",
            resolucao=self.resolucao.toPlainText(),
            observacoes=self.observacoes.toPlainText(),
            dificuldade=self.c_dificuldade.currentIndex() + 1,
            fonte=self.e_fonte.text().strip(),
            ano=self.s_ano.value() or None,
            categoria_id=self.categoria.categoria_id,
            tags=self.tags.tags(),
            nao_embaralhar=self.ch_nao_embaralhar.isChecked() and tipo in ("multipla", "vf"),
        )
        if self.questao_carregada is not None:
            q.criada_em = self.questao_carregada.criada_em
            q.alterada_em = self.questao_carregada.alterada_em
        return q, self.categoria.nova

    def _estado(self) -> tuple:
        q, _ = self.questao_do_formulario()
        return (
            q.tipo, q.enunciado, tuple((i.texto, i.correta, i.comentario) for i in q.itens),
            q.resposta_curta, q.resolucao, q.observacoes, q.dificuldade, q.fonte, q.ano,
            self.categoria.estado(), tuple(q.tags), q.nao_embaralhar,
        )

    def modificado(self) -> bool:
        return self._base is not None and self._estado() != self._base

    def _marcar_base(self) -> None:
        self._base = self._estado()
        self._atualizar_cabecalho()

    def _alterou(self, *_args) -> None:
        if self._carregando:
            return
        self.timer_previa.start()
        self.l_modificado.setVisible(self.modificado())
        self.l_status.clear()
        self.estado_mudou.emit()

    def _atualizar_cabecalho(self) -> None:
        if self.questao_id is None:
            self.l_titulo.setText("Nova questão")
            self.l_datas.clear()
        else:
            self.l_titulo.setText(f"Questão nº {self.questao_id}")
            q = self.questao_carregada
            if q is not None:
                self.l_datas.setText(f"criada em {q.criada_em} · alterada em {q.alterada_em}")
        self.l_modificado.setVisible(self.modificado())
        self.estado_mudou.emit()

    def _tipo_mudou(self) -> None:
        tipo = self.tipo()
        self.itens.definir_tipo(tipo)
        com_itens = tipo in ("multipla", "vf")
        self.itens.setVisible(com_itens)
        self.l_itens.setVisible(com_itens)
        self.l_itens.setText("Afirmativas" if tipo == "vf" else "Alternativas")
        self.ch_nao_embaralhar.setVisible(com_itens)
        self.ch_nao_embaralhar.setText("Não embaralhar afirmativas" if tipo == "vf" else "Não embaralhar alternativas")
        self.resposta.setVisible(tipo == "curta")
        self.l_resposta.setVisible(tipo == "curta")
        if com_itens and not self._carregando:
            self.itens.garantir_minimo(ITENS_INICIAIS[tipo])
        self._alterou()

    # =========================================================================
    # carregar / limpar
    # =========================================================================
    def _preencher(self, q: Questao, categoria_nova: CategoriaNova | None = None) -> None:
        self._carregando = True
        try:
            self.c_tipo.setCurrentIndex(max(0, self.c_tipo.findData(q.tipo)))
            self.enunciado.setPlainText(q.enunciado)
            itens = list(q.itens)
            if q.tipo in ITENS_INICIAIS and not itens:
                itens = [Item() for _ in range(ITENS_INICIAIS[q.tipo])]
            self.itens.definir_tipo(q.tipo)
            self.itens.definir_itens(itens)
            self.resposta.setPlainText(q.resposta_curta)
            self.resolucao.setPlainText(q.resolucao)
            self.observacoes.setPlainText(q.observacoes)
            self.c_dificuldade.setCurrentIndex(min(4, max(0, q.dificuldade - 1)))
            self.s_ano.setValue(q.ano or 0)
            self.e_fonte.setText(q.fonte)
            self.categoria.definir(q.categoria_id, categoria_nova)
            self.tags.definir_tags(q.tags)
            self.ch_nao_embaralhar.setChecked(q.nao_embaralhar)
        finally:
            self._carregando = False
        self._tipo_mudou_sem_alterar()
        self._marcar_base()
        self.atualizar_previa()

    def _tipo_mudou_sem_alterar(self) -> None:
        self._carregando = True
        try:
            self._tipo_mudou()
        finally:
            self._carregando = False

    def nova_questao(self, manter_de: Questao | None = None, categoria_nova: CategoriaNova | None = None) -> None:
        q = Questao()
        if manter_de is not None:
            q.tipo = manter_de.tipo
            q.categoria_id = manter_de.categoria_id
            q.tags = list(manter_de.tags)
            q.fonte = manter_de.fonte
            q.ano = manter_de.ano
        self.questao_id = None
        self.questao_carregada = None
        self._preencher(q, categoria_nova)
        self.enunciado.setFocus()

    def carregar_questao(self, q: Questao, como_nova: bool = False) -> None:
        """Mostra a questão para edição (ou uma cópia não salva, se ``como_nova``)."""
        if como_nova:
            q = q.copia()
            q.id = None
            for item in q.itens:
                item.id = None
            self.questao_id = None
            self.questao_carregada = None
            self._preencher(q)
            # a cópia ainda não existe no banco: começa como "não salva"
            self._base = ()
            self._atualizar_cabecalho()
            self.l_titulo.setText("Nova questão (cópia)")
        else:
            self.questao_id = q.id
            self.questao_carregada = q
            self._preencher(q)

    def questoes_excluidas(self, ids: list[int]) -> None:
        """Se a questão em edição foi excluída, o conteúdo fica como questão nova."""
        if self.questao_id is not None and self.questao_id in ids:
            self.questao_id = None
            self.questao_carregada = None
            self._base = ()
            self._atualizar_cabecalho()
            self.l_titulo.setText("Nova questão (a original foi excluída do banco)")

    def pode_descartar(self) -> bool:
        """Pergunta o que fazer se houver alterações não salvas. True = pode seguir."""
        if not self.modificado():
            return True
        r = QMessageBox.question(
            self, "Alterações não salvas",
            "A questão em edição tem alterações não salvas.\nDeseja descartá-las?",
            QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        return r == QMessageBox.StandardButton.Discard

    def _limpar_clicado(self) -> None:
        if self.pode_descartar():
            self.nova_questao()

    # =========================================================================
    # prévia
    # =========================================================================
    def aplicar_config(self) -> None:
        self.previa.definir_macros(extrair_macros(self.ctx.config.preambulo))

    def atualizar_previa(self) -> None:
        q, _ = self.questao_do_formulario()
        if not q.enunciado.strip() and not any(i.texto.strip() for i in q.itens) and not q.resolucao.strip():
            self.previa.mostrar_vazio("A prévia aparece aqui enquanto você digita.")
            return
        self.previa.mostrar(html_questao(q, resolvedor_imagens(self.ctx.midia)))

    def _recarregar_sugestoes(self) -> None:
        self.tags.definir_sugestoes(self.ctx.repo.nomes_tags())
        self.completar_fonte.setModel(None)
        from PySide6.QtCore import QStringListModel

        self.completar_fonte.setModel(QStringListModel(self.ctx.repo.fontes(), self.completar_fonte))

    # =========================================================================
    # imagens
    # =========================================================================
    def _inserir_imagem(self, editor: EditorLatex) -> None:
        pasta = editor.inserir_imagem_de_arquivo(self.ctx.local.ultima_pasta_imagens)
        if pasta:
            self._lembrar_pasta_imagem(pasta)

    def _lembrar_pasta_imagem(self, pasta: str) -> None:
        self.ctx.local.ultima_pasta_imagens = pasta
        self.itens.pasta_inicial = pasta
        self.ctx.salvar_local()

    def _erro_imagem(self, mensagem: str) -> None:
        QMessageBox.warning(self, "Imagem", mensagem)

    # =========================================================================
    # salvar
    # =========================================================================
    def _validar(self, q: Questao) -> bool:
        if not q.enunciado.strip():
            QMessageBox.warning(self, "Salvar", "O enunciado está vazio.")
            self.enunciado.setFocus()
            return False
        avisos = []
        if q.tipo == "multipla":
            if len(q.itens) < 2:
                avisos.append("A questão tem menos de duas alternativas.")
            corretas = sum(1 for i in q.itens if i.correta)
            if corretas == 0:
                avisos.append("Nenhuma alternativa está marcada como correta.")
            elif corretas > 1:
                avisos.append(f"Há {corretas} alternativas marcadas como corretas.")
        elif q.tipo == "vf" and not q.itens:
            avisos.append("A questão não tem afirmativas.")
        elif q.tipo == "curta" and not q.resposta_curta.strip():
            avisos.append("A resposta esperada está vazia.")
        if avisos:
            caixa = QMessageBox(self)
            caixa.setWindowTitle("Salvar")
            caixa.setIcon(QMessageBox.Icon.Warning)
            caixa.setText("\n".join(avisos))
            salvar = caixa.addButton("Salvar mesmo assim", QMessageBox.ButtonRole.AcceptRole)
            caixa.addButton("Voltar e corrigir", QMessageBox.ButtonRole.RejectRole)
            caixa.exec()
            return caixa.clickedButton() is salvar
        return True

    def salvar(self, e_nova: bool = False) -> None:
        if self._salvando:
            return
        if self.ctx.somente_leitura:
            QMessageBox.information(self, "Salvar", "O banco está aberto somente para leitura.")
            return
        q, categoria_nova = self.questao_do_formulario()
        q.itens = [i for i in q.itens if not item_vazio(i) or i.correta]
        if not self._validar(q):
            return
        self._salvando = True
        self._etapa_latex(q, categoria_nova, e_nova)

    def _etapa_latex(self, q: Questao, categoria_nova, e_nova: bool) -> None:
        self._etapa_duplicadas(q, categoria_nova, e_nova)

    def _etapa_duplicadas(self, q: Questao, categoria_nova, e_nova: bool) -> None:
        self._gravar(q, categoria_nova, e_nova)

    def _cancelar_salvamento(self) -> None:
        self._salvando = False

    def _gravar(self, q: Questao, categoria_nova, e_nova: bool) -> None:
        try:
            qid = self.ctx.repo.salvar_questao(q, categoria_nova)
        except Exception as e:  # noqa: BLE001 - mostrar qualquer falha ao usuário
            self._salvando = False
            QMessageBox.critical(self, "Erro ao salvar", f"A questão não foi salva.\n\n{e}")
            return
        self._salvando = False
        if categoria_nova is not None:
            self.ctx.sinais.categorias_alteradas.emit()
        self.ctx.sinais.questoes_alteradas.emit()
        self.ctx.sinais.tags_alteradas.emit()
        self.questao_salva.emit(qid)
        salva = self.ctx.repo.obter_questao(qid)
        if e_nova:
            self.nova_questao(manter_de=salva)
            self.l_status.setText(f"Questão nº {qid} salva. Nova questão em branco.")
        else:
            self.carregar_questao(salva)
            self.l_status.setText(f"Questão nº {qid} salva.")
