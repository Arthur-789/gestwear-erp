"""Regras de negócio do Financeiro: contas a receber e recebimentos."""
from datetime import date

from db.connection import execute, fetch_all, fetch_one, transaction
from services.excecoes import RegraDeNegocioError, traduzir_erros_banco
from services.validadores import escapar_like
from utils.datas import hoje, momento_da_data

ORIGENS = {"VENDA": "Venda", "TROCA": "Troca"}
SITUACOES = {"ABERTA": "Aberta", "VENCIDA": "Vencida", "RECEBIDA": "Recebida", "CANCELADA": "Cancelada"}

_FROM = """
    FROM contas_receber r
    JOIN categorias_financeiras cat ON cat.id = r.categoria_id
    LEFT JOIN clientes cli ON cli.id = r.cliente_id
    LEFT JOIN contas_financeiras cf ON cf.id = r.conta_financeira_id
"""
_DATA_ORIGEM_SQL = """
    COALESCE(
        (SELECT (v.data_venda AT TIME ZONE 'America/Recife')::date
           FROM vendas v WHERE v.id = r.venda_id),
        (SELECT (t.data AT TIME ZONE 'America/Recife')::date
           FROM trocas_devolucoes t WHERE t.id = r.troca_devolucao_id)
    )
"""


def _filtros(situacao, origem, cliente_id, busca, venc_de, venc_ate) -> tuple[str, list]:
    condicoes, params = [], []
    if situacao == "VENCIDA":
        condicoes.append("(r.status = 'ABERTA' AND r.data_vencimento < %s)")
        params.append(hoje())
    elif situacao == "ABERTA":
        condicoes.append("(r.status = 'ABERTA' AND r.data_vencimento >= %s)")
        params.append(hoje())
    elif situacao in ("RECEBIDA", "CANCELADA"):
        condicoes.append("r.status = %s")
        params.append(situacao)
    if origem == "VENDA":
        condicoes.append("r.venda_id IS NOT NULL")
    elif origem == "TROCA":
        condicoes.append("r.troca_devolucao_id IS NOT NULL")
    if cliente_id is not None:
        condicoes.append("r.cliente_id = %s")
        params.append(cliente_id)
    if busca and busca.strip():
        condicoes.append("cli.nome ILIKE %s")
        params.append(f"%{escapar_like(busca.strip())}%")
    if venc_de:
        condicoes.append("r.data_vencimento >= %s")
        params.append(venc_de)
    if venc_ate:
        condicoes.append("r.data_vencimento <= %s")
        params.append(venc_ate)
    return (("WHERE " + " AND ".join(condicoes)) if condicoes else ""), params


def listar(
    situacao: str | None = None,
    origem: str | None = None,
    cliente_id: int | None = None,
    busca: str | None = None,
    venc_de: date | None = None,
    venc_ate: date | None = None,
    limite: int = 500,
) -> list[dict]:
    where, params = _filtros(situacao, origem, cliente_id, busca, venc_de, venc_ate)
    return fetch_all(
        f"""
        SELECT r.id, r.venda_id, r.troca_devolucao_id, r.num_parcela, r.total_parcelas, r.valor,
               r.data_vencimento, r.data_recebimento, r.status,
               CASE WHEN r.status = 'ABERTA' AND r.data_vencimento < %s
                    THEN 'VENCIDA' ELSE r.status END AS situacao,
               cat.nome AS categoria, cli.nome AS cliente, cf.nome AS conta
          {_FROM}
          {where}
         ORDER BY (r.status <> 'ABERTA'),
                  CASE WHEN r.status = 'ABERTA' THEN r.data_vencimento END,
                  r.data_vencimento DESC, r.id DESC
         LIMIT %s
        """,
        [hoje()] + params + [limite],
    )


def resumo(situacao=None, origem=None, cliente_id=None, busca=None, venc_de=None, venc_ate=None) -> dict:
    """Totais do filtro (sem limite de linhas): a vencer, vencido, recebido e quantidade."""
    where, params = _filtros(situacao, origem, cliente_id, busca, venc_de, venc_ate)
    return fetch_one(
        f"""
        SELECT COALESCE(SUM(r.valor) FILTER (WHERE r.status = 'ABERTA' AND r.data_vencimento >= %s), 0) AS a_vencer,
               COALESCE(SUM(r.valor) FILTER (WHERE r.status = 'ABERTA' AND r.data_vencimento < %s), 0) AS vencido,
               COALESCE(SUM(r.valor) FILTER (WHERE r.status = 'RECEBIDA'), 0) AS recebido,
               count(*) AS total
          {_FROM}
          {where}
        """,
        [hoje(), hoje()] + params,
    )


def buscar(conta_id: int) -> dict | None:
    return fetch_one(
        f"""
        SELECT r.id, r.venda_id, r.troca_devolucao_id, r.num_parcela, r.total_parcelas, r.valor,
               r.data_vencimento, r.data_recebimento, r.status,
               CASE WHEN r.status = 'ABERTA' AND r.data_vencimento < %s
                    THEN 'VENCIDA' ELSE r.status END AS situacao,
               cat.nome AS categoria, cli.nome AS cliente, cf.nome AS conta,
               {_DATA_ORIGEM_SQL} AS data_origem
          {_FROM}
         WHERE r.id = %s
        """,
        (hoje(), conta_id),
    )


def receber(conta_id: int, conta_financeira_id: int, data_recebimento: date, usuario_id: int) -> dict:
    """Baixa a conta: registra a entrada na conta financeira e marca como recebida (uma única vez)."""
    if not isinstance(data_recebimento, date) or data_recebimento > hoje():
        raise RegraDeNegocioError("A data do recebimento não pode ser futura.")
    with traduzir_erros_banco(), transaction() as conn:
        conta = fetch_one(
            f"""
            SELECT r.id, r.status, r.valor, r.venda_id, r.troca_devolucao_id, r.num_parcela,
                   r.total_parcelas, {_DATA_ORIGEM_SQL} AS data_origem
              FROM contas_receber r
             WHERE r.id = %s
               FOR UPDATE OF r
            """,
            (conta_id,),
            conn,
        )
        if not conta:
            raise RegraDeNegocioError("Conta a receber não encontrada.")
        if conta["status"] == "RECEBIDA":
            raise RegraDeNegocioError("Esta conta já foi recebida.")
        if conta["status"] != "ABERTA":
            raise RegraDeNegocioError("Esta conta está cancelada.")
        if conta["data_origem"] and data_recebimento < conta["data_origem"]:
            raise RegraDeNegocioError(
                "A data do recebimento não pode ser anterior à origem da conta "
                f"({conta['data_origem']:%d/%m/%Y})."
            )
        financeira = fetch_one(
            "SELECT ativa FROM contas_financeiras WHERE id = %s", (conta_financeira_id,), conn
        )
        if not financeira:
            raise RegraDeNegocioError("Selecione a conta financeira do recebimento.")
        if not financeira["ativa"]:
            raise RegraDeNegocioError("A conta financeira selecionada está inativa.")

        origem = (
            f"Venda #{conta['venda_id']}" if conta["venda_id"] else f"Troca #{conta['troca_devolucao_id']}"
        )
        descricao = f"Recebimento: {origem} ({conta['num_parcela']}/{conta['total_parcelas']})"
        momento = momento_da_data(data_recebimento)
        execute(
            "INSERT INTO movimentacoes_financeiras (conta_financeira_id, tipo, valor, data_movimento, "
            "conta_receber_id, descricao, usuario_id) VALUES (%s, 'ENTRADA', %s, %s, %s, %s, %s)",
            (conta_financeira_id, conta["valor"], momento, conta_id, descricao, usuario_id),
            conn,
        )
        execute(
            "UPDATE contas_receber SET status = 'RECEBIDA', data_recebimento = %s, "
            "conta_financeira_id = %s WHERE id = %s",
            (momento, conta_financeira_id, conta_id),
            conn,
        )
    return {"valor": conta["valor"]}
