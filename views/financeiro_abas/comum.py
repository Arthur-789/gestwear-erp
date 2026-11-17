"""Componentes compartilhados pelas abas do Financeiro."""
from datetime import date
from decimal import Decimal

import streamlit as st

from services import tesouraria_service as tesouraria
from utils.datas import hoje
from utils.formatacao import fmt_brl


def formulario_baixa(
    chave: str,
    rotulo_botao: str,
    rotulo_conta: str,
    valor: Decimal,
    data_origem: date | None,
    saida: bool,
) -> tuple[bool, int | None, date]:
    """Escolha da conta financeira e da data da baixa. Devolve (clicou, conta_id, data)."""
    contas = {c["id"]: c for c in tesouraria.listar_contas(somente_ativas=True)}
    a, b = st.columns([3, 2])
    conta_id = a.selectbox(
        rotulo_conta,
        list(contas),
        format_func=lambda i: f"{contas[i]['nome']} | saldo {fmt_brl(contas[i]['saldo_atual'])}",
        key=f"{chave}_conta",
    )
    data = b.date_input(
        "Data",
        value=hoje(),
        min_value=data_origem,
        max_value=hoje(),
        format="DD/MM/YYYY",
        key=f"{chave}_data",
    )
    if saida and conta_id is not None and contas[conta_id]["saldo_atual"] < valor:
        st.warning(
            f"O saldo de {contas[conta_id]['nome']} ficará negativo após este pagamento "
            f"({fmt_brl(contas[conta_id]['saldo_atual'] - valor)})."
        )
    clicou = st.button(rotulo_botao, type="primary", key=f"{chave}_confirmar", disabled=conta_id is None)
    return clicou, conta_id, data
