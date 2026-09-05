import pandas as pd
from sqlalchemy import text
from src.config import EXTRACT_TABLES, SQL_DIR

def ler_query_do_arquivo(nome_arquivo):
    """Lê o conteúdo de um arquivo .sql dentro da pasta 'sql'"""

    caminho = SQL_DIR / f"{nome_arquivo}.sql"
    if not caminho.exists():
        raise FileNotFoundError(f"Query SQL não encontrada: {caminho}")

    with caminho.open("r", encoding="utf-8") as file:
        return file.read()

def _aplicar_filtro_incremental_fato(query):
    query_sem_ponto_virgula = query.strip().rstrip(";")
    return query_sem_ponto_virgula + "\nWHERE nf.data_venda >= :data_inicio_incremental"

def extrair_dados(engine, data_inicio_incremental=None):
    dataframes = {}
    
    with engine.connect() as conn:
        for tabela in EXTRACT_TABLES:
            query = ler_query_do_arquivo(tabela)
            params = None

            if tabela == "fato_vendas" and data_inicio_incremental is not None:
                query = _aplicar_filtro_incremental_fato(query)
                params = {"data_inicio_incremental": data_inicio_incremental}

            if tabela == "fato_vendas" and data_inicio_incremental is not None:
                print(f"Extraindo {tabela} a partir de {data_inicio_incremental}...")
            else:
                print(f"Extraindo {tabela}...")
            # Executa a query lida do arquivo e guarda no dicionário de DataFrames
            dataframes[tabela] = pd.read_sql(text(query), conn, params=params)
            
    return dataframes
