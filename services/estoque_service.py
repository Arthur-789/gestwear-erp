"""Regras de negócio do módulo Estoque: posição, histórico e ajuste de inventário."""
from datetime import date

from db.connection import fetch_all, fetch_one, transaction
from services.excecoes import RegraDeNegocioError, traduzir_erros_banco
from services.validadores import escapar_like

TIPOS_MOVIMENTACAO = {
    "ENTRADA_COMPRA": "Entrada por compra",
    "SAIDA_VENDA": "Saída por venda",
    "ENTRADA_DEVOLUCAO": "Entrada por devolução",
    "SAIDA_TROCA": "Saída por troca",
    "AJUSTE": "Ajuste de inventário",
}

_EM_ALERTA = "(v.estoque_minimo > 0 AND v.estoque_atual <= v.estoque_minimo)"

_BASE_POSICAO = """
    FROM produto_variacoes v
    JOIN produtos p ON p.id = v.produto_id
    JOIN categorias c ON c.id = p.categoria_id
    JOIN tamanhos t ON t.id = v.tamanho_id
    JOIN cores co ON co.id = v.cor_id
"""


def posicao_estoque(
    busca: str | None = None,
    categoria_id: int | None = None,
    somente_alerta: bool = False,
    incluir_inativos: bool = False,
) -> list[dict]:
    condicoes, params = [], []
    if not incluir_inativos:
        condicoes.append("(v.ativo AND p.ativo)")
    if busca and busca.strip():
        like = f"%{escapar_like(busca.strip())}%"
        condicoes.append("(p.nome ILIKE %s OR v.sku ILIKE %s)")
        params += [like, like]
    if categoria_id is not None:
        condicoes.append("p.categoria_id = %s")
        params.append(categoria_id)
    if somente_alerta:
        condicoes.append(_EM_ALERTA)
    where = ("WHERE " + " AND ".join(condicoes)) if condicoes else ""
    return fetch_all(
        f"""
        SELECT v.id, v.sku, p.nome AS produto, c.nome AS categoria, t.nome AS tamanho,
               co.nome AS cor, v.estoque_atual, v.estoque_minimo, v.custo_medio,
               v.preco_venda, (v.ativo AND p.ativo) AS ativo, {_EM_ALERTA} AS em_alerta
          {_BASE_POSICAO}
          {where}
         ORDER BY p.nome, t.ordem, co.nome
        """,
        params,
    )


def alertas_reposicao(limite: int = 10) -> dict:
    """Total de SKUs ativos abaixo do mínimo e os mais críticos."""
    total = fetch_one(
        f"SELECT count(*) AS n {_BASE_POSICAO} WHERE v.ativo AND p.ativo AND {_EM_ALERTA}"
    )["n"]
    itens = fetch_all(
        f"""
        SELECT v.sku, p.nome AS produto, t.nome AS tamanho, co.nome AS cor,
               v.estoque_atual, v.estoque_minimo
          {_BASE_POSICAO}
         WHERE v.ativo AND p.ativo AND {_EM_ALERTA}
         ORDER BY v.estoque_atual - v.estoque_minimo, p.nome
         LIMIT %s
        """,
        (limite,),
    )
    return {"total": total, "itens": itens}


def historico_movimentacoes(
    busca: str | None = None,
    tipo: str | None = None,
    data_inicio: date | None = None,
    data_fim: date | None = None,
    limite: int = 500,
) -> list[dict]:
    condicoes, params = [], []
    if busca and busca.strip():
        like = f"%{escapar_like(busca.strip())}%"
        condicoes.append("(p.nome ILIKE %s OR v.sku ILIKE %s)")
        params += [like, like]
    if tipo:
        condicoes.append("m.tipo = %s")
        params.append(tipo)
    if data_inicio:
        condicoes.append("(m.criado_em AT TIME ZONE 'America/Recife')::date >= %s")
        params.append(data_inicio)
    if data_fim:
        condicoes.append("(m.criado_em AT TIME ZONE 'America/Recife')::date <= %s")
        params.append(data_fim)
    where = ("WHERE " + " AND ".join(condicoes)) if condicoes else ""
    linhas = fetch_all(
        f"""
        SELECT m.id, m.criado_em, v.sku, p.nome AS produto, m.tipo, m.quantidade,
               m.saldo_anterior, m.saldo_posterior, m.compra_id, m.venda_id,
               m.troca_devolucao_id, m.motivo, u.nome AS usuario
          FROM movimentacoes_estoque m
          JOIN produto_variacoes v ON v.id = m.variacao_id
          JOIN produtos p ON p.id = v.produto_id
          JOIN usuarios u ON u.id = m.usuario_id
          {where}
         ORDER BY m.criado_em DESC, m.id DESC
         LIMIT %s
        """,
        params + [limite],
    )
    for linha in linhas:
        if linha["compra_id"]:
            linha["origem"] = f"Compra #{linha['compra_id']}"
        elif linha["venda_id"]:
            linha["origem"] = f"Venda #{linha['venda_id']}"
        elif linha["troca_devolucao_id"]:
            linha["origem"] = f"Troca/devolução #{linha['troca_devolucao_id']}"
        else:
            linha["origem"] = "-"
    return linhas


def ajustar_estoque(variacao_id: int, saldo_contado, motivo: str, usuario_id: int) -> int:
    """Ajusta o saldo para a contagem física. Devolve a diferença aplicada."""
    try:
        contado = int(saldo_contado)
    except (TypeError, ValueError):
        raise RegraDeNegocioError("Informe a quantidade contada.")
    if contado < 0 or contado > 1000000:
        raise RegraDeNegocioError("A quantidade contada deve estar entre 0 e 1000000.")
    motivo = " ".join((motivo or "").split())
    if len(motivo) < 5:
        raise RegraDeNegocioError("Informe o motivo do ajuste (mínimo 5 caracteres).")
    with traduzir_erros_banco(), transaction() as conn:
        atual = fetch_one(
            "SELECT estoque_atual FROM produto_variacoes WHERE id = %s FOR UPDATE",
            (variacao_id,),
            conn,
        )
        if not atual:
            raise RegraDeNegocioError("SKU não encontrado.")
        diferenca = contado - atual["estoque_atual"]
        if diferenca == 0:
            raise RegraDeNegocioError("A quantidade contada é igual ao saldo atual.")
        fetch_one(
            "INSERT INTO movimentacoes_estoque (variacao_id, tipo, quantidade, usuario_id, motivo) "
            "VALUES (%s, 'AJUSTE', %s, %s, %s) RETURNING id",
            (variacao_id, diferenca, usuario_id, motivo),
            conn,
        )
    return diferenca
