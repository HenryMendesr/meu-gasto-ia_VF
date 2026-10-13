# Preparação para WhatsApp e IA

O painel e uma futura integração usam a mesma API local. Isso evita criar duas regras diferentes para gravar no Excel.

## Estado atual

- O Excel é a fonte oficial dos gastos, renda em dinheiro e crédito do voucher.
- Cada alteração cria uma cópia em `backups/` antes de substituir a planilha.
- Os 20 backups mais recentes são mantidos.
- Gravações simultâneas são processadas uma por vez.
- Um lançamento idêntico retorna conflito e exige confirmação explícita.
- A planilha e o dashboard são validados e atualizados depois da gravação.

## Endpoints locais

Com `python3 src/dashboard_server.py` em execução:

- `GET /api/health`: integridade básica e quantidade de gastos.
- `GET /api/expenses`: lista de lançamentos para leitura.
- `POST /api/expenses`: grava um gasto.
- `GET /api/incomes`: consulta renda e voucher por mês.
- `POST /api/incomes`: atualiza renda e voucher do mês.
- `GET /api/budgets`: consulta limites mensais por categoria.
- `POST /api/budgets`: atualiza o limite de uma categoria no mês.

Exemplo de lançamento:

```json
{
  "date": "2026-10-13",
  "amount": 71.0,
  "where": "Posto",
  "category": "Transporte",
  "payment": "Crédito",
  "description": "Gasolina"
}
```

Uma futura IA deve transformar a mensagem do WhatsApp nesse formato e chamar `POST /api/expenses`. Se a API responder `409` com `code: duplicate`, o bot deve pedir confirmação antes de reenviar com `allow_duplicate: true`.

## Antes de expor na internet

O servidor atual escuta apenas o computador local e não possui autenticação externa. A etapa do WhatsApp deverá adicionar autenticação, HTTPS, validação da assinatura do webhook, controle de usuário e armazenamento seguro das credenciais. Esses itens pertencem à próxima fase e não devem ser contornados expondo a porta local diretamente.
