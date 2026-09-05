from sqlalchemy import text
from src.config import DIMENSION_KEYS, DW_SCHEMA, FACT_COLUMNS, FACT_FOREIGN_KEYS, LOAD_ORDER, STAGING_SCHEMA

def _q(nome):
    return '"' + nome.replace('"', '""') + '"'

def _schema_table(schema, tabela):
    return f"{_q(schema)}.{_q(tabela)}"

def _validar_dataframes_para_carga(dataframes):
    faltantes = [tabela for tabela in LOAD_ORDER if tabela not in dataframes]
    if faltantes:
        raise ValueError(f"DataFrames ausentes na carga: {', '.join(faltantes)}")

    for tabela, chave in DIMENSION_KEYS.items():
        df = dataframes[tabela]
        if chave not in df.columns:
            raise ValueError(f"Coluna chave ausente em {tabela}: {chave}")
        if df[chave].isna().any():
            raise ValueError(f"Chave nula encontrada em {tabela}.{chave}")
        if df[chave].duplicated().any():
            raise ValueError(f"Chave duplicada encontrada em {tabela}.{chave}")

    if "id_fato_venda" not in dataframes["fato_vendas"].columns:
        raise ValueError("Coluna chave ausente em fato_vendas: id_fato_venda")
    colunas_fato_faltantes = [coluna for coluna in FACT_COLUMNS if coluna not in dataframes["fato_vendas"].columns]
    if colunas_fato_faltantes:
        raise ValueError(f"Colunas ausentes em fato_vendas: {', '.join(colunas_fato_faltantes)}")
    if dataframes["fato_vendas"]["id_item_nota_fiscal"].isna().any():
        raise ValueError("Chave nula encontrada em fato_vendas.id_item_nota_fiscal")
    if dataframes["fato_vendas"]["id_fato_venda"].duplicated().any():
        raise ValueError("Chave duplicada encontrada em fato_vendas.id_fato_venda")

    fato = dataframes["fato_vendas"]
    for coluna_fato, (tabela_dimensao, coluna_dimensao) in FACT_FOREIGN_KEYS.items():
        if coluna_fato not in fato.columns:
            raise ValueError(f"Coluna de FK ausente em fato_vendas: {coluna_fato}")
        if fato[coluna_fato].isna().any():
            raise ValueError(f"Chave nula encontrada em fato_vendas.{coluna_fato}")

        valores_dimensao = set(dataframes[tabela_dimensao][coluna_dimensao].dropna())
        orfaos = fato.loc[~fato[coluna_fato].isin(valores_dimensao), coluna_fato].dropna().unique()
        if len(orfaos):
            amostra = ", ".join(str(valor) for valor in orfaos[:5])
            raise ValueError(
                f"fato_vendas.{coluna_fato} possui valor(es) sem correspondência em "
                f"{tabela_dimensao}: {amostra}"
            )

    colunas_valores = ["quantidade", "valor_unitario", "valor_total_item"]
    faltantes = [coluna for coluna in colunas_valores if coluna not in fato.columns]
    if faltantes:
        raise ValueError(f"Colunas numéricas ausentes em fato_vendas: {', '.join(faltantes)}")

    valores_invalidos = (
        fato["quantidade"].isna()
        | fato["valor_unitario"].isna()
        | fato["valor_total_item"].isna()
        | (fato["quantidade"] <= 0)
        | (fato["valor_unitario"] < 0)
        | (fato["valor_total_item"] < 0)
    )
    if valores_invalidos.any():
        raise ValueError(f"fato_vendas possui {int(valores_invalidos.sum())} registro(s) com valores inválidos")

    totais_inconsistentes = (fato["valor_total_item"] - (fato["quantidade"] * fato["valor_unitario"])).abs() > 0.01
    if totais_inconsistentes.any():
        raise ValueError(
            "fato_vendas possui "
            f"{int(totais_inconsistentes.sum())} registro(s) com total diferente de quantidade * valor_unitario"
        )

def _preparar_schema(conn, schema, tabelas):
    conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {_q(schema)}"))

    # A fato referencia as dimensões, por isso ela é descartada primeiro no full refresh.
    for tabela in reversed(tabelas):
        conn.execute(text(f"DROP TABLE IF EXISTS {_schema_table(schema, tabela)} CASCADE"))

def _aplicar_constraints_dw(conn, schema):
    for tabela, chave in DIMENSION_KEYS.items():
        conn.execute(text(
            f"ALTER TABLE {_schema_table(schema, tabela)} "
            f"ADD CONSTRAINT {_q(f'pk_{tabela}')} PRIMARY KEY ({_q(chave)})"
        ))

    conn.execute(text(
        f"ALTER TABLE {_schema_table(schema, 'fato_vendas')} "
        f"ADD CONSTRAINT {_q('pk_fato_vendas')} PRIMARY KEY ({_q('id_fato_venda')})"
    ))

    for coluna_fato, (tabela_dimensao, coluna_dimensao) in FACT_FOREIGN_KEYS.items():
        conn.execute(text(
            f"ALTER TABLE {_schema_table(schema, 'fato_vendas')} "
            f"ADD CONSTRAINT {_q(f'fk_fato_vendas_{tabela_dimensao}')} "
            f"FOREIGN KEY ({_q(coluna_fato)}) "
            f"REFERENCES {_schema_table(schema, tabela_dimensao)} ({_q(coluna_dimensao)})"
        ))
        conn.execute(text(
            f"CREATE INDEX IF NOT EXISTS {_q(f'idx_fato_vendas_{coluna_fato}')} "
            f"ON {_schema_table(schema, 'fato_vendas')} ({_q(coluna_fato)})"
        ))

def _carregar_dataframe(conn, df, schema, tabela, if_exists="fail"):
    df.to_sql(
        tabela,
        con=conn,
        schema=schema,
        if_exists=if_exists,
        index=False,
        chunksize=5000,
        method="multi",
    )

def _carregar_staging(conn, dataframes, schema_staging):
    conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {_q(schema_staging)}"))

    for tabela in LOAD_ORDER:
        df = dataframes[tabela]
        print(f"Carregando staging {tabela} ({len(df)} linhas)...")
        conn.execute(text(f"DROP TABLE IF EXISTS {_schema_table(schema_staging, tabela)}"))
        _carregar_dataframe(conn, df, schema_staging, tabela)

def _colunas_sql(colunas):
    return ", ".join(_q(coluna) for coluna in colunas)

def _upsert_dimensao(conn, dataframes, tabela, schema_destino, schema_staging):
    chave = DIMENSION_KEYS[tabela]
    colunas = list(dataframes[tabela].columns)
    colunas_nao_chave = [coluna for coluna in colunas if coluna != chave]
    atualizacoes = ", ".join(f"{_q(coluna)} = EXCLUDED.{_q(coluna)}" for coluna in colunas_nao_chave)
    clausula_update = f"DO UPDATE SET {atualizacoes}" if atualizacoes else "DO NOTHING"

    conn.execute(text(f"""
        INSERT INTO {_schema_table(schema_destino, tabela)} ({_colunas_sql(colunas)})
        SELECT {_colunas_sql(colunas)}
        FROM {_schema_table(schema_staging, tabela)}
        ON CONFLICT ({_q(chave)}) {clausula_update}
    """))

def _inserir_fato_da_staging(conn, dataframes, schema_destino, schema_staging):
    colunas = list(dataframes["fato_vendas"].columns)
    conn.execute(text(f"""
        INSERT INTO {_schema_table(schema_destino, 'fato_vendas')} ({_colunas_sql(colunas)})
        SELECT {_colunas_sql(colunas)}
        FROM {_schema_table(schema_staging, 'fato_vendas')}
    """))

def _carregar_full(dataframes, conn, schema_destino):
    _preparar_schema(conn, schema_destino, LOAD_ORDER)

    for tabela in LOAD_ORDER:
        df = dataframes[tabela]
        print(f"Carregando {tabela} ({len(df)} linhas)...")
        _carregar_dataframe(conn, df, schema_destino, tabela)

    _aplicar_constraints_dw(conn, schema_destino)

def _carregar_incremental(dataframes, conn, schema_destino, schema_staging, data_inicio_incremental):
    if data_inicio_incremental is None:
        raise ValueError("Carga incremental exige data_inicio_incremental.")

    _carregar_staging(conn, dataframes, schema_staging)

    for tabela in ["dim_produto", "dim_forma_pagamento", "dim_cliente", "dim_vendedor", "dim_tempo"]:
        print(f"Atualizando dimensão {tabela} via upsert...")
        _upsert_dimensao(conn, dataframes, tabela, schema_destino, schema_staging)

    print(f"Reprocessando fato_vendas a partir de {data_inicio_incremental}...")
    conn.execute(text(
        f"DELETE FROM {_schema_table(schema_destino, 'fato_vendas')} WHERE data_venda >= :data_inicio"
    ), {"data_inicio": data_inicio_incremental})
    _inserir_fato_da_staging(conn, dataframes, schema_destino, schema_staging)

def carregar_dados(
    dataframes,
    engine,
    schema_destino=DW_SCHEMA,
    modo_carga="full",
    data_inicio_incremental=None,
    schema_staging=STAGING_SCHEMA,
):
    _validar_dataframes_para_carga(dataframes)
    modo_carga = modo_carga.lower()

    with engine.begin() as conn:
        if modo_carga == "full":
            _carregar_full(dataframes, conn, schema_destino)
        elif modo_carga == "incremental":
            _carregar_incremental(dataframes, conn, schema_destino, schema_staging, data_inicio_incremental)
        else:
            raise ValueError("modo_carga deve ser full ou incremental.")

    print("Carga concluída com sucesso!")
