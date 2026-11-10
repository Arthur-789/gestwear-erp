-- =====================================================================
-- GestWear ERP: teste das regras de integridade do banco
-- Executa cenários dentro de um bloco e termina com um erro intencional
-- que desfaz tudo (nenhum dado é gravado). Cada linha "OK" é uma regra
-- validada; "FALHOU" indica regra não aplicada.
-- =====================================================================
DO $$
DECLARE
    v_user   BIGINT := (SELECT id FROM usuarios ORDER BY id LIMIT 1);
    v_forn   BIGINT;
    v_prod   BIGINT;
    v_var    BIGINT;
    v_compra BIGINT;
    v_venda  BIGINT;
    v_item   BIGINT;
    v_saldo  INTEGER;
    v_log    TEXT := '';
BEGIN
    INSERT INTO fornecedores (razao_social, cnpj) VALUES ('Fornecedor Teste', '99999999000199') RETURNING id INTO v_forn;
    INSERT INTO produtos (nome, categoria_id) VALUES ('Produto Teste', (SELECT id FROM categorias ORDER BY id LIMIT 1)) RETURNING id INTO v_prod;
    INSERT INTO produto_variacoes (produto_id, tamanho_id, cor_id, sku, preco_venda, custo_medio)
    VALUES (v_prod, (SELECT id FROM tamanhos WHERE nome = 'M'), (SELECT id FROM cores WHERE nome = 'Branco'), 'TESTE-SKU', 50, 20)
    RETURNING id INTO v_var;

    INSERT INTO compras (fornecedor_id, usuario_id, status, data_recebimento, valor_total, primeiro_vencimento)
    VALUES (v_forn, v_user, 'RECEBIDA', now(), 200, current_date + 30) RETURNING id INTO v_compra;
    INSERT INTO itens_compra (compra_id, variacao_id, quantidade, custo_unitario) VALUES (v_compra, v_var, 10, 20);
    INSERT INTO movimentacoes_estoque (variacao_id, tipo, quantidade, compra_id, usuario_id)
    VALUES (v_var, 'ENTRADA_COMPRA', 10, v_compra, v_user);
    SELECT estoque_atual INTO v_saldo FROM produto_variacoes WHERE id = v_var;
    v_log := v_log || E'\n' || CASE WHEN v_saldo = 10 THEN 'OK    ' ELSE 'FALHOU' END || ' 1. Entrada de compra atualiza saldo (esperado 10, obtido ' || v_saldo || ')';

    INSERT INTO vendas (usuario_id, subtotal, desconto, valor_total, forma_pagamento)
    VALUES (v_user, 100, 0, 100, 'PIX') RETURNING id INTO v_venda;
    INSERT INTO itens_venda (venda_id, variacao_id, quantidade, preco_unitario, custo_unitario)
    VALUES (v_venda, v_var, 2, 50, 20) RETURNING id INTO v_item;
    INSERT INTO movimentacoes_estoque (variacao_id, tipo, quantidade, venda_id, usuario_id)
    VALUES (v_var, 'SAIDA_VENDA', -2, v_venda, v_user);
    SELECT estoque_atual INTO v_saldo FROM produto_variacoes WHERE id = v_var;
    v_log := v_log || E'\n' || CASE WHEN v_saldo = 8 THEN 'OK    ' ELSE 'FALHOU' END || ' 2. Saida de venda baixa o saldo (esperado 8, obtido ' || v_saldo || ')';

    BEGIN
        INSERT INTO movimentacoes_estoque (variacao_id, tipo, quantidade, venda_id, usuario_id)
        VALUES (v_var, 'SAIDA_VENDA', -99, v_venda, v_user);
        v_log := v_log || E'\nFALHOU 3. Permitiu saldo negativo';
    EXCEPTION WHEN OTHERS THEN v_log := v_log || E'\nOK     3. Saldo negativo bloqueado';
    END;

    BEGIN
        UPDATE produto_variacoes SET estoque_atual = 500 WHERE id = v_var;
        v_log := v_log || E'\nFALHOU 4. Permitiu alterar o saldo diretamente';
    EXCEPTION WHEN OTHERS THEN v_log := v_log || E'\nOK     4. Alteracao direta do saldo bloqueada';
    END;

    BEGIN
        DELETE FROM movimentacoes_estoque WHERE variacao_id = v_var;
        v_log := v_log || E'\nFALHOU 5. Permitiu apagar historico de estoque';
    EXCEPTION WHEN OTHERS THEN v_log := v_log || E'\nOK     5. Historico de estoque imutavel';
    END;

    BEGIN
        INSERT INTO vendas (usuario_id, subtotal, valor_total, forma_pagamento, num_parcelas)
        VALUES (v_user, 100, 100, 'CREDITO', 3);
        v_log := v_log || E'\nFALHOU 6. Permitiu parcelado sem cliente';
    EXCEPTION WHEN OTHERS THEN v_log := v_log || E'\nOK     6. Parcelado sem cliente bloqueado';
    END;

    BEGIN
        INSERT INTO vendas (usuario_id, subtotal, desconto, valor_total, forma_pagamento)
        VALUES (v_user, 100, 150, -50, 'PIX');
        v_log := v_log || E'\nFALHOU 7. Permitiu desconto maior que o subtotal';
    EXCEPTION WHEN OTHERS THEN v_log := v_log || E'\nOK     7. Desconto maior que o subtotal bloqueado';
    END;

    BEGIN
        UPDATE itens_venda SET quantidade_devolvida = 5 WHERE id = v_item;
        v_log := v_log || E'\nFALHOU 8. Permitiu devolver mais que o vendido';
    EXCEPTION WHEN OTHERS THEN v_log := v_log || E'\nOK     8. Devolucao maior que o vendido bloqueada';
    END;

    BEGIN
        INSERT INTO clientes (nome, cpf) VALUES ('Cliente Teste', '123');
        v_log := v_log || E'\nFALHOU 9. Permitiu CPF invalido';
    EXCEPTION WHEN OTHERS THEN v_log := v_log || E'\nOK     9. CPF invalido bloqueado';
    END;

    BEGIN
        INSERT INTO usuarios (email, nome, perfil)
        SELECT upper(email), 'Duplicado', 'VENDEDOR' FROM usuarios WHERE id = v_user;
        v_log := v_log || E'\nFALHOU 10. Permitiu e-mail duplicado (maiuscula/minuscula)';
    EXCEPTION WHEN OTHERS THEN v_log := v_log || E'\nOK     10. E-mail duplicado bloqueado';
    END;

    BEGIN
        INSERT INTO cores (nome, codigo) VALUES ('Cor Teste', 'a-b');
        v_log := v_log || E'\nFALHOU 11. Permitiu código de cor inválido';
    EXCEPTION WHEN OTHERS THEN v_log := v_log || E'\nOK     11. Código de cor inválido bloqueado';
    END;

    BEGIN
        INSERT INTO categorias (nome, codigo) VALUES ('Outra Camiseta', 'CAM');
        v_log := v_log || E'\nFALHOU 12. Permitiu código de categoria duplicado';
    EXCEPTION WHEN OTHERS THEN v_log := v_log || E'\nOK     12. Código de categoria duplicado bloqueado';
    END;

    RAISE EXCEPTION E'RESULTADO DOS TESTES (erro intencional: nada foi gravado):%', v_log;
END;
$$;
