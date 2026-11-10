-- =====================================================================
-- GestWear ERP: dados iniciais (tamanhos, cores, categorias e contas)
-- =====================================================================

INSERT INTO tamanhos (nome, ordem) VALUES
    ('PP', 1), ('P', 2), ('M', 3), ('G', 4), ('GG', 5), ('XG', 6),
    ('36', 10), ('38', 11), ('40', 12), ('42', 13), ('44', 14), ('46', 15),
    ('UN', 99);

INSERT INTO cores (nome, codigo) VALUES
    ('Branco', 'BR'), ('Preto', 'PT'), ('Cinza', 'CZ'), ('Azul', 'AZ'),
    ('Azul Marinho', 'MR'), ('Vermelho', 'VM'), ('Verde', 'VD'), ('Bege', 'BG'),
    ('Rosa', 'RS'), ('Amarelo', 'AM'), ('Marrom', 'MA'), ('Jeans Claro', 'JC'),
    ('Jeans Escuro', 'JE');

INSERT INTO categorias (nome, codigo) VALUES
    ('Camisetas', 'CAM'), ('Camisas', 'CMS'), ('Calças', 'CAL'),
    ('Bermudas e Shorts', 'BER'), ('Vestidos e Saias', 'VES'),
    ('Agasalhos', 'AGA'), ('Íntimas e Meias', 'INT'), ('Acessórios', 'ACE');

INSERT INTO contas_financeiras (nome, tipo, saldo_inicial) VALUES
    ('Caixa da Loja', 'CAIXA', 0),
    ('Conta Bancária', 'BANCO', 0);

INSERT INTO categorias_financeiras (nome, tipo) VALUES
    ('Vendas', 'RECEITA'),
    ('Diferença de Trocas', 'RECEITA'),
    ('Compra de Mercadorias', 'DESPESA'),
    ('Estornos e Devoluções', 'DESPESA'),
    ('Aluguel', 'DESPESA'),
    ('Energia e Água', 'DESPESA'),
    ('Salários e Encargos', 'DESPESA'),
    ('Marketing', 'DESPESA'),
    ('Impostos e Taxas', 'DESPESA'),
    ('Outras Despesas', 'DESPESA');
