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


def fmt_cpf(valor: str | None) -> str:
    d = "".join(c for c in (valor or "") if c.isdigit())
    if len(d) != 11:
        return valor or ""
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"


def fmt_cnpj(valor: str | None) -> str:
    d = "".join(c for c in (valor or "") if c.isdigit())
    if len(d) != 14:
        return valor or ""
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"


def fmt_telefone(valor: str | None) -> str:
    d = "".join(c for c in (valor or "") if c.isdigit())
    if len(d) == 11:
        return f"({d[:2]}) {d[2:7]}-{d[7:]}"
    if len(d) == 10:
        return f"({d[:2]}) {d[2:6]}-{d[6:]}"
    return valor or ""


def rotulo_situacao(ativo: bool) -> str:
    return "Ativo" if ativo else "Inativo"
