"""Consultas do dashboard de BI: indicadores, séries, rankings e análises gerenciais.

Todas as funções leem diretamente o banco, sempre com período em datas locais
(fuso da loja) e valores em Decimal. Nada aqui grava dados.
"""
from datetime import date, timedelta
from decimal import Decimal

from db.connection import fetch_all, fetch_one
from services.excecoes import RegraDeNegocioError
from utils.datas import hoje, somar_meses

AGRUPAMENTOS = {"day": "Dia", "week": "Semana", "month": "Mês"}
DIAS_SEMANA = {1: "Segunda", 2: "Terça", 3: "Quarta", 4: "Quinta", 5: "Sexta", 6: "Sábado", 7: "Domingo"}

_FUSO = "'America/Recife'"
_ZERO = Decimal("0.00")


def _dia(coluna: str) -> str:
    """Expressão SQL da data local de uma coluna timestamptz."""
    return f"({coluna} AT TIME ZONE {_FUSO})::date"


def _agrupar(coluna: str, agrupamento: str, timestamp: bool = True) -> str:
    """Expressão SQL do início do período (dia, semana ou mês) de uma coluna."""
    if agrupamento not in AGRUPAMENTOS:
        raise RegraDeNegocioError("Selecione o agrupamento.")
    base = f"{coluna} AT TIME ZONE {_FUSO}" if timestamp else coluna
    return f"date_trunc('{agrupamento}', {base})::date"


def validar_periodo(inicio: date, fim: date) -> None:
    if not isinstance(inicio, date) or not isinstance(fim, date):
        raise RegraDeNegocioError("Informe o período.")
    if fim < inicio:
        raise RegraDeNegocioError("A data final não pode ser anterior à inicial.")


def periodo_anterior(inicio: date, fim: date) -> tuple[date, date]:
    """Período imediatamente anterior, com a mesma duração."""
    dias = (fim - inicio).days + 1
    fim_anterior = inicio - timedelta(days=1)
    return fim_anterior - timedelta(days=dias - 1), fim_anterior


def agrupamento_sugerido(inicio: date, fim: date) -> str:
    dias = (fim - inicio).days + 1
    return "day" if dias <= 45 else "week" if dias <= 180 else "month"


def _inicio_do_periodo(data: date, agrupamento: str) -> date:
    if agrupamento == "week":
        return data - timedelta(days=data.weekday())
    return data.replace(day=1) if agrupamento == "month" else data


def periodos(inicio: date, fim: date, agrupamento: str) -> list[date]:
    """Início de cada período entre as datas (inclusive os vazios)."""
    validar_periodo(inicio, fim)
    atual, lista = _inicio_do_periodo(inicio, agrupamento), []
    while atual <= fim:
        lista.append(atual)
        if agrupamento == "day":
            atual += timedelta(days=1)
        elif agrupamento == "week":
            atual += timedelta(days=7)
        else:
            atual = somar_meses(atual, 1)
    return lista


def _razao(numerador: Decimal, denominador: Decimal) -> Decimal | None:
    return None if not denominador else numerador / denominador


def variacao(atual: Decimal | int, anterior: Decimal | int) -> Decimal | None:
    """Variação percentual (fração) entre dois períodos; None quando não há base de comparação."""
    return None if not anterior else (Decimal(atual) - Decimal(anterior)) / Decimal(anterior)


# ---------------------------------------------------------------- Indicadores do período
def indicadores(inicio: date, fim: date) -> dict:
    """Indicadores consolidados do período (vendas, trocas, custo, margem e despesas)."""
    validar_periodo(inicio, fim)
    p = (inicio, fim)
    vendas = fetch_one(
        f"""
        SELECT COALESCE(SUM(valor_total), 0) AS faturamento, COUNT(*) AS num_vendas,
               COALESCE(SUM(desconto), 0) AS descontos, COALESCE(SUM(subtotal), 0) AS subtotal_bruto,
               COUNT(*) FILTER (WHERE cliente_id IS NOT NULL) AS vendas_com_cliente,
               COUNT(DISTINCT cliente_id) AS clientes_ativos
          FROM vendas WHERE {_dia('data_venda')} BETWEEN %s AND %s
        """,
        p,
    )
    itens = fetch_one(
        f"""
        SELECT COALESCE(SUM(i.quantidade), 0) AS unidades,
               COALESCE(SUM(i.quantidade * i.custo_unitario), 0) AS cmv_vendas
          FROM itens_venda i JOIN vendas v ON v.id = i.venda_id
         WHERE {_dia('v.data_venda')} BETWEEN %s AND %s
        """,
        p,
    )
    trocas = fetch_one(
        f"""
        SELECT COALESCE(SUM(valor_devolvido), 0) AS valor_devolvido,
               COALESCE(SUM(valor_novos), 0) AS valor_novos,
               COUNT(*) FILTER (WHERE tipo = 'DEVOLUCAO') AS devolucoes,
               COUNT(*) FILTER (WHERE tipo = 'TROCA') AS trocas
          FROM trocas_devolucoes WHERE {_dia('data')} BETWEEN %s AND %s
        """,
        p,
    )
    devolvidos = fetch_one(
        f"""
        SELECT COALESCE(SUM(d.quantidade), 0) AS unidades_devolvidas,
               COALESCE(SUM(d.quantidade * iv.custo_unitario) FILTER (WHERE d.retorna_estoque), 0)
                   AS custo_devolvido_estoque,
               COALESCE(SUM(d.quantidade * iv.custo_unitario) FILTER (WHERE NOT d.retorna_estoque), 0)
                   AS perda_defeito
          FROM itens_devolvidos d
          JOIN itens_venda iv ON iv.id = d.item_venda_id
          JOIN trocas_devolucoes t ON t.id = d.troca_devolucao_id
         WHERE {_dia('t.data')} BETWEEN %s AND %s
        """,
        p,
    )
    novos = fetch_one(
        f"""
        SELECT COALESCE(SUM(n.quantidade * n.custo_unitario), 0) AS custo_novos
          FROM itens_novos_troca n JOIN trocas_devolucoes t ON t.id = n.troca_devolucao_id
         WHERE {_dia('t.data')} BETWEEN %s AND %s
        """,
        p,
    )
    despesas = fetch_one(
        """
        SELECT COALESCE(SUM(valor), 0) AS despesas FROM contas_pagar
         WHERE compra_id IS NULL AND troca_devolucao_id IS NULL AND status <> 'CANCELADA'
           AND data_vencimento BETWEEN %s AND %s
        """,
        p,
    )["despesas"]

    receita_liquida = vendas["faturamento"] - trocas["valor_devolvido"] + trocas["valor_novos"]
    cmv = itens["cmv_vendas"] - devolvidos["custo_devolvido_estoque"] + novos["custo_novos"]
    margem = receita_liquida - cmv
    return {
        "faturamento": vendas["faturamento"],
        "num_vendas": vendas["num_vendas"],
        "descontos": vendas["descontos"],
        "subtotal_bruto": vendas["subtotal_bruto"],
        "vendas_com_cliente": vendas["vendas_com_cliente"],
        "clientes_ativos": vendas["clientes_ativos"],
        "unidades": itens["unidades"],
        "ticket_medio": _razao(vendas["faturamento"], vendas["num_vendas"]) or _ZERO,
        "itens_por_venda": _razao(Decimal(itens["unidades"]), Decimal(vendas["num_vendas"])) or _ZERO,
        "devolucoes": trocas["devolucoes"],
        "trocas": trocas["trocas"],
        "valor_devolvido": trocas["valor_devolvido"],
        "valor_novos": trocas["valor_novos"],
        "unidades_devolvidas": devolvidos["unidades_devolvidas"],
        "perda_defeito": devolvidos["perda_defeito"],
        "receita_liquida": receita_liquida,
        "cmv": cmv,
        "margem_bruta": margem,
        "margem_pct": _razao(margem, receita_liquida),
        "despesas": despesas,
        "resultado": margem - despesas,
        "taxa_devolucao_valor": _razao(trocas["valor_devolvido"], vendas["faturamento"]),
        "taxa_devolucao_unidades": _razao(
            Decimal(devolvidos["unidades_devolvidas"]), Decimal(itens["unidades"])
        ),
        "desconto_medio_pct": _razao(vendas["descontos"], vendas["subtotal_bruto"]),
    }


def serie(inicio: date, fim: date, agrupamento: str) -> list[dict]:
    """Evolução por período: faturamento, vendas, ticket, margem bruta, despesas e resultado."""
    validar_periodo(inicio, fim)
    p = (inicio, fim)

    def por_periodo(sql: str) -> dict:
        return {linha["periodo"]: linha for linha in fetch_all(sql, p)}

    vendas = por_periodo(
        f"""
        SELECT {_agrupar('data_venda', agrupamento)} AS periodo, SUM(valor_total) AS faturamento,
               COUNT(*) AS num_vendas
          FROM vendas WHERE {_dia('data_venda')} BETWEEN %s AND %s GROUP BY 1
        """
    )
    cmv_vendas = por_periodo(
        f"""
        SELECT {_agrupar('v.data_venda', agrupamento)} AS periodo,
               SUM(i.quantidade * i.custo_unitario) AS valor
          FROM itens_venda i JOIN vendas v ON v.id = i.venda_id
         WHERE {_dia('v.data_venda')} BETWEEN %s AND %s GROUP BY 1
        """
    )
    ajuste_receita = por_periodo(
        f"""
        SELECT {_agrupar('data', agrupamento)} AS periodo, SUM(valor_novos - valor_devolvido) AS valor
          FROM trocas_devolucoes WHERE {_dia('data')} BETWEEN %s AND %s GROUP BY 1
        """
    )
    custo_devolvido = por_periodo(
        f"""
        SELECT {_agrupar('t.data', agrupamento)} AS periodo,
               SUM(d.quantidade * iv.custo_unitario) AS valor
          FROM itens_devolvidos d
          JOIN itens_venda iv ON iv.id = d.item_venda_id
          JOIN trocas_devolucoes t ON t.id = d.troca_devolucao_id
         WHERE d.retorna_estoque AND {_dia('t.data')} BETWEEN %s AND %s GROUP BY 1
        """
    )
    custo_novos = por_periodo(
        f"""
        SELECT {_agrupar('t.data', agrupamento)} AS periodo, SUM(n.quantidade * n.custo_unitario) AS valor
          FROM itens_novos_troca n JOIN trocas_devolucoes t ON t.id = n.troca_devolucao_id
         WHERE {_dia('t.data')} BETWEEN %s AND %s GROUP BY 1
        """
    )
    despesas = por_periodo(
        f"""
        SELECT {_agrupar('data_vencimento', agrupamento, timestamp=False)} AS periodo,
               SUM(valor) AS valor
          FROM contas_pagar
         WHERE compra_id IS NULL AND troca_devolucao_id IS NULL AND status <> 'CANCELADA'
           AND data_vencimento BETWEEN %s AND %s GROUP BY 1
        """
    )

    def valor(mapa: dict, periodo: date, campo: str = "valor") -> Decimal:
        return mapa[periodo][campo] if periodo in mapa else _ZERO

    resultado = []
    for periodo in periodos(inicio, fim, agrupamento):
        faturamento = valor(vendas, periodo, "faturamento")
        num_vendas = vendas[periodo]["num_vendas"] if periodo in vendas else 0
        receita = faturamento + valor(ajuste_receita, periodo)
        cmv = valor(cmv_vendas, periodo) - valor(custo_devolvido, periodo) + valor(custo_novos, periodo)
        margem = receita - cmv
        gasto = valor(despesas, periodo)
        resultado.append(
            {
                "periodo": periodo,
                "faturamento": faturamento,
                "num_vendas": num_vendas,
                "ticket_medio": faturamento / num_vendas if num_vendas else _ZERO,
                "receita_liquida": receita,
                "cmv": cmv,
                "margem_bruta": margem,
                "despesas": gasto,
                "resultado": margem - gasto,
            }
        )
    return resultado


# ---------------------------------------------------------------- Vendas
def vendas_por_forma_pagamento(inicio: date, fim: date) -> list[dict]:
    return fetch_all(
        f"""
        SELECT forma_pagamento, COUNT(*) AS num_vendas, SUM(valor_total) AS faturamento,
               AVG(valor_total) AS ticket_medio
          FROM vendas WHERE {_dia('data_venda')} BETWEEN %s AND %s
         GROUP BY forma_pagamento ORDER BY faturamento DESC
        """,
        (inicio, fim),
    )


def vendas_por_vendedor(inicio: date, fim: date) -> list[dict]:
    return fetch_all(
        f"""
        SELECT u.nome AS vendedor, COUNT(*) AS num_vendas, SUM(v.valor_total) AS faturamento,
               AVG(v.valor_total) AS ticket_medio, SUM(v.desconto) AS descontos,
               SUM(v.desconto) / NULLIF(SUM(v.subtotal), 0) AS desconto_pct
          FROM vendas v JOIN usuarios u ON u.id = v.usuario_id
         WHERE {_dia('v.data_venda')} BETWEEN %s AND %s
         GROUP BY u.nome ORDER BY faturamento DESC
        """,
        (inicio, fim),
    )


def vendas_por_dia_semana(inicio: date, fim: date) -> list[dict]:
    """Faturamento por dia da semana, com a média por ocorrência do dia no período."""
    linhas = {
        linha["dia"]: linha
        for linha in fetch_all(
            f"""
            SELECT EXTRACT(ISODOW FROM data_venda AT TIME ZONE {_FUSO})::int AS dia,
                   COUNT(*) AS num_vendas, SUM(valor_total) AS faturamento
              FROM vendas WHERE {_dia('data_venda')} BETWEEN %s AND %s GROUP BY 1
            """,
            (inicio, fim),
        )
    }
    ocorrencias = {d: 0 for d in DIAS_SEMANA}
    dia = inicio
    while dia <= fim:
        ocorrencias[dia.isoweekday()] += 1
        dia += timedelta(days=1)
    resultado = []
    for numero, nome in DIAS_SEMANA.items():
        linha = linhas.get(numero)
        faturamento = linha["faturamento"] if linha else _ZERO
        resultado.append(
            {
                "dia": numero,
                "nome": nome,
                "num_vendas": linha["num_vendas"] if linha else 0,
                "faturamento": faturamento,
                "ocorrencias": ocorrencias[numero],
                "media_por_dia": faturamento / ocorrencias[numero] if ocorrencias[numero] else _ZERO,
            }
        )
    return resultado


def vendas_por_parcelas(inicio: date, fim: date) -> list[dict]:
    """Vendas no crédito por número de parcelas."""
    return fetch_all(
        f"""
        SELECT num_parcelas, COUNT(*) AS num_vendas, SUM(valor_total) AS faturamento
          FROM vendas WHERE forma_pagamento = 'CREDITO' AND {_dia('data_venda')} BETWEEN %s AND %s
         GROUP BY num_parcelas ORDER BY num_parcelas
        """,
        (inicio, fim),
    )


def faixas_desconto(inicio: date, fim: date) -> list[dict]:
    return fetch_all(
        f"""
        SELECT CASE WHEN desconto = 0 THEN '1. Sem desconto'
                    WHEN desconto / subtotal <= 0.05 THEN '2. Até 5%%'
                    WHEN desconto / subtotal <= 0.10 THEN '3. De 5%% a 10%%'
                    ELSE '4. Acima de 10%%' END AS faixa,
               COUNT(*) AS num_vendas, SUM(valor_total) AS faturamento, SUM(desconto) AS descontos
          FROM vendas WHERE {_dia('data_venda')} BETWEEN %s AND %s
         GROUP BY 1 ORDER BY 1
        """,
        (inicio, fim),
    )


def top_clientes(inicio: date, fim: date, limite: int = 10) -> list[dict]:
    return fetch_all(
        f"""
        SELECT c.nome AS cliente, COUNT(*) AS compras, SUM(v.valor_total) AS faturamento,
               AVG(v.valor_total) AS ticket_medio, MAX(v.data_venda) AS ultima_compra
          FROM vendas v JOIN clientes c ON c.id = v.cliente_id
         WHERE {_dia('v.data_venda')} BETWEEN %s AND %s
         GROUP BY c.id, c.nome ORDER BY faturamento DESC LIMIT %s
        """,
        (inicio, fim, limite),
    )


# ---------------------------------------------------------------- Produtos
# Receita do item: o desconto da venda é rateado proporcionalmente entre os itens
_RECEITA_ITEM = "i.subtotal * v.valor_total / v.subtotal"
_CUSTO_ITEM = "i.quantidade * i.custo_unitario"


def ranking_produtos(inicio: date, fim: date) -> list[dict]:
    linhas = fetch_all(
        f"""
        SELECT p.id, p.nome AS produto, cat.nome AS categoria, SUM(i.quantidade) AS unidades,
               SUM({_RECEITA_ITEM}) AS faturamento,
               SUM({_RECEITA_ITEM}) - SUM({_CUSTO_ITEM}) AS margem
          FROM itens_venda i
          JOIN vendas v ON v.id = i.venda_id
          JOIN produto_variacoes s ON s.id = i.variacao_id
          JOIN produtos p ON p.id = s.produto_id
          JOIN categorias cat ON cat.id = p.categoria_id
         WHERE {_dia('v.data_venda')} BETWEEN %s AND %s
         GROUP BY p.id, p.nome, cat.nome ORDER BY faturamento DESC
        """,
        (inicio, fim),
    )
    for linha in linhas:
        linha["margem_pct"] = _razao(linha["margem"], linha["faturamento"])
    return linhas


def vendas_por_categoria(inicio: date, fim: date) -> list[dict]:
    linhas = fetch_all(
        f"""
        SELECT cat.nome AS categoria, SUM(i.quantidade) AS unidades,
               SUM({_RECEITA_ITEM}) AS faturamento,
               SUM({_RECEITA_ITEM}) - SUM({_CUSTO_ITEM}) AS margem
          FROM itens_venda i
          JOIN vendas v ON v.id = i.venda_id
          JOIN produto_variacoes s ON s.id = i.variacao_id
          JOIN produtos p ON p.id = s.produto_id
          JOIN categorias cat ON cat.id = p.categoria_id
         WHERE {_dia('v.data_venda')} BETWEEN %s AND %s
         GROUP BY cat.nome ORDER BY faturamento DESC
        """,
        (inicio, fim),
    )
    for linha in linhas:
        linha["margem_pct"] = _razao(linha["margem"], linha["faturamento"])
    return linhas


def curva_abc(ranking: list[dict]) -> list[dict]:
    """Classifica os produtos pelo faturamento acumulado: A até 80%, B até 95%, C no restante.

    O produto que atravessa um limite permanece na classe em que começou.
    """
    total = sum((r["faturamento"] for r in ranking), _ZERO)
    if not total:
        return []
    acumulado, resultado = _ZERO, []
    for posicao, linha in enumerate(sorted(ranking, key=lambda r: r["faturamento"], reverse=True), start=1):
        antes = acumulado / total
        acumulado += linha["faturamento"]
        classe = "A" if antes < Decimal("0.80") else "B" if antes < Decimal("0.95") else "C"
        resultado.append(
            {**linha, "posicao": posicao, "participacao": linha["faturamento"] / total,
             "acumulado": acumulado / total, "classe": classe}
        )
    return resultado


def vendas_por_tamanho(inicio: date, fim: date) -> list[dict]:
    return fetch_all(
        f"""
        SELECT t.nome AS tamanho, SUM(i.quantidade) AS unidades, SUM({_RECEITA_ITEM}) AS faturamento
          FROM itens_venda i
          JOIN vendas v ON v.id = i.venda_id
          JOIN produto_variacoes s ON s.id = i.variacao_id
          JOIN tamanhos t ON t.id = s.tamanho_id
         WHERE {_dia('v.data_venda')} BETWEEN %s AND %s
         GROUP BY t.id, t.nome, t.ordem ORDER BY t.ordem
        """,
        (inicio, fim),
    )


def vendas_por_cor(inicio: date, fim: date) -> list[dict]:
    return fetch_all(
        f"""
        SELECT co.nome AS cor, SUM(i.quantidade) AS unidades, SUM({_RECEITA_ITEM}) AS faturamento
          FROM itens_venda i
          JOIN vendas v ON v.id = i.venda_id
          JOIN produto_variacoes s ON s.id = i.variacao_id
          JOIN cores co ON co.id = s.cor_id
         WHERE {_dia('v.data_venda')} BETWEEN %s AND %s
         GROUP BY co.nome ORDER BY unidades DESC
        """,
        (inicio, fim),
    )


# ---------------------------------------------------------------- Estoque
def posicao_estoque() -> dict:
    """Situação atual do estoque dos SKUs ativos."""
    total = fetch_one(
        """
        SELECT COUNT(*) AS skus, COALESCE(SUM(s.estoque_atual), 0) AS unidades,
               COALESCE(SUM(s.estoque_atual * s.custo_medio), 0) AS valor_custo,
               COALESCE(SUM(s.estoque_atual * s.preco_venda), 0) AS valor_venda,
               COUNT(*) FILTER (WHERE s.estoque_minimo > 0 AND s.estoque_atual <= s.estoque_minimo)
                   AS criticos,
               COUNT(*) FILTER (WHERE s.estoque_atual = 0) AS zerados
          FROM produto_variacoes s JOIN produtos p ON p.id = s.produto_id
         WHERE s.ativo AND p.ativo
        """
    )
    return total


def giro_por_sku(inicio: date, fim: date) -> list[dict]:
    """Por SKU ativo: estoque no início e no fim do período, vendas, cobertura e última venda.

    O estoque em uma data é reconstruído a partir do saldo atual e das movimentações posteriores.
    """
    dias = (fim - inicio).days + 1
    linhas = fetch_all(
        f"""
        WITH mov AS (
            SELECT variacao_id,
                   COALESCE(SUM(quantidade) FILTER (WHERE {_dia('criado_em')} >= %s), 0) AS depois_inicio,
                   COALESCE(SUM(quantidade) FILTER (WHERE {_dia('criado_em')} > %s), 0) AS depois_fim
              FROM movimentacoes_estoque GROUP BY variacao_id
        ),
        vend AS (
            SELECT i.variacao_id, SUM(i.quantidade) AS vendidas
              FROM itens_venda i JOIN vendas v ON v.id = i.venda_id
             WHERE {_dia('v.data_venda')} BETWEEN %s AND %s GROUP BY i.variacao_id
        ),
        ultima AS (
            SELECT i.variacao_id, MAX({_dia('v.data_venda')}) AS ultima_venda
              FROM itens_venda i JOIN vendas v ON v.id = i.venda_id GROUP BY i.variacao_id
        )
        SELECT s.id, s.sku, p.nome AS produto, cat.nome AS categoria, t.nome AS tamanho,
               co.nome AS cor, s.estoque_atual, s.estoque_minimo, s.custo_medio, s.preco_venda,
               s.estoque_atual - COALESCE(m.depois_inicio, 0) AS estoque_inicio,
               s.estoque_atual - COALESCE(m.depois_fim, 0) AS estoque_fim,
               COALESCE(v.vendidas, 0) AS vendidas, u.ultima_venda
          FROM produto_variacoes s
          JOIN produtos p ON p.id = s.produto_id
          JOIN categorias cat ON cat.id = p.categoria_id
          JOIN tamanhos t ON t.id = s.tamanho_id
          JOIN cores co ON co.id = s.cor_id
          LEFT JOIN mov m ON m.variacao_id = s.id
          LEFT JOIN vend v ON v.variacao_id = s.id
          LEFT JOIN ultima u ON u.variacao_id = s.id
         WHERE s.ativo AND p.ativo
         ORDER BY p.nome, t.ordem, co.nome
        """,
        (inicio, fim, inicio, fim),
    )
    for linha in linhas:
        media_diaria = Decimal(linha["vendidas"]) / dias
        linha["venda_media_diaria"] = media_diaria
        linha["cobertura_dias"] = Decimal(linha["estoque_atual"]) / media_diaria if media_diaria else None
        linha["valor_custo"] = linha["estoque_atual"] * linha["custo_medio"]
    return linhas


def giro_por_categoria(linhas_sku: list[dict], inicio: date, fim: date) -> list[dict]:
    """Giro (vendas ÷ estoque médio) e cobertura em dias por categoria, a partir de giro_por_sku."""
    dias = (fim - inicio).days + 1
    agrupado: dict[str, dict] = {}
    for sku in linhas_sku:
        g = agrupado.setdefault(
            sku["categoria"],
            {"categoria": sku["categoria"], "vendidas": 0, "estoque_inicio": 0, "estoque_fim": 0,
             "estoque_atual": 0, "valor_custo": _ZERO},
        )
        g["vendidas"] += sku["vendidas"]
        g["estoque_inicio"] += sku["estoque_inicio"]
        g["estoque_fim"] += sku["estoque_fim"]
        g["estoque_atual"] += sku["estoque_atual"]
        g["valor_custo"] += sku["valor_custo"]
    resultado = []
    for g in sorted(agrupado.values(), key=lambda x: x["categoria"]):
        medio = Decimal(g["estoque_inicio"] + g["estoque_fim"]) / 2
        media_diaria = Decimal(g["vendidas"]) / dias
        g["estoque_medio"] = medio
        g["giro"] = _razao(Decimal(g["vendidas"]), medio)
        g["cobertura_dias"] = _razao(Decimal(g["estoque_fim"]), media_diaria)
        resultado.append(g)
    return resultado


def skus_criticos(linhas_sku: list[dict]) -> list[dict]:
    criticos = [s for s in linhas_sku if s["estoque_minimo"] > 0 and s["estoque_atual"] <= s["estoque_minimo"]]
    return sorted(criticos, key=lambda s: (s["estoque_atual"] - s["estoque_minimo"], s["produto"]))


def estoque_parado(linhas_sku: list[dict]) -> list[dict]:
    """SKUs com saldo e nenhuma venda no período, do maior valor imobilizado para o menor."""
    parados = [s for s in linhas_sku if s["estoque_atual"] > 0 and s["vendidas"] == 0]
    return sorted(parados, key=lambda s: s["valor_custo"], reverse=True)


# ---------------------------------------------------------------- Financeiro
def situacao_contas() -> dict:
    """Carteira de contas a receber e a pagar na data de hoje, com prazos de atraso."""
    referencia = hoje()
    resultado = {}
    for chave, tabela in (("receber", "contas_receber"), ("pagar", "contas_pagar")):
        totais = fetch_one(
            f"""
            SELECT COALESCE(SUM(valor), 0) AS aberto,
                   COALESCE(SUM(valor) FILTER (WHERE data_vencimento < %s), 0) AS vencido,
                   COUNT(*) FILTER (WHERE data_vencimento < %s) AS qtd_vencidas,
                   COALESCE(SUM(valor) FILTER (WHERE data_vencimento BETWEEN %s AND %s), 0) AS a_vencer_7,
                   COALESCE(SUM(valor) FILTER (WHERE data_vencimento BETWEEN %s AND %s), 0) AS a_vencer_30
              FROM {tabela} WHERE status = 'ABERTA'
            """,
            (
                referencia, referencia,
                referencia, referencia + timedelta(days=7),
                referencia, referencia + timedelta(days=30),
            ),
        )
        faixas = fetch_all(
            f"""
            SELECT CASE WHEN %s - data_vencimento <= 30 THEN '1 a 30 dias'
                        WHEN %s - data_vencimento <= 60 THEN '31 a 60 dias'
                        WHEN %s - data_vencimento <= 90 THEN '61 a 90 dias'
                        ELSE 'Mais de 90 dias' END AS faixa,
                   COUNT(*) AS quantidade, SUM(valor) AS valor
              FROM {tabela} WHERE status = 'ABERTA' AND data_vencimento < %s
             GROUP BY 1 ORDER BY MIN(%s - data_vencimento)
            """,
            (referencia, referencia, referencia, referencia, referencia),
        )
        totais["faixas"] = faixas
        totais["pct_vencido"] = _razao(totais["vencido"], totais["aberto"])
        resultado[chave] = totais
    return resultado


def clientes_em_atraso(limite: int = 10) -> list[dict]:
    referencia = hoje()
    return fetch_all(
        """
        SELECT c.nome AS cliente, COUNT(*) AS parcelas, SUM(r.valor) AS valor,
               MAX(%s - r.data_vencimento) AS maior_atraso
          FROM contas_receber r JOIN clientes c ON c.id = r.cliente_id
         WHERE r.status = 'ABERTA' AND r.data_vencimento < %s
         GROUP BY c.id, c.nome ORDER BY valor DESC LIMIT %s
        """,
        (referencia, referencia, limite),
    )


def despesas_por_categoria(inicio: date, fim: date) -> list[dict]:
    """Despesas avulsas por categoria, pelo vencimento no período."""
    return fetch_all(
        """
        SELECT cat.nome AS categoria, SUM(p.valor) AS valor,
               COALESCE(SUM(p.valor) FILTER (WHERE p.status = 'PAGA'), 0) AS pago,
               COALESCE(SUM(p.valor) FILTER (WHERE p.status = 'ABERTA'), 0) AS pendente
          FROM contas_pagar p JOIN categorias_financeiras cat ON cat.id = p.categoria_id
         WHERE p.compra_id IS NULL AND p.troca_devolucao_id IS NULL AND p.status <> 'CANCELADA'
           AND p.data_vencimento BETWEEN %s AND %s
         GROUP BY cat.nome ORDER BY valor DESC
        """,
        (inicio, fim),
    )


# ---------------------------------------------------------------- Operações
def devolucoes_por_motivo(inicio: date, fim: date) -> list[dict]:
    return fetch_all(
        f"""
        SELECT t.motivo,
               COUNT(*) FILTER (WHERE t.tipo = 'DEVOLUCAO') AS devolucoes,
               COUNT(*) FILTER (WHERE t.tipo = 'TROCA') AS trocas,
               COUNT(*) AS total, SUM(t.valor_devolvido) AS valor_devolvido,
               COALESCE((SELECT SUM(d.quantidade) FROM itens_devolvidos d
                          JOIN trocas_devolucoes t2 ON t2.id = d.troca_devolucao_id
                         WHERE t2.motivo = t.motivo
                           AND {_dia('t2.data')} BETWEEN %s AND %s), 0) AS unidades
          FROM trocas_devolucoes t
         WHERE {_dia('t.data')} BETWEEN %s AND %s
         GROUP BY t.motivo ORDER BY total DESC
        """,
        (inicio, fim, inicio, fim),
    )


def produtos_mais_devolvidos(inicio: date, fim: date, limite: int = 10) -> list[dict]:
    """Produtos com mais unidades devolvidas e o índice sobre as unidades vendidas no mesmo período."""
    linhas = fetch_all(
        f"""
        WITH devolvidas AS (
            SELECT s.produto_id, SUM(d.quantidade) AS unidades,
                   SUM(d.quantidade) FILTER (WHERE NOT d.retorna_estoque) AS por_defeito
              FROM itens_devolvidos d
              JOIN itens_venda iv ON iv.id = d.item_venda_id
              JOIN produto_variacoes s ON s.id = iv.variacao_id
              JOIN trocas_devolucoes t ON t.id = d.troca_devolucao_id
             WHERE {_dia('t.data')} BETWEEN %s AND %s GROUP BY s.produto_id
        ),
        vendidas AS (
            SELECT s.produto_id, SUM(i.quantidade) AS unidades
              FROM itens_venda i
              JOIN vendas v ON v.id = i.venda_id
              JOIN produto_variacoes s ON s.id = i.variacao_id
             WHERE {_dia('v.data_venda')} BETWEEN %s AND %s GROUP BY s.produto_id
        )
        SELECT p.nome AS produto, d.unidades AS devolvidas, COALESCE(d.por_defeito, 0) AS por_defeito,
               COALESCE(v.unidades, 0) AS vendidas
          FROM devolvidas d
          JOIN produtos p ON p.id = d.produto_id
          LEFT JOIN vendidas v ON v.produto_id = d.produto_id
         ORDER BY d.unidades DESC, p.nome LIMIT %s
        """,
        (inicio, fim, inicio, fim, limite),
    )
    for linha in linhas:
        linha["indice"] = _razao(Decimal(linha["devolvidas"]), Decimal(linha["vendidas"]))
    return linhas


def compras_por_fornecedor(inicio: date, fim: date) -> list[dict]:
    """Pedidos do período por fornecedor (pelo dia do pedido), exceto cancelados."""
    return fetch_all(
        f"""
        SELECT f.razao_social AS fornecedor, COUNT(*) AS pedidos, SUM(c.valor_total) AS valor,
               COALESCE((SELECT SUM(ic.quantidade) FROM itens_compra ic
                          JOIN compras c2 ON c2.id = ic.compra_id
                         WHERE c2.fornecedor_id = f.id AND c2.status <> 'CANCELADA'
                           AND {_dia('c2.data_pedido')} BETWEEN %s AND %s), 0) AS unidades,
               AVG({_dia('c.data_recebimento')} - {_dia('c.data_pedido')})
                   FILTER (WHERE c.status = 'RECEBIDA') AS prazo_medio_dias,
               COUNT(*) FILTER (WHERE c.status = 'PEDIDO') AS pendentes
          FROM compras c JOIN fornecedores f ON f.id = c.fornecedor_id
         WHERE c.status <> 'CANCELADA' AND {_dia('c.data_pedido')} BETWEEN %s AND %s
         GROUP BY f.id, f.razao_social ORDER BY valor DESC
        """,
        (inicio, fim, inicio, fim),
    )


def compras_serie(inicio: date, fim: date, agrupamento: str) -> list[dict]:
    """Valor comprado por período, para comparar com o custo das mercadorias vendidas."""
    validar_periodo(inicio, fim)
    linhas = {
        linha["periodo"]: linha["valor"]
        for linha in fetch_all(
            f"""
            SELECT {_agrupar('data_pedido', agrupamento)} AS periodo, SUM(valor_total) AS valor
              FROM compras WHERE status <> 'CANCELADA' AND {_dia('data_pedido')} BETWEEN %s AND %s
             GROUP BY 1
            """,
            (inicio, fim),
        )
    }
    return [{"periodo": p, "compras": linhas.get(p, _ZERO)} for p in periodos(inicio, fim, agrupamento)]


def primeira_data_com_dados() -> date | None:
    """Data da venda mais antiga, para limitar o filtro de período."""
    linha = fetch_one(f"SELECT MIN({_dia('data_venda')}) AS primeira FROM vendas")
    return linha["primeira"] if linha else None
