-- =====================================================================
-- GestWear ERP: esquema do banco de dados (PostgreSQL)
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- FUNÇÕES AUXILIARES
-- ---------------------------------------------------------------------
CREATE FUNCTION fn_set_atualizado_em() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.atualizado_em := now();
    RETURN NEW;
END;
$$;

-- ---------------------------------------------------------------------
-- AUTENTICAÇÃO E CONTROLE DE ACESSO
-- ---------------------------------------------------------------------
CREATE TABLE usuarios (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email            VARCHAR(255) NOT NULL,
    nome             VARCHAR(150) NOT NULL,
    perfil           VARCHAR(20)  NOT NULL
                     CHECK (perfil IN ('ADMIN', 'GERENTE', 'VENDEDOR')),
    ativo            BOOLEAN      NOT NULL DEFAULT TRUE,
    criado_em        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    ultimo_login_em  TIMESTAMPTZ
);
CREATE UNIQUE INDEX ux_usuarios_email ON usuarios (lower(email));

-- ---------------------------------------------------------------------
-- CADASTROS
-- ---------------------------------------------------------------------
CREATE TABLE categorias (
    id     BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nome   VARCHAR(80) NOT NULL UNIQUE,
    ativo  BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE tamanhos (
    id     BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nome   VARCHAR(10) NOT NULL UNIQUE,
    ordem  SMALLINT    NOT NULL DEFAULT 0
);

CREATE TABLE cores (
    id    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nome  VARCHAR(40) NOT NULL UNIQUE
);

CREATE TABLE produtos (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nome           VARCHAR(150) NOT NULL,
    descricao      TEXT,
    categoria_id   BIGINT NOT NULL REFERENCES categorias (id),
    ativo          BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em      TIMESTAMPTZ NOT NULL DEFAULT now(),
    atualizado_em  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX ux_produtos_nome ON produtos (lower(nome));
CREATE INDEX ix_produtos_categoria ON produtos (categoria_id);

CREATE TABLE produto_variacoes (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    produto_id      BIGINT NOT NULL REFERENCES produtos (id),
    tamanho_id      BIGINT NOT NULL REFERENCES tamanhos (id),
    cor_id          BIGINT NOT NULL REFERENCES cores (id),
    sku             VARCHAR(40) NOT NULL UNIQUE,
    preco_venda     NUMERIC(12,2) NOT NULL CHECK (preco_venda > 0),
    custo_medio     NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (custo_medio >= 0),
    estoque_atual   INTEGER NOT NULL DEFAULT 0 CHECK (estoque_atual >= 0),
    estoque_minimo  INTEGER NOT NULL DEFAULT 0 CHECK (estoque_minimo >= 0),
    ativo           BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT now(),
    atualizado_em   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (produto_id, tamanho_id, cor_id)
);
CREATE INDEX ix_variacoes_produto ON produto_variacoes (produto_id);

CREATE TABLE clientes (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nome           VARCHAR(150) NOT NULL,
    cpf            VARCHAR(11) UNIQUE CHECK (cpf ~ '^[0-9]{11}$'),
    telefone       VARCHAR(20),
    email          VARCHAR(255),
    cidade         VARCHAR(80),
    uf             CHAR(2),
    ativo          BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em      TIMESTAMPTZ NOT NULL DEFAULT now(),
    atualizado_em  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE fornecedores (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    razao_social   VARCHAR(150) NOT NULL,
    cnpj           VARCHAR(14) NOT NULL UNIQUE CHECK (cnpj ~ '^[0-9]{14}$'),
    contato        VARCHAR(100),
    telefone       VARCHAR(20),
    email          VARCHAR(255),
    cidade         VARCHAR(80),
    uf             CHAR(2),
    ativo          BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em      TIMESTAMPTZ NOT NULL DEFAULT now(),
    atualizado_em  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TRIGGER tg_produtos_atualizado BEFORE UPDATE ON produtos
    FOR EACH ROW EXECUTE FUNCTION fn_set_atualizado_em();
CREATE TRIGGER tg_variacoes_atualizado BEFORE UPDATE ON produto_variacoes
    FOR EACH ROW EXECUTE FUNCTION fn_set_atualizado_em();
CREATE TRIGGER tg_clientes_atualizado BEFORE UPDATE ON clientes
    FOR EACH ROW EXECUTE FUNCTION fn_set_atualizado_em();
CREATE TRIGGER tg_fornecedores_atualizado BEFORE UPDATE ON fornecedores
    FOR EACH ROW EXECUTE FUNCTION fn_set_atualizado_em();

-- ---------------------------------------------------------------------
-- COMPRAS
-- ---------------------------------------------------------------------
CREATE TABLE compras (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    fornecedor_id       BIGINT NOT NULL REFERENCES fornecedores (id),
    usuario_id          BIGINT NOT NULL REFERENCES usuarios (id),
    data_pedido         TIMESTAMPTZ NOT NULL DEFAULT now(),
    data_recebimento    TIMESTAMPTZ,
    status              VARCHAR(12) NOT NULL DEFAULT 'PEDIDO'
                        CHECK (status IN ('PEDIDO', 'RECEBIDA', 'CANCELADA')),
    valor_total         NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (valor_total >= 0),
    num_parcelas        SMALLINT NOT NULL DEFAULT 1 CHECK (num_parcelas BETWEEN 1 AND 12),
    primeiro_vencimento DATE NOT NULL,
    observacao          TEXT,
    CHECK (status <> 'RECEBIDA' OR data_recebimento IS NOT NULL)
);
CREATE INDEX ix_compras_fornecedor ON compras (fornecedor_id);
CREATE INDEX ix_compras_data ON compras (data_pedido);

CREATE TABLE itens_compra (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    compra_id       BIGINT NOT NULL REFERENCES compras (id) ON DELETE CASCADE,
    variacao_id     BIGINT NOT NULL REFERENCES produto_variacoes (id),
    quantidade      INTEGER NOT NULL CHECK (quantidade > 0),
    custo_unitario  NUMERIC(12,2) NOT NULL CHECK (custo_unitario >= 0),
    subtotal        NUMERIC(12,2) GENERATED ALWAYS AS (quantidade * custo_unitario) STORED,
    UNIQUE (compra_id, variacao_id)
);
CREATE INDEX ix_itens_compra_variacao ON itens_compra (variacao_id);

-- ---------------------------------------------------------------------
-- VENDAS
-- ---------------------------------------------------------------------
CREATE TABLE vendas (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cliente_id       BIGINT REFERENCES clientes (id),
    usuario_id       BIGINT NOT NULL REFERENCES usuarios (id),
    data_venda       TIMESTAMPTZ NOT NULL DEFAULT now(),
    subtotal         NUMERIC(12,2) NOT NULL CHECK (subtotal > 0),
    desconto         NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (desconto >= 0),
    valor_total      NUMERIC(12,2) NOT NULL,
    forma_pagamento  VARCHAR(10) NOT NULL
                     CHECK (forma_pagamento IN ('DINHEIRO', 'PIX', 'DEBITO', 'CREDITO')),
    num_parcelas     SMALLINT NOT NULL DEFAULT 1 CHECK (num_parcelas BETWEEN 1 AND 12),
    observacao       TEXT,
    CHECK (desconto <= subtotal),
    CHECK (valor_total = subtotal - desconto),
    CHECK (forma_pagamento = 'CREDITO' OR num_parcelas = 1),
    CHECK (num_parcelas = 1 OR cliente_id IS NOT NULL)
);
CREATE INDEX ix_vendas_data ON vendas (data_venda);
CREATE INDEX ix_vendas_cliente ON vendas (cliente_id);
CREATE INDEX ix_vendas_usuario ON vendas (usuario_id);

CREATE TABLE itens_venda (
    id                    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    venda_id              BIGINT NOT NULL REFERENCES vendas (id) ON DELETE CASCADE,
    variacao_id           BIGINT NOT NULL REFERENCES produto_variacoes (id),
    quantidade            INTEGER NOT NULL CHECK (quantidade > 0),
    preco_unitario        NUMERIC(12,2) NOT NULL CHECK (preco_unitario > 0),
    custo_unitario        NUMERIC(12,2) NOT NULL CHECK (custo_unitario >= 0),
    subtotal              NUMERIC(12,2) GENERATED ALWAYS AS (quantidade * preco_unitario) STORED,
    quantidade_devolvida  INTEGER NOT NULL DEFAULT 0,
    UNIQUE (venda_id, variacao_id),
    CHECK (quantidade_devolvida BETWEEN 0 AND quantidade)
);
CREATE INDEX ix_itens_venda_variacao ON itens_venda (variacao_id);

-- ---------------------------------------------------------------------
-- OPERACIONAL: TROCAS E DEVOLUÇÕES
-- ---------------------------------------------------------------------
CREATE TABLE trocas_devolucoes (
    id                          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    venda_id                    BIGINT NOT NULL REFERENCES vendas (id),
    usuario_id                  BIGINT NOT NULL REFERENCES usuarios (id),
    tipo                        VARCHAR(10) NOT NULL CHECK (tipo IN ('DEVOLUCAO', 'TROCA')),
    motivo                      VARCHAR(25) NOT NULL
                                CHECK (motivo IN ('DEFEITO', 'TAMANHO_INADEQUADO',
                                                  'ARREPENDIMENTO', 'OUTRO')),
    data                        TIMESTAMPTZ NOT NULL DEFAULT now(),
    valor_devolvido             NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (valor_devolvido >= 0),
    valor_novos                 NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (valor_novos >= 0),
    valor_diferenca             NUMERIC(12,2) GENERATED ALWAYS AS (valor_novos - valor_devolvido) STORED,
    forma_pagamento_diferenca   VARCHAR(10)
                                CHECK (forma_pagamento_diferenca IN ('DINHEIRO', 'PIX', 'DEBITO')),
    observacao                  TEXT,
    CHECK (tipo = 'TROCA' OR valor_novos = 0),
    CHECK (valor_novos - valor_devolvido <= 0 OR forma_pagamento_diferenca IS NOT NULL)
);
CREATE INDEX ix_trocas_venda ON trocas_devolucoes (venda_id);
CREATE INDEX ix_trocas_data ON trocas_devolucoes (data);

CREATE TABLE itens_devolvidos (
    id                    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    troca_devolucao_id    BIGINT NOT NULL REFERENCES trocas_devolucoes (id) ON DELETE CASCADE,
    item_venda_id         BIGINT NOT NULL REFERENCES itens_venda (id),
    quantidade            INTEGER NOT NULL CHECK (quantidade > 0),
    valor_unitario        NUMERIC(12,2) NOT NULL CHECK (valor_unitario >= 0),
    subtotal              NUMERIC(12,2) GENERATED ALWAYS AS (quantidade * valor_unitario) STORED,
    retorna_estoque       BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE INDEX ix_itens_devolvidos_troca ON itens_devolvidos (troca_devolucao_id);
CREATE INDEX ix_itens_devolvidos_item ON itens_devolvidos (item_venda_id);

CREATE TABLE itens_novos_troca (
    id                    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    troca_devolucao_id    BIGINT NOT NULL REFERENCES trocas_devolucoes (id) ON DELETE CASCADE,
    variacao_id           BIGINT NOT NULL REFERENCES produto_variacoes (id),
    quantidade            INTEGER NOT NULL CHECK (quantidade > 0),
    preco_unitario        NUMERIC(12,2) NOT NULL CHECK (preco_unitario > 0),
    custo_unitario        NUMERIC(12,2) NOT NULL CHECK (custo_unitario >= 0),
    subtotal              NUMERIC(12,2) GENERATED ALWAYS AS (quantidade * preco_unitario) STORED
);
CREATE INDEX ix_itens_novos_troca ON itens_novos_troca (troca_devolucao_id);

-- ---------------------------------------------------------------------
-- ESTOQUE: MOVIMENTAÇÕES (histórico imutável)
-- ---------------------------------------------------------------------
CREATE TABLE movimentacoes_estoque (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    variacao_id         BIGINT NOT NULL REFERENCES produto_variacoes (id),
    tipo                VARCHAR(20) NOT NULL
                        CHECK (tipo IN ('ENTRADA_COMPRA', 'SAIDA_VENDA', 'ENTRADA_DEVOLUCAO',
                                        'SAIDA_TROCA', 'AJUSTE')),
    quantidade          INTEGER NOT NULL CHECK (quantidade <> 0),
    saldo_anterior      INTEGER NOT NULL DEFAULT 0,
    saldo_posterior     INTEGER NOT NULL DEFAULT 0,
    compra_id           BIGINT REFERENCES compras (id),
    venda_id            BIGINT REFERENCES vendas (id),
    troca_devolucao_id  BIGINT REFERENCES trocas_devolucoes (id),
    usuario_id          BIGINT NOT NULL REFERENCES usuarios (id),
    motivo              TEXT,
    criado_em           TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (
        (tipo IN ('ENTRADA_COMPRA', 'ENTRADA_DEVOLUCAO') AND quantidade > 0) OR
        (tipo IN ('SAIDA_VENDA', 'SAIDA_TROCA') AND quantidade < 0) OR
        (tipo = 'AJUSTE')
    ),
    CHECK (num_nonnulls(compra_id, venda_id, troca_devolucao_id) <= 1),
    CHECK (tipo <> 'ENTRADA_COMPRA'    OR compra_id IS NOT NULL),
    CHECK (tipo <> 'SAIDA_VENDA'       OR venda_id IS NOT NULL),
    CHECK (tipo NOT IN ('ENTRADA_DEVOLUCAO', 'SAIDA_TROCA') OR troca_devolucao_id IS NOT NULL),
    CHECK (tipo <> 'AJUSTE' OR (motivo IS NOT NULL AND length(trim(motivo)) > 0))
);
CREATE INDEX ix_mov_estoque_variacao ON movimentacoes_estoque (variacao_id, criado_em);
CREATE INDEX ix_mov_estoque_data ON movimentacoes_estoque (criado_em);

-- Aplica a movimentação no saldo da variação e impede saldo negativo
CREATE FUNCTION fn_aplicar_movimentacao_estoque() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_saldo INTEGER;
BEGIN
    SELECT estoque_atual INTO v_saldo
      FROM produto_variacoes
     WHERE id = NEW.variacao_id
       FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Variacao % nao encontrada', NEW.variacao_id;
    END IF;

    NEW.saldo_anterior  := v_saldo;
    NEW.saldo_posterior := v_saldo + NEW.quantidade;

    IF NEW.saldo_posterior < 0 THEN
        RAISE EXCEPTION 'Estoque insuficiente para a variacao % (saldo %, movimento %)',
            NEW.variacao_id, v_saldo, NEW.quantidade
            USING ERRCODE = 'check_violation';
    END IF;

    PERFORM set_config('app.movimentando_estoque', '1', true);
    UPDATE produto_variacoes
       SET estoque_atual = NEW.saldo_posterior
     WHERE id = NEW.variacao_id;
    PERFORM set_config('app.movimentando_estoque', '0', true);

    RETURN NEW;
END;
$$;

CREATE TRIGGER tg_mov_estoque_aplicar BEFORE INSERT ON movimentacoes_estoque
    FOR EACH ROW EXECUTE FUNCTION fn_aplicar_movimentacao_estoque();

-- Impede a alteração direta do saldo (somente via movimentação)
CREATE FUNCTION fn_proteger_estoque_atual() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.estoque_atual IS DISTINCT FROM OLD.estoque_atual
       AND coalesce(current_setting('app.movimentando_estoque', true), '') <> '1' THEN
        RAISE EXCEPTION 'estoque_atual so pode ser alterado por movimentacoes_estoque';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER tg_variacoes_proteger_estoque BEFORE UPDATE ON produto_variacoes
    FOR EACH ROW EXECUTE FUNCTION fn_proteger_estoque_atual();

-- Movimentações são histórico: não podem ser alteradas nem removidas
CREATE FUNCTION fn_bloquear_alteracao_historico() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Registros de % sao imutaveis', TG_TABLE_NAME;
END;
$$;

CREATE TRIGGER tg_mov_estoque_imutavel BEFORE UPDATE OR DELETE ON movimentacoes_estoque
    FOR EACH ROW EXECUTE FUNCTION fn_bloquear_alteracao_historico();

-- ---------------------------------------------------------------------
-- FINANCEIRO
-- ---------------------------------------------------------------------
CREATE TABLE contas_financeiras (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nome           VARCHAR(80) NOT NULL UNIQUE,
    tipo           VARCHAR(10) NOT NULL CHECK (tipo IN ('CAIXA', 'BANCO')),
    saldo_inicial  NUMERIC(12,2) NOT NULL DEFAULT 0,
    ativa          BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE categorias_financeiras (
    id     BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nome   VARCHAR(80) NOT NULL UNIQUE,
    tipo   VARCHAR(10) NOT NULL CHECK (tipo IN ('RECEITA', 'DESPESA')),
    ativa  BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE contas_receber (
    id                   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    venda_id             BIGINT REFERENCES vendas (id),
    troca_devolucao_id   BIGINT REFERENCES trocas_devolucoes (id),
    cliente_id           BIGINT REFERENCES clientes (id),
    categoria_id         BIGINT NOT NULL REFERENCES categorias_financeiras (id),
    num_parcela          SMALLINT NOT NULL DEFAULT 1,
    total_parcelas       SMALLINT NOT NULL DEFAULT 1,
    valor                NUMERIC(12,2) NOT NULL CHECK (valor > 0),
    data_vencimento      DATE NOT NULL,
    data_recebimento     TIMESTAMPTZ,
    conta_financeira_id  BIGINT REFERENCES contas_financeiras (id),
    status               VARCHAR(10) NOT NULL DEFAULT 'ABERTA'
                         CHECK (status IN ('ABERTA', 'RECEBIDA', 'CANCELADA')),
    criado_em            TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (num_nonnulls(venda_id, troca_devolucao_id) = 1),
    CHECK (num_parcela BETWEEN 1 AND total_parcelas),
    CHECK (status <> 'RECEBIDA' OR (data_recebimento IS NOT NULL AND conta_financeira_id IS NOT NULL))
);
CREATE UNIQUE INDEX ux_receber_venda_parcela ON contas_receber (venda_id, num_parcela)
    WHERE venda_id IS NOT NULL;
CREATE INDEX ix_receber_venc ON contas_receber (status, data_vencimento);
CREATE INDEX ix_receber_cliente ON contas_receber (cliente_id);

CREATE TABLE contas_pagar (
    id                   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    compra_id            BIGINT REFERENCES compras (id),
    troca_devolucao_id   BIGINT REFERENCES trocas_devolucoes (id),
    fornecedor_id        BIGINT REFERENCES fornecedores (id),
    cliente_id           BIGINT REFERENCES clientes (id),
    categoria_id         BIGINT NOT NULL REFERENCES categorias_financeiras (id),
    descricao            VARCHAR(200) NOT NULL,
    num_parcela          SMALLINT NOT NULL DEFAULT 1,
    total_parcelas       SMALLINT NOT NULL DEFAULT 1,
    valor                NUMERIC(12,2) NOT NULL CHECK (valor > 0),
    data_vencimento      DATE NOT NULL,
    data_pagamento       TIMESTAMPTZ,
    conta_financeira_id  BIGINT REFERENCES contas_financeiras (id),
    status               VARCHAR(10) NOT NULL DEFAULT 'ABERTA'
                         CHECK (status IN ('ABERTA', 'PAGA', 'CANCELADA')),
    criado_em            TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (num_nonnulls(compra_id, troca_devolucao_id) <= 1),
    CHECK (num_nonnulls(fornecedor_id, cliente_id) <= 1),
    CHECK (num_parcela BETWEEN 1 AND total_parcelas),
    CHECK (status <> 'PAGA' OR (data_pagamento IS NOT NULL AND conta_financeira_id IS NOT NULL))
);
CREATE UNIQUE INDEX ux_pagar_compra_parcela ON contas_pagar (compra_id, num_parcela)
    WHERE compra_id IS NOT NULL;
CREATE INDEX ix_pagar_venc ON contas_pagar (status, data_vencimento);
CREATE INDEX ix_pagar_fornecedor ON contas_pagar (fornecedor_id);

CREATE TABLE movimentacoes_financeiras (
    id                   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    conta_financeira_id  BIGINT NOT NULL REFERENCES contas_financeiras (id),
    tipo                 VARCHAR(7) NOT NULL CHECK (tipo IN ('ENTRADA', 'SAIDA')),
    valor                NUMERIC(12,2) NOT NULL CHECK (valor > 0),
    data_movimento       TIMESTAMPTZ NOT NULL DEFAULT now(),
    conta_receber_id     BIGINT UNIQUE REFERENCES contas_receber (id),
    conta_pagar_id       BIGINT UNIQUE REFERENCES contas_pagar (id),
    descricao            VARCHAR(200),
    usuario_id           BIGINT NOT NULL REFERENCES usuarios (id),
    conciliado           BOOLEAN NOT NULL DEFAULT FALSE,
    conciliado_em        TIMESTAMPTZ,
    CHECK (
        (tipo = 'ENTRADA' AND conta_receber_id IS NOT NULL AND conta_pagar_id IS NULL) OR
        (tipo = 'SAIDA'   AND conta_pagar_id   IS NOT NULL AND conta_receber_id IS NULL)
    ),
    CHECK (NOT conciliado OR conciliado_em IS NOT NULL)
);
CREATE INDEX ix_mov_fin_conta ON movimentacoes_financeiras (conta_financeira_id, data_movimento);
CREATE INDEX ix_mov_fin_data ON movimentacoes_financeiras (data_movimento);

-- ---------------------------------------------------------------------
-- SEGURANÇA (Supabase): habilita RLS para bloquear o acesso pela API REST
-- pública (anon key). A aplicação usa conexão direta ao banco (role
-- postgres), que não é afetada pelo RLS.
-- ---------------------------------------------------------------------
DO $$
DECLARE
    t RECORD;
BEGIN
    FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t.tablename);
    END LOOP;
END;
$$;

COMMIT;
