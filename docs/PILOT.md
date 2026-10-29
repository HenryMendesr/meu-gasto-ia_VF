# Piloto e operação do produto

## O que o código entrega

O foco é finanças pessoais: entender o mês, organizar dívidas e acompanhar a carteira. Não é uma corretora, conta bancária ou consultoria de investimentos. As cotações são referências externas, com fonte e horário, e podem ter atraso. A importação CSV/OFX é assistida; a categorização aprende somente escolhas confirmadas do usuário.

A tela Minha conta permite feedback e contagens opcionais de uso. Isso prepara a coleta de evidências, mas não comprova demanda, retenção, segurança auditada ou receita. Nenhum usuário real foi contatado ou inscrito automaticamente nesta alteração.

## Rodada com usuários reais

Convidar inicialmente 5–10 pessoas, mediante aceite do responsável. Pedir que cada uma registre ou importe um mês, explique o saldo exibido, crie uma meta, marque uma parcela como paga e registre uma compra/venda de teste em uma conta separada. Não solicitar extratos nem senhas para acompanhar a sessão.

Registrar tempo até o primeiro resumo útil, necessidade de ajuda, divergências percebidas, onde a pessoa desiste e se volta na semana seguinte. Perguntar o que substituiu na rotina e por que pagaria pelo produto; não apresentar intenção declarada como receita.

Com consentimento opcional, `investments:<user_id>.preferences.analytics_consent` autoriza contagens por dia/evento em `usage_metrics`. Não há nomes de ativos, valores ou descrições nos eventos. A opção fica desligada por padrão; desligar remove as contagens atuais. Backups restaurados também a desligam. Eventos não substituem entrevistas ou registros de pagamentos. O feedback fica em `feedback` na carteira da própria conta, limitado aos 30 mais recentes. O acesso operacional ao banco deve ser restrito ao responsável autorizado.

## Diagnóstico e suporte

A API retorna `X-Request-ID`. Falhas inesperadas retornam mensagem genérica com a referência. Os logs da aplicação registram rota, status e tipo de erro; requisições lentas acima de dois segundos geram aviso. Não registrar corpo, extrato, senha ou saldo nos logs. O provedor de infraestrutura pode ter logs próprios.

Solicitar a referência do erro e, se necessário, o diagnóstico de Minha conta, que contém versão, horário, tipo/estado do armazenamento e disponibilidade de cópia anterior. Não solicitar o arquivo financeiro completo para um problema de interface. A tela de feedback não promete atendimento ao vivo; definir um canal e prazo reais antes de anunciar suporte comercial.

## Recuperação e backups

Cada usuário pode gerar seis códigos de recuperação após confirmar a senha. Só hashes ficam no servidor; o texto é exibido uma vez. Cada código é consumido em uma recuperação e invalida sessões anteriores. Gerar novos códigos substitui os antigos. Alterar a senha também revoga sessões. Sem um código previamente guardado, não há recuperação automática por e-mail nesta versão. A senha configurada por `APP_PASSWORD` é administrada no servidor.

O JSON financeiro não inclui senha, hash, segredo de sessão nem códigos. Inclui informações pessoais financeiras e deve ser protegido pelo dono. Restauração exige validação de estrutura e valores, prévia, senha atual e confirmação RESTAURAR. Substitui somente dados financeiros da conta e mantém uma cópia anterior. A autenticação permanece. Download e restauração foram testados em SQLite; caminhos PostgreSQL têm verificações de escopo com mocks e precisam de ensaio em staging para validar o serviço real.

O backup anterior à restauração é uma proteção adicional dentro do mesmo banco. Não substitui cópia externa e política de recuperação de desastre do Neon. Configurar retenção/PITR conforme plano contratado e ensaiar restauração em um projeto separado antes de prometer RPO/RTO. Documentar valores realmente medidos. Exclusão remove registros ativos da conta e a cópia anterior da aplicação; retenção em backups de infraestrutura depende do provedor. Arquivos baixados continuam com o usuário.

## Antes de operação comercial

Configurar e verificar alertas externos de disponibilidade, retenção e restauração do banco, canal de atendimento, informações do controlador e documentos de privacidade/termos adequados à operação. Integração bancária/Open Finance, envio de e-mail e feed de bolsa em tempo real exigem contratação/configuração próprias e não estão conectados por esta alteração. Não publicar alegações de certificação, conformidade integral ou tração que não tenham sido verificadas.

## Recebimentos programados e cartões

A programação de salário usa o calendário de São Paulo e se processa nos acessos ao bootstrap/resumo/relatório e na consulta periódica da interface. Não existe cron contratado/configurado para executar com o app fechado; vencimentos acumulados são processados no próximo acesso. Cada recebimento usa uma chave mês/parcela persistida na transação da carteira. Alterar datas e valores não reescreve recebimentos vencidos; ajustes do valor efetivo ficam no histórico. Pausar não remove lançamentos anteriores. Valores teóricos não comprovam depósitos bancários e não alteram o caixa dos investimentos.

Os cartões guardam somente nome de exibição e dia do vencimento, com cálculo do próximo vencimento. Não coletar PAN/CVV/senhas nesse campo. Lembretes não afirmam que uma fatura em aberto existe, não sabem o valor devido e não confirmam pagamento.


## Separação de previsões e caixa

A programação agora gera previsões; somente recebimentos explicitamente confirmados entram na renda disponível. O total previsto inclui parcelas futuras do mês. Estados antigos `scheduled` não são promovidos automaticamente a confirmados. Renda manual oferece confirmação explícita. O saldo confirmado apresentado é o fluxo do mês, sem saldo inicial bancário, e não deve ser anunciado como saldo disponível real da conta.

Compras de cartão são compromissos e seus pagamentos são os movimentos de caixa. Pagamento parcial reduz a reserva da fatura, antecipação desloca a saída para o mês real e reversão reabre a obrigação. Os testes cobrem limites do ciclo, centavos, restauração de vínculos, idempotência e não duplicação de despesas. Pagamento de fatura no extrato precisa de revisão: não importar novamente como gasto o valor já registrado em Cartões. Não há leitura de fatura bancária, execução de pagamento, cálculo automático de rotativo/IOF ou conciliação bancária automática. Valores com juros cobrados devem ser informados no total da compra ou no compromisso correspondente.

## Piloto de 30 dias — roteiro e registro

Estado desta entrega: **preparado, ainda não executado**. O responsável deve preencher a data inicial, participantes que aceitaram e canal de suporte. Não existem resultados de pessoas reais registrados por esta alteração.

| Período | Atividade | Evidência a registrar |
| --- | --- | --- |
| Dias 1–7 | Cadastrar contas e saldo inicial, importar/revisar movimentos, conferir salário e primeira fatura | Tempo até primeiro resumo, dúvidas e divergências de saldo |
| Dias 8–14 | Conferir contas, registrar transferência própria, pagar parcela e fatura parcial | Diferenças antes/depois, duplicidades percebidas, necessidade de ajuda |
| Dias 15–21 | Testar estorno e resgate em conta de teste; usar pendências na rotina | Resultado esperado/observado, erros e referência de suporte |
| Dias 22–30 | Fechar o mês, conferir faturas e relatório, exportar/restaurar em conta de teste | Saldo explicado pelo participante, retorno semanal, motivo de abandono |

Use um registro por ocorrência: dia do piloto, identificador anônimo do participante, tarefa, esperado, observado, severidade, referência de erro e resolução. Não copiar extratos, senhas ou valores pessoais para issues. Combine individualmente a participação e o registro do feedback.

Critérios para ampliar o piloto: nenhuma duplicidade ou divergência financeira sem explicação; nenhum defeito crítico em aberto; todos os participantes que concluíram conseguem explicar a diferença entre saldo da conta, planejamento, voucher e caixa de investimentos; restauração de staging ensaiada e documentada. Medir retorno nas semanas 2, 3 e 4, sem chamar isso de validação antes dos 30 dias.

## Verificações reproduzíveis

```bash
python -m venv .venv
# Ativar o ambiente conforme seu sistema antes dos comandos abaixo.
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -q
SANITIZE_BUILD=1 python src/build_dashboard.py
python scripts/check_dashboard.py
```

A verificação de JavaScript exige Node.js. O workflow `.github/workflows/checks.yml` executa os mesmos checks a cada push/PR. Os testes usam SQLite temporário e mocks dos caminhos PostgreSQL; não substituem ensaio no Neon/Vercel real. Antes da publicação, registrar ambiente, versão, resultado do teste autenticado, exportação/restauração em staging e responsável pelo retorno à versão anterior. Não há credenciais de produção configuradas neste ambiente.

## Limites dos novos controles

Contas são um livro manual separado do orçamento: abertura, movimentos assinados, transferências em duas pontas e ajustes de conciliação. Um gasto/importação/pagamento já existente **não é automaticamente vinculado a uma conta**. Cadastre o movimento correspondente uma vez no livro da conta; ele não aumenta despesas/renda do relatório. Conciliações exibem a diferença, exigem motivo e rejeitam saldo alterado desde a abertura do formulário.

Estornos registrados reduzem o total líquido da fatura escolhida. Pagamentos anteriores são preservados. Excedentes em faturas pagas aparecem como crédito para conferir; não geram renda nem são transferidos automaticamente para outra fatura ou conta. Não há conciliação automática com o banco. A conferência registra o total do extrato e mostra a diferença atual, inclusive após um novo lançamento.

Resgates de renda fixa usam o saldo estimado pela regra cadastrada, com redução proporcional do principal. O usuário informa bruto e impostos/taxas reais; o líquido entra no caixa, e o resultado realizado considera esse líquido. Resgates seguem ordem cronológica. É possível desfazer primeiro o resgate mais recente, com motivo e saldo suficiente no caixa para retirar o líquido anteriormente creditado. Estornos de fatura também podem ser desfeitos com motivo. Aplicações com resgates ficam preservadas contra edição/exclusão. Se o saldo da instituição divergir da estimativa, confira o cadastro antes do primeiro resgate. Não há cálculo tributário automático.

Cotações externas identificadas em moeda estrangeira são rejeitadas em atualização e histórico. Use cotação manual já convertida em reais ou um código em BRL. Não existe conversão cambial automática nem reconstrução de taxas históricas nesta entrega. Referências antigas de pares estrangeiros consultadas externamente passam a usar o custo em reais até a conferência; dados antigos sem identificação de moeda/fonte exigem revisão manual.
