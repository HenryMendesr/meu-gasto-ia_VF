# Minha Carteira

PWA multiusuário para controlar gastos, renda, voucher, limites mensais e investimentos. A versão publicada usa PostgreSQL no Neon e uma API Python serverless na Vercel. Nenhuma credencial fica no navegador ou no GitHub.

## Publicação na Vercel

Importe este repositório na Vercel e mantenha as configurações automáticas. Antes do primeiro deploy, cadastre em **Settings → Environment Variables**:

- `DATABASE_URL`: conexão com pooling fornecida pelo Neon.
- `APP_PASSWORD`: compatibilidade com a versão anterior; depois de configurar `REGISTRATION_CODE` e criar sua conta, pode ser removida.
- `REGISTRATION_CODE`: código privado compartilhado somente com familiares e amigos autorizados.
- `SESSION_SECRET`: valor aleatório longo usado para assinar as sessões.

Marque as quatro variáveis para **Production**, **Preview** e **Development**. Não use valores do arquivo `.env.example`; ele contém somente exemplos.

A Vercel fornece HTTPS automaticamente. O aplicativo não precisa de computador ligado nem de uma porta aberta no roteador.

## Migrar os dados locais

O banco SQLite local está ignorado pelo Git e nunca é enviado à Vercel. Para transferir os dados existentes uma única vez, defina `DATABASE_URL` somente no terminal local e execute:

```bash
python3 scripts/migrate_to_neon.py --email seu-email@exemplo.com
```

Crie sua conta no aplicativo antes de executar o comando. O script cancela a operação se encontrar gastos nessa conta no Neon, evitando duplicidade. A conexão nunca deve ser adicionada a arquivos versionados.

## Instalar como aplicativo

- **Android:** abra o endereço HTTPS no Chrome e toque em **Instalar app**.
- **iPhone/iPad:** abra no Safari e use **Compartilhar → Adicionar à Tela de Início**.
- **Computador:** abra no Chrome ou Edge e use o ícone de instalação na barra de endereço.

O manifesto abre o app em janela independente. O service worker armazena somente ícones, manifesto e a página offline; páginas autenticadas, APIs e informações financeiras não entram no cache.

## Funcionamento offline

Quando não houver conexão, o aplicativo mostra uma tela clara de indisponibilidade. Consultas e alterações precisam de internet porque o banco fica no Neon. Cotações e CDI também dependem das respectivas fontes externas.

Novas versões são baixadas em segundo plano. Quando um service worker novo estiver pronto, o aplicativo oferece o botão **Atualizar** e só recarrega depois da confirmação.

## Investimentos

A aba **Investir** aceita renda fixa, ações, fundos imobiliários, ETFs, criptomoedas e outros ativos. Os saldos de renda fixa são recalculados pela API ao abrir a carteira, voltar à aba e a cada minuto enquanto a aba está visível, sem precisar atualizar cotações. O formulário mostra uma prévia antes de salvar.

Para **Prefixado** e **Outro**, informe uma taxa efetiva **ao ano** ou **ao mês**. O cálculo usa juros compostos e dias corridos (ano de 365 dias), com conversão equivalente entre as taxas, e para no vencimento. A carteira apresenta saldo, rendimento acumulado, taxa equivalente mensal e rendimento bruto estimado de um mês sobre o saldo atual. A estimativa não desconta impostos, tarifas ou seguros.

Em **CDI**, informe o percentual do índice e o CDI anual de referência, ou use **Atualizar taxas e cotações** para consultar a série 12 do Banco Central. O cálculo converte a referência em taxa diária com 252 dias úteis e aplica a participação contratada; o saldo é uma projeção pelo índice de referência, não uma reprodução das taxas históricas. Em **IPCA + taxa**, informe o IPCA anual de referência; o índice é composto com a taxa real contratada. Um índice ausente gera aviso e não apresenta rendimento mensal como zero conhecido.

A atualização do saldo tem três modos: **Automática pela taxa** parte do valor e data da aplicação; **Render a partir de saldo informado** corrige um saldo de referência a partir da data informada; **Saldo manual** mantém o valor fornecido. Saldos manuais do cadastro antigo passam a servir como referência na data de sua última edição, para continuar rendendo sem perder o saldo informado.

Carteiras só de renda fixa têm gráfico estimado desde a aplicação, com até um ano de projeção retrospectiva e valores calculados pela mesma regra do saldo. Carteiras com renda variável usam os registros de atualização. Os gráficos individuais oferecem 1 mês, 3 meses, 6 meses, 1 ano e 5 anos. Na renda variável, as cotações usam Brapi/Yahoo Finance e o gráfico consulta histórico do Yahoo Finance ao ser aberto.

O preenchimento por imagem está disponível na execução local com Tesseract. Na Vercel, preencha os campos manualmente quando o OCR estiver indisponível.

## Importação de extratos

Na aba **Lançar gasto**, a área **Importar extrato** aceita arquivos CSV, OFX e PDF de até 6 MB e mostra no máximo 500 linhas por vez. O arquivo é processado apenas para gerar uma prévia e não é armazenado. Categorias conhecidas são sugeridas pelo estabelecimento; itens sem correspondência ficam destacados e exigem categoria manual. Comentários, seleção das linhas e categorias podem ser revisados antes da confirmação. Lançamentos duplicados são ignorados durante a importação.

Linhas de saldo, como **saldo do dia**, saldo anterior e saldo disponível, são descartadas. Créditos são separados dos gastos e podem ser classificados como salário, pagamento recebido, transferência recebida, reembolso, rendimentos ou outras entradas. Essas entradas aparecem em um gráfico próprio no dashboard e não consomem limites de gastos.

A conferência também mostra confiança, possíveis duplicidades, transferências próprias, recorrências, tarifas, juros, estornos e compras parceladas encontradas na descrição. Quando há evidência de salário, o aplicativo sugere dia, valor habitual e origem; a renda mensal só é atualizada se o usuário marcar a confirmação antes de importar.

Como layouts de PDF variam entre bancos, CSV ou OFX oferecem resultados mais precisos. A prévia sempre deve ser conferida antes de salvar.

## Limites mensais

A aba **Limites** permite criar categorias personalizadas e definir, editar ou remover o teto de cada categoria por mês. O resumo mostra o limite total, o valor utilizado e o saldo disponível, com alertas em amarelo a partir de 80% e em vermelho ao ultrapassar 100%. O dashboard apresenta o mesmo acompanhamento em barras compactas e os valores são recalculados quando um gasto é criado, editado ou excluído.

## Compras parceladas

Ao escolher **Crédito**, o lançamento pode ser dividido em até 120 parcelas. Empréstimos, dívidas e financiamentos possuem cadastro próprio na aba **Dívidas**, inclusive quando a cobrança ocorre por Pix ou transferência. Informe o valor financiado **sem juros**, a taxa **mensal** (zero para compras sem juros), a quantidade e a primeira cobrança. O app calcula parcelas fixas pela Tabela Price, separa juros e amortização e ajusta os centavos na última cobrança. A taxa aceita vírgula ou ponto.

Alterar a quantidade recalcula o valor da parcela; alterar o valor recalcula a quantidade. Apagar um dos campos o preenche novamente usando o outro. Parcelas que não cobrem os juros ou exigem mais de 120 meses são rejeitadas. Os campos de gasto e parcela usam máscara monetária com duas casas: digitar `12345` mostra `123,45`.

A prévia mostra quanto reservar para antecipar a última parcela ou quitar todas, com o desconto dos juros futuros. As dívidas salvas aparecem em **Detalhes financeiros**, com estimativas para as parcelas futuras a partir da data atual. O desconto usa meses de 30,4375 dias; são estimativas sem tarifas, seguros ou parcelas vencidas e precisam ser confirmadas com o credor. O app não executa amortizações no banco.

As parcelas pertencem a um grupo, aparecem nos meses futuros e podem ser editadas ou excluídas individualmente ou em conjunto. A primeira cobrança define o calendário, pois ainda não há cadastro de fechamento e vencimento de cartões. Alterar uma parcela salva ajusta o compromisso registrado; não renegocia a dívida.

## Empréstimos, dívidas e financiamentos

A aba **Dívidas** cadastra empréstimos (pessoal, consignado e com garantia), dívidas (cartão, cheque especial, contas em atraso e renegociações) e financiamento de imóveis, veículos ou outros bens. Os campos incluem credor, saldo a pagar, juros mensais, prazo de 1 a 600 parcelas, primeiro vencimento, data do contrato, categoria e forma de pagamento. No financiamento, o valor do bem menos a entrada já paga define o principal; a entrada não gera um novo gasto. Price usa parcelas fixas e SAC usa amortização constante com parcelas decrescentes.

Ao salvar, o app gera os gastos de cada parcela nos meses de vencimento, preserva a separação entre principal e juros e atualiza os gráficos. A aba mostra a curva do saldo devedor projetado, barras mensais de principal e juros, resumo dos valores, filtro por contrato e tabela com todos os vencimentos. Os dados antigos de empréstimos e financiamentos também aparecem na aba. Os gráficos são projeções pelo calendário e não comprovam pagamentos. Excluir um compromisso sem parcelas pagas remove todas as suas parcelas. A edição preserva as parcelas pagas e recalcula somente as pendentes. Contratos quitados não podem ser reescritos. Para excluir todo o contrato, é necessário desfazer as baixas registradas.

## Agendamento de Pix e transferência

Selecione **Agendar Pix ou transferência** e informe a data prevista. O gasto fica salvo nessa data, identificado como **Agendado no app**, e pode ser editado ou excluído. Esse registro serve ao planejamento financeiro: o pagamento precisa ser agendado no banco. O agendamento simples não se aplica simultaneamente a um parcelamento, que já possui seu próprio calendário.

## Segurança

- Banco Neon acessado somente pela API, usando `DATABASE_URL` secreta.
- Cookie de sessão `HttpOnly`, `Secure` e `SameSite=Strict`.
- Contas individuais com senha derivada por PBKDF2 e cadastro protegido por código de convite.
- Limite de tentativas repetidas de login e de código de convite.
- Cada consulta filtra os dados pelo proprietário autenticado.
- Requisições de alteração vindas de outros sites são bloqueadas.
- Sessões assinadas e válidas por 30 dias.
- Textos importados e cadastrados são neutralizados antes de entrar no HTML.
- Nenhuma senha, token ou chave no JavaScript.
- APIs e página principal protegidas por autenticação.
- Respostas financeiras com cache desativado.
- Arquivos `.env`, banco SQLite e configuração da Vercel ignorados pelo Git.

## Uso local

Para usar a versão local com SQLite, execute:

```bash
python3 src/dashboard_server.py
```

No Windows, também é possível abrir `INICIAR_PAINEL.bat`. O primeiro acesso local permite criar uma senha. Os dados ficam em `data/meu_gasto.db`, com até 20 backups em `backups/app/`.

## Desenvolvimento

```bash
python3 -m pip install -r requirements.txt
python3 -m unittest discover -s tests -v
SANITIZE_BUILD=1 python3 src/build_dashboard.py
```

O último comando gera o HTML versionado sem incorporar dados locais.

Arquivos principais:

- `api/index.py`: API FastAPI para a Vercel.
- `src/cloud_storage.py`: persistência PostgreSQL/Neon.
- `src/storage.py`: persistência SQLite local.
- `src/runtime_storage.py`: seleção automática do banco.
- `scripts/migrate_to_neon.py`: migração única do SQLite.
- `vercel.json`: rotas, função e cabeçalhos da Vercel.
- `public/manifest.webmanifest`: instalação da PWA.
- `public/service-worker.js`: cache seguro e atualização.

Os gráficos individuais de renda variável abrem com os últimos três meses de cotações, independentemente da data de compra. Mostram uma linha contínua de preços em fundo preto, com consulta de data, preço e volume por mouse, toque ou teclado. A fonte é Yahoo Finance, não um feed oficial em tempo real da B3. A linha tracejada indica seu preço médio.

A opção **Meus ganhos e perdas** mostra apenas o resultado em reais desde a compra, incluindo vendas registradas. O painel geral também apresenta o resultado acumulado nas datas de atualização da carteira, sem incluir o capital aplicado. Lucro e prejuízo incluem resultado em aberto, vendas líquidas e proventos registrados. Taxas informadas nas operações entram no custo ou são descontadas da venda; impostos não são estimados automaticamente. Para renda fixa, os saldos históricos são estimativas pela taxa cadastrada.

Use **Registrar venda** para informar data, quantidade e preço por unidade ou valor total recebido. Vendas parciais reduzem a posição aberta; vendas totais encerram a posição sem apagar o histórico. O valor líquido da nova venda (bruto menos taxas informadas) entra automaticamente no caixa de investimentos, na mesma transação do registro da venda. Vendas antigas não são creditadas retroativamente. Ativos com vendas preservam os dados originais da compra e não podem ser excluídos, para manter o resultado realizado. Em renda variável, use **Movimentar → Novo aporte** para comprar mais no mesmo ativo. O custo com taxas é debitado do caixa; o preço médio é recalculado sobre a posição ainda aberta, preservando o resultado das vendas anteriores. Registre compras e vendas em ordem cronológica. Aportes de renda fixa continuam com cadastros individuais.

A interface usa um tema escuro com navegação lateral no computador e inferior no celular. A paleta e os componentes compartilhados ficam em `public/app.css`; os layouts complementares ficam nos arquivos CSS dos painéis. Ao alterar a interface, regenere `templates/index.html` com `SANITIZE_BUILD=1 python3 src/build_dashboard.py`.

Em **Dívidas**, use **Editar dívida** para preencher o formulário com o contrato cadastrado. Ao salvar, todas as parcelas desse cadastro são substituídas em uma única transação, inclusive as de datas passadas; outros gastos permanecem intactos. A opção **Calcular juros pela parcela** estima a taxa mensal efetiva a partir do saldo sem juros, da prestação e do número de meses, usando parcelas fixas (Price). A última prestação pode ajustar centavos. A estimativa não representa o CET e não separa tarifas, impostos ou seguros incluídos no valor informado.

Em **Investimentos → Caixa**, o botão **Ajustar caixa** registra o saldo total disponível para investir. O painel mostra o caixa separado dos ativos e o total de investimentos + caixa. Novos cadastros descontam automaticamente o valor aplicado: quantidade × preço médio na renda variável e principal na renda fixa. É necessário ter saldo suficiente. A edição desses cadastros ajusta apenas a diferença de custo; excluí-los sem vendas devolve o valor debitado. Cadastros anteriores não recebem desconto ou devolução retroativa. Caixa e ativo são salvos na mesma transação para evitar débitos perdidos ou caixa negativo em compras simultâneas. O saldo não entra na rentabilidade nem na renda mensal. Novas vendas líquidas e proventos registrados também entram automaticamente no caixa. Depósitos, retiradas e correções externas continuam pelo botão Ajustar caixa.


## Proventos, metas e relatório mensal

Em **Investir → Movimentar → Receber provento**, registre dividendos, JCP, rendimentos de FIIs e outros proventos pelo valor líquido recebido. O recebimento entra no caixa e no resultado do ativo, sem alterar a quantidade. A posição, os custos médios e os gráficos pessoais passam a considerar as datas dos aportes, vendas e recebimentos. A rentabilidade apresentada é acumulada simples sobre o total das compras, não anualizada. Operações e caixa são gravados de forma atômica; novas vendas, aportes e proventos usam identificadores de requisição para evitar movimentos duplicados em tentativas repetidas.

Em **Dívidas → Calendário e pagamentos**, marque cada parcela como paga e informe a data real. A baixa atualiza o próprio lançamento, sem gerar outra despesa nem movimentar o caixa de investimentos. É possível desfazer a baixa. Totais e projeções mostram o que permanece em aberto; o relatório considera a parcela no mês do pagamento, mesmo quando o vencimento é de outro mês.

Em **Planejar → Nova meta**, informe nome, valor desejado, total já reservado e prazo. O aplicativo mostra progresso, valor restante e sugestão mensal aproximada. O progresso é manual e não retira dinheiro de outras contas ou investimentos.

Em **Visão geral → Relatório mensal**, acompanhe renda, saídas, aportes, vendas líquidas, proventos e dívidas, compare seis meses e exporte um CSV. Quando há renda mensal cadastrada, ela tem prioridade sobre o total importado para não duplicar salário; confira o valor informado caso existam outras entradas. Sem renda cadastrada, usam-se as entradas importadas. Voucher e caixa de investimentos são mostrados separadamente. O patrimônio histórico usa os registros salvos nas atualizações do app; ele não é reconstruído retroativamente quando não há dados, e aportes não são apresentados como rendimento.


### Transparência, correções e conta

O resumo mostra **saldo planejado**, com explicação dos lançamentos e parcelas pendentes; ele não é um saldo bancário. A renda do mês pode usar o valor informado, as entradas importadas ou seleção automática, sem somar as duas bases. A mesma escolha vale no relatório. Vencimentos pendentes aparecem no resumo e as cotações mostram fonte/data, com indicação de valores manuais ou atualização antiga.

Em **Investir → Histórico de movimentações → Corrigir**, veja uma prévia do efeito no caixa, quantidade, preço médio e resultado antes de corrigir, estornar ou restaurar. A operação e o motivo ficam preservados; mudanças concorrentes exigem nova prévia. Compras anteriores ao controle automático não geram débito retroativo. **Conferir saldo** registra diferenças do caixa e seu motivo.

**Minha conta** reúne senha, códigos de recuperação de uso único, exportação JSON, restauração com prévia e cópia anterior, exclusão da conta, diagnóstico e feedback. Contagens de uso são opcionais e desligadas por padrão. Códigos devem ser guardados antes de perder o acesso; não há envio de recuperação por e-mail nesta versão. Consulte [piloto e operação](docs/PILOT.md) para limites, validação com clientes e dependências externas.


### Resumo diário de investimentos

Logo abaixo do cabeçalho de Investir, o resumo permite alternar entre Hoje e o último dia com operações registradas. Mostra aplicações/compras, vendas líquidas, resultado realizado, proventos, movimentação do caixa e taxas. Despesas pessoais aparecem separadas: dívidas seguem a data de pagamento e gastos comuns a data do lançamento. Operações estornadas ficam fora dos totais.

A variação da posição considera quantidade anterior e final, cotação do dia e fechamento anterior, ajustada pelas compras, vendas e proventos; aportes não viram lucro. Cotações devem ter data do pregão identificada pelo provedor. Sem referências suficientes, o resumo identifica os ativos pendentes e não apresenta um total completo. Uma cotação consultada hoje pode ser de outro pregão. Renda fixa automática tem variação estimada pela taxa; valores manuais não são tratados como desempenho diário comprovado.


### Posições ativas e histórico pesquisável

A tabela principal de Investir mostra somente posições abertas de renda variável, além dos cadastros de renda fixa. A venda total retira o ativo dessa tabela sem apagar suas operações ou seu resultado. O histórico abaixo permite buscar nome, código ou instituição e filtrar posições ativas/encerradas. Mostra preço unitário, quantidade, posição e preço médio antes/depois de compras e vendas, além do resultado realizado por dia e proventos separados. A busca consulta todo o histórico; Carregar mais permite continuar além das primeiras 40 operações.

Posições encerradas mantêm ações de comprar novamente ou receber proventos. Uma recompra reabre o ativo, preservando as vendas anteriores. Estornos são identificados e não entram nos resultados; estornar uma venda pode reabrir a posição. Renda fixa não é encerrada automaticamente só pelo vencimento, pois isso não comprova resgate.

### Salário em duas datas e vencimentos de cartões

Em **Visão geral → Detalhes financeiros → Salário em uma ou duas datas**, ative a programação, informe empresa/origem, mês inicial, dia e valor de cada recebimento. Por exemplo, R$ 1.500 no dia 15 e R$ 2.500 no dia 30. O resumo usa somente as datas já alcançadas, sem somar o mesmo salário informado/importado. A origem do cálculo pode ser alterada no seletor de renda.

O app processa automaticamente os vencimentos ao abrir/atualizar, ao consultar o relatório e a cada minuto enquanto estiver aberto e sem edição em andamento. Se ficou fechado, os recebimentos pendentes entram no próximo acesso. Não há tarefa de servidor executando sem acesso ao app nesta implementação. Dias 29–31 que não existem no mês são ajustados para o último dia. Datas anteriores do mês inicial também entram ao salvar. Uma chave por mês/parcela impede lançamentos duplicados, inclusive em acessos simultâneos. O valor lançado é uma previsão pelo calendário: o usuário pode conferir/ajustar, desconsiderar ou restaurar. Alterar a programação preserva os valores já lançados e desativar interrompe lançamentos futuros. O caixa de investimentos não é movimentado pelo salário.

Em **Dívidas → Meus cartões**, cadastre nome e dia do vencimento. Há edição, exclusão, próximo vencimento e lembretes no resumo. O menu lateral tem um atalho **Cartões** abaixo de Dívidas; no celular, use Meus cartões dentro de Dívidas. Nenhum número de cartão é necessário. O cadastro não cria gasto, dívida ou pagamento automático de fatura. Programações, recebimentos e cartões são privados por conta e acompanham o backup JSON.
