"""Módulo Cadastro: produtos e variações (SKU)."""
import pandas as pd
import streamlit as st

from config import PERFIS_GESTAO
from services import catalogo_service as catalogo
from services.auth_service import usuario_atual
from services.excecoes import RegraDeNegocioError
from utils.formatacao import fmt_brl, rotulo_situacao
from utils.ui import avisar_apos_recarregar, exibir_mensagens

usuario = usuario_atual()
pode_editar = usuario["perfil"] in PERFIS_GESTAO

st.title("Produtos")
exibir_mensagens()


def tabela_variacoes(variacoes: list[dict]) -> pd.DataFrame:
    linhas = []
    for v in variacoes:
        linha = {
            "SKU": v["sku"],
            "Tamanho": v["tamanho"],
            "Cor": v["cor"],
            "Preço": fmt_brl(v["preco_venda"]),
        }
        if pode_editar:
            linha["Custo médio"] = fmt_brl(v["custo_medio"])
        linha.update(
            {
                "Estoque": v["estoque_atual"],
                "Mínimo": v["estoque_minimo"],
                "Situação": rotulo_situacao(v["ativo"]),
            }
        )
        linhas.append(linha)
    return pd.DataFrame(linhas)


def faixa_preco(minimo, maximo) -> str:
    if minimo is None:
        return "-"
    return fmt_brl(minimo) if minimo == maximo else f"{fmt_brl(minimo)} a {fmt_brl(maximo)}"


nomes_abas = ["Lista"] + (["Novo produto", "Gerenciar produto"] if pode_editar else [])
abas = st.tabs(nomes_abas)

# ---------------------------------------------------------------- Lista
with abas[0]:
    categorias = catalogo.listar_categorias()
    cat_por_id = {c["id"]: c["nome"] for c in categorias}
    c1, c2, c3 = st.columns([2, 1, 1])
    busca = c1.text_input("Buscar por nome ou SKU", key="prod_busca")
    categoria_filtro = c2.selectbox(
        "Categoria", [None] + list(cat_por_id), format_func=lambda i: "Todas" if i is None else cat_por_id[i]
    )
    situacao = c3.selectbox("Situação", ["Todos", "Ativos", "Inativos"], key="prod_situacao")
    ativo_filtro = {"Todos": None, "Ativos": True, "Inativos": False}[situacao]

    produtos = catalogo.listar_produtos(busca, categoria_filtro, ativo_filtro)
    if not produtos:
        st.info("Nenhum produto encontrado.")
    else:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Produto": p["nome"],
                        "Categoria": p["categoria"],
                        "Variações": p["variacoes"],
                        "Estoque total": p["estoque_total"],
                        "Preço": faixa_preco(p["preco_min"], p["preco_max"]),
                        "Situação": rotulo_situacao(p["ativo"]),
                    }
                    for p in produtos
                ]
            ),
            hide_index=True,
            width="stretch",
        )
        por_id = {p["id"]: p for p in produtos}
        escolhido = st.selectbox(
            "Ver variações de", list(por_id), format_func=lambda i: por_id[i]["nome"], key="prod_ver"
        )
        variacoes = catalogo.listar_variacoes(escolhido)
        if variacoes:
            st.dataframe(tabela_variacoes(variacoes), hide_index=True, width="stretch")
        else:
            st.caption("Este produto ainda não tem variações.")

if not pode_editar:
    st.stop()

# ---------------------------------------------------------------- Novo produto
with abas[1]:
    categorias_ativas = catalogo.listar_categorias(somente_ativas=True)
    if not categorias_ativas:
        st.warning("Cadastre ao menos uma categoria em Tabelas auxiliares.")
    else:
        with st.form("form_novo_produto", clear_on_submit=True):
            nome = st.text_input("Nome do produto")
            categoria_id = st.selectbox(
                "Categoria",
                [c["id"] for c in categorias_ativas],
                format_func=lambda i: next(c["nome"] for c in categorias_ativas if c["id"] == i),
            )
            descricao = st.text_area("Descrição (opcional)")
            if st.form_submit_button("Cadastrar produto", type="primary"):
                try:
                    novo_id = catalogo.criar_produto(nome, descricao, categoria_id)
                    st.session_state["produto_gerenciar"] = novo_id
                    avisar_apos_recarregar(
                        "Produto cadastrado. Na aba Gerenciar produto, adicione as variações."
                    )
                    st.rerun()
                except RegraDeNegocioError as e:
                    st.error(str(e))

# ---------------------------------------------------------------- Gerenciar
with abas[2]:
    todos = catalogo.listar_produtos()
    if not todos:
        st.info("Cadastre um produto na aba Novo produto.")
        st.stop()

    nomes = {p["id"]: p["nome"] for p in todos}
    pid = st.selectbox("Produto", list(nomes), format_func=lambda i: nomes[i], key="produto_gerenciar")
    produto = catalogo.buscar_produto(pid)
    variacoes = catalogo.listar_variacoes(pid)

    st.subheader("Dados do produto")
    todas_categorias = catalogo.listar_categorias()
    opcoes_cat = {
        c["id"]: c["nome"] + ("" if c["ativo"] else " (inativa)")
        for c in todas_categorias
        if c["ativo"] or c["id"] == produto["categoria_id"]
    }
    with st.form(f"form_produto_{pid}"):
        nome_e = st.text_input("Nome do produto", value=produto["nome"])
        categoria_e = st.selectbox(
            "Categoria",
            list(opcoes_cat),
            index=list(opcoes_cat).index(produto["categoria_id"]),
            format_func=lambda i: opcoes_cat[i],
            disabled=bool(variacoes),
            help="A categoria não pode ser alterada depois que o produto tem variações (SKUs).",
        )
        descricao_e = st.text_area("Descrição", value=produto["descricao"] or "")
        ativo_e = st.checkbox("Produto ativo", value=produto["ativo"])
        if st.form_submit_button("Salvar produto", type="primary"):
            try:
                catalogo.atualizar_produto(pid, nome_e, descricao_e, categoria_e, ativo_e)
                avisar_apos_recarregar("Produto atualizado.")
                st.rerun()
            except RegraDeNegocioError as e:
                st.error(str(e))

    st.subheader("Variações")
    if variacoes:
        st.dataframe(tabela_variacoes(variacoes), hide_index=True, width="stretch")
    else:
        st.caption("Nenhuma variação cadastrada.")

    tamanhos = catalogo.listar_tamanhos()
    cores = catalogo.listar_cores()
    tam_nome = {t["id"]: t["nome"] for t in tamanhos}
    cor_nome = {c["id"]: c["nome"] for c in cores}

    with st.expander("Nova variação", expanded=not variacoes):
        if not produto["ativo"]:
            st.warning("Produto inativo: não é possível adicionar variações.")
        else:
            with st.form(f"form_nova_variacao_{pid}", clear_on_submit=True):
                col1, col2 = st.columns(2)
                tamanho_id = col1.selectbox("Tamanho", list(tam_nome), format_func=lambda i: tam_nome[i])
                cor_id = col2.selectbox("Cor", list(cor_nome), format_func=lambda i: cor_nome[i])
                col3, col4 = st.columns(2)
                preco = col3.number_input(
                    "Preço de venda (R$)", min_value=0.0, value=None, step=1.0,
                    format="%.2f", placeholder="0,00",
                )
                minimo = col4.number_input("Estoque mínimo", min_value=0, value=0, step=1)
                if st.form_submit_button("Adicionar variação", type="primary"):
                    try:
                        criada = catalogo.criar_variacao(pid, tamanho_id, cor_id, preco, minimo)
                        avisar_apos_recarregar(f"Variação criada com o SKU {criada['sku']}.")
                        st.rerun()
                    except RegraDeNegocioError as e:
                        st.error(str(e))

    if variacoes:
        with st.expander("Editar variação"):
            por_id_v = {v["id"]: v for v in variacoes}
            vid = st.selectbox(
                "Variação",
                list(por_id_v),
                format_func=lambda i: f"{por_id_v[i]['sku']} ({por_id_v[i]['tamanho']} / {por_id_v[i]['cor']})",
                key=f"variacao_editar_{pid}",
            )
            v = por_id_v[vid]
            with st.form(f"form_editar_variacao_{vid}"):
                col1, col2 = st.columns(2)
                preco_e = col1.number_input(
                    "Preço de venda (R$)", min_value=0.01, value=float(v["preco_venda"]),
                    step=1.0, format="%.2f",
                )
                minimo_e = col2.number_input(
                    "Estoque mínimo", min_value=0, value=int(v["estoque_minimo"]), step=1
                )
                ativo_v = st.checkbox("Variação ativa", value=v["ativo"])
                if st.form_submit_button("Salvar variação", type="primary"):
                    try:
                        alertas = catalogo.atualizar_variacao(vid, preco_e, minimo_e, ativo_v)
                        avisar_apos_recarregar("Variação atualizada.")
                        for alerta in alertas:
                            avisar_apos_recarregar(alerta, "warning")
                        st.rerun()
                    except RegraDeNegocioError as e:
                        st.error(str(e))
