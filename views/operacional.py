"""Módulo Operacional: trocas e devoluções de vendas."""
from decimal import Decimal

import pandas as pd
import streamlit as st

from config import PERFIS_GESTAO, PRAZO_TROCA_DIAS
from services import catalogo_service as catalogo
from services import operacional_service as oper
from services import vendas_service
from services.auth_service import usuario_atual
from services.excecoes import RegraDeNegocioError
from utils.datas import data_local, hoje
from utils.formatacao import escapar_markdown, fmt_brl, fmt_brl_md, fmt_data, fmt_datahora
from utils.ui import avisar_apos_recarregar, exibir_mensagens

usuario = usuario_atual()
pode_ver_custo = usuario["perfil"] in PERFIS_GESTAO

st.title("Trocas e devoluções")
exibir_mensagens()


def descricao_sku(s: dict) -> str:
    return f"{s['sku']} | {s['produto']} | {s['tamanho']} | {s['cor']}"


def acerto_financeiro(tipo: str, devolvido, novos, diferenca) -> str:
    """Resumo do que a operação gerou no financeiro."""
    if tipo == "DEVOLUCAO":
        return f"Estorno de {fmt_brl(devolvido)}"
    if diferenca > 0:
        return f"Cliente pagou {fmt_brl(diferenca)}"
    if diferenca < 0:
        return f"Estorno de {fmt_brl(-diferenca)}"
    return "Sem diferença"


def situacao_lancamento(lanc: dict) -> str:
    if lanc["status"] in ("PAGA", "RECEBIDA"):
        return lanc["status"].title()
    if lanc["status"] == "CANCELADA":
        return "Cancelada"
    return "Vencida" if lanc["data_vencimento"] < hoje() else "Aberta"


abas = st.tabs(["Nova solicitação", "Histórico"])

# ---------------------------------------------------------------- Nova solicitação
with abas[0]:
    nonce = st.session_state.get("oper_nonce", 0)
    k = f"oper{nonce}"
    chave_carrinho = f"carrinho_{k}"
    carrinho = st.session_state.setdefault(chave_carrinho, [])

    elegiveis = oper.listar_vendas_elegiveis()
    if not elegiveis:
        st.info(
            f"Nenhuma venda disponível: só é possível trocar ou devolver vendas dos últimos "
            f"{PRAZO_TROCA_DIAS} dias que ainda tenham itens a devolver."
        )
    else:
        por_venda = {v["id"]: v for v in elegiveis}
        venda_id = st.selectbox(
            f"Venda de origem (últimos {PRAZO_TROCA_DIAS} dias)",
            list(por_venda),
            format_func=lambda i: (
                f"#{i} | {fmt_datahora(por_venda[i]['data_venda'])} | "
                f"{por_venda[i]['cliente'] or 'Consumidor final'} | {fmt_brl(por_venda[i]['valor_total'])}"
            ),
            key=f"{k}_venda",
        )
        data_da_venda = data_local(por_venda[venda_id]["data_venda"])

        c1, c2, c3 = st.columns([2, 2, 1])
        tipo = c1.radio(
            "Tipo", list(oper.TIPOS), format_func=lambda t: oper.TIPOS[t],
            horizontal=True, key=f"{k}_tipo",
        )
        motivo = c2.selectbox(
            "Motivo", list(oper.MOTIVOS), format_func=lambda m: oper.MOTIVOS[m],
            index=None, placeholder="Selecione o motivo", key=f"{k}_motivo",
        )
        data_operacao = c3.date_input(
            "Data", value=hoje(), min_value=data_da_venda, max_value=hoje(),
            format="DD/MM/YYYY", key=f"{k}_data_{venda_id}",
        )

        st.markdown("**Itens a devolver**")
        if motivo is None:
            st.caption("Selecione o motivo: ele define se os itens voltam ao estoque.")
        elif motivo == "DEFEITO":
            st.caption("Itens com defeito não voltam ao estoque (perda ao custo).")
        else:
            st.caption("Os itens devolvidos voltam ao estoque.")
        devolvidos, valor_devolvido = [], Decimal("0.00")
        for item in (i for i in oper.itens_devolviveis(venda_id) if i["disponivel"] > 0):
            a, b, c = st.columns([5, 2, 2], vertical_alignment="center")
            a.write(
                f"{descricao_sku(item)}  \n"
                f"Vendidos: {item['quantidade']} | já devolvidos: {item['quantidade_devolvida']}"
            )
            b.write(f"{fmt_brl_md(item['valor_unitario'])} por unidade")
            quantidade = c.number_input(
                "Quantidade", min_value=0, max_value=item["disponivel"], value=0, step=1,
                label_visibility="collapsed", key=f"{k}_dev_{item['id']}_{item['disponivel']}",
            )
            if quantidade:
                devolvidos.append({"item_venda_id": item["id"], "quantidade": int(quantidade)})
                valor_devolvido += quantidade * item["valor_unitario"]
        st.caption("O valor devolvido já considera o desconto proporcional dado na venda.")

        valor_novos = Decimal("0.00")
        if tipo == "TROCA":
            st.markdown("**Itens novos**")
            no_carrinho = {i["variacao_id"]: i["quantidade"] for i in carrinho}
            disponiveis = {
                s["id"]: s
                for s in catalogo.listar_skus_ativos()
                if s["estoque_atual"] - no_carrinho.get(s["id"], 0) > 0
            }
            if not disponiveis:
                st.warning("Nenhum SKU ativo com estoque disponível.")
            else:
                a, b, c = st.columns([6, 1, 1], vertical_alignment="bottom")
                variacao_id = a.selectbox(
                    "SKU",
                    list(disponiveis),
                    format_func=lambda i: (
                        f"{descricao_sku(disponiveis[i])} | {fmt_brl(disponiveis[i]['preco_venda'])} | "
                        f"{disponiveis[i]['estoque_atual'] - no_carrinho.get(i, 0)} un."
                    ),
                    key=f"{k}_sku",
                )
                livre = disponiveis[variacao_id]["estoque_atual"] - no_carrinho.get(variacao_id, 0)
                quantidade_nova = b.number_input(
                    "Qtd", min_value=1, max_value=livre, value=1, step=1,
                    key=f"{k}_nqtd_{variacao_id}_{livre}",
                )
                if c.button("Adicionar", key=f"{k}_adicionar"):
                    existente = next((i for i in carrinho if i["variacao_id"] == variacao_id), None)
                    if existente:
                        existente["quantidade"] += int(quantidade_nova)
                    else:
                        carrinho.append(
                            {
                                "variacao_id": variacao_id,
                                "quantidade": int(quantidade_nova),
                                "preco_unitario": disponiveis[variacao_id]["preco_venda"],
                                "descricao": descricao_sku(disponiveis[variacao_id]),
                            }
                        )
                    st.rerun()

            if carrinho:
                for posicao, novo in enumerate(carrinho):
                    col_a, col_b, col_c, col_d, col_e = st.columns([5, 1, 2, 2, 1], vertical_alignment="center")
                    subtotal_novo = novo["quantidade"] * novo["preco_unitario"]
                    valor_novos += subtotal_novo
                    col_a.write(novo["descricao"])
                    col_b.write(f"{novo['quantidade']} un.")
                    col_c.write(fmt_brl_md(novo["preco_unitario"]))
                    col_d.write(fmt_brl_md(subtotal_novo))
                    if col_e.button("", icon=":material/delete:", key=f"{k}_remover_{novo['variacao_id']}"):
                        carrinho.pop(posicao)
                        st.rerun()
            else:
                st.caption("Nenhum item novo adicionado.")

        st.markdown("**Resumo**")
        diferenca = valor_novos - valor_devolvido if tipo == "TROCA" else Decimal("0.00")
        forma_diferenca = None
        if tipo == "DEVOLUCAO":
            m1, m2 = st.columns(2)
            m1.metric("Valor devolvido", fmt_brl_md(valor_devolvido))
            m2.metric("Estorno ao cliente", fmt_brl_md(valor_devolvido))
            if valor_devolvido:
                st.caption("Será gerada uma conta a pagar de estorno, a ser paga pelo Financeiro.")
        else:
            m1, m2, m3 = st.columns(3)
            m1.metric("Valor devolvido", fmt_brl_md(valor_devolvido))
            m2.metric("Valor dos itens novos", fmt_brl_md(valor_novos))
            if diferenca > 0:
                m3.metric("Cliente paga", fmt_brl_md(diferenca))
                forma_diferenca = st.selectbox(
                    "Forma de pagamento da diferença", list(oper.FORMAS_DIFERENCA),
                    format_func=lambda f: vendas_service.FORMAS_PAGAMENTO[f], key=f"{k}_forma",
                )
            elif diferenca < 0:
                m3.metric("Estorno ao cliente", fmt_brl_md(-diferenca))
                st.caption("A diferença a favor do cliente gera uma conta a pagar de estorno.")
            else:
                m3.metric("Diferença", fmt_brl_md(0))

        observacao = st.text_input("Observação (opcional)", key=f"{k}_obs")

        incompleta = motivo is None or not devolvidos or (tipo == "TROCA" and not carrinho)
        if st.button(
            f"Registrar {oper.TIPOS[tipo].lower()}", type="primary",
            key=f"{k}_registrar", disabled=incompleta,
        ):
            try:
                r = oper.registrar(
                    venda_id=venda_id,
                    tipo=tipo,
                    motivo=motivo,
                    data_operacao=data_operacao,
                    forma_pagamento_diferenca=forma_diferenca,
                    observacao=observacao,
                    itens_devolvidos=devolvidos,
                    itens_novos=[
                        {c_: i[c_] for c_ in ("variacao_id", "quantidade", "preco_unitario")}
                        for i in carrinho
                    ],
                    usuario_id=usuario["id"],
                )
                texto = f"{oper.TIPOS[tipo]} #{r['id']} registrada. "
                texto += acerto_financeiro(tipo, r["valor_devolvido"], r["valor_novos"], r["diferenca"]) + ". "
                if r["unidades_ao_estoque"]:
                    texto += f"{r['unidades_ao_estoque']} unidade(s) voltaram ao estoque. "
                if r["unidades_perdidas"]:
                    texto += f"{r['unidades_perdidas']} unidade(s) com defeito não voltaram ao estoque. "
                st.session_state["oper_nonce"] = nonce + 1
                st.session_state.pop(chave_carrinho, None)
                st.session_state["oper_detalhe"] = r["id"]
                avisar_apos_recarregar(texto + "Veja o detalhe na aba Histórico.")
                st.rerun()
            except RegraDeNegocioError as e:
                st.error(str(e))

# ---------------------------------------------------------------- Histórico
with abas[1]:
    f1, f2, f3, f4 = st.columns(4)
    filtro_tipo = f1.selectbox(
        "Tipo", [None] + list(oper.TIPOS),
        format_func=lambda t: "Todos" if t is None else oper.TIPOS[t], key="oper_filtro_tipo",
    )
    filtro_motivo = f2.selectbox(
        "Motivo", [None] + list(oper.MOTIVOS),
        format_func=lambda m: "Todos" if m is None else oper.MOTIVOS[m], key="oper_filtro_motivo",
    )
    data_de = f3.date_input("A partir de", value=None, format="DD/MM/YYYY", key="oper_de")
    data_ate = f4.date_input("Até", value=None, format="DD/MM/YYYY", key="oper_ate")

    limite = 500
    lista = oper.listar(filtro_tipo, filtro_motivo, data_de, data_ate, limite)
    if not lista:
        st.info("Nenhuma troca ou devolução encontrada.")
    else:
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Solicitações", len(lista))
        m2.metric("Devoluções", sum(1 for t in lista if t["tipo"] == "DEVOLUCAO"))
        m3.metric("Trocas", sum(1 for t in lista if t["tipo"] == "TROCA"))
        m4.metric("Valor devolvido", fmt_brl_md(sum((t["valor_devolvido"] for t in lista), Decimal("0"))))
        if len(lista) == limite:
            st.caption(f"Exibindo as {limite} solicitações mais recentes do filtro; os totais consideram apenas elas.")

        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Nº": t["id"],
                        "Data": fmt_datahora(t["data"]),
                        "Venda": t["venda_id"],
                        "Tipo": oper.TIPOS[t["tipo"]],
                        "Motivo": oper.MOTIVOS[t["motivo"]],
                        "Cliente": t["cliente"] or "Consumidor final",
                        "Valor devolvido": fmt_brl(t["valor_devolvido"]),
                        "Itens novos": fmt_brl(t["valor_novos"]),
                        "Acerto": acerto_financeiro(
                            t["tipo"], t["valor_devolvido"], t["valor_novos"], t["valor_diferenca"]
                        ),
                        "Responsável": t["usuario"],
                    }
                    for t in lista
                ]
            ),
            hide_index=True,
            width="stretch",
        )

        st.subheader("Detalhe")
        por_id = {t["id"]: t for t in lista}
        if st.session_state.get("oper_detalhe") not in por_id:
            st.session_state.pop("oper_detalhe", None)
        troca_id = st.selectbox(
            "Solicitação",
            list(por_id),
            format_func=lambda i: (
                f"#{i} | {oper.TIPOS[por_id[i]['tipo']]} | venda #{por_id[i]['venda_id']} | "
                f"{fmt_datahora(por_id[i]['data'])} | {fmt_brl(por_id[i]['valor_devolvido'])}"
            ),
            key="oper_detalhe",
        )
        troca = oper.buscar(troca_id)

        perda = sum(
            (d["quantidade"] * d["custo_unitario"] for d in troca["devolvidos"] if not d["retorna_estoque"]),
            Decimal("0"),
        )
        colunas = st.columns(4 if pode_ver_custo else 3)
        colunas[0].metric("Tipo", oper.TIPOS[troca["tipo"]])
        colunas[1].metric("Motivo", oper.MOTIVOS[troca["motivo"]])
        colunas[2].metric(
            "Acerto financeiro",
            escapar_markdown(
                acerto_financeiro(troca["tipo"], troca["valor_devolvido"], troca["valor_novos"], troca["valor_diferenca"])
            ),
        )
        if pode_ver_custo:
            colunas[3].metric("Perda por defeito (custo)", fmt_brl_md(perda))
        st.caption(
            f"Venda #{troca['venda_id']} de {fmt_data(troca['data_venda'])} | "
            f"Cliente: {troca['cliente'] or 'Consumidor final'} | Responsável: {troca['usuario']}"
            + (
                f" | Diferença paga em {vendas_service.FORMAS_PAGAMENTO[troca['forma_pagamento_diferenca']]}"
                if troca["forma_pagamento_diferenca"] else ""
            )
            + (f" | Observação: {troca['observacao']}" if troca["observacao"] else "")
        )

        st.markdown("**Itens devolvidos**")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "SKU": d["sku"],
                        "Produto": d["produto"],
                        "Tamanho": d["tamanho"],
                        "Cor": d["cor"],
                        "Quantidade": d["quantidade"],
                        "Valor unitário": fmt_brl(d["valor_unitario"]),
                        "Subtotal": fmt_brl(d["subtotal"]),
                        "Volta ao estoque": "Sim" if d["retorna_estoque"] else "Não",
                    }
                    for d in troca["devolvidos"]
                ]
            ),
            hide_index=True,
            width="stretch",
        )

        if troca["novos"]:
            st.markdown("**Itens novos**")
            linhas_novos = []
            for n in troca["novos"]:
                linha = {
                    "SKU": n["sku"],
                    "Produto": n["produto"],
                    "Tamanho": n["tamanho"],
                    "Cor": n["cor"],
                    "Quantidade": n["quantidade"],
                    "Preço unitário": fmt_brl(n["preco_unitario"]),
                }
                if pode_ver_custo:
                    linha["Custo unitário"] = fmt_brl_md(n["custo_unitario"])
                linha["Subtotal"] = fmt_brl_md(n["subtotal"])
                linhas_novos.append(linha)
            st.dataframe(pd.DataFrame(linhas_novos), hide_index=True, width="stretch")

        if troca["lancamentos"]:
            st.markdown("**Lançamentos financeiros**")
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Natureza": "A pagar (estorno)" if lc["natureza"] == "PAGAR" else "A receber (diferença)",
                            "Valor": fmt_brl(lc["valor"]),
                            "Vencimento": fmt_data(lc["data_vencimento"]),
                            "Situação": situacao_lancamento(lc),
                            "Baixa em": fmt_datahora(lc["data_baixa"]),
                        }
                        for lc in troca["lancamentos"]
                    ]
                ),
                hide_index=True,
                width="stretch",
            )
