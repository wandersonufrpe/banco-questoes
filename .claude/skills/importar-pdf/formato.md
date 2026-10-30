# Formato do arquivo da questão

Arquivo `trabalho/<pacote>/questoes/<id>.txt`, em UTF-8, com o mesmo id do recorte
(`q001`, `q144`…). Duas partes:

1. **Cabeçalho**: uma linha por campo, `@campo: valor`.
2. **Seções**: cada uma começa numa linha `@@nome` e vai até a próxima `@@`. O
   conteúdo é LaTeX puro (sem escapes: escreva `\frac`, não `\\frac`).

Linhas em branco no começo e no fim de cada seção são ignoradas.

## Exemplo completo (múltipla escolha)

```
@numero: 4
@pagina: 1
@tipo: multipla
@dificuldade: 3
@fonte: OBMEP 2025 — Nível 3, 1ª fase, questão 4
@ano: 2025
@categoria: Geometria Plana > Áreas
@tags: área de triângulos; semelhança
@resposta: C
@resposta_independente: C
@gabarito_pdf: C
@sympy: área = 12 conferida com SymPy
@confianca: alta
@figura: 1 | ok
@preambulo: \usepackage{tikz}

@@enunciado
Na figura, $ABCD$ é um quadrado de lado $6$ e $M$ é o ponto médio de $BC$.
Qual é a área do triângulo $AMD$?
\begin{center}
\begin{tikzpicture}[scale=0.6]
  \draw (0,0) node[below left] {$A$} -- (6,0) node[below right] {$B$}
        -- (6,6) node[above right] {$C$} -- (0,6) node[above left] {$D$} -- cycle;
  \draw (0,0) -- (6,3) node[right] {$M$} -- (0,6);
\end{tikzpicture}
\end{center}

@@alternativa
$9$
@@comentario
É a área do triângulo $ABM$, não a de $AMD$.

@@alternativa
$15$
@@comentario
Errou a altura: usou $5$ em vez de $6$.

@@alternativa correta
$18$
@@comentario
Correta: base $AD=6$ e altura igual ao lado, $6$; área $\frac{6\cdot 6}{2}=18$.

@@alternativa
$27$
@@comentario
Subtraiu do quadrado só um dos triângulos laterais: $36-9=27$.

@@alternativa
$36$
@@comentario
É a área do quadrado inteiro.

@@resolucao
A base $AD$ mede $6$. A distância de $M$ até o lado $AD$ é a distância entre as
retas $AD$ e $BC$, isto é, o lado do quadrado, $6$. Logo
\[
  \text{área}(AMD) = \frac{AD\cdot 6}{2} = \frac{6\cdot 6}{2} = 18.
\]
Outra forma: a área do quadrado ($36$) menos as áreas de $ABM$ ($9$) e $DCM$ ($9$)
dá $36-9-9=18$. Resposta: (C).

@@observacoes
Importada de pf1n3_2025.pdf (questão 4). Gabarito oficial: C.

@@verificacao
Resolução principal: 18 (C). Segunda resolução (subagente, sem ver a resposta): 18.
SymPy: 36 - 9 - 9 = 18. Gabarito do PDF: C. Tudo concorda.
```

## Campos do cabeçalho

| Campo | Valor |
|---|---|
| `@numero` | número da questão no PDF |
| `@pagina` | página do PDF onde ela começa |
| `@tipo` | `multipla`, `vf` (verdadeiro ou falso), `curta` (resposta curta) ou `discursiva` |
| `@dificuldade` | 1 a 5 (veja metadados.md) |
| `@fonte` | ex.: `ENEM 2025 — 2º dia, caderno amarelo, questão 144` |
| `@ano` | ano da prova |
| `@categoria` | caminho com ` > `, ex.: `Álgebra > Equações do 1º grau` |
| `@tags` | separadas por `;` |
| `@nao_embaralhar` | `sim` se as alternativas não podem mudar de ordem |
| `@resposta` | sua resposta final (letra na múltipla escolha; `VFFV` no verdadeiro ou falso; valor nas outras) |
| `@resposta_independente` | resposta da segunda resolução |
| `@gabarito_pdf` | gabarito oficial, se houver (senão omita) |
| `@sympy` | o que foi conferido no SymPy (senão omita) |
| `@confianca` | `alta`, `média` ou `baixa` |
| `@figura` | `N \| ok`, `N \| ajustar \| o que difere` ou `N \| texto`; uma linha por figura do PDF |
| `@aviso` | algo que o professor precisa saber (pode repetir) |
| `@preambulo` | linha de preâmbulo de que a questão precisa (pode repetir), ex.: `\usepackage{tikz}` |

## Seções

| Seção | Conteúdo |
|---|---|
| `@@enunciado` | obrigatória |
| `@@alternativa` / `@@alternativa correta` | múltipla escolha, na ordem do PDF; exatamente uma correta |
| `@@afirmativa verdadeira` / `@@afirmativa falsa` | verdadeiro ou falso |
| `@@comentario` | logo depois da alternativa/afirmativa a que se refere |
| `@@resposta_esperada` | só no tipo `curta` (ex.: `$12$`) |
| `@@resolucao` | obrigatória: resolução completa |
| `@@observacoes` | texto simples (não vai para a prova) |
| `@@verificacao` | relatório da conferência (o professor lê no app) |

## Figuras e `tikzpicture`

A k-ésima `tikzpicture` do enunciado e das alternativas (nessa ordem) corresponde
à k-ésima figura com `@figura` `ok` ou `ajustar`, em ordem de número. Figuras
marcadas `texto` não têm `tikzpicture`. Figuras extras na resolução são livres.
