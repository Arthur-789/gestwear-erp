"""Constantes e parâmetros globais do sistema."""
from decimal import Decimal
from zoneinfo import ZoneInfo

APP_NOME = "GestWear ERP"
APP_ICONE = "👕"

# Fuso horário de exibição (o banco armazena timestamptz)
FUSO = ZoneInfo("America/Recife")

# Perfis de acesso
PERFIS = ("ADMIN", "GERENTE", "VENDEDOR")

# Parâmetros de negócio
PRAZO_TROCA_DIAS = 30
DESCONTO_MAX_SEM_APROVACAO = Decimal("0.10")  # 10% do subtotal
PARCELA_MINIMA_CREDITO = Decimal("30.00")
MAX_PARCELAS = 12
