# cisco-ccw-mcp

Servidor MCP que expõe consulta de catálogo/preço Cisco e gestão de
Estimates do Cisco Commerce Workspace (CCW) como tools utilizáveis pelo
Claude em linguagem natural.

## ⚠️ Antes de tudo: sobre as credenciais

**Nunca cole Client ID/Secret em uma conversa com o Claude.** Elas vão para
`.env`, um arquivo local que fica só na sua máquina e nunca é lido em voz
alta, logado ou enviado para lugar nenhum além da Cisco.

Se você já colou um Client Secret em algum chat antes de configurar isso,
considere-o comprometido e **regenere-o no Cisco API Console**
(apiconsole.cisco.com → seu app → regenerar secret).

## Arquitetura

```
Claude Chat
   ↓ (MCP, stdio)
cisco-ccw-mcp (este projeto)
   ↓
CiscoAuth (OAuth2, token só em memória)
   ↓
CiscoBaseClient (retry/backoff/401-refresh)
   ↓                              ↓
CiscoCatalogClient (REST/JSON)   CiscoEstimateClient (SOAP/XML)
   ↓                              ↓
Prepare Configuration API        Manage Estimate Web Services
Price List API                   (createEstimate, updateEstimate,
                                   acquireEstimate, listEstimate)
```

Dois pontos que descobrimos durante a validação e que moldam o código:

1. **A Estimate API é SOAP/XML**, não REST/JSON como o resto da Cisco.
   `app/clients/estimates.py` monta e faz parse de XML diretamente.
2. **APIs que aparecem por padrão no API Console** (CX Cloud, PSIRT,
   Corona, Hello/HelloCommerce, etc.) **não são as APIs de Commerce**.
   O que precisamos — Estimate API, Price List API, Prepare Configuration
   API — fica no grupo **Cisco Commerce Xpress Connect**, que você
   confirmou já ter no seu app.

## O que ainda precisa ser confirmado com seus dados reais

Os *paths* exatos de `search`/`item`/`price` em `app/clients/catalog.py` e
os nomes de campo do XML em `app/clients/estimates.py` foram montados a
partir da documentação pública e de exemplos de outros parceiros — a Cisco
não publica um contrato REST único e estável para essas APIs, o path
depende da versão habilitada no SEU app. **Isso precisa ser confirmado no
seu primeiro teste real** (ver "Passo a passo" abaixo). Constantes fáceis
de ajustar:

- `app/clients/catalog.py` → `SEARCH_PATH`, `PRODUCT_PATH`, `PRICE_PATH`
- `app/clients/estimates.py` → `CREATE_PATH`, `UPDATE_PATH`, `ACQUIRE_PATH`, `LIST_PATH`, `DELETE_PATH`, `COPY_PATH`

## Setup

```bash
cd cisco-ccw-mcp
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edite .env com seu editor de texto local (NÃO cole aqui no chat)
```

No `.env`, preencha no mínimo:
```
CISCO_CLIENT_ID=<seu client id>
CISCO_CLIENT_SECRET=<seu client secret regenerado>
CCW_DRY_RUN=true
```

Deixe `CCW_DRY_RUN=true` até você validar tudo (ver passo a passo).

## Rodar os testes (sem tocar em nada real)

```bash
pytest -q
```
17 testes cobrem: autenticação (token, expiração, renovação, erro 401 sem
vazar segredo), retry/backoff (429, 5xx), erros HTTP (401/403/404/500),
SKU válido/inexistente, múltiplos SKUs, criação de Estimate em dry-run e
real, e o guardrail de confirmação nas tools de escrita.

## Passo a passo recomendado (leitura → dry-run → escrita real)

1. **Rodar `pytest -q`** — confirma que a lógica interna está correta
   (sem depender da Cisco).
2. **Testar leitura real**: com `CCW_DRY_RUN=true`, conecte ao Claude
   (próxima seção) e peça `"qual o preço de lista do CW9164I-B?"`. Se der
   404/erro de path, ajuste as constantes de `catalog.py` conforme a doc
   do seu app.
3. **Testar Estimate em dry-run**: peça `"crie um estimate com 2 unidades
   de <SKU válido>"`. Com `CCW_DRY_RUN=true` nada é enviado — você recebe o
   XML que seria enviado, para conferir o formato antes de confiar nele.
4. **Só então**, mude `CCW_DRY_RUN=false` no `.env` e reinicie a conexão
   MCP para permitir escrita real. Mesmo assim, toda tool de escrita (criar,
   alterar, remover, excluir Estimate) exige `confirm=True` — e o próprio
   código bloqueia a chamada se isso não vier explícito, então mesmo que o
   Claude "esqueça" de perguntar, nada é alterado sem essa confirmação.

## Deploy remoto grátis no Render (para usar direto no chat, sem Desktop)

Isso é o que permite usar as tools num chat como este, e não só no Claude
Desktop. Render tem tier gratuito permanente sem cartão de crédito — a
única contrapartida é que o serviço "dorme" após 15 min sem uso e leva
uns 30-50s pra acordar na chamada seguinte.

1. **Suba este projeto para um repositório no GitHub** (privado, de
   preferência — mesmo sem credenciais no código, é boa prática).
   ```bash
   cd cisco-ccw-mcp
   git init && git add . && git commit -m "cisco-ccw-mcp"
   git remote add origin <seu-repo-no-github>
   git push -u origin main
   ```
   O `.gitignore` já impede que `.env` seja commitado.

2. **Gere um token de acesso próprio** para proteger o servidor (sem ele,
   qualquer pessoa que descobrir a URL pública poderia usar as tools em nome
   da sua conta Cisco):
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```
   Guarde esse valor — é o `MCP_ACCESS_TOKEN`.

3. **No Render** (render.com, cadastro grátis): "New" → "Blueprint" →
   aponte para o seu repositório. O `render.yaml` já está configurado —
   ele vai pedir para você preencher no dashboard (não no código):
   - `CISCO_CLIENT_ID`
   - `CISCO_CLIENT_SECRET`
   - `MCP_ACCESS_TOKEN` (o token gerado no passo 2)

   Deixe `CCW_DRY_RUN=true` até validar tudo.

4. **Deploy.** Ao terminar, o Render te dá uma URL tipo
   `https://cisco-ccw-mcp.onrender.com`. O endpoint MCP fica em
   `https://cisco-ccw-mcp.onrender.com/mcp`.

5. **Adicione como Custom Connector no claude.ai**:
   Configurações → Connectors → Add custom connector →
   - URL: `https://cisco-ccw-mcp.onrender.com/mcp`
   - Authentication: Bearer token → cole o `MCP_ACCESS_TOKEN`

6. Abra uma conversa nova aqui no chat e teste:
   > "qual o preço do CW9176?"

   Na primeira chamada depois de um tempo sem uso, espere alguns segundos
   (o Render está "acordando" o serviço) — não é erro.

## Conectar ao Claude Desktop (alternativa local, sem depender de hospedagem)

Edite (ou crie) o arquivo de configuração do Claude Desktop:

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "cisco-ccw": {
      "command": "/caminho/absoluto/para/cisco-ccw-mcp/.venv/bin/python",
      "args": ["-m", "app.main"],
      "cwd": "/caminho/absoluto/para/cisco-ccw-mcp"
    }
  }
}
```

Reinicie o Claude Desktop. Numa conversa nova, digite algo como:

> "Consulte o preço de 50 CW9164I-B."

Se as tools estiverem carregadas, o Claude vai chamar `get_cisco_list_price`
automaticamente — sem você rodar nada manualmente.

## Segurança — o que este projeto garante

- Client Secret, senha CCO e tokens **nunca** aparecem em resposta de tool,
  nem em log (`app/logging_setup.py` faz *scrub* automático de chaves
  sensíveis).
- Token fica só em memória do processo MCP, nunca em disco.
- Retry automático em 401 (token renovado 1x), 429 e 5xx com backoff.
- Toda tool de escrita no CCW exige `confirm=True` — bloqueado por padrão
  tanto na camada de prompt (o Claude deve perguntar) quanto na camada de
  código (a tool recusa sem esse parâmetro).
- `CCW_DRY_RUN=true` impede qualquer escrita real, mesmo com `confirm=True`.

## Estrutura

```
cisco-ccw-mcp/
├── app/
│   ├── main.py            # registra as 12 tools MCP
│   ├── config.py          # Settings via pydantic-settings (.env)
│   ├── auth.py             # CiscoAuth
│   ├── logging_setup.py    # logs estruturados, com scrub de segredos
│   ├── clients/
│   │   ├── commerce.py     # CiscoBaseClient (retry/backoff/401)
│   │   ├── catalog.py      # CiscoCatalogClient (REST/JSON)
│   │   └── estimates.py    # CiscoEstimateClient (SOAP/XML)
│   ├── tools/
│   │   ├── products.py
│   │   ├── pricing.py
│   │   └── estimates.py    # guardrail de confirmação
│   └── models/
│       ├── product.py
│       ├── pricing.py
│       └── estimate.py
├── tests/
├── .env.example
└── requirements.txt
```
