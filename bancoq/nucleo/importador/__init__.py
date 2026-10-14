"""Importação de provas antigas em LaTeX.

Os padrões ficam em módulos separados e se registram com ``@registrar``
(veja ``base.py``). Para acrescentar um padrão novo, crie o módulo e importe-o
abaixo.
"""

from . import enumerate as _enumerate  # noqa: F401
from . import exam as _exam  # noqa: F401
from . import manual as _manual  # noqa: F401
from . import titulos as _titulos  # noqa: F401
from .base import (  # noqa: F401
    PadraoImportacao, QuestaoImportada, ResultadoImportacao, definicoes_do_preambulo, importar,
    padrao_por_nome, padroes,
)

padroes_disponiveis = padroes
