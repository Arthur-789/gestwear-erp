"""Regras de negócio do módulo Vendas: venda de balcão, estoque e contas a receber."""
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from config import (
    DESCONTO_MAX_SEM_APROVACAO,
    MAX_PARCELAS,
    PARCELA_MINIMA_CREDITO,
    PERFIS_GESTAO,
)
from db.connection import execute, fetch_all, fetch_one, transaction
from services import lancamentos_service as lanc
from services.excecoes import RegraDeNegocioError, traduzir_erros_banco
from utils.calculos import CENTAVO, dividir_em_parcelas
from utils.datas import hoje, momento_da_data

FORMAS_PAGAMENTO = {
    "DINHEIRO": "Dinheiro",
    "PIX": "Pix",
    "DEBITO": "Cartão de débito",
    "CREDITO": "Cartão de crédito",
}

_CATEGORIA_FINANCEIRA = "Vendas"
_INTERVALO_PARCELAS_DIAS = 30
_LIMITE_QUANTIDADE = 100000
_LIMITE_VALOR = Decimal("10000000000")


def rotulo_pagamento(forma: str, num_parcelas: int) -> str:
    texto = FORMAS_PAGAMENTO[forma]
    return f"{texto} {num_parcelas}x" if forma == "CREDITO" and num_parcelas > 1 else texto


def _decimal(valor, rotulo: str) -> Decimal:
    if valor is None or valor == "":
        raise RegraDeNegocioError(f"Informe {rotulo}.")
    try:
        numero = Decimal(str(valor)).quantize(CENTAVO)
    except (InvalidOperation, ValueError):
        raise RegraDeNegocioError(f"Valor inválido para {rotulo}.")
    if numero < 0 or numero >= _LIMITE_VALOR:
        raise RegraDeNegocioError(f"Valor inválido para {rotulo}.")
    return numero


def calcular_resumo(
    subtotal,
    desconto,
    forma_pagamento: str,
    num_parcelas,
    perfil: str,
    tem_cliente: bool,
) -> dict:
    """Valida desconto e pagamento e devolve total e parcelas.

    Usada pela interface (prévia) e pela gravação da venda, para que as duas
    apliquem exatamente as mesmas regras.
    """
    subtotal = _decimal(subtotal, "o subtotal")
    if subtotal <= 0:
        raise RegraDeNegocioError("Adicione ao menos um item à venda.")
    desconto = _decimal(desconto, "o desconto")
    if desconto >= subtotal:
        raise RegraDeNegocioError("O desconto deve ser menor que o subtotal da venda.")
    if desconto > subtotal * DESCONTO_MAX_SEM_APROVACAO and perfil not in PERFIS_GESTAO:
        limite = int(DESCONTO_MAX_SEM_APROVACAO * 100)
        raise RegraDeNegocioError(
            f"Desconto acima de {limite}% do subtotal exige aprovação: "
            "somente Gerente ou Administrador pode concluir esta venda."
        )

    if forma_pagamento not in FORMAS_PAGAMENTO:
        raise RegraDeNegocioError("Selecione a forma de pagamento.")
    try:
        parcelas = int(num_parcelas)
    except (TypeError, ValueError):
        raise RegraDeNegocioError("Informe o número de parcelas.")
    if forma_pagamento != "CREDITO":
        parcelas = 1
    if not 1 <= parcelas <= MAX_PARCELAS:
        raise RegraDeNegocioError(f"O número de parcelas deve estar entre 1 e {MAX_PARCELAS}.")

    total = subtotal - desconto
    if parcelas > 1:
        if not tem_cliente:
            raise RegraDeNegocioError("Vendas parceladas exigem a identificação do cliente.")
        valores = dividir_em_parcelas(total, parcelas)
        if min(valores) < PARCELA_MINIMA_CREDITO:
            raise RegraDeNegocioError(
                f"A parcela mínima no crédito é R$ {PARCELA_MINIMA_CREDITO:.2f}. "
                "Reduza o número de parcelas."
            )
    else:
        valores = [total]
    return {
        "subtotal": subtotal,
        "desconto": desconto,
        "total": total,
        "num_parcelas": parcelas,
        "parcelas": valores,
    }


def calcular_vencimentos(data_venda: date, num_parcelas: int) -> list[date]:
    """A parcela i vence 30 x i dias após a venda."""
    return [
        data_venda + timedelta(days=_INTERVALO_PARCELAS_DIAS * numero)
        for numero in range(1, num_parcelas + 1)
    ]


def _validar_itens(itens: list[dict]) -> list[dict]:
    if not itens:
        raise RegraDeNegocioError("Adicione ao menos um item à venda.")
    vistos, validos = set(), []
    for item in itens:
        try:
            variacao_id = int(item["variacao_id"])
            quantidade = int(item["quantidade"])
        except (KeyError, TypeError, ValueError):
            raise RegraDeNegocioError("Item inválido na venda.")
        if quantidade < 1 or quantidade > _LIMITE_QUANTIDADE:
            raise RegraDeNegocioError(
                f"A quantidade de cada item deve estar entre 1 e {_LIMITE_QUANTIDADE}."
            )
        if variacao_id in vistos:
            raise RegraDeNegocioError("O mesmo SKU não pode aparecer duas vezes na venda.")
        vistos.add(variacao_id)
        validos.append(
            {
                "variacao_id": variacao_id,
                "quantidade": quantidade,
                "preco_exibido": item.get("preco_unitario"),
            }
        )
    return sorted(validos, key=lambda i: i["variacao_id"])


def _bloquear_e_conferir_itens(conn, itens: list[dict]) -> list[dict]:
    """Trava as variações (em ordem de id, para evitar deadlock) e confere estoque, preço e situação de cada SKU."""
    conferidos = []
    for item in itens:
        variacao = fetch_one(
            """
            SELECT v.id, v.sku, v.preco_venda, v.custo_medio, v.estoque_atual,
                   v.ativo AND p.ativo AS ativo
              FROM produto_variacoes v
              JOIN produtos p ON p.id = v.produto_id
             WHERE v.id = %s
               FOR UPDATE OF v
            """,
            (item["variacao_id"],),
            conn,
        )
        if not variacao:
            raise RegraDeNegocioError("SKU não encontrado.")
        sku = variacao["sku"]
        if not variacao["ativo"]:
            raise RegraDeNegocioError(f"O SKU {sku} está inativo.")
        if item["quantidade"] > variacao["estoque_atual"]:
            raise RegraDeNegocioError(
                f"Estoque insuficiente para o SKU {sku}: "
                f"disponível {variacao['estoque_atual']}, solicitado {item['quantidade']}."
            )
        exibido = item["preco_exibido"]
        if exibido is not None and Decimal(str(exibido)) != variacao["preco_venda"]:
            raise RegraDeNegocioError(
                f"O preço do SKU {sku} foi alterado para R$ {variacao['preco_venda']:.2f}. "
                "Remova o item e adicione novamente."
            )
        conferidos.append(
            {
                **item,
                "sku": sku,
                "preco_unitario": variacao["preco_venda"],
                "custo_unitario": variacao["custo_medio"],
            }
        )
    return conferidos


def criar_venda(
    cliente_id: int | None,
    data_venda: date,
    desconto,
    forma_pagamento: str,
    num_parcelas: int,
    observacao: str | None,
    itens: list[dict],
    usuario_id: int,
) -> dict:
    """Registra a venda, baixa o estoque e lança o financeiro em uma única transação."""
    itens = _validar_itens(itens)
    if not isinstance(data_venda, date) or data_venda > hoje():
        raise RegraDeNegocioError("A data da venda não pode ser futura.")

    with traduzir_erros_banco(), transaction() as conn:
        operador = fetch_one(
            "SELECT perfil, ativo FROM usuarios WHERE id = %s", (usuario_id,), conn
        )
        if not operador or not operador["ativo"]:
            raise RegraDeNegocioError("Usuário não autorizado a registrar vendas.")

        if cliente_id is not None:
            cliente = fetch_one("SELECT ativo FROM clientes WHERE id = %s", (cliente_id,), conn)
            if not cliente:
                raise RegraDeNegocioError("Cliente não encontrado.")
            if not cliente["ativo"]:
                raise RegraDeNegocioError("O cliente selecionado está inativo.")

        conferidos = _bloquear_e_conferir_itens(conn, itens)
        subtotal = sum(
            (i["quantidade"] * i["preco_unitario"] for i in conferidos), Decimal("0.00")
        )
        resumo = calcular_resumo(
            subtotal, desconto, forma_pagamento, num_parcelas,
            operador["perfil"], cliente_id is not None,
        )

        categoria_id = lanc.categoria_financeira_id(conn, _CATEGORIA_FINANCEIRA)
        conta_id = lanc.conta_financeira_id(conn, forma_pagamento) if forma_pagamento != "CREDITO" else None

        momento = momento_da_data(data_venda)
        venda_id = fetch_one(
            "INSERT INTO vendas (cliente_id, usuario_id, data_venda, subtotal, desconto, "
            "valor_total, forma_pagamento, num_parcelas, observacao) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (
                cliente_id,
                usuario_id,
                momento,
                resumo["subtotal"],
                resumo["desconto"],
                resumo["total"],
                forma_pagamento,
                resumo["num_parcelas"],
                (observacao or "").strip() or None,
            ),
            conn,
        )["id"]

        for item in conferidos:
            execute(
                "INSERT INTO itens_venda (venda_id, variacao_id, quantidade, preco_unitario, "
                "custo_unitario) VALUES (%s, %s, %s, %s, %s)",
                (
                    venda_id,
                    item["variacao_id"],
                    item["quantidade"],
                    item["preco_unitario"],
                    item["custo_unitario"],
                ),
                conn,
            )
            execute(
                "INSERT INTO movimentacoes_estoque "
                "(variacao_id, tipo, quantidade, venda_id, usuario_id, criado_em) "
                "VALUES (%s, 'SAIDA_VENDA', %s, %s, %s, %s)",
                (item["variacao_id"], -item["quantidade"], venda_id, usuario_id, momento),
                conn,
            )

        if forma_pagamento == "CREDITO":
            vencimentos = calcular_vencimentos(data_venda, resumo["num_parcelas"])
            for numero, (valor, vencimento) in enumerate(
                zip(resumo["parcelas"], vencimentos), start=1
            ):
                execute(
                    "INSERT INTO contas_receber (venda_id, cliente_id, categoria_id, num_parcela, "
                    "total_parcelas, valor, data_vencimento) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (
                        venda_id,
                        cliente_id,
                        categoria_id,
                        numero,
                        resumo["num_parcelas"],
                        valor,
                        vencimento,
                    ),
                    conn,
                )
        else:
            # Recebimento imediato, já com a movimentação na conta financeira
            lanc.receber_a_vista(
                conn,
                categoria_id=categoria_id,
                conta_id=conta_id,
                valor=resumo["total"],
                momento=momento,
                vencimento=data_venda,
                descricao=f"Venda #{venda_id}",
                usuario_id=usuario_id,
                cliente_id=cliente_id,
                venda_id=venda_id,
            )

    return {
        "id": venda_id,
        "valor_total": resumo["total"],
        "num_parcelas": resumo["num_parcelas"],
        "itens": len(conferidos),
    }


def listar_vendas(
    cliente_id: int | None = None,
    forma_pagamento: str | None = None,
    data_inicio: date | None = None,
    data_fim: date | None = None,
    limite: int = 500,
) -> list[dict]:
    condicoes, params = [], []
    if cliente_id is not None:
        condicoes.append("v.cliente_id = %s")
        params.append(cliente_id)
    if forma_pagamento:
        condicoes.append("v.forma_pagamento = %s")
        params.append(forma_pagamento)
    if data_inicio:
        condicoes.append("(v.data_venda AT TIME ZONE 'America/Recife')::date >= %s")
        params.append(data_inicio)
    if data_fim:
        condicoes.append("(v.data_venda AT TIME ZONE 'America/Recife')::date <= %s")
        params.append(data_fim)
    where = ("WHERE " + " AND ".join(condicoes)) if condicoes else ""
    return fetch_all(
        f"""
        SELECT v.id, v.data_venda, v.subtotal, v.desconto, v.valor_total, v.forma_pagamento,
               v.num_parcelas, c.nome AS cliente, u.nome AS usuario,
               (SELECT coalesce(sum(i.quantidade), 0) FROM itens_venda i WHERE i.venda_id = v.id)
                   AS unidades
          FROM vendas v
          LEFT JOIN clientes c ON c.id = v.cliente_id
          JOIN usuarios u ON u.id = v.usuario_id
          {where}
         ORDER BY v.data_venda DESC, v.id DESC
         LIMIT %s
        """,
        params + [limite],
    )


def buscar_venda(venda_id: int) -> dict | None:
    venda = fetch_one(
        """
        SELECT v.id, v.data_venda, v.subtotal, v.desconto, v.valor_total, v.forma_pagamento,
               v.num_parcelas, v.observacao, c.nome AS cliente, u.nome AS usuario
          FROM vendas v
          LEFT JOIN clientes c ON c.id = v.cliente_id
          JOIN usuarios u ON u.id = v.usuario_id
         WHERE v.id = %s
        """,
        (venda_id,),
    )
    if not venda:
        return None
    venda["itens"] = fetch_all(
        """
        SELECT i.variacao_id, s.sku, p.nome AS produto, t.nome AS tamanho, co.nome AS cor,
               i.quantidade, i.preco_unitario, i.custo_unitario, i.subtotal,
               i.quantidade_devolvida
          FROM itens_venda i
          JOIN produto_variacoes s ON s.id = i.variacao_id
          JOIN produtos p ON p.id = s.produto_id
          JOIN tamanhos t ON t.id = s.tamanho_id
          JOIN cores co ON co.id = s.cor_id
         WHERE i.venda_id = %s
         ORDER BY p.nome, t.ordem, co.nome
        """,
        (venda_id,),
    )
    venda["parcelas"] = fetch_all(
        """
        SELECT r.num_parcela, r.total_parcelas, r.valor, r.data_vencimento,
               r.data_recebimento, r.status, f.nome AS conta
          FROM contas_receber r
          LEFT JOIN contas_financeiras f ON f.id = r.conta_financeira_id
         WHERE r.venda_id = %s
         ORDER BY r.num_parcela
        """,
        (venda_id,),
    )
    return venda
