from datetime import datetime

import pandas as pd
from sqlalchemy import text
from src.config import DIMENSION_KEYS, DW_SCHEMA, FACT_FOREIGN_KEYS, LOAD_ORDER, LOG_DIR

def _q(nome):
    return '"' + nome.replace('"', '""') + '"'

def _schema_table(schema, tabela):
    return f"{_q(schema)}.{_q(tabela)}"

def _scalar(conn, query, params=None):
    return conn.execute(text(query), params or {}).scalar()

def _total_valor_item(df):
    if df is None or "valor_total_item" not in df.columns:
        return None
    return float(pd.to_numeric(df["valor_total_item"], errors="coerce").fillna(0).sum())

def _salvar_relatorio(linhas):
    LOG_DIR.mkdir(exist_ok=True)
    caminho = LOG_DIR / f"validacao_{datetime.now():%Y%m%d_%H%M%S}.log"
    caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return caminho

def _escopo_fato(modo_carga, data_inicio_incremental):
    if modo_carga == "incremental":
        if data_inicio_incremental is None:
            raise ValueError("Validação incremental exige data_inicio_incremental.")
        return " WHERE data_venda >= :data_inicio_incremental", {
            "data_inicio_incremental": data_inicio_incremental,
        }

    return "", {}

def validar_carga(
    engine,
    dataframes_esperados=None,
    dataframes_extraidos=None,
    schema_destino=DW_SCHEMA,
    modo_carga="full",
    data_inicio_incremental=None,
):
    modo_carga = modo_carga.lower()
    where_fato, params_fato = _escopo_fato(modo_carga, data_inicio_incremental)
    linhas_relatorio = [
        "Relatório técnico de validação da carga",
        f"Gerado em: {datetime.now():%Y-%m-%d %H:%M:%S}",
        f"Schema validado: {schema_destino}",
        f"Modo de carga: {modo_carga}",
        f"Início da janela incremental: {data_inicio_incremental}",
        "",
    ]

    def registrar(mensagem):
        print(mensagem)
        linhas_relatorio.append(mensagem)

    registrar("Iniciando validação de qualidade de dados...")

    falhas = []
    qtd_fato_carregada = None
    total_dw = 0

    with engine.connect() as conn:
        # 1. Contagem de linhas
        for tabela in LOAD_ORDER:
            query = f"SELECT COUNT(*) FROM {_schema_table(schema_destino, tabela)}"
            count = _scalar(conn, query)
            registrar(f"{tabela}: {count} linhas")
            if count == 0:
                falhas.append(f"{tabela} está vazia")

            comparar_tabela = modo_carga == "full" or tabela == "fato_vendas"
            if dataframes_esperados is not None and tabela in dataframes_esperados and comparar_tabela:
                esperado = len(dataframes_esperados[tabela])
                count_comparacao = count
                if tabela == "fato_vendas" and modo_carga == "incremental":
                    count_comparacao = _scalar(conn, f"""
                        SELECT COUNT(*)
                        FROM {_schema_table(schema_destino, 'fato_vendas')}
                        {where_fato}
                    """, params_fato)
                    registrar(f"fato_vendas no escopo incremental: {count_comparacao} linhas")

                if count_comparacao != esperado:
                    falhas.append(f"{tabela} possui {count_comparacao} linha(s) no escopo validado, esperado {esperado}")

        total_dw = float(_scalar(conn, f"""
            SELECT COALESCE(SUM(valor_total_item), 0)
            FROM {_schema_table(schema_destino, 'fato_vendas')}
            {where_fato}
        """, params_fato))
        qtd_fato_carregada = int(_scalar(conn, f"""
            SELECT COUNT(*)
            FROM {_schema_table(schema_destino, 'fato_vendas')}
            {where_fato}
        """, params_fato))

        # 2. Chaves nulas ou duplicadas nas dimensões
        for tabela, chave in DIMENSION_KEYS.items():
            tabela_qualificada = _schema_table(schema_destino, tabela)
            nulos = _scalar(conn, f"SELECT COUNT(*) FROM {tabela_qualificada} WHERE {_q(chave)} IS NULL")
            duplicadas = _scalar(conn, f"""
                SELECT COUNT(*)
                FROM (
                    SELECT {_q(chave)}
                    FROM {tabela_qualificada}
                    GROUP BY {_q(chave)}
                    HAVING COUNT(*) > 1
                ) duplicidades
            """)
            if nulos:
                falhas.append(f"{tabela}.{chave} possui {nulos} valor(es) nulo(s)")
            if duplicadas:
                falhas.append(f"{tabela}.{chave} possui {duplicadas} chave(s) duplicada(s)")
            
        # 3. Teste de nulos críticos na fato
        query_nulos = f"""
            SELECT COUNT(*)
            FROM {_schema_table(schema_destino, 'fato_vendas')}
            WHERE id_produto IS NULL
               OR id_item_nota_fiscal IS NULL
               OR id_cliente IS NULL
               OR id_vendedor IS NULL
               OR id_forma_pagamento IS NULL
               OR id_tempo IS NULL
               OR data_venda IS NULL
        """
        nulos_fk = _scalar(conn, query_nulos)
        registrar(f"Registros na Fato com chaves de dimensão nulas: {nulos_fk}")
        if nulos_fk:
            falhas.append(f"fato_vendas possui {nulos_fk} registro(s) com chave crítica nula")

        # 4. Integridade referencial da fato contra as dimensões
        for coluna_fato, (tabela_dimensao, coluna_dimensao) in FACT_FOREIGN_KEYS.items():
            orfaos = _scalar(conn, f"""
                SELECT COUNT(*)
                FROM {_schema_table(schema_destino, 'fato_vendas')} fato
                LEFT JOIN {_schema_table(schema_destino, tabela_dimensao)} dimensao
                    ON fato.{_q(coluna_fato)} = dimensao.{_q(coluna_dimensao)}
                WHERE dimensao.{_q(coluna_dimensao)} IS NULL
            """)
            if orfaos:
                falhas.append(
                    f"fato_vendas.{coluna_fato} possui {orfaos} registro(s) sem correspondência em {tabela_dimensao}"
                )

        # 5. Consistência numérica da fato
        valores_invalidos = _scalar(conn, f"""
            SELECT COUNT(*)
            FROM {_schema_table(schema_destino, 'fato_vendas')}
            WHERE quantidade IS NULL
               OR valor_unitario IS NULL
               OR valor_total_item IS NULL
               OR quantidade <= 0
               OR valor_unitario < 0
               OR valor_total_item < 0
        """)
        if valores_invalidos:
            falhas.append(f"fato_vendas possui {valores_invalidos} registro(s) com valores inválidos")

        totais_inconsistentes = _scalar(conn, f"""
            SELECT COUNT(*)
            FROM {_schema_table(schema_destino, 'fato_vendas')}
            WHERE ABS(valor_total_item - (quantidade * valor_unitario)) > 0.01
        """)
        if totais_inconsistentes:
            falhas.append(
                f"fato_vendas possui {totais_inconsistentes} registro(s) com total diferente de quantidade * valor_unitario"
            )

    if dataframes_esperados is not None and "fato_vendas" in dataframes_esperados:
        fato_esperada = dataframes_esperados["fato_vendas"]
        total_esperado = _total_valor_item(fato_esperada)
        registrar(f"fato_vendas esperada no escopo validado: {len(fato_esperada)} linhas")
        registrar(f"Total valor_total_item esperado: {total_esperado:.2f}")
        registrar(f"Total valor_total_item carregado no escopo validado: {total_dw:.2f}")
        if abs(total_dw - total_esperado) > 0.01:
            falhas.append(
                f"Total de valor_total_item no DW ({total_dw:.2f}) difere do esperado ({total_esperado:.2f})"
            )

    if dataframes_extraidos is not None and "fato_vendas" in dataframes_extraidos:
        fato_extraida = dataframes_extraidos["fato_vendas"]
        total_extraido = _total_valor_item(fato_extraida)
        registrar(f"fato_vendas extraída: {len(fato_extraida)} linhas")
        registrar(f"Total valor_total_item extraído: {total_extraido:.2f}")
        if dataframes_esperados is not None and "fato_vendas" in dataframes_esperados:
            diff_linhas = len(fato_extraida) - len(dataframes_esperados["fato_vendas"])
            diff_total = total_extraido - _total_valor_item(dataframes_esperados["fato_vendas"])
            registrar(f"Registros descartados/tratados antes da carga: {diff_linhas}")
            registrar(f"Diferença de valor tratada antes da carga: {diff_total:.2f}")

    if falhas:
        registrar("Falhas encontradas na validação:")
        for falha in falhas:
            registrar(f"- {falha}")
        caminho = _salvar_relatorio(linhas_relatorio)
        print(f"Relatório de validação salvo em: {caminho}")
        raise ValueError("Validação do DW falhou.")

    registrar("OK: Carga validada sem falhas críticas.")
    caminho = _salvar_relatorio(linhas_relatorio)
    print(f"Relatório de validação salvo em: {caminho}")
    return {
        "qtd_fato_carregada": qtd_fato_carregada,
        "total_valor_carregado": total_dw,
        "relatorio_validacao": str(caminho),
    }
