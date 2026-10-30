---
name: importar-pdf
description: Importa questões de uma prova em PDF para o Banco de Questões de Matemática. Lê cada questão, transcreve em LaTeX, redesenha as figuras em TikZ, resolve e confere a resposta (segunda resolução independente, SymPy e gabarito do PDF), preenche os metadados e entrega na caixa de entrada do aplicativo, onde o professor aprova ou rejeita cada uma. Use quando o professor pedir para importar, cadastrar ou trazer questões de um PDF (OBMEP, ENEM, ENA, vestibular, lista) ou para continuar uma importação já começada.
argument-hint: <arquivo.pdf ou nome do pacote> [questões, ex.: 1-10]
---

# Importar questões de um PDF

Você vai transformar as questões de um PDF em questões do banco, **uma a uma**, e
entregá-las na caixa de entrada do aplicativo. **Nada entra no banco sem o professor
aprovar no aplicativo**: você nunca grava no banco (`banco.db`), nunca edita
`pacote.json` nem `decisoes.json` à mão.

Converse com o professor em português. Ele usa o plano Pro: economize leitura de
imagens e contexto (veja "Economia" no fim).

## Ferramentas

Tudo passa pelo script `./bancoq-ia` na raiz do repositório (na primeira vez ele cria
o ambiente `.venv-ia`; demora um ou dois minutos). As respostas são JSON.

| Comando | Para quê |
|---|---|
| `./bancoq-ia banco` | pasta do banco usado (o último aberto no app; outro: `--banco <pasta>` antes do comando) |
| `./bancoq-ia catalogo` | categorias, tags, fontes e preâmbulo que já existem no banco |
| `./bancoq-ia preparar <pdf> --titulo "..."` | cria ou retoma o pacote: recorte de cada questão, texto extraído, figuras |
| `./bancoq-ia status <pacote>` | o que já foi escrito, entregue, aprovado, e o que falta |
| `./bancoq-ia pagina <pacote> <n> [--grade 50]` | página inteira em PNG (com grade, para achar coordenadas) |
| `./bancoq-ia recortar <pacote> <id> --parte P:x0,y0,x1,y1 [--parte ...] [--figura N]` | refaz um recorte (pontos do PDF) |
| `./bancoq-ia remover-figura <pacote> <id> <N>` | apaga uma "figura" detectada por engano |
| `./bancoq-ia tikz <pacote> <id>` | compila as figuras TikZ da questão e gera a comparação com o original |
| `./bancoq-ia tikz <pacote> <id> --arquivo f.tex --figura N` | testa um TikZ solto antes de pôr na questão |
| `./bancoq-ia validar <pacote> [<id>...] --compilar` | confere a questão (formato, respostas, LaTeX compilando) |
| `./bancoq-ia entregar <pacote> [<id>...]` | copia as questões sem erro para a caixa de entrada do app |
| `./bancoq-ia finalizar <pacote>` | confere e entrega tudo e marca o pacote como pronto |
| `./bancoq-ia python arquivo.py` | roda um script com o Python do ambiente (tem SymPy) |

`<pacote>` é o nome curto devolvido por `preparar` (ex.: `obmep-2025-n3`).

Você trabalha só dentro de `trabalho/<pacote>/` (no repositório):
`recortes/<id>.png`, `figuras/<id>-<n>-original.png`, `texto/<id>.txt`,
`questoes/<id>.txt` (o que você escreve), `comparar/`, `notas.md`.

## Passo a passo

### 1. Começo (ou retomada)

1. `./bancoq-ia banco`. Se der erro, peça ao professor a pasta do banco e use `--banco`.
2. Se o argumento for um nome de pacote ou o professor disser "continue", rode
   `./bancoq-ia status <pacote>`, leia `trabalho/<pacote>/notas.md` e siga do
   primeiro id em `faltando` (e corrija os de `com_erro`).
3. Se for um PDF novo: leia o recorte da primeira questão (ou `pagina 1`) para saber
   que prova é e rode `./bancoq-ia preparar "<pdf>" --titulo "<título>"`, com o título
   no formato da fonte (ex.: `OBMEP 2025 — Nível 3, 1ª fase`). Confira na resposta:
   - quantas questões foram encontradas (compare com a prova; se faltar alguma ou a
     numeração estiver estranha, veja a página e use `recortar`);
   - `paginas_com_gabarito`: se houver, leia essas páginas e anote o gabarito em
     `notas.md`. Se o professor deu um PDF de gabarito à parte, leia-o também;
   - `avisos` (por exemplo, PDF sem camada de texto: leia tudo pelos recortes).
4. `./bancoq-ia catalogo` (uma vez por sessão) para usar as categorias e tags que já
   existem. Anote em `notas.md` as categorias novas que você criar, para usar sempre
   os mesmos nomes.
5. Se o professor pediu só algumas questões (ex.: "1-10", "só geometria"), faça só
   essas.

### 2. Cada questão

Para cada id, nesta ordem:

1. **Ler.** Abra `recortes/<id>.png` (é a fonte da verdade). Se `texto_util` for
   verdadeiro, use também `texto/<id>.txt` para copiar as palavras exatas (os acentos
   podem vir quebrados e as fórmulas costumam vir erradas: confie na imagem). Se o
   recorte estiver cortado ou pegar outra questão, refaça com `pagina --grade` +
   `recortar`. Texto-base comum a várias questões ("Leia o texto para as questões 3
   e 4") entra no enunciado de cada uma.
2. **Transcrever** em LaTeX, fiel ao original: mesmas palavras, mesma ordem das
   alternativas, sem as letras (A), (B)… (o app põe). Veja [latex-e-tikz.md](latex-e-tikz.md).
3. **Figuras.** Para cada `figuras/<id>-<n>-original.png`: confira se é mesmo uma
   figura e se o recorte está bom (senão `recortar --figura n` ou `remover-figura`);
   redesenhe em TikZ no lugar certo do enunciado/alternativa; escreva a questão;
   rode `./bancoq-ia tikz <pacote> <id>` e abra a imagem `comparacao`; ajuste e repita
   **no máximo 3 vezes** por figura. Tabelas e quadros de texto viram LaTeX comum
   (`@figura: n | texto`). Se não ficou fiel (foto, ilustração, desenho muito
   complexo), deixe a melhor aproximação e marque `@figura: n | ajustar | <o que
   difere>`. Detalhes em [latex-e-tikz.md](latex-e-tikz.md).
4. **Resolver** com resolução completa e didática e um comentário para **cada**
   alternativa (por que está certa ou qual erro leva a ela).
5. **Conferir** seguindo [verificacao.md](verificacao.md): segunda resolução
   independente (subagente), SymPy quando houver conta, gabarito do PDF.
6. **Metadados** seguindo [metadados.md](metadados.md): tipo, dificuldade, fonte,
   ano, categoria, tags, observações.
7. **Escrever** `trabalho/<pacote>/questoes/<id>.txt` no formato de
   [formato.md](formato.md).
8. `./bancoq-ia validar <pacote> <id> --compilar` e corrija até não haver erros
   (os avisos podem ficar, se fizerem sentido).
9. `./bancoq-ia entregar <pacote> <id>`: a questão aparece na caixa de entrada.

Entregue cada questão assim que ela ficar pronta: se a sessão acabar no meio, nada
se perde e a próxima continua pelo `status`.

### 3. Fim

1. `./bancoq-ia finalizar <pacote>` (compila tudo de novo e marca como pronto).
2. Resuma para o professor, em poucas linhas: quantas questões foram entregues;
   quais têm figura para ajustar; quais têm divergência com o gabarito ou confiança
   baixa (com o motivo); categorias e tags novas sugeridas; o que ficou de fora.
3. Lembre: no aplicativo, aba **Caixa de entrada**, cada questão é aprovada ou
   rejeitada (pode editar antes de aprovar).

## Regras

- Não invente: se uma parte da questão estiver ilegível, recorte de novo; se mesmo
  assim não der, escreva `@aviso: <o que está ilegível>` e transcreva o que der.
- Não "conserte" a questão original. Se ela tiver erro (ou foi anulada), transcreva
  como está e explique em `@aviso` e na resolução.
- A resposta tem de vir da sua resolução, não só do gabarito. Se não bater com o
  gabarito, siga [verificacao.md](verificacao.md).
- Questões de múltiplos itens abertos — a), b), c) — são `discursiva`, com os itens
  num `enumerate` e a resolução item a item.
- Se o professor pedir algo diferente destas regras para uma prova, faça como ele
  pediu e anote em `notas.md`.

## Economia (plano Pro)

- Leia o recorte de cada questão uma vez; abra páginas inteiras só quando precisar.
- Faça a segunda resolução de várias questões num só subagente (lotes de 5 a 10).
- Trabalhe em lotes (ex.: 10 questões), entregando cada uma, e diga ao professor
  quanto falta. Se o limite de uso chegar, tudo o que foi entregue está salvo.
- Mantenha `notas.md` curto: gabarito, título, categorias novas, pendências.
