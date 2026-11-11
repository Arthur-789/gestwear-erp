"""Módulo Estoque: posição por SKU, histórico de movimentações e ajuste de inventário."""
from datetime import timedelta

import pandas as pd
import streamlit as st

from config import PERFIS_GESTAO
from services import catalogo_service as catalogo
from services import estoque_service as estoque
from services.auth_service import usuario_atual
from services.excecoes import RegraDeNegocioError
from utils.datas import hoje
from utils.formatacao import fmt_brl, fmt_datahora
from utils.ui import avisar_apos_recarregar, exibir_mensagens

usuario = usuario_atual()
pode_ajustar = usuario["perfil"] in PERFIS_GESTAO

st.title("Estoque")
exibir_mensagens()


def situacao(linha: dict) -> str:
    if not linha["ativo"]:
        return "Inativo"
    if linha["estoque_atual"] == 0:
        return "Sem estoque"
    return "Abaixo do mínimo" if linha["em_alerta"] else "Normal"


nomes_abas = ["Posição", "Movimentações"] + (["Ajuste de inventário"] if pode_ajustar else [])
abas = st.tabs(nomes_abas)

# ---------------------------------------------------------------- Posição
with abas[0]:
    categorias = {c["id"]: c["nome"] for c in catalogo.listar_categorias()}
    c1, c2, c3 = st.columns([3, 2, 2])
    busca = c1.text_input("Buscar por produto ou SKU", key="est_busca")
    categoria = c2.selectbox(
        "Categoria", [None] + list(categorias),
        format_func=lambda i: "Todas" if i is None else categorias[i], key="est_categoria",
    )
    c3.write("")
    somente_alerta = c3.checkbox("Somente abaixo do mínimo", key="est_alerta")
    incluir_inativos = c3.checkbox("Incluir inativos", key="est_inativos")

    posicao = estoque.posicao_estoque(busca, categoria, somente_alerta, incluir_inativos)
    unidades = sum(p["estoque_atual"] for p in posicao)
    em_alerta = sum(1 for p in posicao if p["em_alerta"] and p["ativo"])
    colunas_metricas = st.columns(3 if pode_ajustar else 2)
    colunas_metricas[0].metric("Unidades em estoque", unidades)
    colunas_metricas[1].metric("SKUs abaixo do mínimo", em_alerta)
    if pode_ajustar:
        valor = sum(p["estoque_atual"] * p["custo_medio"] for p in posicao)
        colunas_metricas[2].metric("Valor em estoque (custo médio)", fmt_brl(valor))

    if not posicao:
        st.info("Nenhum SKU encontrado.")
    else:
        linhas = []
        for p in posicao:
            linha = {
                "SKU": p["sku"],
                "Produto": p["produto"],
                "Categoria": p["categoria"],
                "Tamanho": p["tamanho"],
                "Cor": p["cor"],
                "Estoque": p["estoque_atual"],
                "Mínimo": p["estoque_minimo"],
                "Situação": situacao(p),
            }
            if pode_ajustar:
                linha["Custo médio"] = fmt_brl(p["custo_medio"])
            linha["Preço"] = fmt_brl(p["preco_venda"])
            linhas.append(linha)
        st.dataframe(pd.DataFrame(linhas), hide_index=True, width="stretch")

# ---------------------------------------------------------------- Movimentações
with abas[1]:
    c1, c2, c3, c4 = st.columns([3, 2, 2, 2])
    busca_m = c1.text_input("Buscar por produto ou SKU", key="mov_busca")
    tipo = c2.selectbox(
        "Tipo", [None] + list(estoque.TIPOS_MOVIMENTACAO),
        format_func=lambda t: "Todos" if t is None else estoque.TIPOS_MOVIMENTACAO[t], key="mov_tipo",
    )
    data_de = c3.date_input(
        "De", value=hoje() - timedelta(days=30), format="DD/MM/YYYY", key="mov_de"
    )
    data_ate = c4.date_input("Até", value=hoje(), format="DD/MM/YYYY", key="mov_ate")
    movimentos = estoque.historico_movimentacoes(busca_m, tipo, data_de, data_ate)
    if not movimentos:
        st.info("Nenhuma movimentação no período.")
    else:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Data": fmt_datahora(m["criado_em"]),
                        "SKU": m["sku"],
                        "Produto": m["produto"],
                        "Tipo": estoque.TIPOS_MOVIMENTACAO[m["tipo"]],
                        "Quantidade": f"{m['quantidade']:+d}",
                        "Saldo anterior": m["saldo_anterior"],
                        "Saldo posterior": m["saldo_posterior"],
                        "Origem": m["origem"],
                        "Motivo": m["motivo"] or "",
                        "Usuário": m["usuario"],
                    }
                    for m in movimentos
                ]
            ),
            hide_index=True,
            width="stretch",
        )
        if len(movimentos) == 500:
            st.caption("Exibindo as 500 movimentações mais recentes do filtro.")

if not pode_ajustar:
    st.stop()

# ---------------------------------------------------------------- Ajuste
with abas[2]:
    st.caption("Informe a quantidade contada fisicamente. O sistema registra a diferença como ajuste.")
    skus = catalogo.listar_skus_ativos()
    if not skus:
        st.info("Nenhum SKU ativo cadastrado.")
    else:
        por_id = {s["id"]: s for s in skus}
        vid = st.selectbox(
            "SKU", list(por_id),
            format_func=lambda i: f"{por_id[i]['sku']} | {por_id[i]['produto']} | {por_id[i]['tamanho']} | {por_id[i]['cor']}",
            key="ajuste_sku",
        )
        atual = por_id[vid]["estoque_atual"]
        st.metric("Saldo atual no sistema", atual)
        with st.form(f"form_ajuste_{vid}"):
            contado = st.number_input("Quantidade contada", min_value=0, value=int(atual), step=1)
            motivo = st.text_input("Motivo do ajuste", placeholder="Ex.: contagem de inventário, perda, avaria")
            if st.form_submit_button("Registrar ajuste", type="primary"):
                try:
                    diferenca = estoque.ajustar_estoque(vid, contado, motivo, usuario["id"])
                    avisar_apos_recarregar(f"Ajuste registrado ({diferenca:+d} unidade(s)).")
                    st.rerun()
                except RegraDeNegocioError as e:
                    st.error(str(e))
