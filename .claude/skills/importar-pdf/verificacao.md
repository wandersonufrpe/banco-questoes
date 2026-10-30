# Conferência da resposta

O professor escolheu **resolver e conferir**: toda questão passa por três checagens,
quando possível. O resultado vai nos campos `@resposta`, `@resposta_independente`,
`@gabarito_pdf`, `@sympy`, `@confianca` e na seção `@@verificacao`.

## 1. Resolução principal

Resolva com cuidado, escreva a resolução completa (é o que vai para o banco) e
anote a resposta em `@resposta`.

## 2. Segunda resolução independente (subagente)

Use um subagente (ferramenta Task/Agent, tipo `general-purpose`) que **não** vê a sua
resolução, a sua resposta nem o gabarito. Para economizar, mande um lote de 5 a 10
questões de uma vez. Modelo de pedido:

```
Resolva de forma independente as questões de matemática abaixo. Para cada uma,
responda só com: id, resposta final (letra, valor ou V/F) e um resumo do raciocínio
em até duas linhas. Não consulte arquivos nem a internet.

[q003] <enunciado em LaTeX>
(A) ... (B) ... (C) ... (D) ... (E) ...
Figura: <descrição objetiva do que a figura mostra: medidas, posições, rótulos>
```

Descreva as figuras em texto (o subagente não as vê). Anote a resposta dele em
`@resposta_independente`.

## 3. SymPy (quando houver conta)

Para contas, equações, simplificações, somas, probabilidades com contagem pequena
etc., confira com um script curto e rode com `./bancoq-ia python <script>.py`
(guarde os scripts em `trabalho/<pacote>/sympy/`). Exemplo:

```python
from sympy import Rational, symbols, solve
x = symbols("x")
print(solve(2*x + 3 - 11, x))          # [4]
print(Rational(1, 2) + Rational(1, 3))  # 5/6
```

Em `@sympy`, escreva em poucas palavras o que foi conferido (ex.: `raízes 2 e 3
conferidas`). Se não houver o que conferir (questão conceitual, geometria sintética),
omita o campo.

Para contagens pequenas, uma força bruta em Python também vale.

## 4. Gabarito do PDF

Se a prova tem gabarito (no próprio PDF, como no ENA, ou num PDF à parte), anote a
letra em `@gabarito_pdf`.

## Quando há divergência

1. Releia o enunciado no recorte (sinal, unidade, "não", "exceto", "aproximadamente").
2. Refaça a conta que diverge, de outro jeito.
3. Se a sua resposta mudar, corrija a resolução inteira e os comentários.
4. Se a divergência continuar:
   - com o subagente: mantenha a resposta que você consegue justificar passo a passo,
     explique a divergência em `@@verificacao` e use `@confianca: média` ou `baixa`;
   - com o gabarito oficial: **não** troque a resposta só para bater. Explique em
     `@@verificacao` e ponha `@aviso: resposta diverge do gabarito oficial (<letra>)`;
     se souber que a questão foi anulada ou teve o gabarito alterado, diga isso.

## Confiança

- `alta`: as checagens disponíveis concordam.
- `média`: houve divergência resolvida, ou só uma checagem foi possível numa questão
  trabalhosa.
- `baixa`: divergência não resolvida, enunciado ambíguo ou ilegível.

## `@@verificacao`

Três a seis linhas, para o professor ler no aplicativo: o que cada checagem deu e,
se houve divergência, como foi resolvida.
