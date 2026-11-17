"""Módulo Financeiro: contas a pagar e a receber, caixa e bancos, fluxo de caixa e conciliação."""
import streamlit as st

from config import PERFIS_GESTAO
from services.auth_service import exigir_perfil
from utils.ui import exibir_mensagens
from views.financeiro_abas import caixa_bancos, conciliacao, contas_pagar, contas_receber, fluxo_caixa

usuario = exigir_perfil(*PERFIS_GESTAO)

st.title("Financeiro")
exibir_mensagens()

abas = st.tabs(["Contas a pagar", "Contas a receber", "Caixa e bancos", "Fluxo de caixa", "Conciliação"])
with abas[0]:
    contas_pagar.renderizar(usuario)
with abas[1]:
    contas_receber.renderizar(usuario)
with abas[2]:
    caixa_bancos.renderizar(usuario)
with abas[3]:
    fluxo_caixa.renderizar(usuario)
with abas[4]:
    conciliacao.renderizar(usuario)
