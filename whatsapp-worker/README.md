# Serviço oficial do WhatsApp

Este diretório contém o webhook em nuvem do Meu Gasto IA. Ele recebe mensagens pela API oficial da Meta, identifica o usuário sem armazenar o telefone completo e grava cada gasto em uma conta privada.

## Comportamento inicial

1. No primeiro contato, o serviço apresenta a regra de privacidade.
2. O usuário responde `ACEITO` para ativar a conta.
3. Depois pode enviar mensagens como `71 gasolina crédito` ou `45 mercado voucher`.
4. `SALDO` mostra os gastos do próprio usuário no mês.
5. `APAGAR HISTÓRICO` e `APAGAR PERFIL` exigem uma segunda confirmação.

O administrador enxerga somente identificador, telefone mascarado, estado e datas operacionais. Não existe endpoint administrativo para consultar gastos ou mensagens.

## Testes locais

```bash
npm install
npm test
```

## Preparação da Cloudflare

1. Crie uma conta na Cloudflare.
2. Instale as dependências e autentique o terminal:

```bash
npm install
npx wrangler login
```

3. Crie o banco D1:

```bash
npx wrangler d1 create meu-gasto-ia
```

4. Copie `wrangler.toml.example` para `wrangler.toml` e substitua `COLOQUE_O_ID_DO_D1_AQUI` pelo identificador retornado.
5. Aplique a migração:

```bash
npx wrangler d1 migrations apply meu-gasto-ia --remote
```

6. Cadastre os segredos, um de cada vez:

```bash
npx wrangler secret put META_VERIFY_TOKEN
npx wrangler secret put META_ACCESS_TOKEN
npx wrangler secret put META_APP_SECRET
npx wrangler secret put META_PHONE_NUMBER_ID
npx wrangler secret put PHONE_HASH_SECRET
npx wrangler secret put ADMIN_API_TOKEN
```

`PHONE_HASH_SECRET` e `ADMIN_API_TOKEN` devem ser valores longos e aleatórios. Nunca coloque os valores no GitHub.

7. Publique:

```bash
npm run deploy
```

## Configuração da Meta

No painel Meta for Developers, configure o webhook do WhatsApp com:

- URL: `https://SEU-WORKER.workers.dev/webhook`
- Token de verificação: o mesmo valor de `META_VERIFY_TOKEN`
- Campo assinado: `messages`

Use um número dedicado ao serviço. O token permanente, o segredo do aplicativo e o ID do número são cadastrados somente como segredos da Cloudflare.

## Administração privada

As rotas abaixo exigem `Authorization: Bearer ADMIN_API_TOKEN`:

- `GET /admin/users`
- `POST /admin/users/{id}/block`
- `POST /admin/users/{id}/unblock`
- `DELETE /admin/users/{id}/history`
- `DELETE /admin/users/{id}`

As duas operações `DELETE` também exigem o cabeçalho `X-Confirm-Delete` com o identificador exato do usuário. A auditoria guarda apenas ação, ID interno e data.

Depois da publicação, abra `https://SEU-WORKER.workers.dev/admin` para usar a tela administrativa. Ela mostra somente telefone mascarado, estado e datas da conta.

O serviço ainda não deve ser divulgado antes da configuração do número oficial, dos segredos e de um teste completo com o número de teste da Meta.
