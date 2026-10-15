# cisco-ccw-mcp

Servidor MCP que expõe a **API GraphQL do Cisco Commerce (CCW Estimate)** ao Claude:
preço de lista e gestão de estimates/BoMs em linguagem natural.

## Tools

Somente leitura:
- `get_cisco_list_price(sku, quantity, price_list)` e `get_cisco_prices(items, price_list)` — preço de lista (GPL)
  via `validateConfig` (sandbox: **não cria estimate**). Lote em uma chamada.
- `search_ccw_estimates(name)`, `get_ccw_estimate(estimate_id)`, `validate_ccw_estimate(estimate_id)`

Escrita (exigem `confirm=True`; com `CCW_DRY_RUN=true` só mostram o payload):
- `create_ccw_estimate`, `add_item_to_ccw_estimate`, `update_ccw_estimate_item`,
  `remove_ccw_estimate_item`, `share_ccw_estimate`

Não existem porque a API do client não libera: busca de catálogo (`getItems`), excluir e copiar estimate.
Exclusão é pelo CCW.

## Pontos de atenção da API

- Estimate só é legível se **compartilhado com o usuário da API** (`ciscoapi@`).
- Estimates criados pela API só aparecem no seu CCW se compartilhados com você: configure `CCW_SHARE_EMAILS`.
- Price list é fixada na criação: `GLBRL` (BRL), `GLICON` (LATAM/Meraki, USD), `GLUS` (USD).
- `updateEstimate` substitui todas as linhas e **não reprecifica** (fica UNVERIFIED, serviços a 0).
  Se o preço importa, crie de novo.
- Serviço/subscrição exige `duration_months`; o create grava subscrições em 36 meses.
- Componentes configurados sem `path` podem gerar estimate INVALID/UNVERIFIED (PN, qtd e lista corretos).

## Autenticação

OAuth2 `client_credentials` em `https://id.cisco.com/oauth2/default/v1/token`, credenciais em header Basic.
Token só em memória; nada de segredo em log ou resposta de tool.

## Variáveis de ambiente

Ver `.env.example`. No Render: `CISCO_CLIENT_ID`, `CISCO_CLIENT_SECRET`, `MCP_ACCESS_TOKEN`, `MCP_TRANSPORT=streamable-http`.

## Conector no claude.ai

URL `https://<seu-servico>.onrender.com/mcp`, autenticação "Nenhum" e cabeçalho
`Authorization: Bearer <MCP_ACCESS_TOKEN>`.

## Testes

```bash
pip install -r requirements.txt
pytest -q
```
