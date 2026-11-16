"""Lançamentos financeiros gerados por outros módulos (vendas, trocas e devoluções).

Todas as funções recebem a conexão da transação do módulo chamador, para que o
lançamento seja gravado junto com a operação de origem (tudo ou nada).
"""
from datetime import date, datetime
from decimal import Decimal

from db.connection import execute, fetch_one
from services.excecoes import RegraDeNegocioError

# Conta financeira que recebe cada forma de pagamento à vista
_TIPO_CONTA_POR_FORMA = {"DINHEIRO": "CAIXA", "PIX": "BANCO", "DEBITO": "BANCO"}


def categoria_financeira_id(conn, nome: str) -> int:
    categoria = fetch_one("SELECT id FROM categorias_financeiras WHERE nome = %s", (nome,), conn)
    if not categoria:
        raise RegraDeNegocioError(f"Categoria financeira '{nome}' não encontrada.")
    return categoria["id"]


def conta_financeira_id(conn, forma_pagamento: str) -> int:
    """Primeira conta ativa do tipo que recebe a forma de pagamento (Caixa ou Banco)."""
    tipo = _TIPO_CONTA_POR_FORMA[forma_pagamento]
    conta = fetch_one(
        "SELECT id FROM contas_financeiras WHERE tipo = %s AND ativa ORDER BY id LIMIT 1",
        (tipo,),
        conn,
    )
    if not conta:
        raise RegraDeNegocioError(
            "Não há conta financeira ativa do tipo "
            f"{'Caixa' if tipo == 'CAIXA' else 'Banco'} para receber o pagamento."
        )
    return conta["id"]


def receber_a_vista(
    conn,
    *,
    categoria_id: int,
    conta_id: int,
    valor: Decimal,
    momento: datetime,
    vencimento: date,
    descricao: str,
    usuario_id: int,
    cliente_id: int | None = None,
    venda_id: int | None = None,
    troca_devolucao_id: int | None = None,
) -> int:
    """Cria a conta a receber já recebida e a entrada na conta financeira."""
    conta_receber_id = fetch_one(
        "INSERT INTO contas_receber (venda_id, troca_devolucao_id, cliente_id, categoria_id, "
        "num_parcela, total_parcelas, valor, data_vencimento, data_recebimento, "
        "conta_financeira_id, status) "
        "VALUES (%s, %s, %s, %s, 1, 1, %s, %s, %s, %s, 'RECEBIDA') RETURNING id",
        (venda_id, troca_devolucao_id, cliente_id, categoria_id, valor, vencimento, momento, conta_id),
        conn,
    )["id"]
    execute(
        "INSERT INTO movimentacoes_financeiras (conta_financeira_id, tipo, valor, data_movimento, "
        "conta_receber_id, descricao, usuario_id) VALUES (%s, 'ENTRADA', %s, %s, %s, %s, %s)",
        (conta_id, valor, momento, conta_receber_id, descricao, usuario_id),
        conn,
    )
    return conta_receber_id


def criar_estorno_a_pagar(
    conn,
    *,
    troca_devolucao_id: int,
    categoria_id: int,
    valor: Decimal,
    vencimento: date,
    descricao: str,
    cliente_id: int | None = None,
) -> int:
    """Cria a conta a pagar (aberta) do valor a devolver ao cliente."""
    return fetch_one(
        "INSERT INTO contas_pagar (troca_devolucao_id, cliente_id, categoria_id, descricao, "
        "num_parcela, total_parcelas, valor, data_vencimento) "
        "VALUES (%s, %s, %s, %s, 1, 1, %s, %s) RETURNING id",
        (troca_devolucao_id, cliente_id, categoria_id, descricao, valor, vencimento),
        conn,
    )["id"]
