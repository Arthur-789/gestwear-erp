"""Módulo Cadastro: categorias, tamanhos e cores."""
import pandas as pd
import streamlit as st

from services import catalogo_service as catalogo
from services.auth_service import exigir_perfil
from services.excecoes import RegraDeNegocioError
from utils.formatacao import rotulo_situacao
from utils.ui import avisar_apos_recarregar, exibir_mensagens

exigir_perfil("ADMIN", "GERENTE")

st.title("Tabelas auxiliares")
st.caption("Categorias, tamanhos e cores usados na composição dos produtos e dos SKUs.")
exibir_mensagens()

aba_cat, aba_tam, aba_cor = st.tabs(["Categorias", "Tamanhos", "Cores"])

# ---------------------------------------------------------------- Categorias
with aba_cat:
    categorias = catalogo.listar_categorias()
    if categorias:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Categoria": c["nome"],
                        "Código": c["codigo"],
                        "Produtos": c["produtos"],
                        "Situação": rotulo_situacao(c["ativo"]),
                    }
                    for c in categorias
                ]
            ),
            hide_index=True,
            width="stretch",
        )
    with st.expander("Nova categoria"):
        with st.form("form_nova_categoria", clear_on_submit=True):
            c1, c2 = st.columns([3, 1])
            nome = c1.text_input("Nome")
            codigo = c2.text_input("Código (2 a 5)", help="Usado no início do SKU. Ex.: CAM")
            if st.form_submit_button("Cadastrar", type="primary"):
                try:
                    catalogo.criar_categoria(nome, codigo)
                    avisar_apos_recarregar("Categoria cadastrada.")
                    st.rerun()
                except RegraDeNegocioError as e:
                    st.error(str(e))
    if categorias:
        with st.expander("Editar categoria"):
            por_id = {c["id"]: c for c in categorias}
            cid = st.selectbox(
                "Categoria", list(por_id), format_func=lambda i: por_id[i]["nome"], key="cat_editar"
            )
            c = por_id[cid]
            with st.form(f"form_editar_categoria_{cid}"):
                col1, col2 = st.columns([3, 1])
                nome_e = col1.text_input("Nome", value=c["nome"])
                codigo_e = col2.text_input("Código", value=c["codigo"])
                ativo_e = st.checkbox("Categoria ativa", value=c["ativo"])
                if st.form_submit_button("Salvar", type="primary"):
                    try:
                        catalogo.atualizar_categoria(cid, nome_e, codigo_e, ativo_e)
                        avisar_apos_recarregar("Categoria atualizada.")
                        st.rerun()
                    except RegraDeNegocioError as e:
                        st.error(str(e))

# ---------------------------------------------------------------- Tamanhos
with aba_tam:
    tamanhos = catalogo.listar_tamanhos()
    if tamanhos:
        st.dataframe(
            pd.DataFrame(
                [
                    {"Tamanho": t["nome"], "Ordem": t["ordem"], "Variações": t["variacoes"]}
                    for t in tamanhos
                ]
            ),
            hide_index=True,
            width="stretch",
        )
    with st.expander("Novo tamanho"):
        with st.form("form_novo_tamanho", clear_on_submit=True):
            c1, c2 = st.columns(2)
            nome = c1.text_input("Nome (1 a 5)", help="Usado no SKU. Ex.: M, GG, 40")
            ordem = c2.number_input("Ordem de exibição", min_value=0, max_value=999, value=0, step=1)
            if st.form_submit_button("Cadastrar", type="primary"):
                try:
                    catalogo.criar_tamanho(nome, ordem)
                    avisar_apos_recarregar("Tamanho cadastrado.")
                    st.rerun()
                except RegraDeNegocioError as e:
                    st.error(str(e))
    if tamanhos:
        with st.expander("Editar ou excluir tamanho"):
            por_id = {t["id"]: t for t in tamanhos}
            tid = st.selectbox(
                "Tamanho", list(por_id), format_func=lambda i: por_id[i]["nome"], key="tam_editar"
            )
            t = por_id[tid]
            with st.form(f"form_editar_tamanho_{tid}"):
                col1, col2 = st.columns(2)
                nome_e = col1.text_input("Nome", value=t["nome"])
                ordem_e = col2.number_input(
                    "Ordem de exibição", min_value=0, max_value=999, value=int(t["ordem"]), step=1
                )
                salvar = st.form_submit_button("Salvar", type="primary")
                excluir = st.form_submit_button("Excluir")
                if salvar or excluir:
                    try:
                        if salvar:
                            catalogo.atualizar_tamanho(tid, nome_e, ordem_e)
                            avisar_apos_recarregar("Tamanho atualizado.")
                        else:
                            catalogo.excluir_tamanho(tid)
                            avisar_apos_recarregar("Tamanho excluído.")
                        st.rerun()
                    except RegraDeNegocioError as e:
                        st.error(str(e))

# ---------------------------------------------------------------- Cores
with aba_cor:
    cores = catalogo.listar_cores()
    if cores:
        st.dataframe(
            pd.DataFrame(
                [
                    {"Cor": c["nome"], "Código": c["codigo"], "Variações": c["variacoes"]}
                    for c in cores
                ]
            ),
            hide_index=True,
            width="stretch",
        )
    with st.expander("Nova cor"):
        with st.form("form_nova_cor", clear_on_submit=True):
            c1, c2 = st.columns([3, 1])
            nome = c1.text_input("Nome")
            codigo = c2.text_input("Código (1 a 4)", help="Usado no fim do SKU. Ex.: AZ")
            if st.form_submit_button("Cadastrar", type="primary"):
                try:
                    catalogo.criar_cor(nome, codigo)
                    avisar_apos_recarregar("Cor cadastrada.")
                    st.rerun()
                except RegraDeNegocioError as e:
                    st.error(str(e))
    if cores:
        with st.expander("Editar ou excluir cor"):
            por_id = {c["id"]: c for c in cores}
            cid = st.selectbox(
                "Cor", list(por_id), format_func=lambda i: por_id[i]["nome"], key="cor_editar"
            )
            c = por_id[cid]
            with st.form(f"form_editar_cor_{cid}"):
                col1, col2 = st.columns([3, 1])
                nome_e = col1.text_input("Nome", value=c["nome"])
                codigo_e = col2.text_input("Código", value=c["codigo"])
                salvar = st.form_submit_button("Salvar", type="primary")
                excluir = st.form_submit_button("Excluir")
                if salvar or excluir:
                    try:
                        if salvar:
                            catalogo.atualizar_cor(cid, nome_e, codigo_e)
                            avisar_apos_recarregar("Cor atualizada.")
                        else:
                            catalogo.excluir_cor(cid)
                            avisar_apos_recarregar("Cor excluída.")
                        st.rerun()
                    except RegraDeNegocioError as e:
                        st.error(str(e))
