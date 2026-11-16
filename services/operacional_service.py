"""Regras de negócio do módulo Operacional: trocas e devoluções de vendas."""
from datetime import date, timedelta
from decimal import Decimal

from config import PRAZO_TROCA_DIAS
from db.connection import execute, fetch_all, fetch_one, transaction
from services import lancamentos_service as lanc
from services.excecoes import RegraDeNegocioError, traduzir_erros_banco
from utils.calculos import valor_unitario_estorno
from utils.datas import data_local, hoje, momento_da_data

TIPOS = {"DEVOLUCAO": "Devolução", "TROCA": "Troca"}
MOTIVOS = {
    "DEFEITO": "Defeito",
    "TAMANHO_INADEQUADO": "Tamanho inadequado",
    "ARREPENDIMENTO": "Arrependimento",
    "OUTRO": "Outro",
}
FORMAS_DIFERENCA = ("DINHEIRO", "PIX", "DEBITO")

_CATEGORIA_ESTORNO = "Estornos e Devoluções"
_CATEGORIA_DIFERENCA = "Diferença de Trocas"
_LIMITE_QUANTIDADE = 100000


def listar_vendas_elegiveis() -> list[dict]:
    """Vendas dentro do prazo de troca que ainda têm itens a devolver."""
    desde = hoje() - timedelta(days=PRAZO_TROCA_DIAS)
    return fetch_all(
        """
        SELECT v.id, v.data_venda, v.valor_total, c.nome AS cliente
          FROM vendas v
          LEFT JOIN clientes c ON c.id = v.cliente_id
         WHERE (v.data_venda AT TIME ZONE 'America/Recife')::date >= %s
           AND EXISTS (SELECT 1 FROM itens_venda i
                        WHERE i.venda_id = v.id AND i.quantidade_devolvida < i.quantidade)
         ORDER BY v.data_venda DESC, v.id DESC
        """,
        (desde,),
    )


def itens_devolviveis(venda_id: int) -> list[dict]:
    """Itens da venda com a quantidade ainda disponível para devolução e o valor de estorno."""
    itens = fetch_all(
        """
        SELECT i.id, i.variacao_id, s.sku, p.nome AS produto, t.nome AS tamanho, co.nome AS cor,
               i.quantidade, i.quantidade_devolvida, i.preco_unitario,
               v.subtotal AS venda_subtotal, v.valor_total AS venda_total
          FROM itens_venda i
          JOIN vendas v ON v.id = i.venda_id
          JOIN produto_variacoes s ON s.id = i.variacao_id
          JOIN produtos p ON p.id = s.produto_id
          JOIN tamanhos t ON t.id = s.tamanho_id
          JOIN cores co ON co.id = s.cor_id
         WHERE i.venda_id = %s
         ORDER BY p.nome, t.ordem, co.nome
        """,
        (venda_id,),
    )
    for item in itens:
        item["disponivel"] = item["quantidade"] - item["quantidade_devolvida"]
        item["valor_unitario"] = valor_unitario_estorno(
            item["preco_unitario"], item["venda_total"], item["venda_subtotal"]
        )
    return itens


def _validar_linhas(linhas: list[dict], chave: str, mensagem_vazio: str) -> list[dict]:
    if not linhas:
        raise RegraDeNegocioError(mensagem_vazio)
    vistos, validas = set(), []
    for linha in linhas:
        try:
            identificador = int(linha[chave])
            quantidade = int(linha["quantidade"])
        except (KeyError, TypeError, ValueError):
            raise RegraDeNegocioError("Item inválido na solicitação.")
        if quantidade < 1 or quantidade > _LIMITE_QUANTIDADE:
            raise RegraDeNegocioError(
                f"A quantidade de cada item deve estar entre 1 e {_LIMITE_QUANTIDADE}."
            )
        if identificador in vistos:
            raise RegraDeNegocioError("O mesmo item não pode aparecer duas vezes na solicitação.")
        vistos.add(identificador)
        validas.append({**linha, chave: identificador, "quantidade": quantidade})
    return sorted(validas, key=lambda i: i[chave])


def _conferir_devolvidos(conn, venda: dict, devolvidos: list[dict], motivo: str) -> list[dict]:
    """Trava os itens da venda e confere a quantidade disponível e calcula o valor de estorno de cada um."""
    conferidos = []
    for devolvido in devolvidos:
        item = fetch_one(
            """
            SELECT i.id, i.variacao_id, i.quantidade, i.quantidade_devolvida, i.preco_unitario,
                   s.sku
              FROM itens_venda i
              JOIN produto_variacoes s ON s.id = i.variacao_id
             WHERE i.id = %s AND i.venda_id = %s
               FOR UPDATE OF i
            """,
            (devolvido["item_venda_id"], venda["id"]),
            conn,
        )
        if not item:
            raise RegraDeNegocioError("O item informado não pertence a esta venda.")
        restante = item["quantidade"] - item["quantidade_devolvida"]
        if devolvido["quantidade"] > restante:
            raise RegraDeNegocioError(
                f"O item {item['sku']} permite devolver no máximo {restante} unidade(s): "
                f"vendidas {item['quantidade']}, já devolvidas {item['quantidade_devolvida']}."
            )
        conferidos.append(
            {
                **item,
                "devolver": devolvido["quantidade"],
                "valor_unitario": valor_unitario_estorno(
                    item["preco_unitario"], venda["valor_total"], venda["subtotal"]
                ),
                # Item com defeito não volta ao estoque
                "retorna_estoque": motivo != "DEFEITO",
            }
        )
    return conferidos


def _conferir_novos(conn, novos: list[dict]) -> list[dict]:
    conferidos = []
    for novo in novos:
        variacao = fetch_one(
            """
            SELECT v.id, v.sku, v.preco_venda, v.custo_medio, v.estoque_atual,
                   v.ativo AND p.ativo AS ativo
              FROM produto_variacoes v
              JOIN produtos p ON p.id = v.produto_id
             WHERE v.id = %s
            """,
            (novo["variacao_id"],),
            conn,
        )
        if not variacao:
            raise RegraDeNegocioError("SKU não encontrado.")
        sku = variacao["sku"]
        if not variacao["ativo"]:
            raise RegraDeNegocioError(f"O SKU {sku} está inativo.")
        if novo["quantidade"] > variacao["estoque_atual"]:
            raise RegraDeNegocioError(
                f"Estoque insuficiente para o SKU {sku}: "
                f"disponível {variacao['estoque_atual']}, solicitado {novo['quantidade']}."
            )
        exibido = novo.get("preco_unitario")
        if exibido is not None and Decimal(str(exibido)) != variacao["preco_venda"]:
            raise RegraDeNegocioError(
                f"O preço do SKU {sku} foi alterado para R$ {variacao['preco_venda']:.2f}. "
                "Remova o item e adicione novamente."
            )
        conferidos.append(
            {
                "variacao_id": variacao["id"],
                "quantidade": novo["quantidade"],
                "preco_unitario": variacao["preco_venda"],
                "custo_unitario": variacao["custo_medio"],
            }
        )
    return conferidos


def registrar(
    venda_id: int,
    tipo: str,
    motivo: str,
    data_operacao: date,
    forma_pagamento_diferenca: str | None,
    observacao: str | None,
    itens_devolvidos: list[dict],
    itens_novos: list[dict],
    usuario_id: int,
) -> dict:
    """Registra a devolução ou troca, movimenta o estoque e lança o financeiro.

    itens_devolvidos: [{"item_venda_id", "quantidade"}]
    itens_novos (somente troca): [{"variacao_id", "quantidade", "preco_unitario" opcional}]
    """
    if tipo not in TIPOS:
        raise RegraDeNegocioError("Selecione o tipo da solicitação.")
    if motivo not in MOTIVOS:
        raise RegraDeNegocioError("Informe o motivo.")
    if not isinstance(data_operacao, date) or data_operacao > hoje():
        raise RegraDeNegocioError("A data não pode ser futura.")
    devolvidos = _validar_linhas(
        itens_devolvidos, "item_venda_id", "Selecione ao menos um item para devolver."
    )
    if tipo == "DEVOLUCAO":
        if itens_novos:
            raise RegraDeNegocioError("Devolução não admite itens novos. Use o tipo Troca.")
        novos = []
    else:
        novos = _validar_linhas(itens_novos, "variacao_id", "Informe os itens novos da troca.")

    with traduzir_erros_banco(), transaction() as conn:
        operador = fetch_one(
            "SELECT ativo FROM usuarios WHERE id = %s", (usuario_id,), conn
        )
        if not operador or not operador["ativo"]:
            raise RegraDeNegocioError("Usuário não autorizado a registrar trocas e devoluções.")

        venda = fetch_one(
            "SELECT id, cliente_id, data_venda, subtotal, valor_total "
            "FROM vendas WHERE id = %s FOR UPDATE",
            (venda_id,),
            conn,
        )
        if not venda:
            raise RegraDeNegocioError("Venda não encontrada.")
        data_venda = data_local(venda["data_venda"])
        if data_operacao < data_venda:
            raise RegraDeNegocioError("A data não pode ser anterior à data da venda.")
        if (data_operacao - data_venda).days > PRAZO_TROCA_DIAS:
            raise RegraDeNegocioError(
                f"O prazo para troca ou devolução é de {PRAZO_TROCA_DIAS} dias após a venda."
            )

        # Travas em ordem de id para evitar deadlock entre operações simultâneas
        conferidos = _conferir_devolvidos(conn, venda, devolvidos, motivo)
        ids_variacoes = sorted({i["variacao_id"] for i in conferidos} | {n["variacao_id"] for n in novos})
        fetch_all(
            "SELECT id FROM produto_variacoes WHERE id = ANY(%s) ORDER BY id FOR UPDATE",
            (ids_variacoes,),
            conn,
        )
        novos = _conferir_novos(conn, novos)

        valor_devolvido = sum((i["devolver"] * i["valor_unitario"] for i in conferidos), Decimal("0.00"))
        if valor_devolvido <= 0:
            raise RegraDeNegocioError("O valor a devolver é zero. Revise os itens selecionados.")
        valor_novos = sum((n["quantidade"] * n["preco_unitario"] for n in novos), Decimal("0.00"))
        diferenca = valor_novos - valor_devolvido

        forma = None
        if diferenca > 0:
            if forma_pagamento_diferenca not in FORMAS_DIFERENCA:
                raise RegraDeNegocioError("Informe a forma de pagamento da diferença.")
            forma = forma_pagamento_diferenca

        momento = momento_da_data(data_operacao)
        troca_id = fetch_one(
            "INSERT INTO trocas_devolucoes (venda_id, usuario_id, tipo, motivo, data, "
            "valor_devolvido, valor_novos, forma_pagamento_diferenca, observacao) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (
                venda_id,
                usuario_id,
                tipo,
                motivo,
                momento,
                valor_devolvido,
                valor_novos,
                forma,
                (observacao or "").strip() or None,
            ),
            conn,
        )["id"]

        for item in conferidos:
            execute(
                "INSERT INTO itens_devolvidos (troca_devolucao_id, item_venda_id, quantidade, "
                "valor_unitario, retorna_estoque) VALUES (%s, %s, %s, %s, %s)",
                (troca_id, item["id"], item["devolver"], item["valor_unitario"], item["retorna_estoque"]),
                conn,
            )
            execute(
                "UPDATE itens_venda SET quantidade_devolvida = quantidade_devolvida + %s WHERE id = %s",
                (item["devolver"], item["id"]),
                conn,
            )
            if item["retorna_estoque"]:
                execute(
                    "INSERT INTO movimentacoes_estoque (variacao_id, tipo, quantidade, "
                    "troca_devolucao_id, usuario_id, criado_em) "
                    "VALUES (%s, 'ENTRADA_DEVOLUCAO', %s, %s, %s, %s)",
                    (item["variacao_id"], item["devolver"], troca_id, usuario_id, momento),
                    conn,
                )

        for novo in novos:
            execute(
                "INSERT INTO itens_novos_troca (troca_devolucao_id, variacao_id, quantidade, "
                "preco_unitario, custo_unitario) VALUES (%s, %s, %s, %s, %s)",
                (troca_id, novo["variacao_id"], novo["quantidade"], novo["preco_unitario"],
                 novo["custo_unitario"]),
                conn,
            )
            execute(
                "INSERT INTO movimentacoes_estoque (variacao_id, tipo, quantidade, "
                "troca_devolucao_id, usuario_id, criado_em) "
                "VALUES (%s, 'SAIDA_TROCA', %s, %s, %s, %s)",
                (novo["variacao_id"], -novo["quantidade"], troca_id, usuario_id, momento),
                conn,
            )

        # Estorno em contas a pagar ou diferença recebida à vista
        rotulo = TIPOS[tipo].lower()
        if tipo == "DEVOLUCAO" or diferenca < 0:
            lanc.criar_estorno_a_pagar(
                conn,
                troca_devolucao_id=troca_id,
                categoria_id=lanc.categoria_financeira_id(conn, _CATEGORIA_ESTORNO),
                valor=valor_devolvido if tipo == "DEVOLUCAO" else -diferenca,
                vencimento=data_operacao,
                descricao=f"Estorno da {rotulo} #{troca_id} (venda #{venda_id})",
                cliente_id=venda["cliente_id"],
            )
        elif diferenca > 0:
            lanc.receber_a_vista(
                conn,
                categoria_id=lanc.categoria_financeira_id(conn, _CATEGORIA_DIFERENCA),
                conta_id=lanc.conta_financeira_id(conn, forma),
                valor=diferenca,
                momento=momento,
                vencimento=data_operacao,
                descricao=f"Diferença da troca #{troca_id} (venda #{venda_id})",
                usuario_id=usuario_id,
                cliente_id=venda["cliente_id"],
                troca_devolucao_id=troca_id,
            )

    return {
        "id": troca_id,
        "tipo": tipo,
        "valor_devolvido": valor_devolvido,
        "valor_novos": valor_novos,
        "diferenca": diferenca,
        "unidades_ao_estoque": sum(i["devolver"] for i in conferidos if i["retorna_estoque"]),
        "unidades_perdidas": sum(i["devolver"] for i in conferidos if not i["retorna_estoque"]),
    }


def listar(
    tipo: str | None = None,
    motivo: str | None = None,
    data_inicio: date | None = None,
    data_fim: date | None = None,
    limite: int = 500,
) -> list[dict]:
    condicoes, params = [], []
    if tipo:
        condicoes.append("t.tipo = %s")
        params.append(tipo)
    if motivo:
        condicoes.append("t.motivo = %s")
        params.append(motivo)
    if data_inicio:
        condicoes.append("(t.data AT TIME ZONE 'America/Recife')::date >= %s")
        params.append(data_inicio)
    if data_fim:
        condicoes.append("(t.data AT TIME ZONE 'America/Recife')::date <= %s")
        params.append(data_fim)
    where = ("WHERE " + " AND ".join(condicoes)) if condicoes else ""
    return fetch_all(
        f"""
        SELECT t.id, t.venda_id, t.tipo, t.motivo, t.data, t.valor_devolvido, t.valor_novos,
               t.valor_diferenca, c.nome AS cliente, u.nome AS usuario
          FROM trocas_devolucoes t
          JOIN vendas v ON v.id = t.venda_id
          LEFT JOIN clientes c ON c.id = v.cliente_id
          JOIN usuarios u ON u.id = t.usuario_id
          {where}
         ORDER BY t.data DESC, t.id DESC
         LIMIT %s
        """,
        params + [limite],
    )


def buscar(troca_id: int) -> dict | None:
    troca = fetch_one(
        """
        SELECT t.id, t.venda_id, t.tipo, t.motivo, t.data, t.valor_devolvido, t.valor_novos,
               t.valor_diferenca, t.forma_pagamento_diferenca, t.observacao,
               v.data_venda, c.nome AS cliente, u.nome AS usuario
          FROM trocas_devolucoes t
          JOIN vendas v ON v.id = t.venda_id
          LEFT JOIN clientes c ON c.id = v.cliente_id
          JOIN usuarios u ON u.id = t.usuario_id
         WHERE t.id = %s
        """,
        (troca_id,),
    )
    if not troca:
        return None
    troca["devolvidos"] = fetch_all(
        """
        SELECT s.sku, p.nome AS produto, t.nome AS tamanho, co.nome AS cor, d.quantidade,
               d.valor_unitario, d.subtotal, d.retorna_estoque, i.custo_unitario
          FROM itens_devolvidos d
          JOIN itens_venda i ON i.id = d.item_venda_id
          JOIN produto_variacoes s ON s.id = i.variacao_id
          JOIN produtos p ON p.id = s.produto_id
          JOIN tamanhos t ON t.id = s.tamanho_id
          JOIN cores co ON co.id = s.cor_id
         WHERE d.troca_devolucao_id = %s
         ORDER BY p.nome, t.ordem, co.nome
        """,
        (troca_id,),
    )
    troca["novos"] = fetch_all(
        """
        SELECT s.sku, p.nome AS produto, t.nome AS tamanho, co.nome AS cor, n.quantidade,
               n.preco_unitario, n.custo_unitario, n.subtotal
          FROM itens_novos_troca n
          JOIN produto_variacoes s ON s.id = n.variacao_id
          JOIN produtos p ON p.id = s.produto_id
          JOIN tamanhos t ON t.id = s.tamanho_id
          JOIN cores co ON co.id = s.cor_id
         WHERE n.troca_devolucao_id = %s
         ORDER BY p.nome, t.ordem, co.nome
        """,
        (troca_id,),
    )
    troca["lancamentos"] = fetch_all(
        """
        SELECT 'PAGAR' AS natureza, valor, data_vencimento, status, data_pagamento AS data_baixa
          FROM contas_pagar WHERE troca_devolucao_id = %s
        UNION ALL
        SELECT 'RECEBER', valor, data_vencimento, status, data_recebimento
          FROM contas_receber WHERE troca_devolucao_id = %s
        """,
        (troca_id, troca_id),
    )
    return troca
