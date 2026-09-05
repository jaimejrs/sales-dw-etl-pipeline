from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import text

from src.config import (
    CONTROL_TABLE,
    DEFAULT_LOOKBACK_DAYS,
    DW_SCHEMA,
    FACT_COLUMNS,
    PIPELINE_NAME,
    STAGING_SCHEMA,
)


@dataclass(frozen=True)
class ContextoCarga:
    modo: str
    data_inicio_incremental: object = None
    data_watermark_anterior: object = None
    janela_reprocessamento_dias: int = DEFAULT_LOOKBACK_DAYS


def _q(nome):
    return '"' + nome.replace('"', '""') + '"'


def _schema_table(schema, tabela):
    return f"{_q(schema)}.{_q(tabela)}"


def preparar_controle_carga(engine, schema_destino=DW_SCHEMA, schema_staging=STAGING_SCHEMA):
    with engine.begin() as conn:
        conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {_q(schema_destino)}"))
        conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {_q(schema_staging)}"))
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS {_schema_table(schema_destino, CONTROL_TABLE)} (
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
            )
        """))
        conn.execute(text(
            f"CREATE INDEX IF NOT EXISTS {_q('idx_etl_controle_carga_pipeline_status')} "
            f"ON {_schema_table(schema_destino, CONTROL_TABLE)} (pipeline_nome, status)"
        ))


def tabela_existe(conn, schema, tabela):
    return bool(conn.execute(text("""
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = :schema
              AND table_name = :tabela
        )
    """), {"schema": schema, "tabela": tabela}).scalar())


def colunas_tabela(conn, schema, tabela):
    return {
        row[0] for row in conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = :schema
              AND table_name = :tabela
        """), {"schema": schema, "tabela": tabela})
    }


def obter_watermark_fato(engine, schema_destino=DW_SCHEMA):
    with engine.connect() as conn:
        if not tabela_existe(conn, schema_destino, "fato_vendas"):
            return None

        colunas_atuais = colunas_tabela(conn, schema_destino, "fato_vendas")
        if not set(FACT_COLUMNS).issubset(colunas_atuais):
            return None

        return conn.execute(text(
            f"SELECT MAX(data_venda) FROM {_schema_table(schema_destino, 'fato_vendas')}"
        )).scalar()


def definir_contexto_carga(engine, modo_solicitado="auto", lookback_days=DEFAULT_LOOKBACK_DAYS, schema_destino=DW_SCHEMA):
    modo_solicitado = (modo_solicitado or "auto").strip().lower()
    if modo_solicitado not in {"auto", "full", "incremental"}:
        raise ValueError("DW_LOAD_MODE deve ser auto, full ou incremental.")

    watermark = obter_watermark_fato(engine, schema_destino)
    if watermark is None:
        if modo_solicitado == "incremental":
            raise ValueError("Carga incremental solicitada, mas a fato ainda não existe ou está incompatível.")

        return ContextoCarga(
            modo="full",
            data_watermark_anterior=watermark,
            janela_reprocessamento_dias=lookback_days,
        )

    if modo_solicitado == "full":
        return ContextoCarga(
            modo="full",
            data_watermark_anterior=watermark,
            janela_reprocessamento_dias=lookback_days,
        )

    data_inicio = watermark - timedelta(days=lookback_days)
    return ContextoCarga(
        modo="incremental",
        data_inicio_incremental=data_inicio,
        data_watermark_anterior=watermark,
        janela_reprocessamento_dias=lookback_days,
    )


def iniciar_carga(engine, contexto, pipeline_nome=PIPELINE_NAME, schema_destino=DW_SCHEMA):
    with engine.begin() as conn:
        return conn.execute(text(f"""
            INSERT INTO {_schema_table(schema_destino, CONTROL_TABLE)} (
                pipeline_nome,
                modo_carga,
                status,
                data_inicio_incremental,
                janela_reprocessamento_dias,
                mensagem
            )
            VALUES (
                :pipeline_nome,
                :modo_carga,
                'running',
                :data_inicio_incremental,
                :janela_reprocessamento_dias,
                :mensagem
            )
            RETURNING id
        """), {
            "pipeline_nome": pipeline_nome,
            "modo_carga": contexto.modo,
            "data_inicio_incremental": contexto.data_inicio_incremental,
            "janela_reprocessamento_dias": contexto.janela_reprocessamento_dias,
            "mensagem": "Carga iniciada.",
        }).scalar_one()


def atualizar_carga_sucesso(engine, id_carga, metricas, schema_destino=DW_SCHEMA):
    if id_carga is None:
        return

    with engine.begin() as conn:
        conn.execute(text(f"""
            UPDATE {_schema_table(schema_destino, CONTROL_TABLE)}
            SET status = 'success',
                data_fim_processamento = CURRENT_TIMESTAMP,
                data_fim_incremental = :data_fim_incremental,
                qtd_fato_extraida = :qtd_fato_extraida,
                qtd_fato_transformada = :qtd_fato_transformada,
                qtd_fato_carregada = :qtd_fato_carregada,
                total_valor_extraido = :total_valor_extraido,
                total_valor_transformado = :total_valor_transformado,
                total_valor_carregado = :total_valor_carregado,
                mensagem = :mensagem
            WHERE id = :id_carga
        """), {
            "id_carga": id_carga,
            "data_fim_incremental": metricas.get("data_fim_incremental"),
            "qtd_fato_extraida": metricas.get("qtd_fato_extraida"),
            "qtd_fato_transformada": metricas.get("qtd_fato_transformada"),
            "qtd_fato_carregada": metricas.get("qtd_fato_carregada"),
            "total_valor_extraido": metricas.get("total_valor_extraido"),
            "total_valor_transformado": metricas.get("total_valor_transformado"),
            "total_valor_carregado": metricas.get("total_valor_carregado"),
            "mensagem": "Carga finalizada com sucesso.",
        })


def atualizar_carga_falha(engine, id_carga, mensagem, schema_destino=DW_SCHEMA):
    if id_carga is None:
        return

    with engine.begin() as conn:
        conn.execute(text(f"""
            UPDATE {_schema_table(schema_destino, CONTROL_TABLE)}
            SET status = 'failed',
                data_fim_processamento = CURRENT_TIMESTAMP,
                mensagem = :mensagem
            WHERE id = :id_carga
        """), {
            "id_carga": id_carga,
            "mensagem": mensagem[:2000],
        })
