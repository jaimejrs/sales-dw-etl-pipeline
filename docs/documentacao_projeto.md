# Documentação Técnica do Projeto

## Visão Geral

Este projeto implementa uma pipeline de Engenharia de Dados em Python para construir uma camada analítica de vendas em PostgreSQL. A origem é o banco operacional do business case, organizado nos schemas `geral`, `vendas` e `rh`. O destino é um Data Warehouse simplificado no schema `dw`.

A estratégia de carga segue um padrão híbrido usado em ambientes corporativos:

- `full`: carga inicial ou reconstrução completa do DW.
- `incremental`: carga recorrente por janela de reprocessamento baseada em `data_venda`.
- `auto`: decide automaticamente. Se a fato ainda não existe ou está incompatível, executa `full`; se já existe, executa `incremental`.

Como a origem não possui coluna explícita de atualização, como `updated_at`, o incremental usa `MAX(data_venda)` já carregada no DW menos uma janela configurável. Essa abordagem reprocessa um período recente para capturar atrasos, correções e registros lançados retroativamente.

## Estrutura de Pastas

```text
BCDEDT/
├── main.py
├── requirements.txt
├── .env.example
├── sql/
│   ├── dim_cliente.sql
│   ├── dim_forma_pagamento.sql
│   ├── dim_produto.sql
│   ├── dim_vendedor.sql
│   ├── fato_vendas.sql
│   └── ddl_dw.sql
├── src/
│   ├── __init__.py
│   ├── config.py
│   ├── controle_carga.py
│   ├── extracao.py
│   ├── transformacao.py
│   ├── carga_dw.py
│   └── validacao.py
├── tests/
│   ├── __init__.py
│   ├── test_carga_dw.py
│   ├── test_extracao.py
│   └── test_transformacao.py
├── docs/
│   ├── documentacao_projeto.md
│   └── modelagem_dw.md
└── notebooks/
    └── analise_exploratoria.ipynb
```

## Arquivos de Configuração

### `requirements.txt`

Lista as bibliotecas necessárias para executar a pipeline:

- `pandas`: manipulação dos DataFrames.
- `SQLAlchemy`: conexão e execução SQL.
- `psycopg2-binary`: driver PostgreSQL.
- `python-dotenv`: leitura do arquivo `.env`.
- `ipykernel`: suporte ao notebook exploratório.

### `.env.example`

Modelo sem credenciais reais.

## Orquestração

### `main.py`

É o ponto de entrada da aplicação. Responsabilidades:

- carregar variáveis de ambiente;
- montar as conexões com origem e destino;
- testar as conexões antes da extração;
- preparar os schemas de controle;
- decidir o modo de carga;
- iniciar o registro de auditoria;
- executar extração, transformação, carga e validação;
- registrar sucesso ou falha em `dw.etl_controle_carga`.

Fluxo resumido:

```text
get_engines()
testar_conexao()
preparar_controle_carga()
definir_contexto_carga()
extrair_dados()
transformar_dados()
carregar_dados()
validar_carga()
atualizar_carga_sucesso() ou atualizar_carga_falha()
```

## Código Fonte

### `src/config.py`

Centraliza constantes do projeto:

- raiz do projeto;
- diretórios de SQL e logs;
- schemas `dw` e `dw_staging`;
- nome da pipeline;
- nome da tabela de controle;
- ordem de extração e carga;
- chaves das dimensões;
- colunas obrigatórias da fato;
- relacionamentos da fato com as dimensões.

Esse arquivo evita duplicação de nomes de tabelas, schemas e colunas entre os módulos.

### `src/controle_carga.py`

Implementa a camada de auditoria e decisão de carga.

Principais funções:

- `preparar_controle_carga`: cria os schemas `dw` e `dw_staging` e a tabela `dw.etl_controle_carga`.
- `obter_watermark_fato`: busca o maior `data_venda` carregado na fato.
- `definir_contexto_carga`: decide entre `full` e `incremental`.
- `iniciar_carga`: registra uma execução com status `running`.
- `atualizar_carga_sucesso`: grava métricas finais e status `success`.
- `atualizar_carga_falha`: grava status `failed` e mensagem de erro.

A tabela `dw.etl_controle_carga` guarda início, fim, modo de carga, janela incremental, quantidade de linhas e totais financeiros.

### `src/extracao.py`

Lê os arquivos SQL da pasta `sql/` e executa as consultas na origem.

No modo incremental, apenas `fato_vendas` recebe filtro:

```sql
WHERE nf.data_venda >= :data_inicio_incremental
```

As dimensões são extraídas completas em toda execução, pois são pequenas e podem sofrer atualização cadastral.

### `src/transformacao.py`

Aplica as regras de tratamento em memória com pandas:

- valida presença de tabelas e colunas obrigatórias;
- converte datas;
- converte chaves para inteiros;
- converte métricas para numérico;
- preenche descrições nulas em produtos, categorias, formas de pagamento, clientes e vendedores;
- remove registros da fato com chaves críticas nulas;
- remove duplicidades exatas da fato;
- deduplica dimensões pela chave principal;
- gera `dim_tempo`;
- cria `id_tempo` e `ano_mes`;
- gera `id_fato_venda`.

A fato preserva o grão de item da nota fiscal por meio de `id_item_nota_fiscal`, extraído de `vendas.item_nota_fiscal.id`.

### `src/carga_dw.py`

Executa a carga no PostgreSQL de destino.

No modo `full`:

- cria o schema `dw`;
- remove tabelas dimensionais e fato anteriores;
- recria as tabelas a partir dos DataFrames;
- aplica PKs, FKs e índices.

No modo `incremental`:

- carrega os DataFrames no schema `dw_staging`;
- faz upsert das dimensões;
- remove da `dw.fato_vendas` a janela `data_venda >= data_inicio_incremental`;
- insere novamente a fato tratada da staging.

Essa estratégia evita reprocessar toda a fato em cargas recorrentes e mantém a possibilidade de corrigir dados recentes.

### `src/validacao.py`

Executa validações SQL no DW e salva relatório em `logs/`.

Validações implementadas:

- contagem de linhas por tabela;
- comparação de linhas da fato no escopo validado;
- comparação do total de `valor_total_item`;
- chaves nulas em dimensões;
- duplicidades em dimensões;
- nulos críticos na fato;
- integridade referencial da fato com produto, cliente, vendedor, forma de pagamento e tempo;
- valores inválidos em métricas;
- consistência de `valor_total_item` contra `quantidade * valor_unitario`.

No full, o escopo validado é a fato inteira. No incremental, o escopo validado é apenas a janela reprocessada.

## Scripts SQL

### `sql/dim_produto.sql`

Extrai produtos e suas categorias a partir de `vendas.produto` e `vendas.categoria`.

Campos finais:

- `id_produto`
- `nome_produto`
- `categoria`
- `valor_venda`
- `valor_custo`

### `sql/dim_forma_pagamento.sql`

Extrai formas de pagamento de `vendas.forma_pagamento`.

Campos finais:

- `id_forma_pagamento`
- `descricao_forma_pagamento`

### `sql/dim_cliente.sql`

Unifica clientes pessoa física e pessoa jurídica. Usa `geral.pessoa`, `geral.pessoa_fisica`, `geral.pessoa_juridica`, `geral.endereco`, `geral.bairro`, `geral.cidade` e `geral.estado`.

Campos finais:

- `id_cliente`
- `nome_cliente`
- `tipo_pessoa`
- `cidade`
- `estado`
- `data_cadastro`

### `sql/dim_vendedor.sql`

Extrai vendedores a partir dos vendedores que aparecem em `vendas.nota_fiscal.id_vendedor`, enriquecendo com `geral.pessoa` e `geral.pessoa_fisica`.

Essa decisão foi tomada porque, no banco real, a fato referencia `geral.pessoa.id` para vendedor.

Campos finais:

- `id_vendedor`
- `nome_vendedor`
- `data_cadastro`

### `sql/fato_vendas.sql`

Extrai o grão de item de nota fiscal a partir de `vendas.nota_fiscal` e `vendas.item_nota_fiscal`.

Campos principais:

- `id_nota_fiscal`
- `id_item_nota_fiscal`
- `numero_nf`
- `data_venda`
- `id_produto`
- `id_cliente`
- `id_vendedor`
- `id_forma_pagamento`
- `quantidade`
- `valor_unitario`
- `valor_total_item`

### `sql/ddl_dw.sql`

DDL opcional de referência para criação das tabelas finais do DW e da tabela de controle. A pipeline cria as estruturas via Python, mas o DDL documenta o modelo físico esperado.

## Estratégia Incremental

O incremental funciona assim:

1. A pipeline consulta `MAX(data_venda)` em `dw.fato_vendas`.
2. Subtrai `DW_INCREMENTAL_LOOKBACK_DAYS`.
3. Extrai da origem apenas vendas com `data_venda >= data_inicio_incremental`.
4. Trata os dados no pandas.
5. Carrega tudo em `dw_staging`.
6. Atualiza dimensões com upsert.
7. Remove do DW a janela reprocessada.
8. Reinsere a janela limpa e validada.

Exemplo:

```text
MAX(data_venda) no DW = 2026-09-05
DW_INCREMENTAL_LOOKBACK_DAYS = 30
data_inicio_incremental = 2026-08-06
```

Nesse caso, somente vendas a partir de `2026-08-06` são reprocessadas.

## Testes

Os testes estão em `tests/`.

### `tests/test_transformacao.py`

Cobre:

- limpeza de fato;
- deduplicação de dimensões;
- geração de `dim_tempo`;
- criação de `id_tempo`;
- criação de `ano_mes`;
- geração de `id_fato_venda`;
- preservação de itens distintos da mesma nota;
- erro quando coluna obrigatória não existe.

### `tests/test_carga_dw.py`

Cobre:

- pré-validação de DataFrames transformados;
- falha quando há FK órfã antes da carga.

### `tests/test_extracao.py`

Cobre:

- montagem do filtro incremental para `fato_vendas`.

Comando:

```powershell
.\.venv311\Scripts\python.exe -m unittest discover -s tests
```

## Como Executar

Instalar dependências:

```powershell
python -m venv .venv311
.\.venv311\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Executar em modo automático:

```powershell
.\.venv311\Scripts\python.exe main.py
```

Forçar full:

```powershell
$env:DW_LOAD_MODE = "full"
.\.venv311\Scripts\python.exe main.py
```

Forçar incremental:

```powershell
$env:DW_LOAD_MODE = "incremental"
.\.venv311\Scripts\python.exe main.py
```

Alterar janela incremental:

```powershell
$env:DW_INCREMENTAL_LOOKBACK_DAYS = "7"
.\.venv311\Scripts\python.exe main.py
```

## Evidências Geradas

A cada execução, a pipeline registra:

- status da carga em `dw.etl_controle_carga`;
- relatório técnico em `logs/validacao_YYYYMMDD_HHMMSS.log`;
- mensagens de progresso no terminal.

Execuções validadas em `2026-09-05`:

| Execução | Modo | Status | Fato extraída | Fato carregada no escopo | Total carregado no escopo |
| --- | --- | --- | ---: | ---: | ---: |
| 1 | `full` | `success` | 356124 | 356124 | 868627720.16 |
| 2 | `incremental` | `success` | 4008 | 4008 | 9614493.69 |

Na segunda execução, o modo `auto` identificou a existência da fato compatível no DW e aplicou incremental com janela de 30 dias.

## Observações de Mercado

O full refresh é útil para carga inicial, reconstrução controlada ou ambientes pequenos. Em operação recorrente, a fato deve usar incremental para reduzir custo, tempo de processamento e risco operacional.

Como o banco de origem deste business case não possui coluna de atualização, o projeto usa incremental por janela de reprocessamento. Em uma empresa, se existisse `updated_at`, CDC ou logs transacionais, esses mecanismos seriam preferíveis para capturar alterações com maior precisão.
