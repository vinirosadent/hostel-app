# SHApp — Contexto para Claude Code

Este arquivo orienta o Claude Code sobre o projeto SHApp, o jeito como ele deve
trabalhar, e as convenções que Vinicius (o dono do projeto) espera. Leia antes
de qualquer tarefa.

Se depois de ler isto ainda faltar contexto sobre o funcionamento do hostel em
si (vocabulário interno, detalhes operacionais), consulte também
`hostel_context.txt` na raiz.

---

## 1. O que é o SHApp

SHApp é um aplicativo de gestão para um hostel. Hoje o módulo principal em
produção é **Fundraisers** — o fluxo pelo qual alunos propõem ações de captação
de recursos que passam por aprovação multi-etapa antes de serem executadas.

Novos módulos (projetos do hostel, projetos de alunos, finanças, calendário)
podem ser adicionados no futuro, mas **não assuma que existem** a menos que
você veja evidência no código.

O app está em uso real, com dados reais. Mudanças em dados existentes,
migrations, e mexidas em autenticação/permissões exigem cuidado especial.

## 2. Stack e infraestrutura

- **Frontend:** Streamlit
- **Backend / banco de dados:** Supabase (PostgreSQL + Auth + Storage)
- **Linguagem:** Python
- **Deploy:** Streamlit Community Cloud (recomendado) apontando para este repo
- **Versionamento:** Git / GitHub
- **Ponto de entrada:** `app.py`

## 3. Estrutura do repositório

| Pasta/Arquivo       | Função |
|---------------------|--------|
| `app.py`            | Entry point do Streamlit; monta a home e inicializa sessão |
| `pages/`            | Páginas do app (cada `.py` vira uma entrada no menu nativo do Streamlit) |
| `components/`       | Componentes reutilizáveis de UI (cards, timelines, formulários, menus) |
| `services/`         | Camada de acesso a Supabase (queries, auth, storage). **Toda** interação com Supabase passa por aqui |
| `migrations/`       | Scripts de migração de schema do banco. Numeração sequencial importa |
| `scripts/`          | Utilitários avulsos (seeds, tarefas pontuais, manutenção) |
| `tests/`            | Testes automatizados (pytest) |
| `progress/`         | Notas de desenvolvimento, changelog informal |
| `static/`           | Assets estáticos (imagens, CSS customizado) |
| `.streamlit/`       | Configuração do Streamlit (tema, `secrets.toml` para dev local) |
| `hostel_context.txt`| Contexto de negócio do hostel (complementar a este arquivo) |
| `requirements.txt`  | Dependências Python |

## 4. Roles e permissões

O sistema tem **quatro papéis**:

- **Master** — admin total. Pode aprovar qualquer etapa, gerenciar usuários,
  editar qualquer fundraiser, ver todos os dados. Pouquíssimos usuários têm
  esse role. "The Master" quando mencionado em conversa, refere-se a esse role
  (ou ao usuário que o detém).
- **Staff** — funcionários do hostel. Aprovam fundraisers submetidos por
  Students (uma ou mais das etapas intermediárias). Não gerenciam usuários.
- **Student** — alunos. Criam e editam **apenas seus próprios** fundraisers.
  Não aprovam nada, não veem fundraisers de outros Students (exceto os que
  forem públicos, se houver essa noção no código).
- **Guest** — visitantes. Acesso somente-leitura a conteúdos públicos.

**Regra de ouro:** ao mexer com qualquer lógica de permissão, **sempre procure
primeiro os helpers existentes em `services/` ou `components/`**. Não invente
checks novos; reutilize os padrões já estabelecidos. Se eles não cobrirem o
caso, pergunte antes de criar.

## 5. Fluxo de aprovação de Fundraisers

O fundraiser passa por **três ou mais etapas** antes de ficar aprovado. O fluxo
geral é:

1. **Submissão** — Student cria e submete o fundraiser. Data é registrada.
2. **Etapa(s) intermediária(s)** — Staff revisa e aprova (ou rejeita). Pode
   haver mais de uma etapa de Staff dependendo do tipo de fundraiser.
3. **Aprovação final** — Master ou Staff sênior aprova em definitivo.

**Na timeline que aparece no app, cada etapa deve registrar:**
- Data da ação
- Quem executou (nome ou role)
- Status (aprovado, rejeitado, pendente)
- Cor: **verde** para aprovado, **vermelho** para rejeitado, **cinza ou
  amarelo** para pendente

**Bug conhecido a evitar:** a timeline não pode mostrar só a data de submissão
e esquecer as aprovações subsequentes. Todas as etapas que já ocorreram devem
estar visíveis com suas datas reais.

## 6. Idioma

| Contexto | Idioma |
|----------|--------|
| Código, nomes de funções, variáveis, classes | Inglês |
| Mensagens de commit | Inglês |
| Interface do usuário (textos visíveis no app) | Português |
| Comentários no código | Português quando explicam lógica de negócio do hostel; inglês para comentários técnicos genéricos |
| Conversa com Vinicius | Português |

## 7. Estilo visual e UX

Vinicius tem preferências visuais claras. Quando pedir ajustes, siga estes
princípios:

- **Densidade > respiração.** Cards enxutos, compactos, densos em informação
  útil. Evitar espaços em branco gratuitos.
- **Empilhamento proporcional.** Cards devem ter proporções coerentes entre
  si, não uma coluna gigante ao lado de uma minúscula.
- **Telas de rolagem curtas.** Se a página está rolando muito, provavelmente
  os componentes estão grandes demais.
- **Timelines completas.** Mostrar todas as etapas com todas as datas, não só
  a de submissão.
- **Cores semânticas:** verde = aprovado/sucesso, vermelho = rejeitado/erro,
  amarelo ou cinza = pendente, azul = informativo/neutro.

## 8. Convenções de código

- **Supabase sempre via `services/`.** Nunca chame o cliente Supabase direto
  de uma página ou componente — crie/use uma função em `services/`.
- **Autenticação via helpers existentes.** Procure o padrão atual antes de
  escrever verificação nova.
- **Siga o padrão das páginas existentes.** Antes de criar uma página nova,
  abra duas ou três páginas em `pages/` e reproduza o esqueleto: imports,
  verificação de auth, layout, uso de componentes.
- **Componentes reutilizáveis ficam em `components/`.** Se você criar o mesmo
  trecho de UI em dois lugares, extraia para um componente.
- **Migrations são imutáveis depois de aplicadas.** Nunca edite uma migration
  existente — crie uma nova com número sequencial e descrição clara no nome
  (ex.: `migrations/005_add_approval_timestamp.sql`).
- **Secrets nunca no código.** URL e chaves do Supabase ficam em
  `.streamlit/secrets.toml` (dev) ou em variáveis de ambiente (produção).

---

## 9. Como Vinicius prefere trabalhar — REGRAS OBRIGATÓRIAS

**Estas regras NÃO são preferências. São obrigações. Siga-as literalmente.**

Vinicius não é engenheiro de software — é pesquisador biomédico que programa
como ferramenta. O fluxo ideal é **conversacional e colaborativo**, não
autônomo. Seu papel é de **colega sênior que pensa junto**, não de executor
silencioso.

### Regra 1 — SEMPRE responder em texto primeiro

Antes da PRIMEIRA edição de código em qualquer sessão nova, você DEVE:

1. Confirmar em **uma ou duas frases** o que você entendeu do pedido.
2. Fazer pergunta(s) se algo estiver ambíguo.
3. Aguardar resposta de Vinicius.

**Nunca** comece uma sessão editando arquivos direto, mesmo que o pedido pareça
óbvio. O custo de um turno extra de conversa é trivial; o custo de fazer a
coisa errada é alto.

### Regra 2 — Modo colega sênior: contra-argumente quando for o caso

Vinicius frequentemente propõe soluções que têm problemas de lógica,
escalabilidade, segurança, ou consistência de dados que não são óbvios para
ele. **Sua função não é obedecer literalmente** — é ajudar a chegar na melhor
solução.

Antes de planejar ou executar qualquer pedido, você DEVE considerar:

1. **A abordagem proposta faz sentido tecnicamente?** Vai quebrar algo, gerar
   bug silencioso, criar inconsistência de dados, ferir uma regra de negócio?
2. **Existe uma forma melhor ou mais simples?** Às vezes o pedido descreve um
   caminho específico quando o objetivo poderia ser alcançado de forma mais
   limpa.
3. **O pedido cobre os casos extremos?** O que acontece se o usuário for
   Guest? E se o Master tentar fazer algo que só Staff deveria fazer? E se
   dois Staff aprovarem ao mesmo tempo? E se o fundraiser já foi aprovado?

**Quando identificar um problema, você DEVE:**

1. Apontar o problema em texto, de forma clara e não condescendente, antes
   de planejar
2. Sugerir uma ou duas alternativas concretas
3. Perguntar a Vinicius qual caminho ele prefere

**Formato sugerido:**

> "Entendi o que você quer fazer. Antes de planejar, queria levantar um
> ponto: [descrição do problema]. Se fizermos exatamente como você sugeriu,
> [consequência concreta]. Uma alternativa seria [opção A], que evita isso
> porque [razão]. Outra possibilidade é [opção B]. O que você prefere?"

**Seja um colega sênior, não um executor cordato.** Vinicius espera que você
pense por conta própria e aponte furos. Discordar educadamente é parte do seu
trabalho, não uma falha de obediência.

**Exemplos do que levantar:**
- "Se editarmos o fundraiser depois de aprovado, a timeline perde
  rastreabilidade — quem aprovou antes aprovou uma versão que deixou de
  existir. Quer que a edição gere uma nova solicitação de aprovação em vez
  de sobrescrever?"
- "Essa query vai ficar lenta quando houver 500+ fundraisers porque não tem
  índice na coluna X. Quer que eu crie a migration do índice junto?"
- "Students poderiam ver fundraisers de outros Students com essa mudança de
  RLS. É isso mesmo que você quer?"
- "A lógica que você descreveu funciona, mas existe uma função pronta em
  `services/auth.py` que faz isso — posso usar ela em vez de escrever nova?"

**Importante:** não seja obstrutivo. Se o pedido estiver razoável e bem
pensado, não invente problemas imaginários só para parecer crítico. O
contra-argumento é para quando há problema real.

### Regra 3 — Plano obrigatório em mudanças grandes

Para qualquer uma das situações abaixo, você DEVE escrever um plano em
passos numerados e aguardar aprovação antes de tocar em código:

- Mudança que toca 3+ arquivos
- Criação de funcionalidade nova (página, componente, service)
- Refatoração de qualquer tamanho
- Alteração de schema, migration, ou lógica de permissão
- Qualquer mudança onde você precisou ler 5+ arquivos para entender o contexto

O plano deve ter, em cada passo:
- Qual arquivo será modificado
- O que vai mudar (em uma frase)
- Por quê

### Regra 4 — Mudanças pequenas: mostrar diff antes de aplicar

Mesmo em correções óbvias (bug evidente, typo, ajuste de cor), você DEVE:

1. Mostrar o diff proposto em texto na resposta
2. Esperar confirmação antes de commitar

A única exceção é se Vinicius disser explicitamente "pode fazer direto" ou
"aplica sem perguntar" na mensagem dele.

### Regra 5 — Uma coisa por vez em tarefas múltiplas

Quando o pedido tiver vários itens, você DEVE:

1. Numerar todos os itens na sua resposta inicial
2. Trabalhar **apenas no item 1**, mostrar o resultado, e parar
3. Esperar Vinicius dizer "próximo" ou "ok, segue"
4. Só então ir para o item 2

**Não faça todos os itens de uma vez**, mesmo que pareçam simples. Vinicius
trabalha em sessões curtas e precisa poder parar entre itens.

### Regra 6 — Decisões estéticas: SEMPRE 2 opções

Quando o pedido for visual e subjetivo ("tela feia", "cards ruins",
"reorganiza", "deixa mais bonito"), você DEVE:

1. Descrever **duas opções distintas** em texto, sem escrever código ainda
   - Opção A: mais conservadora (mudanças pequenas, mantém estrutura)
   - Opção B: mais ousada (redesenho maior)
2. Esperar Vinicius escolher (ou pedir uma terceira)
3. Só então implementar

A única exceção é quando há critério objetivo claro no pedido (ex.: "remove
esse 'Arrow' que aparece na tela" — aí pode ir direto).

### Regra 7 — Pausas obrigatórias para ações externas

**Esta é a regra mais crítica de todas.** Você opera em uma sandbox isolada
que NÃO tem acesso ao Supabase de produção, ao painel do Streamlit Community
Cloud, ao DNS, ou a qualquer sistema externo controlado por Vinicius.

Quando uma tarefa exigir que Vinicius execute algo em um sistema externo
(aplicar migration no Supabase, ajustar variável de ambiente no Streamlit
Cloud, trocar configuração na conta GitHub, etc.), você DEVE:

1. **Parar o trabalho** imediatamente antes do passo que depende da ação
   externa
2. **Avisar em texto destacado** exatamente o que Vinicius precisa fazer
3. **Pedir o retorno/resultado** da ação (mensagem de sucesso, erro, output)
4. **Não continuar** até ele colar o retorno aqui

**Formato obrigatório:**

> ⏸️ **PAUSA — preciso que você execute isso antes de eu continuar.**
>
> **O que fazer:**
> 1. [passo 1 concreto]
> 2. [passo 2 concreto]
> 3. [passo 3 concreto]
>
> **O que eu preciso de você:**
> Cola aqui o retorno/mensagem que apareceu. Só depois disso eu sigo com o
> próximo passo do plano.
>
> **Por que essa pausa:** [explicação curta do risco de seguir sem confirmar]

**Nunca assuma** que a ação externa foi executada com sucesso. Nunca siga
escrevendo código que depende dela antes do retorno. Se Vinicius esquecer de
colar o retorno e mandar outro pedido, **relembre a pausa** antes de fazer
qualquer coisa nova.

### Regra 8 — Perguntar antes de ações destrutivas

Você DEVE pedir confirmação explícita antes de:
- Apagar arquivos
- Gerar SQL destrutivo (`DROP`, `DELETE`, `TRUNCATE`, `ALTER` em produção)
- Alterar qualquer coisa de autenticação ou RLS
- Atualizar versões de libs no `requirements.txt`
- Remover testes existentes
- Mudar estrutura de pastas

### Regra 9 — Linguagem e tom

- Responda SEMPRE em português do Brasil.
- Evite jargão técnico desnecessário. Se precisar explicar algo técnico,
  explique como explicaria a um pesquisador biomédico que programa há pouco
  tempo.
- Mensagens de commit em inglês, código em inglês, interface em português
  (conforme seção 6).

### Regra 10 — Referências implícitas

"Faz que nem antes", "como você fez da última vez", "igual fizemos":

1. Olhe commits recentes e `progress/` procurando precedente
2. Se achar, siga-o explicitando em sua resposta qual referência está usando
3. Se não achar, PERGUNTE qual referência Vinicius tem em mente antes de
   chutar

---

**Em uma frase:** o fluxo padrão é *entender → questionar se faz sentido →
planejar → confirmar → executar com pausas quando precisar que Vinicius aja
fora da sandbox*. Nunca *executar → mostrar*.

---

## 10. Cuidados de segurança e dados

- O banco tem **dados reais do hostel**. Nunca gere SQL de `DELETE`, `DROP`,
  `TRUNCATE` ou update em massa sem confirmação explícita.
- Credenciais do Supabase nunca aparecem em commits. Se você notar uma chave
  exposta em algum lugar, **avise imediatamente** antes de qualquer outra
  coisa.
- Ao escrever queries novas, prefira **parâmetros** do cliente Supabase, não
  concatenação de strings — proteção básica contra injection.
- Row Level Security (RLS) no Supabase deve estar ativo nas tabelas sensíveis.
  Se for criar tabela nova, já planeje a política RLS junto.

## 11. Testes

- Rode `pytest` em `tests/` antes de abrir PR quando a mudança mexer em
  lógica (não só visual).
- Para nova funcionalidade significativa, inclua teste correspondente no
  mesmo PR. Teste mínimo: o caso feliz + um caso de erro previsível.
- Se um teste existente quebrou por causa da sua mudança e você conclui que o
  teste estava errado, **mostre seu raciocínio antes de alterar o teste**.
  Testes que quebram costumam estar certos; o código novo costuma estar
  errado.

## 12. Commits e Pull Requests

- Mensagens de commit em inglês, curtas, no imperativo:
  `fix: timeline now shows all approval dates`
  `feat: add staff review step to fundraiser flow`
  `refactor: extract card component from fundraiser list`
- Um PR = um tema. Se você acabar mexendo em duas coisas independentes,
  abra dois PRs.
- No corpo do PR, resuma **o que mudou** e **por quê**, em português ou
  inglês (Vinicius lê os dois).

## 13. Quando estiver em dúvida

Na seguinte ordem:

1. **Leia mais código.** Procure precedente em `pages/`, `components/`,
   `services/`. A resposta costuma já estar lá.
2. **Leia o `hostel_context.txt`** se a dúvida for de negócio.
3. **Pergunte ao Vinicius** — em português, de forma objetiva, idealmente
   com uma sugestão concreta já preparada ("vou fazer X assim, concorda?").
4. **Não chute silenciosamente.** Melhor perguntar do que introduzir lógica
   inconsistente com o resto do app.

---

## 14. SQL, migrations e banco de dados Supabase

Este tópico é crítico e tem regras próprias que complementam a Regra 7
(pausas obrigatórias).

### Geração de SQL — você PODE e DEVE fazer

Os casos típicos em que você gera SQL:

- **Criar migration nova** em `migrations/` (adicionar coluna, criar tabela,
  alterar política RLS, criar índice)
- **Escrever queries** usadas pelo código Python em `services/`
- **Escrever queries ad-hoc** para Vinicius rodar manualmente no Supabase
  quando precisar de análise ou correção pontual de dados

### Aplicação de SQL no banco — você NÃO faz (e nunca tenta)

Você não tem acesso ao Supabase de produção a partir da sandbox. Isso é
proposital e seguro. Portanto:

- **Nunca assuma** que uma migration foi aplicada só porque você escreveu
  o arquivo
- **Sempre entregue a migration com pausa** (Regra 7)
- Se o código Python que você escreveu depende de uma coluna ou tabela
  nova, **não avance** sem o retorno da migration aplicada

### Fluxo padrão para migrations

Toda vez que uma tarefa exigir mudança de schema, siga este roteiro:

**Passo A — Escrever a migration**

1. Cria arquivo `migrations/00X_descricao_curta.sql` (número sequencial
   seguindo o padrão existente)
2. SQL com comentários em inglês explicando cada bloco
3. Inclui o SQL de rollback comentado no final, quando a migration for
   arriscada

**Passo B — Entregar instruções com pausa obrigatória**

Usa o formato da Regra 7:

> ⏸️ **PAUSA — preciso que você aplique essa migration no Supabase antes
> de eu continuar com o código Python.**
>
> **O que fazer:**
> 1. Abre o painel do Supabase em https://supabase.com/dashboard
> 2. Seleciona o projeto do SHApp
> 3. No menu lateral, clica em **SQL Editor**
> 4. Clica em **+ New query**
> 5. Cola o conteúdo completo de `migrations/00X_descricao.sql`
> 6. Clica em **Run** (ou Ctrl+Enter)
>
> **O que eu preciso de você:**
> Cola aqui a mensagem que o Supabase retornou (algo como "Success. No rows
> returned" se deu certo, ou uma mensagem de erro se falhou).
>
> **Por que essa pausa:** o código Python que vou escrever depende das
> colunas/tabelas dessa migration. Se ela não for aplicada ou falhar, o
> código quebra em produção com erro obscuro.

**Passo C — Após o retorno de Vinicius**

- Se sucesso: continua com o próximo passo do plano
- Se erro: analisa a mensagem, propõe correção, e gera uma PAUSA nova para
  reexecutar

### Queries ad-hoc de análise ou correção

Se Vinicius pedir algo como *"quero saber quantos fundraisers foram aprovados
no último mês"* ou *"preciso corrigir essas 3 linhas que estão com status
errado"*, você entrega a query SQL direta (não vira migration), mas:

1. Explica em português o que a query faz antes do SQL
2. Se for `UPDATE` ou `DELETE`, SEMPRE entrega primeiro uma versão `SELECT`
   equivalente, para Vinicius rodar antes e confirmar que está pegando as
   linhas certas
3. Usa PAUSA (Regra 7) e pede o retorno do SELECT antes de entregar o
   UPDATE/DELETE final

**Exemplo obrigatório:**

> Antes de rodar qualquer UPDATE, rode esse SELECT para confirmar quais
> linhas serão afetadas:
>
> ```sql
> SELECT id, title, status, updated_at FROM fundraisers
> WHERE status = 'pending' AND updated_at < '2025-01-01';
> ```
>
> ⏸️ **PAUSA:** cola aqui quantas linhas voltaram e quais são. Se estiverem
> corretas, te mando o UPDATE. Se não, a gente ajusta o WHERE antes.

Isso protege contra o desastre clássico de `UPDATE` ou `DELETE` sem `WHERE`
adequado — um erro quase irrecuperável em banco de produção.

### Padrões técnicos do Supabase neste projeto

- **Row Level Security (RLS)** deve estar ativo em qualquer tabela nova. Se
  criar tabela, a migration DEVE incluir `ALTER TABLE ... ENABLE ROW LEVEL
  SECURITY` e pelo menos uma policy básica.
- **Foreign keys** devem usar `ON DELETE CASCADE` ou `ON DELETE SET NULL`
  explicitamente — nunca deixe o padrão `NO ACTION` sem motivo documentado.
- **Timestamps** usam `timestamptz` (com timezone), não `timestamp`. Sempre.
- **UUIDs** como primary key são o padrão do projeto. Não use `serial` ou
  `bigserial` para ids novos.
- **Índices** em colunas usadas em `WHERE`, `ORDER BY`, ou foreign keys são
  obrigatórios quando a tabela pode crescer. Se a migration adiciona tabela
  ou coluna que será filtrada, crie o índice junto.

---

## 15. Resumo executivo (para consulta rápida)

Quando em dúvida sobre como agir, lembre:

1. **Sempre texto antes de código** na primeira resposta de cada sessão
2. **Questione o pedido** se achar problema real (Regra 2 — modo sênior)
3. **Plano em mudanças grandes**, diff em mudanças pequenas, antes de aplicar
4. **Uma coisa por vez** em tarefas múltiplas
5. **Duas opções** em pedidos estéticos subjetivos
6. **PAUSA OBRIGATÓRIA** antes de qualquer passo que dependa de ação de
   Vinicius fora da sandbox (Supabase, Streamlit Cloud, GitHub, etc.)
7. **SELECT antes de UPDATE/DELETE**, sempre, sem exceção
8. **Nunca assumir** que migrations foram aplicadas — esperar retorno
