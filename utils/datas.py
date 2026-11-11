"""Funções de data e hora no fuso da loja."""
import calendar
from datetime import date, datetime, time

from config import FUSO


def hoje() -> date:
    return datetime.now(FUSO).date()


def data_local(momento: datetime) -> date:
    """Data de um timestamp no fuso da loja."""
    return momento.astimezone(FUSO).date()


def momento_da_data(data: date) -> datetime:
    """Timestamp para gravar uma data escolhida: agora, se for hoje; senão, meio-dia."""
    if data == hoje():
        return datetime.now(FUSO)
    return datetime.combine(data, time(12, 0), tzinfo=FUSO)


def somar_meses(data: date, meses: int) -> date:
    """Soma meses mantendo o dia, limitado ao último dia do mês de destino."""
    indice = data.month - 1 + meses
    ano, mes = data.year + indice // 12, indice % 12 + 1
    return date(ano, mes, min(data.day, calendar.monthrange(ano, mes)[1]))
