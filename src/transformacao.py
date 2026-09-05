import pandas as pd
from pandas.util import hash_pandas_object
from src.config import DIMENSION_KEYS, EXTRACT_TABLES, FACT_REQUIRED_COLUMNS

def gerar_dim_tempo(df_fato):
    # Extrair datas únicas da fato
    datas = pd.to_datetime(df_fato["data_venda"]).dropna().dt.normalize().drop_duplicates()
    df_tempo = pd.DataFrame({"data": datas}).sort_values("data").reset_index(drop=True)
    df_tempo["id_tempo"] = df_tempo["data"].dt.strftime("%Y%m%d").astype("Int64")
    
    # Criar atributos de tempo
    df_tempo["ano"] = df_tempo["data"].dt.year
    df_tempo["mes"] = df_tempo["data"].dt.month
    df_tempo["dia"] = df_tempo["data"].dt.day
    
    # Mapeamento de meses em português
    meses_pt = {1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
                5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
                9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"}
    df_tempo["nome_mes"] = df_tempo["mes"].map(meses_pt)
    
    dias_semana_pt = {
        0: "Segunda-feira",
        1: "Terça-feira",
        2: "Quarta-feira",
        3: "Quinta-feira",
        4: "Sexta-feira",
        5: "Sábado",
        6: "Domingo",
    }
    df_tempo["dia_semana"] = df_tempo["data"].dt.weekday + 1
    df_tempo["nome_dia_semana"] = df_tempo["data"].dt.weekday.map(dias_semana_pt)
    df_tempo["trimestre"] = df_tempo["data"].dt.quarter
    df_tempo["ano_mes"] = df_tempo["data"].dt.strftime("%Y-%m")
    
    colunas = [
        "id_tempo",
        "data",
        "ano",
        "mes",
        "nome_mes",
        "dia",
        "dia_semana",
        "nome_dia_semana",
        "trimestre",
        "ano_mes",
    ]
    return df_tempo[colunas]

def _validar_tabelas_esperadas(dataframes):
    faltantes = [tabela for tabela in EXTRACT_TABLES if tabela not in dataframes]
    if faltantes:
        raise ValueError(f"DataFrames ausentes na transformação: {', '.join(faltantes)}")

def _validar_colunas(df, tabela, colunas):
    faltantes = [coluna for coluna in colunas if coluna not in df.columns]
    if faltantes:
        raise ValueError(f"Colunas ausentes em {tabela}: {', '.join(faltantes)}")

def _converter_colunas_numericas(df, colunas):
    for coluna in colunas:
        if coluna in df.columns:
            df[coluna] = pd.to_numeric(df[coluna], errors="coerce")
    return df

def _converter_colunas_inteiras(df, colunas):
    for coluna in colunas:
        if coluna in df.columns:
            df[coluna] = pd.to_numeric(df[coluna], errors="coerce").astype("Int64")
    return df

def _preencher_texto(df, coluna, valor_padrao):
    if coluna in df.columns:
        df[coluna] = df[coluna].fillna(valor_padrao)
        df[coluna] = df[coluna].replace(r"^\s*$", valor_padrao, regex=True)
    return df

def _remover_duplicidades_dimensao(df, tabela):
    chave = DIMENSION_KEYS[tabela]
    if chave not in df.columns:
        raise ValueError(f"Coluna chave ausente em {tabela}: {chave}")

    antes = len(df)
    colunas_ordenacao = [chave] + [coluna for coluna in df.columns if coluna != chave]
    df = (
        df.dropna(subset=[chave])
        .sort_values(colunas_ordenacao, na_position="last")
        .drop_duplicates(subset=[chave], keep="first")
    )
    removidos = antes - len(df)
    if removidos:
        print(f"Aviso: {removidos} registro(s) duplicado(s) ou sem chave removido(s) de {tabela}.")
    return df.reset_index(drop=True)

def _gerar_id_fato_venda(df_fato):
    colunas_chave = [
        "id_nota_fiscal",
        "id_item_nota_fiscal",
        "numero_nf",
        "id_produto",
        "id_cliente",
        "id_vendedor",
        "id_forma_pagamento",
        "id_tempo",
        "ano_mes",
        "quantidade",
        "valor_unitario",
        "valor_total_item",
    ]
    chave_hash = hash_pandas_object(df_fato[colunas_chave].astype(str), index=False)
    sequencia = df_fato.groupby(chave_hash, sort=False).cumcount().add(1).astype(str)
    df_fato.insert(0, "id_fato_venda", chave_hash.astype("uint64").astype(str) + "-" + sequencia)
    return df_fato

def transformar_dados(dataframes):
    _validar_tabelas_esperadas(dataframes)
    _validar_colunas(dataframes["fato_vendas"], "fato_vendas", FACT_REQUIRED_COLUMNS)

    dataframes = {nome: df.copy() for nome, df in dataframes.items()}

    # Conversões de tipos básicas
    dataframes["fato_vendas"]["data_venda"] = pd.to_datetime(dataframes["fato_vendas"]["data_venda"], errors="coerce")
    dataframes["dim_cliente"]["data_cadastro"] = pd.to_datetime(dataframes["dim_cliente"]["data_cadastro"], errors="coerce")
    dataframes["dim_vendedor"]["data_cadastro"] = pd.to_datetime(dataframes["dim_vendedor"]["data_cadastro"], errors="coerce")

    colunas_fk_fato = [
        "id_nota_fiscal",
        "id_item_nota_fiscal",
        "id_produto",
        "id_cliente",
        "id_vendedor",
        "id_forma_pagamento",
    ]
    dataframes["fato_vendas"] = _converter_colunas_inteiras(dataframes["fato_vendas"], colunas_fk_fato)
    dataframes["fato_vendas"] = _converter_colunas_numericas(
        dataframes["fato_vendas"],
        ["quantidade", "valor_unitario", "valor_total_item"],
    )

    dataframes["dim_produto"] = _preencher_texto(dataframes["dim_produto"], "nome_produto", "Produto sem descrição")
    dataframes["dim_produto"] = _preencher_texto(dataframes["dim_produto"], "categoria", "Sem categoria")
    dataframes["dim_forma_pagamento"] = _preencher_texto(
        dataframes["dim_forma_pagamento"],
        "descricao_forma_pagamento",
        "Forma de pagamento sem descrição",
    )
    dataframes["dim_cliente"] = _preencher_texto(dataframes["dim_cliente"], "nome_cliente", "Cliente sem descrição")
    dataframes["dim_vendedor"] = _preencher_texto(dataframes["dim_vendedor"], "nome_vendedor", "Vendedor sem descrição")

    # Limpeza de nulos críticos na fato
    colunas_criticas = colunas_fk_fato + ["data_venda"]
    antes = len(dataframes["fato_vendas"])
    dataframes["fato_vendas"] = dataframes["fato_vendas"].dropna(subset=colunas_criticas)
    removidos = antes - len(dataframes["fato_vendas"])
    if removidos:
        print(f"Aviso: {removidos} registro(s) removido(s) da fato por nulos críticos.")

    antes = len(dataframes["fato_vendas"])
    dataframes["fato_vendas"] = dataframes["fato_vendas"].drop_duplicates().reset_index(drop=True)
    removidos = antes - len(dataframes["fato_vendas"])
    if removidos:
        print(f"Aviso: {removidos} registro(s) duplicado(s) removido(s) da fato.")

    # Gerar dim_tempo baseada somente na fato limpa.
    dataframes["dim_tempo"] = gerar_dim_tempo(dataframes["fato_vendas"])
    dataframes["fato_vendas"]["id_tempo"] = dataframes["fato_vendas"]["data_venda"].dt.strftime("%Y%m%d").astype("Int64")
    dataframes["fato_vendas"]["ano_mes"] = dataframes["fato_vendas"]["data_venda"].dt.strftime("%Y-%m")

    for tabela, chave in DIMENSION_KEYS.items():
        if tabela == "dim_tempo":
            continue
        dataframes[tabela] = _converter_colunas_inteiras(dataframes[tabela], [chave])
        dataframes[tabela] = _remover_duplicidades_dimensao(dataframes[tabela], tabela)

    dataframes["fato_vendas"] = _gerar_id_fato_venda(
        dataframes["fato_vendas"].sort_values(
            [
                "id_nota_fiscal",
                "id_item_nota_fiscal",
                "id_produto",
                "id_cliente",
                "id_vendedor",
                "id_forma_pagamento",
                "id_tempo",
            ]
        ).reset_index(drop=True)
    )

    return dataframes
