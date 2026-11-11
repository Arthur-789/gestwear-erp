"""Página inicial: boas-vindas e verificação da conexão com o banco."""
import pandas as pd
import streamlit as st

from config import APP_NOME
from db.connection import fetch_one
from services import estoque_service
from services.auth_service import usuario_atual

usuario = usuario_atual()
st.title(APP_NOME)
st.write(f"Olá, **{usuario['nome']}**. Perfil: **{usuario['perfil'].title()}**.")

st.subheader("Situação do sistema")
try:
    versao = fetch_one("SELECT version() AS v")["v"].split(",")[0]
    contagens = fetch_one(
        """
        SELECT (SELECT count(*) FROM usuarios)      AS usuarios,
               (SELECT count(*) FROM produtos)      AS produtos,
               (SELECT count(*) FROM clientes)      AS clientes,
               (SELECT count(*) FROM fornecedores)  AS fornecedores
        """
    )
    st.success(f"Banco de dados conectado ({versao}).")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Usuários", contagens["usuarios"])
    c2.metric("Produtos", contagens["produtos"])
    c3.metric("Clientes", contagens["clientes"])
    c4.metric("Fornecedores", contagens["fornecedores"])
except Exception as exc:
    st.error(f"Falha ao consultar o banco: {exc}")

st.subheader("Reposição de estoque")
try:
    alertas = estoque_service.alertas_reposicao()
    if alertas["total"] == 0:
        st.success("Nenhum SKU abaixo do estoque mínimo.")
    else:
        st.warning(
            f"{alertas['total']} SKU(s) com estoque igual ou abaixo do mínimo. "
            "Consulte a página Estoque para o detalhamento."
        )
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "SKU": a["sku"],
                        "Produto": a["produto"],
                        "Tamanho": a["tamanho"],
                        "Cor": a["cor"],
                        "Estoque": a["estoque_atual"],
                        "Mínimo": a["estoque_minimo"],
                    }
                    for a in alertas["itens"]
                ]
            ),
            hide_index=True,
            width="stretch",
        )
        if alertas["total"] > len(alertas["itens"]):
            st.caption(f"Exibindo os {len(alertas['itens'])} mais críticos.")
except Exception as exc:
    st.error(f"Falha ao consultar o estoque: {exc}")
