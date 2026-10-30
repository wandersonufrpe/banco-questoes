"""Importação de provas em PDF com a ajuda do Claude Code.

O Claude Code (skill ``importar-pdf``) usa as ferramentas de ``python -m bancoq.ia``
para ler o PDF e grava um *pacote* com as questões em ``<banco>/entrada/pacotes/``.
O aplicativo mostra cada questão do pacote para o professor aprovar ou rejeitar;
nada entra no banco sem essa aprovação.

Este pacote não usa a interface gráfica nem a internet.
"""
