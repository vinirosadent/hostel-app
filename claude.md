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

**Quando o pedido visual for subjetivo** (ex.: "a tela está feia", "os cards
estão ruins", "reorganize isso"), **proponha duas opções distintas** — uma
mais conservadora e uma mais ousada — e deixe Vinicius escolher antes de
implementar. Pode descrever em texto ou mostrar o código das duas.

**Exceção:** se o pedido tiver um critério objetivo já definido
(ex.: "tem um 'Arrow' aparecendo em texto, isso tem que sumir"), vai direto.

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

## 9. Como Vinicius prefere trabalhar

Isto é importante. Vinicius não é engenheiro de software — é pesquisador
biomédico que programa como ferramenta. Ajuste sua comunicação:

### Linguagem
Ele dá instruções em **linguagem natural, em português**, frequentemente
descrevendo problemas de forma verbal ("a tela está ruim", "isso tem que
parar", "cards mais enxutos", "faça que nem antes"). Interprete com bom senso.
**Não force jargão técnico** — se precisar explicar algo técnico, explique de
forma acessível.

### Planejamento
- **Mudanças grandes** (refatoração, múltiplos arquivos, novas features
  significativas, alterações de schema): **proponha um plano em passos antes
  de executar**, em formato enumerado. Espere confirmação ou ajustes antes de
  começar.
- **Mudanças pequenas e óbvias** (bug evidente, typo, ajuste visual pontual,
  adicionar um campo): **vai direto**, mostra o diff, Vinicius aprova.
- Em caso de dúvida sobre o tamanho, trate como grande.

### Formato de entrega
Quando a tarefa tem múltiplos itens, **numere e atenda um por vez**, mostrando
resultado antes de passar para o próximo. Isso é crítico porque Vinicius
costuma trabalhar em sessões curtas entre outras obrigações, e precisa poder
parar no meio e retomar depois.

Se ele disser "me dê em passos de instrução para eu poder fazer depois",
entregue o plano **sem executar nada**, em formato de checklist numerado,
concreto o suficiente para Claude (ou o próprio Vinicius) retomar numa sessão
futura.

### Decisões visuais subjetivas
Quando o pedido for estético e subjetivo, **proponha 2 opções** em vez de
chutar uma. Descreva brevemente cada uma e implemente só depois da escolha.

### Sempre pergunte antes de
- Apagar arquivos
- Rodar migrations destrutivas
- Alterar schema do Supabase
- Mudar lógica de autenticação ou permissões
- Refatorações que tocam muitos arquivos
- Atualizar versão do Streamlit, Supabase client, ou outras libs centrais
- Remover testes existentes

### Pode ir direto em
- Corrigir bugs óbvios (texto errado, valor hardcoded aparecendo na tela,
  crash previsível)
- Ajustes de estilo e layout quando o critério for claro
- Adicionar campos em formulários existentes
- Criar nova página seguindo padrão estabelecido
- Melhorar mensagens de erro
- Adicionar ou melhorar comentários
- Criar testes para código já existente

### Referências implícitas
"Faz que nem antes" ou "como você fez da última vez" significa seguir o
padrão de uma mudança anterior do mesmo tipo. Se o histórico recente tiver
precedente claro (olhe commits e o `progress/`), siga-o. Se não tiver,
pergunte qual referência ele tem em mente.

## 10. Cuidados de segurança e dados

- O banco tem **dados reais do hostel**. Nunca rode `DELETE`, `DROP`,
  `TRUNCATE` ou update em massa sem confirmação explícita.
- Credenciais do Supabase nunca aparecem em commits. Se você notar uma chave
  exposta em algum lugar, **avise imediatamente** antes de qualquer outra
  coisa.
- Ao escrever queries novas, prefira **prepared statements / parâmetros** do
  cliente Supabase, não concatenação de strings — proteção básica contra
  injection.
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
