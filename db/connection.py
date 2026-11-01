"""Acesso ao PostgreSQL (Supabase) com pool de conexões e transações."""
from contextlib import contextmanager

import psycopg
import streamlit as st
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


def _configurar_conexao(conn: psycopg.Connection) -> None:
    # Fuso da sessão (timestamptz continua sendo armazenado em UTC)
    conn.autocommit = True
    conn.execute("SET TIME ZONE 'America/Recife'")
    conn.autocommit = False


@st.cache_resource(show_spinner=False)
def get_pool() -> ConnectionPool:
    """Pool único por processo, criado na primeira chamada."""
    try:
        url = st.secrets["database"]["url"]
    except Exception as exc:
        raise RuntimeError(
            "Segredo [database] url não configurado em .streamlit/secrets.toml"
        ) from exc

    return ConnectionPool(
        conninfo=url,
        min_size=1,
        max_size=5,
        kwargs={"row_factory": dict_row, "prepare_threshold": None},
        configure=_configurar_conexao,
        check=ConnectionPool.check_connection,
        open=True,
        timeout=15,
    )


@contextmanager
def transaction():
    """Abre uma transação: commit ao sair, rollback se houver exceção.

    Garante que operações que alteram várias tabelas sejam atômicas.
    """
    with get_pool().connection() as conn:
        yield conn


def fetch_all(sql: str, params=None, conn=None) -> list[dict]:
    if conn is not None:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()
    with transaction() as c:
        return fetch_all(sql, params, c)


def fetch_one(sql: str, params=None, conn=None) -> dict | None:
    if conn is not None:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()
    with transaction() as c:
        return fetch_one(sql, params, c)


def execute(sql: str, params=None, conn=None) -> int:
    """Executa INSERT/UPDATE/DELETE e devolve o número de linhas afetadas."""
    if conn is not None:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.rowcount
    with transaction() as c:
        return execute(sql, params, c)
