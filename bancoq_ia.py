"""Atalho para as ferramentas da importação: ``python bancoq_ia.py <comando>``.

É o mesmo que ``python -m bancoq.ia``, mas funciona de qualquer pasta.
Normalmente é chamado pelo script ``bancoq-ia``, que escolhe o Python certo.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bancoq.ia.__main__ import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
