"""Regras de negócio do Financeiro: contas a pagar, pagamentos e despesas avulsas."""
from datetime import date

from config import MAX_PARCELAS
from db.connection import execute, fetch_all, fetch_one, transaction
from services.excecoes import RegraDeNegocioError, traduzir_erros_banco
from services.validadores import escapar_like, valor_monetario
from utils.calculos import CENTAVO, dividir_em_parcelas
from utils.datas import hoje, momento_da_data, somar_meses

ORIGENS = {"COMPRA": "Compra", "TROCA": "Troca ou devolução", "AVULSA": "Despesa avulsa"}
SITUACOES = {"ABERTA": "Aberta", "VENCIDA": "Vencida", "PAGA": "Paga", "CANCELADA": "Cancelada"}

# Categorias de despesa geradas pelo próprio sistema; não servem para despesas avulsas
_CATEGORIAS_DO_SISTEMA = ("Compra de Mercadorias", "Estornos e Devoluções")
_TAMANHO_DESCRICAO = 200
_TAMANHO_DESCRICAO_BASE = 150  # deixa espaço para o sufixo " (12/12)"

_FROM = """
    FROM contas_pagar p
    JOIN categorias_financeiras cat ON cat.id = p.categoria_id
    LEFT JOIN fornecedores f ON f.id = p.fornecedor_id
    LEFT JOIN clientes cli ON cli.id = p.cliente_id
    LEFT JOIN contas_financeiras cf ON cf.id = p.conta_financeira_id
"""
_ORIGEM_SQL = (
    "CASE WHEN p.compra_id IS NOT NULL THEN 'COMPRA' "
    "WHEN p.troca_devolucao_id IS NOT NULL THEN 'TROCA' ELSE 'AVULSA' END"
)
_DATA_ORIGEM_SQL = """
    COALESCE(
        (SELECT (co.data_recebimento AT TIME ZONE 'America/Recife')::date
           FROM compras co WHERE co.id = p.compra_id),
        (SELECT (t.data AT TIME ZONE 'America/Recife')::date
           FROM trocas_devolucoes t WHERE t.id = p.troca_devolucao_id)
    )
"""


def _filtros(situacao, origem, categoria_id, busca, venc_de, venc_ate) -> tuple[str, list]:
    condicoes, params = [], []
    if situacao == "VENCIDA":
        condicoes.append("(p.status = 'ABERTA' AND p.data_vencimento < %s)")
        params.append(hoje())
    elif situacao == "ABERTA":
        condicoes.append("(p.status = 'ABERTA' AND p.data_vencimento >= %s)")
        params.append(hoje())
    elif situacao in ("PAGA", "CANCELADA"):
        condicoes.append("p.status = %s")
        params.append(situacao)
    if origem == "COMPRA":
        condicoes.append("p.compra_id IS NOT NULL")
    elif origem == "TROCA":
        condicoes.append("p.troca_devolucao_id IS NOT NULL")
    elif origem == "AVULSA":
        condicoes.append("(p.compra_id IS NULL AND p.troca_devolucao_id IS NULL)")
    if categoria_id is not None:
        condicoes.append("p.categoria_id = %s")
        params.append(categoria_id)
    if busca and busca.strip():
        like = f"%{escapar_like(busca.strip())}%"
        condicoes.append("(p.descricao ILIKE %s OR f.razao_social ILIKE %s OR cli.nome ILIKE %s)")
        params += [like, like, like]
    if venc_de:
        condicoes.append("p.data_vencimento >= %s")
        params.append(venc_de)
    if venc_ate:
        condicoes.append("p.data_vencimento <= %s")
        params.append(venc_ate)
    return (("WHERE " + " AND ".join(condicoes)) if condicoes else ""), params


def listar(
    situacao: str | None = None,
    origem: str | None = None,
    categoria_id: int | None = None,
    busca: str | None = None,
    venc_de: date | None = None,
    venc_ate: date | None = None,
    limite: int = 500,
) -> list[dict]:
    where, params = _filtros(situacao, origem, categoria_id, busca, venc_de, venc_ate)
    return fetch_all(
        f"""
        SELECT p.id, p.descricao, p.num_parcela, p.total_parcelas, p.valor, p.data_vencimento,
               p.data_pagamento, p.status,
               CASE WHEN p.status = 'ABERTA' AND p.data_vencimento < %s
                    THEN 'VENCIDA' ELSE p.status END AS situacao,
               {_ORIGEM_SQL} AS origem, p.compra_id, p.troca_devolucao_id,
               cat.nome AS categoria, COALESCE(f.razao_social, cli.nome) AS favorecido,
               cf.nome AS conta
          {_FROM}
          {where}
         ORDER BY (p.status <> 'ABERTA'),
                  CASE WHEN p.status = 'ABERTA' THEN p.data_vencimento END,
                  p.data_vencimento DESC, p.id DESC
         LIMIT %s
        """,
        [hoje()] + params + [limite],
    )


def resumo(situacao=None, origem=None, categoria_id=None, busca=None, venc_de=None, venc_ate=None) -> dict:
    """Totais do filtro (sem limite de linhas): a vencer, vencido, pago e quantidade."""
    where, params = _filtros(situacao, origem, categoria_id, busca, venc_de, venc_ate)
    return fetch_one(
        f"""
        SELECT COALESCE(SUM(p.valor) FILTER (WHERE p.status = 'ABERTA' AND p.data_vencimento >= %s), 0) AS a_vencer,
               COALESCE(SUM(p.valor) FILTER (WHERE p.status = 'ABERTA' AND p.data_vencimento < %s), 0) AS vencido,
               COALESCE(SUM(p.valor) FILTER (WHERE p.status = 'PAGA'), 0) AS pago,
               count(*) AS total
          {_FROM}
          {where}
        """,
        [hoje(), hoje()] + params,
    )


def buscar(conta_id: int) -> dict | None:
    return fetch_one(
        f"""
        SELECT p.id, p.descricao, p.num_parcela, p.total_parcelas, p.valor, p.data_vencimento,
               p.data_pagamento, p.status, p.categoria_id, p.fornecedor_id, p.cliente_id,
               CASE WHEN p.status = 'ABERTA' AND p.data_vencimento < %s
                    THEN 'VENCIDA' ELSE p.status END AS situacao,
               {_ORIGEM_SQL} AS origem, p.compra_id, p.troca_devolucao_id,
               cat.nome AS categoria, COALESCE(f.razao_social, cli.nome) AS favorecido,
               cf.nome AS conta, {_DATA_ORIGEM_SQL} AS data_origem
          {_FROM}
         WHERE p.id = %s
        """,
        (hoje(), conta_id),
    )


def listar_categorias() -> list[dict]:
    """Todas as categorias de despesa, inclusive as do sistema (para filtros)."""
    return fetch_all(
        "SELECT id, nome FROM categorias_financeiras WHERE tipo = 'DESPESA' ORDER BY nome"
    )


def listar_categorias_despesa() -> list[dict]:
    """Categorias de despesa ativas que podem ser usadas em despesas avulsas."""
    return fetch_all(
        "SELECT id, nome FROM categorias_financeiras "
        "WHERE tipo = 'DESPESA' AND ativa AND nome <> ALL(%s) ORDER BY nome",
        (list(_CATEGORIAS_DO_SISTEMA),),
    )


def _validar_despesa_comum(conn, descricao, categoria_id, fornecedor_id, limite_descricao: int):
    descricao = " ".join((descricao or "").split())
    if len(descricao) < 3:
        raise RegraDeNegocioError("Informe a descrição da despesa (mínimo 3 caracteres).")
    if len(descricao) > limite_descricao:
        raise RegraDeNegocioError(f"A descrição deve ter no máximo {limite_descricao} caracteres.")
    categoria = fetch_one(
        "SELECT ativa, tipo, nome FROM categorias_financeiras WHERE id = %s", (categoria_id,), conn
    )
    if not categoria or categoria["tipo"] != "DESPESA" or categoria["nome"] in _CATEGORIAS_DO_SISTEMA:
        raise RegraDeNegocioError("Selecione uma categoria de despesa.")
    if not categoria["ativa"]:
        raise RegraDeNegocioError("A categoria selecionada está inativa.")
    if fornecedor_id is not None:
        fornecedor = fetch_one("SELECT ativo FROM fornecedores WHERE id = %s", (fornecedor_id,), conn)
        if not fornecedor:
            raise RegraDeNegocioError("Fornecedor não encontrado.")
        if not fornecedor["ativo"]:
            raise RegraDeNegocioError("O fornecedor selecionado está inativo.")
    return descricao


def criar_despesa(
    descricao: str,
    categoria_id: int,
    fornecedor_id: int | None,
    valor_total,
    num_parcelas: int,
    primeiro_vencimento: date,
) -> list[int]:
    """Cria a despesa avulsa em N parcelas mensais. Devolve os ids das contas geradas."""
    total = valor_monetario(valor_total, "valor da despesa")
    try:
        parcelas = int(num_parcelas)
    except (TypeError, ValueError):
        raise RegraDeNegocioError("Informe o número de parcelas.")
    if not 1 <= parcelas <= MAX_PARCELAS:
        raise RegraDeNegocioError(f"O número de parcelas deve estar entre 1 e {MAX_PARCELAS}.")
    if not isinstance(primeiro_vencimento, date):
        raise RegraDeNegocioError("Informe o vencimento.")
    if total < CENTAVO * parcelas:
        raise RegraDeNegocioError("O valor total é insuficiente para o número de parcelas.")

    with traduzir_erros_banco(), transaction() as conn:
        descricao = _validar_despesa_comum(
            conn, descricao, categoria_id, fornecedor_id, _TAMANHO_DESCRICAO_BASE
        )
        ids = []
        for numero, valor in enumerate(dividir_em_parcelas(total, parcelas), start=1):
            texto = f"{descricao} ({numero}/{parcelas})" if parcelas > 1 else descricao
            ids.append(
                fetch_one(
                    "INSERT INTO contas_pagar (fornecedor_id, categoria_id, descricao, num_parcela, "
                    "total_parcelas, valor, data_vencimento) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
                    (
                        fornecedor_id,
                        categoria_id,
                        texto,
                        numero,
                        parcelas,
                        valor,
                        somar_meses(primeiro_vencimento, numero - 1),
                    ),
                    conn,
                )["id"]
            )
        return ids


def _travar_despesa_aberta(conn, conta_id: int, acao: str) -> dict:
    conta = fetch_one(
        "SELECT id, status, compra_id, troca_devolucao_id FROM contas_pagar WHERE id = %s FOR UPDATE",
        (conta_id,),
        conn,
    )
    if not conta:
        raise RegraDeNegocioError("Conta a pagar não encontrada.")
    if conta["compra_id"] is not None or conta["troca_devolucao_id"] is not None:
        raise RegraDeNegocioError(f"Somente despesas avulsas podem ser {acao}.")
    if conta["status"] != "ABERTA":
        raise RegraDeNegocioError(f"Somente despesas em aberto podem ser {acao}.")
    return conta


def atualizar_despesa(
    conta_id: int,
    descricao: str,
    categoria_id: int,
    fornecedor_id: int | None,
    valor,
    vencimento: date,
) -> None:
    novo_valor = valor_monetario(valor, "valor da despesa")
    if not isinstance(vencimento, date):
        raise RegraDeNegocioError("Informe o vencimento.")
    with traduzir_erros_banco(), transaction() as conn:
        _travar_despesa_aberta(conn, conta_id, "editadas")
        descricao = _validar_despesa_comum(
            conn, descricao, categoria_id, fornecedor_id, _TAMANHO_DESCRICAO
        )
        execute(
            "UPDATE contas_pagar SET descricao = %s, categoria_id = %s, fornecedor_id = %s, "
            "valor = %s, data_vencimento = %s WHERE id = %s",
            (descricao, categoria_id, fornecedor_id, novo_valor, vencimento, conta_id),
            conn,
        )


def cancelar_despesa(conta_id: int) -> None:
    with traduzir_erros_banco(), transaction() as conn:
        _travar_despesa_aberta(conn, conta_id, "canceladas")
        execute("UPDATE contas_pagar SET status = 'CANCELADA' WHERE id = %s", (conta_id,), conn)


def pagar(conta_id: int, conta_financeira_id: int, data_pagamento: date, usuario_id: int) -> dict:
    """Baixa a conta: registra a saída na conta financeira e marca como paga (uma única vez)."""
    if not isinstance(data_pagamento, date) or data_pagamento > hoje():
        raise RegraDeNegocioError("A data do pagamento não pode ser futura.")
    with traduzir_erros_banco(), transaction() as conn:
        conta = fetch_one(
            f"SELECT p.id, p.status, p.valor, p.descricao, {_DATA_ORIGEM_SQL} AS data_origem "
            "FROM contas_pagar p WHERE p.id = %s FOR UPDATE OF p",
            (conta_id,),
            conn,
        )
        if not conta:
            raise RegraDeNegocioError("Conta a pagar não encontrada.")
        if conta["status"] == "PAGA":
            raise RegraDeNegocioError("Esta conta já foi paga.")
        if conta["status"] != "ABERTA":
            raise RegraDeNegocioError("Esta conta está cancelada.")
        if conta["data_origem"] and data_pagamento < conta["data_origem"]:
            raise RegraDeNegocioError(
                "A data do pagamento não pode ser anterior à origem da conta "
                f"({conta['data_origem']:%d/%m/%Y})."
            )
        financeira = fetch_one(
            "SELECT ativa FROM contas_financeiras WHERE id = %s", (conta_financeira_id,), conn
        )
        if not financeira:
            raise RegraDeNegocioError("Selecione a conta financeira do pagamento.")
        if not financeira["ativa"]:
            raise RegraDeNegocioError("A conta financeira selecionada está inativa.")

        momento = momento_da_data(data_pagamento)
        execute(
            "INSERT INTO movimentacoes_financeiras (conta_financeira_id, tipo, valor, data_movimento, "
            "conta_pagar_id, descricao, usuario_id) VALUES (%s, 'SAIDA', %s, %s, %s, %s, %s)",
            (conta_financeira_id, conta["valor"], momento, conta_id, conta["descricao"], usuario_id),
            conn,
        )
        execute(
            "UPDATE contas_pagar SET status = 'PAGA', data_pagamento = %s, conta_financeira_id = %s "
            "WHERE id = %s",
            (momento, conta_financeira_id, conta_id),
            conn,
        )
    return {"valor": conta["valor"]}
