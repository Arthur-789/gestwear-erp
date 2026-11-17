"""Fluxo de caixa: realizado (movimentações) e projetado (contas em aberto)."""
from datetime import date, timedelta
from decimal import Decimal

from db.connection import fetch_all, fetch_one
from services.excecoes import RegraDeNegocioError
from utils.datas import hoje, somar_meses

AGRUPAMENTOS = {"day": "Dia", "month": "Mês"}

_FUSO_SQL = "'America/Recife'"
_MAX_DIAS_POR_DIA = 366
_MAX_DIAS_POR_MES = 1830
_ZERO = Decimal("0.00")


def _validar_periodo(data_inicio: date, data_fim: date, agrupamento: str) -> None:
    if agrupamento not in AGRUPAMENTOS:
        raise RegraDeNegocioError("Selecione o agrupamento.")
    if not isinstance(data_inicio, date) or not isinstance(data_fim, date):
        raise RegraDeNegocioError("Informe o período.")
    if data_fim < data_inicio:
        raise RegraDeNegocioError("A data final não pode ser anterior à inicial.")
    dias = (data_fim - data_inicio).days + 1
    if agrupamento == "day" and dias > _MAX_DIAS_POR_DIA:
        raise RegraDeNegocioError("Para períodos acima de 366 dias, agrupe por mês.")
    if agrupamento == "month" and dias > _MAX_DIAS_POR_MES:
        raise RegraDeNegocioError("O período máximo é de 5 anos.")


def _periodos(data_inicio: date, data_fim: date, agrupamento: str) -> list[date]:
    atual = data_inicio if agrupamento == "day" else data_inicio.replace(day=1)
    periodos = []
    while atual <= data_fim:
        periodos.append(atual)
        atual = atual + timedelta(days=1) if agrupamento == "day" else somar_meses(atual, 1)
    return periodos


def saldo_ate(data_limite_exclusiva: date, conta_id: int | None = None) -> Decimal:
    """Saldo contábil no início do dia informado (movimentações anteriores a ele)."""
    filtro_conta = "WHERE id = %s" if conta_id is not None else ""
    filtro_mov = "AND conta_financeira_id = %s" if conta_id is not None else ""
    parametros_conta = [conta_id] if conta_id is not None else []
    inicial = fetch_one(
        f"SELECT COALESCE(SUM(saldo_inicial), 0) AS valor FROM contas_financeiras {filtro_conta}",
        parametros_conta,
    )["valor"]
    movimento = fetch_one(
        f"""
        SELECT COALESCE(SUM(CASE tipo WHEN 'ENTRADA' THEN valor ELSE -valor END), 0) AS valor
          FROM movimentacoes_financeiras
         WHERE (data_movimento AT TIME ZONE {_FUSO_SQL})::date < %s {filtro_mov}
        """,
        [data_limite_exclusiva] + parametros_conta,
    )["valor"]
    return inicial + movimento


def realizado(
    data_inicio: date, data_fim: date, agrupamento: str, conta_id: int | None = None
) -> dict:
    """Entradas e saídas efetivas por período, com saldo acumulado a partir do saldo inicial do período."""
    _validar_periodo(data_inicio, data_fim, agrupamento)
    filtro_conta = "AND m.conta_financeira_id = %s" if conta_id is not None else ""
    linhas = fetch_all(
        f"""
        SELECT date_trunc('{agrupamento}', m.data_movimento AT TIME ZONE {_FUSO_SQL})::date AS periodo,
               COALESCE(SUM(m.valor) FILTER (WHERE m.tipo = 'ENTRADA'), 0) AS entradas,
               COALESCE(SUM(m.valor) FILTER (WHERE m.tipo = 'SAIDA'), 0) AS saidas
          FROM movimentacoes_financeiras m
         WHERE (m.data_movimento AT TIME ZONE {_FUSO_SQL})::date BETWEEN %s AND %s {filtro_conta}
         GROUP BY 1
        """,
        [data_inicio, data_fim] + ([conta_id] if conta_id is not None else []),
    )
    por_periodo = {linha["periodo"]: linha for linha in linhas}
    saldo_inicial = saldo_ate(data_inicio, conta_id)
    acumulado, periodos = saldo_inicial, []
    for periodo in _periodos(data_inicio, data_fim, agrupamento):
        linha = por_periodo.get(periodo)
        entradas = linha["entradas"] if linha else _ZERO
        saidas = linha["saidas"] if linha else _ZERO
        acumulado += entradas - saidas
        periodos.append(
            {
                "periodo": periodo,
                "entradas": entradas,
                "saidas": saidas,
                "saldo_periodo": entradas - saidas,
                "saldo_acumulado": acumulado,
            }
        )
    return {
        "saldo_inicial": saldo_inicial,
        "saldo_final": acumulado,
        "total_entradas": sum((p["entradas"] for p in periodos), _ZERO),
        "total_saidas": sum((p["saidas"] for p in periodos), _ZERO),
        "periodos": periodos,
    }


def projetado(data_fim: date, agrupamento: str) -> dict:
    """Contas em aberto por vencimento, de hoje até a data final.

    O saldo inicial é o saldo atual das contas; as contas já vencidas entram no
    início da projeção, como se fossem liquidadas imediatamente.
    """
    inicio = hoje()
    _validar_periodo(inicio, data_fim, agrupamento)

    def somar_por_periodo(tabela: str) -> dict:
        linhas = fetch_all(
            f"""
            SELECT date_trunc('{agrupamento}', data_vencimento)::date AS periodo, SUM(valor) AS total
              FROM {tabela}
             WHERE status = 'ABERTA' AND data_vencimento BETWEEN %s AND %s
             GROUP BY 1
            """,
            (inicio, data_fim),
        )
        return {linha["periodo"]: linha["total"] for linha in linhas}

    def somar_atraso(tabela: str) -> Decimal:
        return fetch_one(
            f"SELECT COALESCE(SUM(valor), 0) AS total FROM {tabela} "
            "WHERE status = 'ABERTA' AND data_vencimento < %s",
            (inicio,),
        )["total"]

    a_receber, a_pagar = somar_por_periodo("contas_receber"), somar_por_periodo("contas_pagar")
    atraso_receber, atraso_pagar = somar_atraso("contas_receber"), somar_atraso("contas_pagar")
    saldo_inicial = saldo_ate(inicio + timedelta(days=1))
    acumulado = saldo_inicial + atraso_receber - atraso_pagar
    periodos = []
    for periodo in _periodos(inicio, data_fim, agrupamento):
        receber, pagar = a_receber.get(periodo, _ZERO), a_pagar.get(periodo, _ZERO)
        acumulado += receber - pagar
        periodos.append(
            {
                "periodo": periodo,
                "receber": receber,
                "pagar": pagar,
                "saldo_periodo": receber - pagar,
                "saldo_acumulado": acumulado,
            }
        )
    return {
        "saldo_inicial": saldo_inicial,
        "atraso_receber": atraso_receber,
        "atraso_pagar": atraso_pagar,
        "saldo_final": acumulado,
        "total_receber": sum((p["receber"] for p in periodos), _ZERO) + atraso_receber,
        "total_pagar": sum((p["pagar"] for p in periodos), _ZERO) + atraso_pagar,
        "periodos": periodos,
    }
