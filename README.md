# BCDEDT - Pipeline ETL de Vendas

Pipeline Python para extrair dados do banco operacional PostgreSQL, transformar o modelo relacional de vendas em um modelo dimensional simples e carregar o resultado no schema `dw`.

## Arquitetura

O orquestrador está em `main.py` e executa quatro etapas:

1. Extração dos SQLs em `sql/` para DataFrames.
2. Transformação com padronização de tipos, limpeza de chaves críticas, deduplicação de dimensões e geração da `dim_tempo`.
3. Carga híbrida no DW: full load inicial e incremental recorrente via staging.
4. Validação técnica da carga no DW.

## Tabelas Geradas

- `dw.dim_produto`
- `dw.dim_forma_pagamento`
- `dw.dim_cliente`
- `dw.dim_vendedor`
- `dw.dim_tempo`
- `dw.fato_vendas`

A `fato_vendas` recebe as chaves dimensionais extraídas da origem e a coluna `id_tempo`, derivada de `data_venda` no formato `YYYYMMDD`.

O detalhamento de origem dos campos e regras de transformação está em `docs/modelagem_dw.md`. A documentação técnica completa dos arquivos está em `docs/documentacao_projeto.md`. Um DDL opcional das tabelas finais está em `sql/ddl_dw.sql`.

## Configuração

Crie um ambiente virtual e instale as dependências:

```powershell
python -m venv .venv311
.\.venv311\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Crie o `.env` a partir do exemplo:

```powershell
Copy-Item .env.example .env
```

Preencha usando URLs completas ou variáveis separadas. A origem também aceita o formato pedido no business case:

```env
PG_HOST=host_origem
PG_PORT=5432
PG_DATABASE=banco_origem
PG_USER=usuario_origem
PG_PASSWORD=senha_origem
DW_DATABASE_URL=postgresql+psycopg2://usuario:senha@localhost:5432/banco_dw
```

## Execução

```powershell
python main.py
```

A carga é híbrida:

- `auto`: usa full load quando o DW ainda não existe ou está incompatível; depois passa para incremental.
- `full`: recria as tabelas dimensionais e fato dentro de uma transação.
- `incremental`: extrai a fato por janela de `data_venda`, carrega `dw_staging`, faz upsert das dimensões e reprocessa somente a janela da fato.

Controle pelo `.env`:

```env
DW_LOAD_MODE=auto
DW_INCREMENTAL_LOOKBACK_DAYS=30
```

## Validações

A etapa `validar_carga` verifica:

- contagem de linhas por tabela;
- tabelas vazias;
- chaves nulas ou duplicadas nas dimensões;
- nulos críticos na fato;
- integridade referencial da fato contra as dimensões;
- valores inválidos em `quantidade`, `valor_unitario` e `valor_total_item`;
- consistência de `valor_total_item` contra `quantidade * valor_unitario`.
- registro de auditoria em `dw.etl_controle_carga`.

Falhas críticas encerram a execução com código de erro. Cada execução salva um relatório simples em `logs/validacao_YYYYMMDD_HHMMSS.log`.

## Testes

```powershell
python -m unittest discover -s tests
```

Os testes atuais cobrem a transformação em memória, a limpeza, a `dim_tempo`, as chaves técnicas e a pré-validação de integridade antes da carga.
