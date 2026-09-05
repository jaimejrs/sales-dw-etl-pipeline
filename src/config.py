from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SQL_DIR = PROJECT_ROOT / "sql"
LOG_DIR = PROJECT_ROOT / "logs"
DW_SCHEMA = "dw"
STAGING_SCHEMA = "dw_staging"
PIPELINE_NAME = "pipeline_vendas_dw"
CONTROL_TABLE = "etl_controle_carga"
DEFAULT_LOOKBACK_DAYS = 30

EXTRACT_TABLES = [
    "dim_produto",
    "dim_forma_pagamento",
    "dim_cliente",
    "dim_vendedor",
    "fato_vendas",
]
#É fundamental manter a ordem correta de carga para garantir a integridade referencial das tabelas
LOAD_ORDER = [
    "dim_produto",
    "dim_forma_pagamento",
    "dim_cliente",
    "dim_vendedor",
    "dim_tempo",
    "fato_vendas",
]

DIMENSION_KEYS = {
    "dim_produto": "id_produto",
    "dim_forma_pagamento": "id_forma_pagamento",
    "dim_cliente": "id_cliente",
    "dim_vendedor": "id_vendedor",
    "dim_tempo": "id_tempo",
}

FACT_REQUIRED_COLUMNS = [
    "id_nota_fiscal",
    "id_item_nota_fiscal",
    "data_venda",
    "id_produto",
    "id_cliente",
    "id_vendedor",
    "id_forma_pagamento",
    "quantidade",
    "valor_unitario",
    "valor_total_item",
]

FACT_FOREIGN_KEYS = {
    "id_produto": ("dim_produto", "id_produto"),
    "id_cliente": ("dim_cliente", "id_cliente"),
    "id_vendedor": ("dim_vendedor", "id_vendedor"),
    "id_forma_pagamento": ("dim_forma_pagamento", "id_forma_pagamento"),
    "id_tempo": ("dim_tempo", "id_tempo"),
}

FACT_COLUMNS = [
    "id_fato_venda",
    "id_nota_fiscal",
    "id_item_nota_fiscal",
    "numero_nf",
    "data_venda",
    "id_produto",
    "id_cliente",
    "id_vendedor",
    "id_forma_pagamento",
    "quantidade",
    "valor_unitario",
    "valor_total_item",
    "id_tempo",
    "ano_mes",
]
