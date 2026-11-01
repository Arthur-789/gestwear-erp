"""Funções de formatação para exibição."""
from datetime import date, datetime
from decimal import Decimal

from config import FUSO


def fmt_datahora(valor: datetime | None) -> str:
    if valor is None:
        return "-"
    return valor.astimezone(FUSO).strftime("%d/%m/%Y %H:%M")


def fmt_data(valor: date | datetime | None) -> str:
    if valor is None:
        return "-"
    if isinstance(valor, datetime):
        valor = valor.astimezone(FUSO)
    return valor.strftime("%d/%m/%Y")


def fmt_brl(valor: Decimal | float | int | None) -> str:
    if valor is None:
        return "-"
    texto = f"{float(valor):,.2f}"
    return "R$ " + texto.replace(",", "X").replace(".", ",").replace("X", ".")
