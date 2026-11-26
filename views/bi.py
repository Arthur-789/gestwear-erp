"""Dashboard de Business Intelligence (somente gestão): indicadores lidos direto do banco."""
import streamlit as st

from config import PERFIS_GESTAO
from services.auth_service import exigir_perfil
from views.bi_abas import comum, financeiro, operacoes, produtos_estoque, vendas, visao_geral
from utils.ui import cabecalho

exigir_perfil(*PERFIS_GESTAO)

cabecalho("Dashboard BI", "bi")
inicio, fim, agrupamento = comum.seletor_periodo()

abas = st.tabs(["Visão geral", "Vendas", "Produtos e estoque", "Financeiro", "Operações"])
with abas[0]:
    visao_geral.renderizar(inicio, fim, agrupamento)
with abas[1]:
    vendas.renderizar(inicio, fim, agrupamento)
with abas[2]:
    produtos_estoque.renderizar(inicio, fim, agrupamento)
with abas[3]:
    financeiro.renderizar(inicio, fim, agrupamento)
with abas[4]:
    operacoes.renderizar(inicio, fim, agrupamento)
