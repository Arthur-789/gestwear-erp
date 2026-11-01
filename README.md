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
| Cadastros | Em desenvolvimento |
| Compras | Em desenvolvimento |
| Estoque | Em desenvolvimento |
| Vendas | Em desenvolvimento |
| Operacional (trocas e devoluções) | Em desenvolvimento |
| Financeiro | Em desenvolvimento |
| Business Intelligence (dashboard) | Em desenvolvimento |

## Estrutura do projeto

| Caminho | Papel |
|---|---|
| `app.py` | Ponto de entrada: login, menu por perfil |
| `config.py` | Constantes e parâmetros de negócio |
| `pages/` | Interface (uma página por funcionalidade) |
| `services/` | Regras de negócio e integração entre módulos |
| `db/` | Conexão e acesso ao PostgreSQL |
| `utils/` | Funções auxiliares (formatação) |
| `database/` | Scripts SQL: `schema.sql`, `seed_inicial.sql`, `reset.sql` e `teste_banco.sql` |
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

## Solução de problemas

| Sintoma | Solução |
|---|---|
| `redirect_uri_mismatch` | A URI do `secrets.toml` deve ser idêntica à cadastrada no cliente OAuth |
| Google bloqueia o acesso | Cadastrar o e-mail em *Test users* (público externo em teste) |
| "Acesso negado... não está cadastrado" | Inserir o e-mail na tabela `usuarios` ou cadastrá-lo na página Usuários |
| Falha de conexão com o banco | Usar a URI do Session pooler e conferir a senha |
| `ModuleNotFoundError` | Ativar o ambiente virtual e executar `python -m pip install -r requirements.txt` |
