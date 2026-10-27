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
