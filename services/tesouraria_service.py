"""Regras de negócio do Financeiro: contas financeiras (caixa e bancos), extrato e conciliação."""
from datetime import date
from decimal import Decimal

from db.connection import execute, fetch_all, fetch_one, transaction
from services.excecoes import RegraDeNegocioError, traduzir_erros_banco
from services.validadores import valor_monetario
from utils.datas import hoje, momento_da_data

TIPOS_CONTA = {"CAIXA": "Caixa", "BANCO": "Banco"}
TIPOS_MOVIMENTO = {"ENTRADA": "Entrada", "SAIDA": "Saída"}

_FUSO_SQL = "'America/Recife'"


def listar_contas(somente_ativas: bool = False) -> list[dict]:
    """Contas financeiras com saldo contábil (todos os movimentos) e saldo conciliado."""
    contas = fetch_all(
        f"""
        SELECT c.id, c.nome, c.tipo, c.saldo_inicial, c.ativa,
               COALESCE(SUM(m.valor) FILTER (WHERE m.tipo = 'ENTRADA'), 0) AS entradas,
               COALESCE(SUM(m.valor) FILTER (WHERE m.tipo = 'SAIDA'), 0) AS saidas,
               COALESCE(SUM(CASE m.tipo WHEN 'ENTRADA' THEN m.valor ELSE -m.valor END)
                        FILTER (WHERE m.conciliado), 0) AS movimento_conciliado,
               count(m.id) AS movimentos,
               count(m.id) FILTER (WHERE NOT m.conciliado) AS pendentes
          FROM contas_financeiras c
          LEFT JOIN movimentacoes_financeiras m ON m.conta_financeira_id = c.id
         {"WHERE c.ativa" if somente_ativas else ""}
         GROUP BY c.id
         ORDER BY c.id
        """
    )
    for conta in contas:
        conta["saldo_atual"] = conta["saldo_inicial"] + conta["entradas"] - conta["saidas"]
        conta["saldo_conciliado"] = conta["saldo_inicial"] + conta["movimento_conciliado"]
    return contas


def _normalizar_nome(nome: str | None) -> str:
    nome = " ".join((nome or "").split())
    if len(nome) < 3:
        raise RegraDeNegocioError("Informe o nome da conta (mínimo 3 caracteres).")
    if len(nome) > 80:
        raise RegraDeNegocioError("O nome da conta deve ter no máximo 80 caracteres.")
    return nome


def _nome_em_uso(conn, nome: str, ignorar_id: int | None = None) -> bool:
    sql, params = "SELECT 1 FROM contas_financeiras WHERE lower(nome) = lower(%s)", [nome]
    if ignorar_id is not None:
        sql += " AND id <> %s"
        params.append(ignorar_id)
    return fetch_one(sql + " LIMIT 1", params, conn) is not None


def criar_conta(nome: str, tipo: str, saldo_inicial) -> int:
    nome = _normalizar_nome(nome)
    if tipo not in TIPOS_CONTA:
        raise RegraDeNegocioError("Selecione o tipo da conta.")
    saldo = valor_monetario(saldo_inicial, "saldo inicial", permitir_zero=True)
    with traduzir_erros_banco(), transaction() as conn:
        if _nome_em_uso(conn, nome):
            raise RegraDeNegocioError("Já existe uma conta com este nome.")
        return fetch_one(
            "INSERT INTO contas_financeiras (nome, tipo, saldo_inicial) VALUES (%s, %s, %s) RETURNING id",
            (nome, tipo, saldo),
            conn,
        )["id"]


def atualizar_conta(conta_id: int, nome: str, ativa: bool, saldo_inicial=None) -> None:
    """Altera nome, situação e (somente sem movimentações) o saldo inicial. O tipo não muda."""
    nome = _normalizar_nome(nome)
    with traduzir_erros_banco(), transaction() as conn:
        conta = fetch_one(
            "SELECT id, tipo, ativa, saldo_inicial FROM contas_financeiras WHERE id = %s FOR UPDATE",
            (conta_id,),
            conn,
        )
        if not conta:
            raise RegraDeNegocioError("Conta não encontrada.")
        if _nome_em_uso(conn, nome, conta_id):
            raise RegraDeNegocioError("Já existe uma conta com este nome.")

        if conta["ativa"] and not ativa:
            outra = fetch_one(
                "SELECT 1 FROM contas_financeiras WHERE tipo = %s AND ativa AND id <> %s LIMIT 1",
                (conta["tipo"], conta_id),
                conn,
            )
            if not outra:
                raise RegraDeNegocioError(
                    f"Mantenha ao menos uma conta ativa do tipo {TIPOS_CONTA[conta['tipo']]}: "
                    "vendas e pagamentos dependem dela."
                )

        novo_saldo = conta["saldo_inicial"]
        if saldo_inicial is not None:
            novo_saldo = valor_monetario(saldo_inicial, "saldo inicial", permitir_zero=True)
            if novo_saldo != conta["saldo_inicial"]:
                movimentos = fetch_one(
                    "SELECT count(*) AS n FROM movimentacoes_financeiras WHERE conta_financeira_id = %s",
                    (conta_id,),
                    conn,
                )["n"]
                if movimentos:
                    raise RegraDeNegocioError(
                        "O saldo inicial só pode ser alterado enquanto a conta não tem movimentações."
                    )
        execute(
            "UPDATE contas_financeiras SET nome = %s, ativa = %s, saldo_inicial = %s WHERE id = %s",
            (nome, ativa, novo_saldo, conta_id),
            conn,
        )


def _filtros_extrato(conta_id, data_inicio, data_fim, conciliado) -> tuple[str, list]:
    condicoes, params = [], []
    if conta_id is not None:
        condicoes.append("m.conta_financeira_id = %s")
        params.append(conta_id)
    if data_inicio:
        condicoes.append(f"(m.data_movimento AT TIME ZONE {_FUSO_SQL})::date >= %s")
        params.append(data_inicio)
    if data_fim:
        condicoes.append(f"(m.data_movimento AT TIME ZONE {_FUSO_SQL})::date <= %s")
        params.append(data_fim)
    if conciliado is not None:
        condicoes.append("m.conciliado = %s")
        params.append(conciliado)
    return (("WHERE " + " AND ".join(condicoes)) if condicoes else ""), params


def extrato(
    conta_id: int | None = None,
    data_inicio: date | None = None,
    data_fim: date | None = None,
    conciliado: bool | None = None,
    limite: int = 500,
) -> list[dict]:
    where, params = _filtros_extrato(conta_id, data_inicio, data_fim, conciliado)
    return fetch_all(
        f"""
        SELECT m.id, m.data_movimento, m.tipo, m.valor, m.descricao, m.conciliado, m.conciliado_em,
               c.nome AS conta, u.nome AS usuario
          FROM movimentacoes_financeiras m
          JOIN contas_financeiras c ON c.id = m.conta_financeira_id
          JOIN usuarios u ON u.id = m.usuario_id
          {where}
         ORDER BY m.data_movimento DESC, m.id DESC
         LIMIT %s
        """,
        params + [limite],
    )


def totais_extrato(
    conta_id: int | None = None,
    data_inicio: date | None = None,
    data_fim: date | None = None,
    conciliado: bool | None = None,
) -> dict:
    where, params = _filtros_extrato(conta_id, data_inicio, data_fim, conciliado)
    return fetch_one(
        f"""
        SELECT COALESCE(SUM(m.valor) FILTER (WHERE m.tipo = 'ENTRADA'), 0) AS entradas,
               COALESCE(SUM(m.valor) FILTER (WHERE m.tipo = 'SAIDA'), 0) AS saidas,
               count(*) AS total
          FROM movimentacoes_financeiras m
          {where}
        """,
        params,
    )


def conciliar(movimento_ids: list[int], data_conciliacao: date) -> int:
    """Marca movimentações como conciliadas. Todas precisam estar pendentes e não ser posteriores à data."""
    ids = sorted({int(i) for i in movimento_ids})
    if not ids:
        raise RegraDeNegocioError("Selecione ao menos uma movimentação.")
    if not isinstance(data_conciliacao, date) or data_conciliacao > hoje():
        raise RegraDeNegocioError("A data da conciliação não pode ser futura.")
    with traduzir_erros_banco(), transaction() as conn:
        movimentos = fetch_all(
            f"SELECT id, conciliado, (data_movimento AT TIME ZONE {_FUSO_SQL})::date AS dia "
            "FROM movimentacoes_financeiras WHERE id = ANY(%s) ORDER BY id FOR UPDATE",
            (ids,),
            conn,
        )
        if len(movimentos) != len(ids):
            raise RegraDeNegocioError("Movimentação não encontrada.")
        if any(m["conciliado"] for m in movimentos):
            raise RegraDeNegocioError("Há movimentações que já estão conciliadas. Atualize a lista.")
        mais_recente = max(m["dia"] for m in movimentos)
        if data_conciliacao < mais_recente:
            raise RegraDeNegocioError(
                "A data da conciliação não pode ser anterior à data de uma das movimentações "
                f"({mais_recente:%d/%m/%Y})."
            )
        execute(
            "UPDATE movimentacoes_financeiras SET conciliado = TRUE, conciliado_em = %s "
            "WHERE id = ANY(%s)",
            (momento_da_data(data_conciliacao), ids),
            conn,
        )
    return len(ids)


def desfazer_conciliacao(movimento_ids: list[int]) -> int:
    ids = sorted({int(i) for i in movimento_ids})
    if not ids:
        raise RegraDeNegocioError("Selecione ao menos uma movimentação.")
    with traduzir_erros_banco(), transaction() as conn:
        movimentos = fetch_all(
            "SELECT id, conciliado FROM movimentacoes_financeiras WHERE id = ANY(%s) ORDER BY id FOR UPDATE",
            (ids,),
            conn,
        )
        if len(movimentos) != len(ids):
            raise RegraDeNegocioError("Movimentação não encontrada.")
        if not all(m["conciliado"] for m in movimentos):
            raise RegraDeNegocioError("Há movimentações que não estão conciliadas. Atualize a lista.")
        execute(
            "UPDATE movimentacoes_financeiras SET conciliado = FALSE, conciliado_em = NULL "
            "WHERE id = ANY(%s)",
            (ids,),
            conn,
        )
    return len(ids)


def saldo_total_ativas() -> Decimal:
    """Saldo contábil somado das contas ativas."""
    return sum((c["saldo_atual"] for c in listar_contas(somente_ativas=True)), Decimal("0.00"))
