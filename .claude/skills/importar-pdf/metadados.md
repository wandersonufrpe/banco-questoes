# Metadados

O professor revisa tudo no aplicativo, mas a sugestão deve servir sem retoques.

## Tipo

- `multipla`: alternativas (A)–(E) com uma correta.
- `vf`: afirmativas para julgar (verdadeiro ou falso); a resposta é a sequência, ex. `VFFV`.
  Questões "quais afirmativas são verdadeiras? (A) I e II (B)…" são `multipla`.
- `curta`: resposta numérica ou curta, sem alternativas (ex.: OBMEP 2ª fase item único,
  "calcule…"). Preencha `@@resposta_esperada`.
- `discursiva`: demonstrações, itens a), b), c) abertos.

## Dificuldade (1 a 5)

Pense num aluno do nível a que a prova se destina.

| | |
|---|---|
| 1 | aplicação direta de um conceito ou conta simples |
| 2 | um passo de raciocínio além da aplicação direta |
| 3 | dois ou três passos, exige escolher a estratégia |
| 4 | ideia não óbvia ou vários conceitos combinados |
| 5 | muito difícil para o nível (questões finais de olimpíada) |

Em provas com ordem crescente de dificuldade (OBMEP), a posição ajuda a calibrar.

## Fonte e ano

`@fonte`: `<Prova> <ano> — <detalhes>, questão <n>`, com os detalhes que identificam a
prova. Exemplos:

- `OBMEP 2025 — Nível 3, 1ª fase, questão 4`
- `ENEM 2025 — 2º dia, caderno amarelo, questão 144`
- `ENA 2027 (PROFMAT), questão 3`
- `UFPE 2024 — Vestibular, 2ª fase, questão 10`
- `Lista de exercícios — Funções (Prof. …), questão 5` (para materiais sem ano)

Use o mesmo título do pacote (`--titulo` do `preparar`) e veja em `catalogo` →
`fontes` como as fontes já estão escritas no banco, para manter o padrão.
`@ano`: ano em que a prova foi aplicada (não o do arquivo). Se não houver, omita.

## Categoria

Uma categoria por questão, como caminho do geral para o específico
(`Área > Assunto`, no máximo 3 níveis), pelo conteúdo **principal** cobrado.

1. Use uma categoria que já existe (`catalogo` → `categorias`), com a mesma grafia.
2. Só crie uma nova se nenhuma servir; siga o estilo das existentes e anote em
   `notas.md` para repetir igual nas próximas questões.
3. Banco vazio: use estas áreas no primeiro nível e assuntos no segundo:
   `Aritmética`, `Álgebra`, `Funções`, `Geometria Plana`, `Geometria Espacial`,
   `Geometria Analítica`, `Trigonometria`, `Combinatória`, `Probabilidade`,
   `Estatística`, `Matemática Financeira`, `Lógica`, `Teoria dos Números`.
   Exemplos: `Álgebra > Equações do 2º grau`, `Geometria Plana > Semelhança de triângulos`,
   `Combinatória > Princípio multiplicativo`.

Categorias novas só são criadas no banco se o professor aprovar a questão.

## Tags

De 2 a 5, em minúsculas (exceto nomes próprios), curtas, em português: o assunto mais
fino e a técnica usada. Ex.: `área de triângulos; ponto médio; decomposição de figuras`.

- Prefira as que já existem (`catalogo` → `tags`), com a mesma grafia.
- Não repita a categoria nem a fonte como tag (o nome da prova já está na fonte).
- Contexto útil para montar provas também vale: `leitura de gráfico`,
  `interpretação de tabela`, `contextualizada`.

## Não embaralhar

`@nao_embaralhar: sim` quando a ordem das alternativas importa: "todas as
anteriores", "nenhuma das anteriores", "(A) e (B)", alternativas que se referem a
outras. Senão, omita.

## Observações

Uma linha simples (não vai para a prova): de onde veio e o gabarito oficial. Ex.:
`Importada de pf1n3_2025.pdf (questão 4). Gabarito oficial: C.` Acrescente o que
o professor precisar saber (questão anulada, figura aproximada…).
