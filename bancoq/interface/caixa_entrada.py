"""Caixa de entrada: questões preparadas pelo Claude, aprovadas ou rejeitadas uma a uma.

Os pacotes ficam em ``<banco>/entrada/pacotes/``. Esta tela só lê o pacote e grava
as decisões em ``decisoes.json``; a questão aprovada passa pelo mesmo caminho do
cadastro (checagem do LaTeX e de duplicadas) antes de entrar no banco.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QPixmap
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QInputDialog, QLabel, QListWidget, QListWidgetItem, QMessageBox,
    QPushButton, QScrollArea, QSplitter, QStackedWidget, QTextBrowser, QVBoxLayout, QWidget,
)

from ..contexto import Contexto
from ..ia.pacote import (
    APROVADA,
    REJEITADA,
    SITUACAO_PRONTO,
    ErroPacote,
    Pacote,
    QuestaoPacote,
    faltando_no_preambulo,
    listar_pacotes,
    pasta_pacotes,
    resolver_categoria,
    validar_questao,
)
from ..ia.relatorio import precisa_atencao, relatorio_html
from ..nucleo.duplicadas import procurar_parecidas
from ..nucleo.latex_html import texto_simples
from ..nucleo.modelos_prova import posicao_begin_document
from .cadastro import TelaCadastro

COR_APROVADA = QColor("#1f7a3a")
COR_REJEITADA = QColor("#888888")
COR_ATENCAO = QColor("#a34a00")


class VisorImagem(QWidget):
    """Recorte original da questão, ajustado à largura ou com zoom."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        barra = QHBoxLayout()
        titulo = QLabel("<b>Original (PDF)</b>")
        barra.addWidget(titulo)
        barra.addStretch(1)
        self.b_menos = QPushButton("−")
        self.b_ajustar = QPushButton("Ajustar")
        self.b_mais = QPushButton("+")
        for b in (self.b_menos, self.b_ajustar, self.b_mais):
            b.setFlat(True)
            barra.addWidget(b)
        lay.addLayout(barra)
        self.rolagem = QScrollArea()
        self.rolagem.setWidgetResizable(False)
        self.rolagem.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.imagem = QLabel()
        self.imagem.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.imagem.setWordWrap(True)
        self.rolagem.setWidget(self.imagem)
        lay.addWidget(self.rolagem, 1)
        self._pix: QPixmap | None = None
        self._zoom: float | None = None          # None = ajustar à largura
        self.b_menos.clicked.connect(lambda: self._mudar_zoom(1 / 1.25))
        self.b_mais.clicked.connect(lambda: self._mudar_zoom(1.25))
        self.b_ajustar.clicked.connect(self._ajustar)

    def mostrar(self, caminho: Path | None, mensagem: str = "Sem recorte do PDF.") -> None:
        self._pix = QPixmap(str(caminho)) if caminho is not None else None
        if self._pix is not None and self._pix.isNull():
            self._pix = None
        self._mensagem = mensagem
        self._desenhar()

    def _escala_ajustada(self) -> float:
        largura = max(100, self.rolagem.viewport().width() - 4)
        return largura / self._pix.width()

    def _mudar_zoom(self, fator: float) -> None:
        if self._pix is None:
            return
        atual = self._zoom if self._zoom is not None else self._escala_ajustada()
        self._zoom = min(4.0, max(0.2, atual * fator))
        self._desenhar()

    def _ajustar(self) -> None:
        self._zoom = None
        self._desenhar()

    def _desenhar(self) -> None:
        if self._pix is None:
            self.imagem.setPixmap(QPixmap())
            self.imagem.setText(getattr(self, "_mensagem", ""))
            self.imagem.resize(self.rolagem.viewport().size())
            return
        escala = self._zoom if self._zoom is not None else self._escala_ajustada()
        pix = self._pix.scaledToWidth(max(50, int(self._pix.width() * escala)),
                                      Qt.TransformationMode.SmoothTransformation)
        self.imagem.setPixmap(pix)
        self.imagem.resize(pix.size())

    def resizeEvent(self, ev) -> None:  # noqa: N802
        super().resizeEvent(ev)
        if self._zoom is None:
            self._desenhar()


class TelaCaixaEntrada(QWidget):
    pendentes_mudou = Signal(int)
    mensagem = Signal(str)

    def __init__(self, ctx: Contexto, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.pacote: Pacote | None = None
        self.ident: str | None = None
        self._questoes: dict[str, QuestaoPacote] = {}
        self._mtime_atual: int | None = None
        self._assinatura: tuple | None = None
        self._linha_atual = -1

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(6, 6, 6, 6)
        topo = QHBoxLayout()
        topo.addWidget(QLabel("Pacote:"))
        self.c_pacote = QComboBox()
        self.c_pacote.setMinimumWidth(380)
        topo.addWidget(self.c_pacote)
        self.b_atualizar = QPushButton("Atualizar")
        self.b_atualizar.setToolTip("Procura questões novas (a lista também se atualiza sozinha)")
        topo.addWidget(self.b_atualizar)
        self.l_situacao = QLabel()
        self.l_situacao.setStyleSheet("color: gray;")
        topo.addWidget(self.l_situacao)
        topo.addStretch(1)
        self.b_arquivar = QPushButton("Arquivar pacote…")
        self.b_arquivar.setToolTip("Tira o pacote da caixa de entrada (vai para entrada/concluidos)")
        topo.addWidget(self.b_arquivar)
        raiz.addLayout(topo)

        self.pilha = QStackedWidget()
        raiz.addWidget(self.pilha, 1)
        self.l_vazia = QLabel()
        self.l_vazia.setWordWrap(True)
        self.l_vazia.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.l_vazia.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.pilha.addWidget(self.l_vazia)

        divisor = QSplitter(Qt.Orientation.Horizontal)
        esquerda = QSplitter(Qt.Orientation.Vertical)
        painel_lista = QWidget()
        ll = QVBoxLayout(painel_lista)
        ll.setContentsMargins(0, 0, 0, 0)
        self.lista = QListWidget()
        ll.addWidget(self.lista, 1)
        linha = QHBoxLayout()
        self.l_contagem = QLabel()
        self.l_contagem.setStyleSheet("color: gray;")
        linha.addWidget(self.l_contagem)
        linha.addStretch(1)
        self.b_desfazer = QPushButton("Voltar para pendente")
        self.b_desfazer.setToolTip("Desfaz a rejeição desta questão")
        linha.addWidget(self.b_desfazer)
        ll.addLayout(linha)
        esquerda.addWidget(painel_lista)
        self.visor = VisorImagem()
        esquerda.addWidget(self.visor)
        esquerda.setSizes([220, 600])
        divisor.addWidget(esquerda)
        self.cadastro = TelaCadastro(ctx, modo_aprovacao=True)
        divisor.addWidget(self.cadastro)
        divisor.setStretchFactor(0, 2)
        divisor.setStretchFactor(1, 5)
        divisor.setSizes([380, 980])
        self.pilha.addWidget(divisor)

        self.conferencia = QTextBrowser()
        self.conferencia.setOpenLinks(False)
        self.cadastro.abas_previa.addTab(self.conferencia, "Conferência")

        self.c_pacote.currentIndexChanged.connect(self._pacote_escolhido)
        self.lista.currentRowChanged.connect(self._linha_escolhida)
        self.b_atualizar.clicked.connect(self._atualizar_clicado)
        self.b_arquivar.clicked.connect(self._arquivar)
        self.b_desfazer.clicked.connect(self._desfazer)
        self.cadastro.antes_de_salvar = self._antes_de_aprovar
        self.cadastro.questao_salva.connect(self._aprovada)
        self.cadastro.rejeitar_pedido.connect(self._rejeitar)
        ctx.sinais.config_alterada.connect(self._mostrar_conferencia)

        self.timer = QTimer(self)
        self.timer.setInterval(4000)
        self.timer.timeout.connect(self._verificar_mudancas)
        self.timer.start()
        if ctx.somente_leitura:
            self.b_arquivar.setEnabled(False)
            self.b_desfazer.setEnabled(False)
        self.recarregar(forcar=True)

    # =========================================================================
    # pacotes
    # =========================================================================
    def _pacotes(self) -> list[Pacote]:
        return listar_pacotes(self.ctx.banco.pasta)

    def total_pendentes(self) -> int:
        return sum(len(p.pendentes()) for p in self._pacotes())

    def _assinatura_disco(self) -> tuple:
        """Nomes e datas dos arquivos que importam (para perceber o que o Claude entregou)."""
        base = pasta_pacotes(self.ctx.banco.pasta)
        itens = []
        if base.is_dir():
            for pasta in sorted(base.iterdir()):
                for arq in (pasta / "pacote.json", pasta / "decisoes.json"):
                    if arq.exists():
                        itens.append((str(arq), arq.stat().st_mtime_ns))
                qs = pasta / "questoes"
                if qs.is_dir():
                    for arq in sorted(qs.glob("*.txt")):
                        itens.append((str(arq), arq.stat().st_mtime_ns))
        return tuple(itens)

    def _verificar_mudancas(self) -> None:
        if not self.isVisible():
            return
        try:
            assinatura = self._assinatura_disco()
        except OSError:
            return
        if assinatura != self._assinatura:
            self.recarregar()

    def recarregar(self, forcar: bool = False) -> None:
        """Relê os pacotes mantendo o pacote e a questão escolhidos."""
        try:
            self._assinatura = self._assinatura_disco()
        except OSError:
            self._assinatura = None
        pacotes = self._pacotes()
        atual = self.pacote.pasta if self.pacote is not None else None
        self.c_pacote.blockSignals(True)
        self.c_pacote.clear()
        escolher = 0
        for k, pac in enumerate(pacotes):
            pend = len(pac.pendentes())
            texto = f"{pac.titulo or pac.nome} — {pend} pendente(s) de {len(pac.ids())}"
            if pac.situacao != SITUACAO_PRONTO:
                texto += " (em preparação)"
            self.c_pacote.addItem(texto, str(pac.pasta))
            if atual is not None and pac.pasta == atual:
                escolher = k
            elif atual is None and pend and not len(pacotes[escolher].pendentes()):
                escolher = k
        self.c_pacote.blockSignals(False)
        self.pendentes_mudou.emit(sum(len(p.pendentes()) for p in pacotes))
        if not pacotes:
            self.pacote = None
            self.ident = None
            self._mostrar_vazia()
            return
        self.pilha.setCurrentIndex(1)
        self.c_pacote.setCurrentIndex(escolher)
        mesmo = atual is not None and pacotes[escolher].pasta == atual
        self._carregar_pacote(pacotes[escolher].pasta, manter=mesmo, forcar=forcar)

    def _atualizar_clicado(self) -> None:
        if self.cadastro.pode_descartar():
            self.recarregar(forcar=True)

    def _mostrar_vazia(self) -> None:
        pasta = pasta_pacotes(self.ctx.banco.pasta)
        self.l_vazia.setText(
            "<h3>A caixa de entrada está vazia</h3>"
            "<p>Aqui aparecem as questões que o Claude preparou a partir de provas em PDF, "
            "para você aprovar ou rejeitar uma a uma.</p>"
            "<p>Para importar uma prova, abra o Claude Code na pasta do repositório "
            "<i>banco-questoes</i> e peça:<br><code>/importar-pdf caminho/da/prova.pdf</code></p>"
            "<p>Veja a seção “Importação de provas em PDF” do README.</p>"
            f"<p style='color:gray'>Pasta da caixa de entrada: {pasta}</p>")
        self.pilha.setCurrentIndex(0)
        self.l_situacao.clear()
        self.b_arquivar.setEnabled(False)

    def _pacote_escolhido(self, indice: int) -> None:
        pasta = self.c_pacote.itemData(indice)
        if pasta is None:
            return
        if self.pacote is not None and Path(pasta) == self.pacote.pasta:
            return
        if not self.cadastro.pode_descartar():
            self.c_pacote.blockSignals(True)
            self.c_pacote.setCurrentIndex(self.c_pacote.findData(str(self.pacote.pasta)))
            self.c_pacote.blockSignals(False)
            return
        self._carregar_pacote(Path(pasta), manter=False, forcar=True)

    def _carregar_pacote(self, pasta: Path, manter: bool, forcar: bool) -> None:
        try:
            self.pacote = Pacote.abrir(pasta)
        except ErroPacote as e:
            self.mensagem.emit(str(e))
            return
        decisoes = self.pacote.decisoes()
        self._questoes = {i: self.pacote.questao(i) for i in self.pacote.ids()}
        self.lista.blockSignals(True)
        self.lista.clear()
        for ident, qp in self._questoes.items():
            it = QListWidgetItem()
            self._formatar_item(it, qp, decisoes.get(ident))
            self.lista.addItem(it)
        ids = list(self._questoes)
        alvo = self.ident if manter and self.ident in self._questoes else None
        if alvo is None:
            pend = [i for i in ids if i not in decisoes]
            alvo = pend[0] if pend else (ids[0] if ids else None)
        linha = ids.index(alvo) if alvo is not None else -1
        self.lista.setCurrentRow(linha)
        self.lista.blockSignals(False)
        self._linha_atual = linha
        self._atualizar_situacao(decisoes)
        if alvo is None:
            self.ident = None
            self.visor.mostrar(None, "O Claude ainda não entregou nenhuma questão deste pacote.")
            self.conferencia.clear()
            self.cadastro.nova_questao()
            self.cadastro.definir_acoes(False, "Nenhuma questão entregue ainda.")
            return
        mtime = self._mtime(alvo)
        mudou = alvo != self.ident or mtime != self._mtime_atual
        if forcar or (mudou and not self.cadastro.modificado()):
            self._abrir_questao(alvo)
        else:
            self._mostrar_conferencia()
            self._atualizar_acoes()

    def _mtime(self, ident: str) -> int | None:
        try:
            return self.pacote.arquivo_questao(ident).stat().st_mtime_ns
        except OSError:
            return None

    def _formatar_item(self, it: QListWidgetItem, qp: QuestaoPacote, decisao) -> None:
        problemas = validar_questao(qp, self.pacote)
        motivos = precisa_atencao(qp, problemas)
        rotulo = f"Questão {qp.numero}" if qp.numero else qp.ident
        resumo = texto_simples(qp.enunciado, 60)
        if decisao is None:
            simbolo = "●"
        elif decisao.situacao == APROVADA:
            simbolo = "✔"
            it.setForeground(QBrush(COR_APROVADA))
        else:
            simbolo = "✖"
            it.setForeground(QBrush(COR_REJEITADA))
        texto = f"{simbolo} {rotulo}{' ⚠' if motivos and decisao is None else ''} — {resumo}"
        it.setText(texto)
        dica = [f"{rotulo} ({qp.ident})"]
        if decisao is not None:
            dica.append(f"{decisao.situacao} em {decisao.em}")
        if motivos:
            dica.append("Atenção: " + ", ".join(motivos))
            if decisao is None:
                it.setForeground(QBrush(COR_ATENCAO))
        it.setToolTip("\n".join(dica))
        it.setData(Qt.ItemDataRole.UserRole, qp.ident)

    def _atualizar_situacao(self, decisoes) -> None:
        total = len(self._questoes)
        aprov = sum(1 for d in decisoes.values() if d.situacao == APROVADA)
        rej = sum(1 for d in decisoes.values() if d.situacao == REJEITADA)
        pend = total - aprov - rej
        previstas = self.pacote.previstas
        if self.pacote.situacao == SITUACAO_PRONTO:
            situacao = "pronto para revisão"
        else:
            situacao = "o Claude ainda está preparando"
            if previstas:
                situacao += f" ({total} de {previstas} entregues)"
        self.l_situacao.setText(situacao)
        self.l_contagem.setText(f"{pend} pendente(s) · {aprov} aprovada(s) · {rej} rejeitada(s)")
        self.b_arquivar.setEnabled(not self.ctx.somente_leitura)

    # =========================================================================
    # questão
    # =========================================================================
    def _linha_escolhida(self, linha: int) -> None:
        if linha < 0 or linha == self._linha_atual:
            return
        if not self.cadastro.pode_descartar():
            self.lista.blockSignals(True)
            self.lista.setCurrentRow(self._linha_atual)
            self.lista.blockSignals(False)
            return
        self._linha_atual = linha
        ident = self.lista.item(linha).data(Qt.ItemDataRole.UserRole)
        self._abrir_questao(ident)

    def _abrir_questao(self, ident: str) -> None:
        self.ident = ident
        self._mtime_atual = self._mtime(ident)
        qp = self.pacote.questao(ident)
        self._questoes[ident] = qp
        q = qp.para_questao()
        q.categoria_id, nova = resolver_categoria(self.ctx.repo, qp.categoria)
        titulo = f"Questão {qp.numero}" if qp.numero else ident
        self.cadastro.carregar_para_aprovacao(q, nova, f"{titulo} — {self.pacote.titulo}", qp.preambulo)
        self.visor.mostrar(self.pacote.recorte(ident))
        self._mostrar_conferencia()
        self._atualizar_acoes()

    def _atualizar_acoes(self) -> None:
        if self.ident is None or self.pacote is None:
            return
        d = self.pacote.decisoes().get(self.ident)
        if d is None:
            self.cadastro.definir_acoes(True)
            self.b_desfazer.setEnabled(False)
        elif d.situacao == APROVADA:
            self.cadastro.definir_acoes(False, f"Aprovada: questão nº {d.questao_id} no banco." if d.questao_id
                                        else "Aprovada.")
            self.b_desfazer.setEnabled(False)
        else:
            self.cadastro.definir_acoes(False, "Rejeitada." + (f" Motivo: {d.motivo}" if d.motivo else ""))
            self.b_desfazer.setEnabled(not self.ctx.somente_leitura)

    def _preambulo_atual(self) -> str:
        modelo = self.ctx.texto_modelo()
        i = posicao_begin_document(modelo)
        return self.ctx.config.preambulo + "\n" + (modelo[:i] if i >= 0 else modelo)

    def _mostrar_conferencia(self) -> None:
        if self.ident is None or self.pacote is None or self.ident not in self._questoes:
            self.conferencia.clear()
            return
        qp = self._questoes[self.ident]
        problemas = validar_questao(qp, self.pacote)
        cid, nova = resolver_categoria(self.ctx.repo, qp.categoria)
        existentes = {t.lower() for t in self.ctx.repo.nomes_tags()}
        parecidas = procurar_parecidas(qp.enunciado, self.ctx.repo.enunciados(),
                                       self.ctx.config.limite_duplicadas)
        largura = max(180, (self.conferencia.viewport().width() - 60) // 2)
        self.conferencia.setHtml(relatorio_html(
            qp, self.pacote, problemas,
            decisao=self.pacote.decisoes().get(self.ident),
            categoria=" > ".join(qp.categoria), categoria_nova=nova is not None,
            tags_novas=[t for t in qp.tags if t.lower() not in existentes],
            preambulo_faltando=faltando_no_preambulo(qp.preambulo, self._preambulo_atual()),
            parecidas=parecidas, largura_imagem=min(largura, 320)))
        atencao = precisa_atencao(qp, problemas) or parecidas
        indice = self.cadastro.abas_previa.indexOf(self.conferencia)
        self.cadastro.abas_previa.setTabText(indice, "Conferência ⚠" if atencao else "Conferência")

    # =========================================================================
    # decisões
    # =========================================================================
    def _antes_de_aprovar(self) -> bool:
        if self.ident is None or self.pacote is None:
            return False
        if self.pacote.decisoes().get(self.ident) is not None:
            return False
        qp = self._questoes.get(self.ident)
        faltando = faltando_no_preambulo(qp.preambulo if qp else [], self._preambulo_atual())
        if not faltando:
            return True
        caixa = QMessageBox(self)
        caixa.setWindowTitle("Preâmbulo do banco")
        caixa.setIcon(QMessageBox.Icon.Question)
        caixa.setText("Esta questão precisa destas linhas no preâmbulo do banco "
                      "(Configurações > Preâmbulo e macros):\n\n" + "\n".join(faltando)
                      + "\n\nAcrescentar agora?")
        acrescentar = caixa.addButton("Acrescentar e continuar", QMessageBox.ButtonRole.AcceptRole)
        sem = caixa.addButton("Continuar sem acrescentar", QMessageBox.ButtonRole.DestructiveRole)
        caixa.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
        caixa.exec()
        if caixa.clickedButton() is acrescentar:
            atual = self.ctx.config.preambulo.rstrip()
            self.ctx.config.preambulo = (atual + "\n" if atual else "") + "\n".join(faltando) + "\n"
            self.ctx.salvar_config()
            return True
        return caixa.clickedButton() is sem

    def _aprovada(self, qid: int) -> None:
        if self.ident is None or self.pacote is None:
            return
        self.pacote.registrar_decisao(self.ident, APROVADA, questao_id=qid)
        self.mensagem.emit(f"Questão aprovada: nº {qid} no banco.")
        self._depois_de_decidir()

    def _rejeitar(self) -> None:
        if self.ident is None or self.pacote is None or self.ctx.somente_leitura:
            return
        motivo, ok = QInputDialog.getText(self, "Rejeitar questão",
                                          "Motivo (opcional; fica registrado no pacote):")
        if not ok:
            return
        self.pacote.registrar_decisao(self.ident, REJEITADA, motivo=motivo.strip())
        self.cadastro.esquecer_alteracoes()
        self.mensagem.emit("Questão rejeitada.")
        self._depois_de_decidir()

    def _depois_de_decidir(self) -> None:
        decisoes = self.pacote.decisoes()
        ids = list(self._questoes)
        atual = ids.index(self.ident) if self.ident in ids else -1
        it = self.lista.item(atual)
        if it is not None:
            self._formatar_item(it, self._questoes[self.ident], decisoes.get(self.ident))
        self._atualizar_situacao(decisoes)
        self._assinatura = self._assinatura_disco()
        self.pendentes_mudou.emit(self.total_pendentes())
        pend = [i for i in ids[atual + 1:] + ids[:atual] if i not in decisoes]
        if pend:
            linha = ids.index(pend[0])
            self.lista.blockSignals(True)
            self.lista.setCurrentRow(linha)
            self.lista.blockSignals(False)
            self._linha_atual = linha
            self._abrir_questao(pend[0])
            return
        self._abrir_questao(self.ident)
        if self.pacote.situacao == SITUACAO_PRONTO:
            r = QMessageBox.question(
                self, "Pacote concluído",
                f"Todas as questões de “{self.pacote.titulo}” foram decididas.\n"
                "Arquivar o pacote (sai da caixa de entrada e vai para entrada/concluidos)?")
            if r == QMessageBox.StandardButton.Yes:
                self._arquivar(perguntar=False)

    def _desfazer(self) -> None:
        if self.ident is None or self.pacote is None:
            return
        d = self.pacote.decisoes().get(self.ident)
        if d is None or d.situacao != REJEITADA:
            return
        self.pacote.desfazer_decisao(self.ident)
        self._depois_de_desfazer()

    def _depois_de_desfazer(self) -> None:
        decisoes = self.pacote.decisoes()
        it = self.lista.currentItem()
        if it is not None:
            self._formatar_item(it, self._questoes[self.ident], decisoes.get(self.ident))
        self._atualizar_situacao(decisoes)
        self._assinatura = self._assinatura_disco()
        self.pendentes_mudou.emit(self.total_pendentes())
        self._abrir_questao(self.ident)

    def _arquivar(self, perguntar: bool = True) -> None:
        if self.pacote is None or self.ctx.somente_leitura:
            return
        if perguntar:
            pend = len(self.pacote.pendentes())
            texto = f"Arquivar “{self.pacote.titulo}”? Ele sai da caixa de entrada e vai para entrada/concluidos."
            if pend:
                texto += f"\n\nAinda há {pend} questão(ões) pendente(s); elas não entram no banco."
            if self.pacote.situacao != SITUACAO_PRONTO:
                texto += "\n\nO Claude ainda não marcou este pacote como pronto."
            r = QMessageBox.question(self, "Arquivar pacote", texto)
            if r != QMessageBox.StandardButton.Yes:
                return
            if not self.cadastro.pode_descartar():
                return
        self.cadastro.esquecer_alteracoes()
        try:
            destino = self.pacote.mover_para_concluidos(self.ctx.banco.pasta)
        except OSError as e:
            QMessageBox.warning(self, "Arquivar pacote", f"Não foi possível mover o pacote:\n{e}")
            return
        self.mensagem.emit(f"Pacote arquivado em {destino}.")
        self.pacote = None
        self.ident = None
        self.recarregar(forcar=True)

    # =========================================================================
    def pode_descartar(self) -> bool:
        return self.cadastro.pode_descartar()

    def showEvent(self, ev) -> None:  # noqa: N802
        super().showEvent(ev)
        self._verificar_mudancas()
