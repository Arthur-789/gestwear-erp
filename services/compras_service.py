"""Regras de negócio do módulo Compras: pedidos, recebimento e contas a pagar."""
from datetime import date
from decimal import Decimal, InvalidOperation

from db.connection import execute, fetch_all, fetch_one, transaction
from services.excecoes import RegraDeNegocioError, traduzir_erros_banco
from utils.calculos import CENTAVO, calcular_custo_medio, dividir_em_parcelas
from utils.datas import data_local, hoje, momento_da_data, somar_meses

STATUS_COMPRA = {"PEDIDO": "Pedido", "RECEBIDA": "Recebida", "CANCELADA": "Cancelada"}
MAX_PARCELAS = 12
_LIMITE_VALOR = Decimal("10000000000")
_CATEGORIA_FINANCEIRA = "Compra de Mercadorias"


def _decimal(valor, rotulo: str, permitir_zero: bool = False) -> Decimal:
    if valor is None or valor == "":
        raise RegraDeNegocioError(f"Informe {rotulo}.")
    try:
        numero = Decimal(str(valor)).quantize(CENTAVO)
    except (InvalidOperation, ValueError):
        raise RegraDeNegocioError(f"Valor inválido para {rotulo}.")
    if numero < 0 or (numero == 0 and not permitir_zero) or numero >= _LIMITE_VALOR:
        raise RegraDeNegocioError(f"Valor inválido para {rotulo}.")
    return numero


def _validar_itens(conn, itens: list[dict]) -> list[dict]:
    if not itens:
        raise RegraDeNegocioError("Adicione ao menos um item ao pedido.")
    vistos, validos = set(), []
    for item in itens:
        try:
            variacao_id = int(item["variacao_id"])
            quantidade = int(item["quantidade"])
        except (KeyError, TypeError, ValueError):
            raise RegraDeNegocioError("Item inválido no pedido.")
        if quantidade < 1 or quantidade > 100000:
            raise RegraDeNegocioError("A quantidade de cada item deve estar entre 1 e 100000.")
        if variacao_id in vistos:
            raise RegraDeNegocioError("O mesmo SKU não pode aparecer duas vezes no pedido.")
        vistos.add(variacao_id)
        custo = _decimal(item.get("custo_unitario"), "o custo unitário", permitir_zero=True)
        variacao = fetch_one(
            "SELECT v.sku, v.ativo, p.ativo AS produto_ativo FROM produto_variacoes v "
            "JOIN produtos p ON p.id = v.produto_id WHERE v.id = %s",
            (variacao_id,),
            conn,
        )
        if not variacao:
            raise RegraDeNegocioError("SKU não encontrado.")
        if not (variacao["ativo"] and variacao["produto_ativo"]):
            raise RegraDeNegocioError(f"O SKU {variacao['sku']} está inativo.")
        validos.append(
            {"variacao_id": variacao_id, "quantidade": quantidade, "custo_unitario": custo}
        )
    return validos


def _validar_cabecalho(
    conn,
    fornecedor_id: int,
    data_pedido: date,
    num_parcelas: int,
    primeiro_vencimento: date,
    total: Decimal,
    fornecedor_atual_id: int | None = None,
) -> int:
    fornecedor = fetch_one(
        "SELECT ativo FROM fornecedores WHERE id = %s", (fornecedor_id,), conn
    )
    if not fornecedor:
        raise RegraDeNegocioError("Selecione o fornecedor.")
    if not fornecedor["ativo"] and fornecedor_id != fornecedor_atual_id:
        raise RegraDeNegocioError("O fornecedor selecionado está inativo.")
    if not isinstance(data_pedido, date) or data_pedido > hoje():
        raise RegraDeNegocioError("A data do pedido não pode ser futura.")
    try:
        parcelas = int(num_parcelas)
    except (TypeError, ValueError):
        raise RegraDeNegocioError("Informe o número de parcelas.")
    if not 1 <= parcelas <= MAX_PARCELAS:
        raise RegraDeNegocioError(f"O número de parcelas deve estar entre 1 e {MAX_PARCELAS}.")
    if not isinstance(primeiro_vencimento, date) or primeiro_vencimento < data_pedido:
        raise RegraDeNegocioError(
            "O primeiro vencimento não pode ser anterior à data do pedido."
        )
    if total <= 0:
        raise RegraDeNegocioError(
            "O valor total do pedido deve ser maior que zero. Informe o custo unitário dos itens."
        )
    if total < CENTAVO * parcelas:
        raise RegraDeNegocioError("O valor total é insuficiente para o número de parcelas.")
    return parcelas


def _total(itens: list[dict]) -> Decimal:
    return sum((i["quantidade"] * i["custo_unitario"] for i in itens), Decimal("0.00"))


def _gravar_itens(conn, compra_id: int, itens: list[dict]) -> None:
    for item in itens:
        execute(
            "INSERT INTO itens_compra (compra_id, variacao_id, quantidade, custo_unitario) "
            "VALUES (%s, %s, %s, %s)",
            (compra_id, item["variacao_id"], item["quantidade"], item["custo_unitario"]),
            conn,
        )


def criar_pedido(
    fornecedor_id: int,
    data_pedido: date,
    num_parcelas: int,
    primeiro_vencimento: date,
    observacao: str | None,
    itens: list[dict],
    usuario_id: int,
) -> int:
    with traduzir_erros_banco(), transaction() as conn:
        validos = _validar_itens(conn, itens)
        total = _total(validos)
        parcelas = _validar_cabecalho(
            conn, fornecedor_id, data_pedido, num_parcelas, primeiro_vencimento, total
        )
        compra_id = fetch_one(
            "INSERT INTO compras (fornecedor_id, usuario_id, data_pedido, valor_total, "
            "num_parcelas, primeiro_vencimento, observacao) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (
                fornecedor_id,
                usuario_id,
                momento_da_data(data_pedido),
                total,
                parcelas,
                primeiro_vencimento,
                (observacao or "").strip() or None,
            ),
            conn,
        )["id"]
        _gravar_itens(conn, compra_id, validos)
        return compra_id


def atualizar_pedido(
    compra_id: int,
    fornecedor_id: int,
    data_pedido: date,
    num_parcelas: int,
    primeiro_vencimento: date,
    observacao: str | None,
    itens: list[dict],
) -> None:
    with traduzir_erros_banco(), transaction() as conn:
        atual = fetch_one(
            "SELECT status, fornecedor_id FROM compras WHERE id = %s FOR UPDATE", (compra_id,), conn
        )
        if not atual:
            raise RegraDeNegocioError("Pedido não encontrado.")
        if atual["status"] != "PEDIDO":
            raise RegraDeNegocioError("Somente pedidos pendentes podem ser editados.")
        validos = _validar_itens(conn, itens)
        total = _total(validos)
        parcelas = _validar_cabecalho(
            conn, fornecedor_id, data_pedido, num_parcelas, primeiro_vencimento, total,
            fornecedor_atual_id=atual["fornecedor_id"],
        )
        execute("DELETE FROM itens_compra WHERE compra_id = %s", (compra_id,), conn)
        _gravar_itens(conn, compra_id, validos)
        execute(
            "UPDATE compras SET fornecedor_id = %s, data_pedido = %s, valor_total = %s, "
            "num_parcelas = %s, primeiro_vencimento = %s, observacao = %s WHERE id = %s",
            (
                fornecedor_id,
                momento_da_data(data_pedido),
                total,
                parcelas,
                primeiro_vencimento,
                (observacao or "").strip() or None,
                compra_id,
            ),
            conn,
        )


def cancelar_pedido(compra_id: int) -> None:
    with traduzir_erros_banco(), transaction() as conn:
        atual = fetch_one(
            "SELECT status FROM compras WHERE id = %s FOR UPDATE", (compra_id,), conn
        )
        if not atual:
            raise RegraDeNegocioError("Pedido não encontrado.")
        if atual["status"] != "PEDIDO":
            raise RegraDeNegocioError("Somente pedidos pendentes podem ser cancelados.")
        execute("UPDATE compras SET status = 'CANCELADA' WHERE id = %s", (compra_id,), conn)


def receber_compra(compra_id: int, data_recebimento: date, usuario_id: int) -> dict:
    """Recebe a compra: entrada no estoque, novo custo médio e contas a pagar."""
    with traduzir_erros_banco(), transaction() as conn:
        compra = fetch_one(
            """
            SELECT c.id, c.status, c.data_pedido, c.valor_total, c.num_parcelas,
                   c.primeiro_vencimento, c.fornecedor_id, f.razao_social
              FROM compras c JOIN fornecedores f ON f.id = c.fornecedor_id
             WHERE c.id = %s
               FOR UPDATE OF c
            """,
            (compra_id,),
            conn,
        )
        if not compra:
            raise RegraDeNegocioError("Pedido não encontrado.")
        if compra["status"] != "PEDIDO":
            raise RegraDeNegocioError("Somente pedidos pendentes podem ser recebidos.")
        if not isinstance(data_recebimento, date) or data_recebimento > hoje():
            raise RegraDeNegocioError("A data do recebimento não pode ser futura.")
        if data_recebimento < data_local(compra["data_pedido"]):
            raise RegraDeNegocioError(
                "A data do recebimento não pode ser anterior à data do pedido."
            )

        categoria = fetch_one(
            "SELECT id FROM categorias_financeiras WHERE nome = %s", (_CATEGORIA_FINANCEIRA,), conn
        )
        if not categoria:
            raise RegraDeNegocioError(
                f"Categoria financeira '{_CATEGORIA_FINANCEIRA}' não encontrada."
            )

        itens = fetch_all(
            """
            SELECT ic.variacao_id, ic.quantidade, ic.custo_unitario, v.sku,
                   v.ativo AND p.ativo AS ativo
              FROM itens_compra ic
              JOIN produto_variacoes v ON v.id = ic.variacao_id
              JOIN produtos p ON p.id = v.produto_id
             WHERE ic.compra_id = %s
             ORDER BY ic.variacao_id
            """,
            (compra_id,),
            conn,
        )
        inativos = [i["sku"] for i in itens if not i["ativo"]]
        if inativos:
            raise RegraDeNegocioError(
                "Há SKUs inativos no pedido (" + ", ".join(inativos) + "). Edite o pedido."
            )

        momento = momento_da_data(data_recebimento)
        for item in itens:
            variacao = fetch_one(
                "SELECT estoque_atual, custo_medio FROM produto_variacoes WHERE id = %s FOR UPDATE",
                (item["variacao_id"],),
                conn,
            )
            novo_custo = calcular_custo_medio(
                variacao["estoque_atual"], variacao["custo_medio"],
                item["quantidade"], item["custo_unitario"],
            )
            execute(
                "UPDATE produto_variacoes SET custo_medio = %s WHERE id = %s",
                (novo_custo, item["variacao_id"]),
                conn,
            )
            execute(
                "INSERT INTO movimentacoes_estoque "
                "(variacao_id, tipo, quantidade, compra_id, usuario_id, criado_em) "
                "VALUES (%s, 'ENTRADA_COMPRA', %s, %s, %s, %s)",
                (item["variacao_id"], item["quantidade"], compra_id, usuario_id, momento),
                conn,
            )

        execute(
            "UPDATE compras SET status = 'RECEBIDA', data_recebimento = %s WHERE id = %s",
            (momento, compra_id),
            conn,
        )

        valores = dividir_em_parcelas(compra["valor_total"], compra["num_parcelas"])
        for numero, valor in enumerate(valores, start=1):
            execute(
                "INSERT INTO contas_pagar (compra_id, fornecedor_id, categoria_id, descricao, "
                "num_parcela, total_parcelas, valor, data_vencimento) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    compra_id,
                    compra["fornecedor_id"],
                    categoria["id"],
                    f"Compra #{compra_id} - {compra['razao_social']} ({numero}/{len(valores)})",
                    numero,
                    len(valores),
                    valor,
                    somar_meses(compra["primeiro_vencimento"], numero - 1),
                ),
                conn,
            )
    return {"itens": len(itens), "parcelas": len(valores)}


def listar_compras(
    fornecedor_id: int | None = None,
    status: str | None = None,
    data_inicio: date | None = None,
    data_fim: date | None = None,
) -> list[dict]:
    condicoes, params = [], []
    if fornecedor_id is not None:
        condicoes.append("c.fornecedor_id = %s")
        params.append(fornecedor_id)
    if status:
        condicoes.append("c.status = %s")
        params.append(status)
    if data_inicio:
        condicoes.append("(c.data_pedido AT TIME ZONE 'America/Recife')::date >= %s")
        params.append(data_inicio)
    if data_fim:
        condicoes.append("(c.data_pedido AT TIME ZONE 'America/Recife')::date <= %s")
        params.append(data_fim)
    where = ("WHERE " + " AND ".join(condicoes)) if condicoes else ""
    return fetch_all(
        f"""
        SELECT c.id, c.status, c.data_pedido, c.data_recebimento, c.valor_total, c.num_parcelas,
               f.razao_social AS fornecedor, u.nome AS usuario,
               (SELECT count(*) FROM itens_compra i WHERE i.compra_id = c.id) AS itens
          FROM compras c
          JOIN fornecedores f ON f.id = c.fornecedor_id
          JOIN usuarios u ON u.id = c.usuario_id
          {where}
         ORDER BY c.data_pedido DESC, c.id DESC
        """,
        params,
    )


def buscar_compra(compra_id: int) -> dict | None:
    compra = fetch_one(
        """
        SELECT c.id, c.status, c.data_pedido, c.data_recebimento, c.valor_total, c.num_parcelas,
               c.primeiro_vencimento, c.observacao, c.fornecedor_id,
               f.razao_social AS fornecedor, u.nome AS usuario
          FROM compras c
          JOIN fornecedores f ON f.id = c.fornecedor_id
          JOIN usuarios u ON u.id = c.usuario_id
         WHERE c.id = %s
        """,
        (compra_id,),
    )
    if not compra:
        return None
    compra["itens"] = fetch_all(
        """
        SELECT ic.variacao_id, v.sku, p.nome AS produto, t.nome AS tamanho, co.nome AS cor,
               ic.quantidade, ic.custo_unitario, ic.subtotal
          FROM itens_compra ic
          JOIN produto_variacoes v ON v.id = ic.variacao_id
          JOIN produtos p ON p.id = v.produto_id
          JOIN tamanhos t ON t.id = v.tamanho_id
          JOIN cores co ON co.id = v.cor_id
         WHERE ic.compra_id = %s
         ORDER BY p.nome, t.ordem, co.nome
        """,
        (compra_id,),
    )
    compra["parcelas"] = fetch_all(
        "SELECT num_parcela, total_parcelas, valor, data_vencimento, status "
        "FROM contas_pagar WHERE compra_id = %s ORDER BY num_parcela",
        (compra_id,),
    )
    return compra
