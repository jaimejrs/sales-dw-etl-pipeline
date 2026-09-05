import os
import sys
from urllib.parse import quote_plus
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from src.config import DEFAULT_LOOKBACK_DAYS, PROJECT_ROOT
from src.controle_carga import (
    atualizar_carga_falha,
    atualizar_carga_sucesso,
    definir_contexto_carga,
    iniciar_carga,
    preparar_controle_carga,
)
from src.extracao import extrair_dados
from src.transformacao import transformar_dados
from src.carga_dw import carregar_dados
from src.validacao import validar_carga

def _montar_url_postgres(prefixo):
    usuario = os.getenv(f"{prefixo}_USER")
    senha = os.getenv(f"{prefixo}_PASSWORD")
    host = os.getenv(f"{prefixo}_HOST")
    database = os.getenv(f"{prefixo}_DATABASE")
    porta = os.getenv(f"{prefixo}_PORT")

    faltantes = [
        nome for nome, valor in {
            f"{prefixo}_USER": usuario,
            f"{prefixo}_PASSWORD": senha,
            f"{prefixo}_HOST": host,
            f"{prefixo}_DATABASE": database,
        }.items()
        if not valor
    ]
    if faltantes:
        raise ValueError(f"ERRO: variáveis ausentes no .env: {', '.join(faltantes)}")

    porta_url = f":{porta}" if porta else ""
    return (
        "postgresql+psycopg2://"
        f"{quote_plus(usuario)}:{quote_plus(senha)}@{host}{porta_url}/{quote_plus(database)}"
    )

def _obter_url_banco(nome_url, prefixo, descricao):
    url = os.getenv(nome_url)
    if url:
        return url

    try:
        return _montar_url_postgres(prefixo)
    except ValueError as exc:
        raise ValueError(
            f"ERRO: informe {nome_url} ou as variáveis {prefixo}_USER, "
            f"{prefixo}_PASSWORD, {prefixo}_HOST e {prefixo}_DATABASE ({descricao})."
        ) from exc

def _connect_args_postgres():
    timeout = int(os.getenv("DB_CONNECT_TIMEOUT", "10"))
    return {"connect_timeout": timeout}

def get_engines():
    """Lê as variáveis de ambiente e cria as conexões para Origem e Destino."""
    load_dotenv(PROJECT_ROOT / ".env")
    
    URL_ORIGEM = _obter_url_banco("DATABASE_URL", "PG", "banco de origem")
    URL_DESTINO = _obter_url_banco("DW_DATABASE_URL", "DW", "banco de destino")

    engine_origem = create_engine(URL_ORIGEM, pool_pre_ping=True, connect_args=_connect_args_postgres())
    engine_destino = create_engine(URL_DESTINO, pool_pre_ping=True, connect_args=_connect_args_postgres())
    
    return engine_origem, engine_destino

def testar_conexao(engine, nome):
    with engine.connect() as conn:
        banco = conn.execute(text("SELECT current_database();")).scalar()
        print(f"Conexão com {nome} OK: {banco}")

def _total_valor_item(df):
    if df is None or "valor_total_item" not in df.columns:
        return 0
    return float(pd.to_numeric(df["valor_total_item"], errors="coerce").fillna(0).sum())

def _metricas_carga(dados_brutos, dados_transformados, resultado_validacao):
    fato_extraida = dados_brutos.get("fato_vendas")
    fato_transformada = dados_transformados.get("fato_vendas")
    data_fim_incremental = None

    if fato_transformada is not None and not fato_transformada.empty:
        data_fim_incremental = fato_transformada["data_venda"].max()

    return {
        "data_fim_incremental": data_fim_incremental,
        "qtd_fato_extraida": 0 if fato_extraida is None else len(fato_extraida),
        "qtd_fato_transformada": 0 if fato_transformada is None else len(fato_transformada),
        "qtd_fato_carregada": resultado_validacao.get("qtd_fato_carregada"),
        "total_valor_extraido": _total_valor_item(fato_extraida),
        "total_valor_transformado": _total_valor_item(fato_transformada),
        "total_valor_carregado": resultado_validacao.get("total_valor_carregado"),
    }

def _configuracao_carga():
    modo = os.getenv("DW_LOAD_MODE", "auto")
    lookback_days = int(os.getenv("DW_INCREMENTAL_LOOKBACK_DAYS", str(DEFAULT_LOOKBACK_DAYS)))
    if lookback_days < 0:
        raise ValueError("DW_INCREMENTAL_LOOKBACK_DAYS deve ser maior ou igual a zero.")
    return modo, lookback_days

def run_pipeline():
    print("=== INICIANDO PIPELINE DE DADOS ===")
    id_carga = None
    
    # Pega as duas conexões
    engine_origem, engine_destino = get_engines()

    # Teste obrigatório de conexão antes da extração principal.
    testar_conexao(engine_origem, "origem")
    testar_conexao(engine_destino, "destino")

    preparar_controle_carga(engine_destino)
    modo_solicitado, lookback_days = _configuracao_carga()
    contexto = definir_contexto_carga(engine_destino, modo_solicitado, lookback_days)

    print(f"Modo de carga definido: {contexto.modo}")
    if contexto.modo == "incremental":
        print(f"Watermark anterior: {contexto.data_watermark_anterior}")
        print(f"Janela de reprocessamento: {contexto.janela_reprocessamento_dias} dia(s)")
        print(f"Data inicial da extração incremental: {contexto.data_inicio_incremental}")
    
    id_carga = iniciar_carga(engine_destino, contexto)

    try:
        # 1. Extração (Conecta no banco de ORIGEM)
        dados_brutos = extrair_dados(engine_origem, contexto.data_inicio_incremental)
        
        # 2. Transformação (Feito em memória usando o Pandas, não usa banco)
        dados_transformados = transformar_dados(dados_brutos)
        
        # 3. Carga (Conecta no banco de DESTINO)
        carregar_dados(
            dados_transformados,
            engine_destino,
            modo_carga=contexto.modo,
            data_inicio_incremental=contexto.data_inicio_incremental,
        )
        
        # 4. Validação (Conecta no banco de DESTINO para checar se gravou certo)
        resultado_validacao = validar_carga(
            engine_destino,
            dados_transformados,
            dados_brutos,
            modo_carga=contexto.modo,
            data_inicio_incremental=contexto.data_inicio_incremental,
        )

        atualizar_carga_sucesso(
            engine_destino,
            id_carga,
            _metricas_carga(dados_brutos, dados_transformados, resultado_validacao),
        )
    except Exception as exc:
        atualizar_carga_falha(engine_destino, id_carga, str(exc))
        raise
    
    print("\n=== PIPELINE FINALIZADO COM SUCESSO ===")

if __name__ == "__main__":
    try:
        run_pipeline()
    except Exception as e:
        print(f"\nERRO NO PIPELINE: {e}")
        sys.exit(1)
