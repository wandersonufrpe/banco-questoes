# Banco de Questões de Matemática

Aplicativo de desktop **offline** (PySide6 + QtWebEngine com MathJax local, SQLite,
PyMuPDF), todo em português. O usuário é um professor; responda em português.

## Importar provas em PDF

Use a skill **`importar-pdf`** (`/importar-pdf <arquivo.pdf>`). Ela usa o script
`./bancoq-ia` (ferramentas em `bancoq/ia/`), trabalha em `trabalho/<pacote>/` e
entrega as questões na caixa de entrada do banco
(`<banco>/entrada/pacotes/<pacote>/`), onde o professor aprova cada uma no app.

Nunca grave no banco diretamente (`banco.db`, `midia/`), nem edite `pacote.json`
ou `decisoes.json` à mão.

## Desenvolvimento

- Código: `bancoq/nucleo/` (sem Qt), `bancoq/interface/` (Qt), `bancoq/ia/`
  (importação com IA, sem Qt), `tests/`.
- Testes: `python -m pytest -q` (no Linux sem tela: `QT_QPA_PLATFORM=offscreen`).
- Decisões de projeto em `DECISOES.md`; plano das versões em `PLANO.md`.
- Dados fictícios só nos testes; o banco do usuário começa vazio.
