-- =====================================================================
-- GestWear ERP: dados iniciais (tamanhos, cores, categorias e contas)
-- =====================================================================

INSERT INTO tamanhos (nome, ordem) VALUES
    ('PP', 1), ('P', 2), ('M', 3), ('G', 4), ('GG', 5), ('XG', 6),
    ('36', 10), ('38', 11), ('40', 12), ('42', 13), ('44', 14), ('46', 15),
    ('UN', 99);

INSERT INTO cores (nome) VALUES
    ('Branco'), ('Preto'), ('Cinza'), ('Azul'), ('Azul Marinho'), ('Vermelho'),
    ('Verde'), ('Bege'), ('Rosa'), ('Amarelo'), ('Marrom'), ('Jeans Claro'), ('Jeans Escuro');

INSERT INTO categorias (nome) VALUES
    ('Camisetas'), ('Camisas'), ('Calças'), ('Bermudas e Shorts'),
    ('Vestidos e Saias'), ('Agasalhos'), ('Íntimas e Meias'), ('Acessórios');

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
