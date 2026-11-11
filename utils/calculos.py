"""Cálculos financeiros e de estoque."""
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

CENTAVO = Decimal("0.01")


def dividir_em_parcelas(total: Decimal, quantidade: int) -> list[Decimal]:
    """Divide o total em parcelas iguais; a última absorve a diferença de centavos."""
    base = (total / quantidade).quantize(CENTAVO, rounding=ROUND_DOWN)
    parcelas = [base] * quantidade
    parcelas[-1] = total - base * (quantidade - 1)
    return parcelas


def calcular_custo_medio(
    saldo: int, custo_atual: Decimal, quantidade: int, custo_unitario: Decimal
) -> Decimal:
    """Custo médio ponderado após a entrada de uma compra."""
    total = saldo * custo_atual + quantidade * custo_unitario
    return (total / (saldo + quantidade)).quantize(CENTAVO, rounding=ROUND_HALF_UP)
