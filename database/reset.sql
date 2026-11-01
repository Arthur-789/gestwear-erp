-- =====================================================================
-- ATENÇÃO: remove todas as tabelas e funções do projeto, com seus dados
-- =====================================================================
BEGIN;

DROP TABLE IF EXISTS
    movimentacoes_financeiras, contas_pagar, contas_receber,
    categorias_financeiras, contas_financeiras,
    movimentacoes_estoque, itens_novos_troca, itens_devolvidos,
    trocas_devolucoes, itens_venda, vendas, itens_compra, compras,
    fornecedores, clientes, produto_variacoes, produtos,
    cores, tamanhos, categorias, usuarios
CASCADE;

DROP FUNCTION IF EXISTS fn_aplicar_movimentacao_estoque() CASCADE;
DROP FUNCTION IF EXISTS fn_proteger_estoque_atual() CASCADE;
DROP FUNCTION IF EXISTS fn_bloquear_alteracao_historico() CASCADE;
DROP FUNCTION IF EXISTS fn_set_atualizado_em() CASCADE;

COMMIT;
