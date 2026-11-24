# GestWear ERP

Sistema de informação para uma loja de roupas, com ERP simplificado (cadastros, compras, estoque, vendas, trocas e devoluções, financeiro) e dashboard de Business Intelligence.

> **Projeto educacional.** Desenvolvido para a disciplina de **Sistemas de Informação e Tecnologias**, do curso de **Bacharelado em Ciência da Computação**. Não se destina ao uso comercial.

## Tecnologias

| Camada | Tecnologia |
|---|---|
| Aplicação e interface | Python 3.12 e Streamlit |
| Banco de dados | PostgreSQL hospedado no Supabase |
| Autenticação | Login com conta Google (OpenID Connect via `st.login`) |
| Publicação | Streamlit Community Cloud |

## Módulos

| Módulo | Situação |
|---|---|
| Autenticação e controle de acesso (perfis Admin, Gerente e Vendedor) | Implementado |
| Cadastros (produtos e variações com SKU, clientes, fornecedores, categorias, tamanhos e cores) | Implementado |
| Compras (pedido, recebimento e contas a pagar) | Implementado |
| Estoque (posição, movimentações, alertas e ajuste de inventário) | Implementado |
| Vendas (venda de balcão, baixa de estoque e contas a receber) | Implementado |
| Operacional (trocas e devoluções, com retorno ao estoque e acerto financeiro) | Implementado |
| Financeiro (contas a pagar e a receber, caixa e bancos, fluxo de caixa e conciliação) | Implementado |
| Business Intelligence (dashboard com indicadores, rankings e análises temporais, comparativas e gerenciais) | Implementado |

## Estrutura do projeto

| Caminho | Papel |
|---|---|
| `app.py` | Ponto de entrada: login, menu por perfil |
| `config.py` | Constantes e parâmetros de negócio |
| `views/` | Interface (uma página por funcionalidade) |
| `services/` | Regras de negócio e integração entre módulos |
| `db/` | Conexão e acesso ao PostgreSQL |
| `utils/` | Funções auxiliares (formatação) |
| `scripts/` | Utilitários de linha de comando (`popular_dados.py`) |
| `database/` | Scripts SQL: `schema.sql`, `seed_inicial.sql`, `reset.sql`, `teste_banco.sql` e `migracoes/` (ajustes para bancos criados em versões anteriores) |
| `.streamlit/` | Configuração do Streamlit e modelo de segredos |

## Requisitos

- Python 3.12 ou superior
- Git
- Conta no [Supabase](https://supabase.com)
- Projeto no [Google Cloud](https://console.cloud.google.com) com cliente OAuth

## Instalação

```bash
git clone https://github.com/SEU_USUARIO/gestwear-erp.git
cd gestwear-erp
python -m venv .venv
```

Ative o ambiente virtual:

| Sistema | Comando |
|---|---|
| Windows (PowerShell) | `.venv\Scripts\Activate.ps1` |
| Windows (CMD) | `.venv\Scripts\activate.bat` |
| Linux e macOS | `source .venv/bin/activate` |

Instale as dependências:

```bash
python -m pip install -r requirements.txt
```

## Configuração

### 1. Banco de dados (Supabase)

1. Crie um projeto no Supabase e guarde a senha do banco.
2. No **SQL Editor**, execute nesta ordem:
   1. `database/schema.sql`
   2. `database/seed_inicial.sql`
3. Cadastre o primeiro administrador, com o e-mail Google que será usado no login:

   ```sql
   INSERT INTO usuarios (email, nome, perfil)
   VALUES ('seu.email@gmail.com', 'Seu Nome', 'ADMIN');
   ```

4. Em **Connect**, copie a URI do **Session pooler** (porta 5432, compatível com IPv4) e substitua `[YOUR-PASSWORD]` pela senha do banco.

Opcional: `database/teste_banco.sql` valida as regras de integridade. Ao terminar, ele exibe um erro intencional com o resultado de cada teste (linhas `OK`) e não grava dados. `database/reset.sql` apaga todas as tabelas para recriar o banco.

### 2. Login Google

1. No Google Cloud, abra **Google Auth Platform** e configure a tela de consentimento (*Branding* e *Audience*). Em modo de teste com público externo, cadastre os e-mails dos usuários em *Test users*.
2. Em **Clients**, crie um cliente do tipo **Web application**.
3. Em **Authorized redirect URIs**, adicione `http://localhost:8501/oauth2callback`.
4. Copie o **Client ID** e o **Client secret**.

### 3. Segredos

Copie `.streamlit/secrets.toml.example` para `.streamlit/secrets.toml` e preencha:

| Chave | Valor |
|---|---|
| `[auth] redirect_uri` | `http://localhost:8501/oauth2callback` |
| `[auth] cookie_secret` | Texto aleatório longo. Para gerar: `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `[auth] client_id` e `client_secret` | Credenciais do cliente OAuth |
| `[auth] server_metadata_url` | Manter o valor do modelo |
| `[database] url` | URI do Session pooler. Caracteres especiais na senha devem ser codificados (`@` vira `%40`) |

O arquivo `secrets.toml` está no `.gitignore` e nunca deve ser versionado.

## Execução local

```bash
streamlit run app.py
```

Acesse http://localhost:8501 e entre com um e-mail cadastrado na tabela `usuarios`. Novos usuários são cadastrados pelo perfil Admin, na página **Usuários**.

## Dados de demonstração

O dashboard de BI lê apenas o que está no banco. Para ter histórico a analisar, o script `scripts/popular_dados.py` gera o histórico do último ano, da data de hoje no ano anterior até hoje (cadastros, compras, vendas, trocas e devoluções, pagamentos, recebimentos e conciliação). Ele usa os próprios serviços do sistema, então todas as regras de negócio, o estoque e o financeiro ficam consistentes.

```bash
python scripts/popular_dados.py
```

| Opção | Descrição |
|---|---|
| `--semente N` | Semente aleatória, para repetir o mesmo histórico. Padrão: 100 |

Observações:

- Execute na raiz do projeto, com o ambiente virtual ativo e o `secrets.toml` configurado.
- O período é sempre o último ano, calculado na hora da execução.
- É preciso ter ao menos um usuário ADMIN cadastrado.
- O script cria usuários de demonstração (e-mails `@gestwear.demo`), que não conseguem entrar no sistema por não terem conta Google, e define o saldo inicial das contas Caixa e Banco.
- O volume é enxuto de propósito (cerca de 60 SKUs, 40 clientes e algumas centenas de vendas): suficiente para demonstrar todas as telas e análises. A duração contra o Supabase depende da latência da conexão.
- O script se recusa a rodar se o banco já tiver vendas ou compras. Para recomeçar, apague os dados antes (veja a seção seguinte).

### Apagar os dados (somente quando necessário)

`scripts/limpar_dados.py` apaga os produtos, clientes, fornecedores, compras, vendas, trocas, estoque e financeiro, e faz os identificadores voltarem a 1. Os usuários (exceto os de demonstração), as tabelas auxiliares e as contas financeiras (com saldo inicial zerado) são mantidos.

```bash
python scripts/limpar_dados.py
```

O script mostra o banco de destino e a quantidade de registros, e só apaga depois que a frase `APAGAR TUDO` for digitada. A operação não pode ser desfeita. Nada no aplicativo chama este script. Para eliminar também a estrutura do banco, use `database/reset.sql`.

## Solução de problemas

| Sintoma | Solução |
|---|---|
| `redirect_uri_mismatch` | A URI do `secrets.toml` deve ser idêntica à cadastrada no cliente OAuth |
| Google bloqueia o acesso | Cadastrar o e-mail em *Test users* (público externo em teste) |
| "Acesso negado... não está cadastrado" | Inserir o e-mail na tabela `usuarios` ou cadastrá-lo na página Usuários |
| Falha de conexão com o banco | Usar a URI do Session pooler e conferir a senha |
| `ModuleNotFoundError` | Ativar o ambiente virtual e executar `python -m pip install -r requirements.txt` |
