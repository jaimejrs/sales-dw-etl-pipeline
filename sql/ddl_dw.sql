CREATE SCHEMA IF NOT EXISTS dw;
CREATE SCHEMA IF NOT EXISTS dw_staging;

CREATE TABLE IF NOT EXISTS dw.etl_controle_carga (
    id BIGSERIAL PRIMARY KEY,
    pipeline_nome TEXT NOT NULL,
    modo_carga TEXT NOT NULL,
    status TEXT NOT NULL,
    data_inicio_processamento TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    data_fim_processamento TIMESTAMP,
    data_inicio_incremental TIMESTAMP,
    data_fim_incremental TIMESTAMP,
    janela_reprocessamento_dias INTEGER,
    qtd_fato_extraida BIGINT,
    qtd_fato_transformada BIGINT,
    qtd_fato_carregada BIGINT,
    total_valor_extraido NUMERIC(18, 2),
    total_valor_transformado NUMERIC(18, 2),
    total_valor_carregado NUMERIC(18, 2),
    mensagem TEXT
);

CREATE INDEX IF NOT EXISTS idx_etl_controle_carga_pipeline_status
    ON dw.etl_controle_carga (pipeline_nome, status);

DROP TABLE IF EXISTS dw.fato_vendas CASCADE;
DROP TABLE IF EXISTS dw.dim_tempo CASCADE;
DROP TABLE IF EXISTS dw.dim_vendedor CASCADE;
DROP TABLE IF EXISTS dw.dim_cliente CASCADE;
DROP TABLE IF EXISTS dw.dim_forma_pagamento CASCADE;
DROP TABLE IF EXISTS dw.dim_produto CASCADE;

CREATE TABLE dw.dim_produto (
    id_produto BIGINT PRIMARY KEY,
    nome_produto TEXT,
    categoria TEXT,
    valor_venda NUMERIC(18, 2),
    valor_custo NUMERIC(18, 2)
);

CREATE TABLE dw.dim_forma_pagamento (
    id_forma_pagamento BIGINT PRIMARY KEY,
    descricao_forma_pagamento TEXT
);

CREATE TABLE dw.dim_cliente (
    id_cliente BIGINT PRIMARY KEY,
    nome_cliente TEXT,
    tipo_pessoa TEXT,
    cidade TEXT,
    estado TEXT,
    data_cadastro TIMESTAMP
);

CREATE TABLE dw.dim_vendedor (
    id_vendedor BIGINT PRIMARY KEY,
    nome_vendedor TEXT,
    data_cadastro TIMESTAMP
);

CREATE TABLE dw.dim_tempo (
    id_tempo BIGINT PRIMARY KEY,
    data TIMESTAMP,
    ano BIGINT,
    mes BIGINT,
    nome_mes TEXT,
    dia BIGINT,
    dia_semana BIGINT,
    nome_dia_semana TEXT,
    trimestre BIGINT,
    ano_mes TEXT
);

CREATE TABLE dw.fato_vendas (
    id_fato_venda TEXT PRIMARY KEY,
    id_nota_fiscal BIGINT,
    id_item_nota_fiscal BIGINT,
    numero_nf TEXT,
    data_venda TIMESTAMP,
    id_produto BIGINT REFERENCES dw.dim_produto (id_produto),
    id_cliente BIGINT REFERENCES dw.dim_cliente (id_cliente),
    id_vendedor BIGINT REFERENCES dw.dim_vendedor (id_vendedor),
    id_forma_pagamento BIGINT REFERENCES dw.dim_forma_pagamento (id_forma_pagamento),
    quantidade NUMERIC(18, 4),
    valor_unitario NUMERIC(18, 4),
    valor_total_item NUMERIC(18, 4),
    id_tempo BIGINT REFERENCES dw.dim_tempo (id_tempo),
    ano_mes TEXT
);

CREATE INDEX IF NOT EXISTS idx_fato_vendas_id_produto ON dw.fato_vendas (id_produto);
CREATE INDEX IF NOT EXISTS idx_fato_vendas_id_cliente ON dw.fato_vendas (id_cliente);
CREATE INDEX IF NOT EXISTS idx_fato_vendas_id_vendedor ON dw.fato_vendas (id_vendedor);
CREATE INDEX IF NOT EXISTS idx_fato_vendas_id_forma_pagamento ON dw.fato_vendas (id_forma_pagamento);
CREATE INDEX IF NOT EXISTS idx_fato_vendas_id_tempo ON dw.fato_vendas (id_tempo);
