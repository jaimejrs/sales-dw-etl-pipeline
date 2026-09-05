# Modelagem do Data Warehouse

Este documento registra a origem dos campos, as regras de transformação e as decisões de modelagem aplicadas pela pipeline.

## Decisões Gerais

- O schema de destino é `dw`.
- A carga é híbrida: full load para inicialização/reconstrução e incremental recorrente por janela de `data_venda`.
- O incremental usa `dw_staging` para receber os dados tratados antes de atualizar o DW final.
- A execução é auditada em `dw.etl_controle_carga`.
- As dimensões são carregadas antes da fato.
- No full load, depois da carga são criadas chaves primárias, chaves estrangeiras e índices nas chaves dimensionais da fato.
- No incremental, as dimensões são atualizadas por upsert e a fato é reprocessada somente na janela incremental.
- Registros da fato com chaves críticas nulas são removidos antes da carga.
- Registros exatamente duplicados na fato são removidos antes da carga para evitar duplicidade operacional.
- Registros duplicados nas dimensões são deduplicados pela chave da dimensão, mantendo a primeira ocorrência após ordenação determinística.
- Toda validação gera relatório em `logs/`.

## `dw.dim_produto`

Origem: `vendas.produto` e `vendas.categoria`.

| Campo DW | Origem | Regra |
| --- | --- | --- |
| `id_produto` | `vendas.produto.id` | Chave da dimensão |
| `nome_produto` | `vendas.produto.nome` | Cópia direta |
| `categoria` | `vendas.categoria.descricao` | Enriquecimento por `id_categoria` |
| `valor_venda` | `vendas.produto.valor_venda` | Cópia direta |
| `valor_custo` | `vendas.produto.valor_custo` | Cópia direta |

## `dw.dim_forma_pagamento`

Origem: `vendas.forma_pagamento`.

| Campo DW | Origem | Regra |
| --- | --- | --- |
| `id_forma_pagamento` | `vendas.forma_pagamento.id` | Chave da dimensão |
| `descricao_forma_pagamento` | `vendas.forma_pagamento.descricao` | Cópia direta |

## `dw.dim_cliente`

Origem: `geral.pessoa`, `geral.pessoa_fisica`, `geral.pessoa_juridica`, `geral.endereco`, `geral.bairro`, `geral.cidade` e `geral.estado`.

| Campo DW | Origem | Regra |
| --- | --- | --- |
| `id_cliente` | `geral.pessoa.id` | Chave da dimensão |
| `nome_cliente` | `geral.pessoa_fisica.nome` ou `geral.pessoa_juridica.razao_social` | PF e PJ são unificados |
| `tipo_pessoa` | Regra da consulta | `PF` para pessoa física e `PJ` para pessoa jurídica |
| `cidade` | `geral.cidade.descricao` | Enriquecimento por endereço |
| `estado` | `geral.estado.sigla` | Enriquecimento por endereço |
| `data_cadastro` | `geral.pessoa.data_cadastro` | Convertida para data/hora |

## `dw.dim_vendedor`

Origem: `vendas.nota_fiscal`, `geral.pessoa` e `geral.pessoa_fisica`.

| Campo DW | Origem | Regra |
| --- | --- | --- |
| `id_vendedor` | `geral.pessoa.id` | Chave da dimensão |
| `nome_vendedor` | `geral.pessoa_fisica.nome` | Cópia direta |
| `data_cadastro` | `geral.pessoa.data_cadastro` | Convertida para data/hora |

A dimensão mantém os vendedores que aparecem em `vendas.nota_fiscal.id_vendedor`, que no banco operacional referencia o cadastro de pessoa.

## `dw.dim_tempo`

Origem: datas presentes em `fato_vendas.data_venda` após limpeza da fato.

| Campo DW | Origem | Regra |
| --- | --- | --- |
| `id_tempo` | `data_venda` | Inteiro no formato `YYYYMMDD` |
| `data` | `data_venda` | Data normalizada sem horário |
| `ano` | `data` | Ano |
| `mes` | `data` | Mês numérico |
| `nome_mes` | `mes` | Nome do mês em português |
| `dia` | `data` | Dia do mês |
| `dia_semana` | `data` | Dia da semana de 1 a 7 |
| `nome_dia_semana` | `data` | Nome do dia da semana em português |
| `trimestre` | `data` | Trimestre |
| `ano_mes` | `data` | Texto no formato `YYYY-MM` |

## `dw.fato_vendas`

Origem: `vendas.nota_fiscal` e `vendas.item_nota_fiscal`.

| Campo DW | Origem | Regra |
| --- | --- | --- |
| `id_fato_venda` | Campos da linha da fato | Chave técnica determinística gerada na transformação |
| `id_nota_fiscal` | `vendas.nota_fiscal.id` | Identificador da nota fiscal |
| `id_item_nota_fiscal` | `vendas.item_nota_fiscal.id` | Identificador do item da nota; preserva o grão da fato |
| `numero_nf` | `vendas.nota_fiscal.numero_nf` | Cópia direta |
| `data_venda` | `vendas.nota_fiscal.data_venda` | Convertida para data/hora |
| `id_tempo` | `data_venda` | FK para `dw.dim_tempo` |
| `id_produto` | `vendas.item_nota_fiscal.id_produto` | FK para `dw.dim_produto` |
| `id_cliente` | `vendas.nota_fiscal.id_cliente` | FK para `dw.dim_cliente` |
| `id_vendedor` | `vendas.nota_fiscal.id_vendedor` | FK para `dw.dim_vendedor` |
| `id_forma_pagamento` | `vendas.nota_fiscal.id_forma_pagto` | FK para `dw.dim_forma_pagamento` |
| `quantidade` | `vendas.item_nota_fiscal.quantidade` | Cópia numérica |
| `valor_unitario` | `vendas.item_nota_fiscal.valor_unitario` | Cópia numérica |
| `valor_total_item` | `vendas.item_nota_fiscal.valor_venda_real` | Cópia numérica; validada contra `quantidade * valor_unitario` |
| `ano_mes` | `data_venda` | Campo derivado para conferência temporal no formato `YYYY-MM` |

## Regras de Qualidade

- As chaves de dimensão não podem ser nulas ou duplicadas.
- A fato não pode ter chaves críticas nulas.
- Toda chave dimensional da fato deve existir na dimensão correspondente.
- A quantidade de linhas carregadas na fato deve bater com a fato transformada.
- O total de `valor_total_item` carregado deve bater com a fato transformada.
- O relatório registra também a diferença entre fato extraída e fato transformada, quando houver limpeza.
- `quantidade` deve ser maior que zero.
- `valor_unitario` e `valor_total_item` não podem ser negativos.
- A diferença entre `valor_total_item` e `quantidade * valor_unitario` deve ser menor ou igual a `0.01`.
