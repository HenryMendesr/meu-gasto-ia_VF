# Minha Carteira

PWA multiusuário para controlar gastos, renda, voucher, limites mensais e investimentos. A versão publicada usa PostgreSQL no Neon e uma API Python serverless na Vercel. Nenhuma credencial fica no navegador ou no GitHub.

## Publicação na Vercel

As alterações de desenvolvimento ficam na branch `work`. Integre-as à `main` para publicação; confira em **Vercel → Settings → Environments → Production → Branch Tracking** (ou **Settings → Git**, conforme a interface) se a branch de produção está definida como `main`. Um push somente na `work` não atualiza a produção quando ela acompanha a `main`.

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

Na primeira visita à aba **Investir**, o guia pergunta se a pessoa já sabe investir. Quem está começando pode responder cinco perguntas sobre objetivo, prazo, necessidade de resgate, reação a perdas e experiência. O resultado educativo (conservador, moderado ou arrojado) e a escolha de dispensar o guia ficam salvos nas preferências da conta, inclusive no backup. O botão **Meu perfil e guia de investimentos** permite refazer as respostas e consultar explicações sobre CDB, LCI, LCA, Tesouro Prefixado, Tesouro Selic, Tesouro IPCA+ e debêntures comuns ou incentivadas, com riscos, liquidez, garantias e impostos. O questionário não substitui uma avaliação completa de adequação ao perfil.

O botão **Simular investimento** aceita valor inicial, aporte mensal ao fim do mês, prazo em meses ou anos e taxa anual informada pela pessoa. Há cenários prefixados, percentuais do CDI, IPCA mais juros e Selic, conforme a modalidade. São modalidades reais, sem catálogo de ofertas ou cotações atuais. O resultado separa capital aportado, rendimento bruto, IR/IOF estimados por aporte, rendimento líquido e total acumulado, com gráfico e tabela mensal. A projeção usa juros compostos por dias corridos e índices constantes; o percentual do CDI é aplicado à taxa diária equivalente em base de 252 dias úteis. Considera isenção para pessoa física em LCI, LCA e debêntures incentivadas elegíveis. Não inclui custódia, tarifas, pagamentos periódicos, amortizações, inflação descontada ou preço de venda antecipada; as condições reais de cada nova aplicação precisam ser conferidas na instituição. Simulações não movimentam a carteira.

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

Em **Planejar**, os limites são organizados em cinco grupos: **Custos fixos** (moradia, mercado, carro/transporte, saúde e contas), **Conforto** (alimentação fora, compras e assinaturas), **Lazer e experiências** (lazer, viagens e presentes), **Conhecimento** (educação e cursos) e **Outros** (demais gastos). As categorias detalhadas continuam nos lançamentos e no histórico; abra **O que entra neste grupo?** para consultar a composição. Categorias personalizadas como Carro, Gasolina e Farmácia são reconhecidas como custos fixos; nomes sem associação entram em Outros.

Arraste a barra de cada grupo ou digite um valor exato. Com renda cadastrada, a barra usa percentuais da renda; sem renda, usa reais. O gráfico e o resumo mostram a prévia na hora. Clique em **Salvar alterações** para confirmar ou em **Desfazer** para voltar aos valores salvos. Os limites antigos das categorias são somados por grupo sem regravar o histórico; ao salvar um limite de grupo, esse valor passa a valer para o mês, inclusive quando for zero. Ajustes pendentes são preservados ao trocar de mês enquanto a página permanecer aberta. Os limites são salvos em reais e não mudam automaticamente quando a renda muda. O resumo e os alertas do Início acompanham os mesmos grupos, com atenção a partir de 80% de utilização.

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

O acabamento de **Planejar** usa tokens de espaçamento, cores, sombras e transições do [Open Props 1.7.23](https://open-props.style/). A biblioteca e a licença MIT ficam em `src/vendor/open-props/`, com seletores limitados à tela de planejamento. O build incorpora o CSS localmente, sem CDN, fontes remotas ou dependência de rede no navegador.

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

Em **Visão geral → Detalhes financeiros → Salário em uma ou duas datas**, ative a programação, informe empresa/origem, mês inicial, dia e valor de cada recebimento. Por exemplo, R$ 1.500 no dia 15 e R$ 2.500 no dia 30. O resumo separa a previsão total do mês da renda confirmada. Datas alcançadas continuam como previsões até a confirmação do usuário, sem somar novamente salário informado/importado. A origem do cálculo pode ser alterada no seletor de renda.

O app gera automaticamente as previsões ao abrir/atualizar, ao consultar o relatório e a cada minuto enquanto estiver aberto e sem edição em andamento. Se ficou fechado, os recebimentos pendentes entram no próximo acesso. Não há tarefa de servidor executando sem acesso ao app nesta implementação. Dias 29–31 que não existem no mês são ajustados para o último dia. Datas anteriores do mês inicial também entram ao salvar. Uma chave por mês/parcela impede lançamentos duplicados, inclusive em acessos simultâneos. O valor lançado é uma previsão pelo calendário: o usuário pode conferir/ajustar, desconsiderar ou restaurar. Alterar a programação preserva os valores já lançados e desativar interrompe lançamentos futuros. O caixa de investimentos não é movimentado pelo salário.

Em **Dívidas → Meus cartões**, cadastre nome e dia do vencimento. Há edição, exclusão, próximo vencimento e lembretes no resumo. O menu lateral tem um atalho **Cartões** abaixo de Dívidas; no celular, use Meus cartões dentro de Dívidas. Nenhum número de cartão é necessário. O cadastro sozinho não cria gasto ou pagamento; compras vinculadas compõem faturas e seus pagamentos são confirmados pelo usuário. Programações, recebimentos e cartões são privados por conta e acompanham o backup JSON.


### Previsto, confirmado e faturas completas

A visão geral distingue renda confirmada, renda ainda prevista e saldo com saídas registradas até hoje. O saldo confirmado é um fluxo do mês, sem saldo inicial bancário e sem o caixa dos investimentos. A renda manual tem confirmação explícita; dados antigos sem esse indicador continuam como previsão até serem conferidos. Salários programados usam apenas recebimentos com estado confirmado na renda disponível. Previsões futuras e vencidas permanecem visíveis. A confirmação permite informar a data real: salário atrasado recebido em outro mês entra no mês em que chegou, preservando a previsão original. Importações são usadas como entrada registrada, respeitando a data, e não se somam a outra base de renda selecionada.

Cartões têm fechamento, vencimento e limite opcional. Compras podem ser cadastradas em Cartões, vinculadas a um gasto avulso existente ou lançadas em Lançar com um cartão selecionado. Compras no dia do fechamento entram no próximo ciclo; é possível escolher a primeira fatura. Parcelas repartem o valor total sem perder centavos e mantêm suas datas se o cartão for editado depois. Faturas mostram compras, pagamentos, saldo pendente, atraso e parcelas futuras. Limite restante é uma estimativa baseada nos registros, sem consulta à instituição.

O planejamento inclui as obrigações nas faturas. O relatório de caixa considera somente os pagamentos confirmados, parciais ou totais, na data efetiva. Não soma novamente as compras. O saldo projetado reserva o restante pendente no vencimento e desloca valores já pagos para o mês do pagamento, inclusive antecipações. Vincular um gasto existente o substitui por suas parcelas na visão do app; o registro de origem é preservado para recuperação e restauração. Não lance uma nova despesa para um pagamento já registrado em Cartões. Na importação, descrições de pagamento de fatura ficam desmarcadas para revisão.

Pagamentos podem ser desfeitos com histórico. Para editar/remover compras em faturas pagas, é preciso desfazer os pagamentos afetados. Cartões e categorias com histórico são preservados. Compras posteriores podem reabrir uma fatura já paga. Exportação e restauração validam vínculos e pagamentos, mantendo as associações mesmo quando IDs do banco mudam. Nenhuma dessas ações executa pagamento, transfere dinheiro ou confirma informação no banco.

### Metas vinculadas aos investimentos

Em Planejar → Nova meta → Como acompanhar, escolha acompanhamento manual, valor atual dos investimentos ou valor aplicado nas posições abertas. Uma meta de R$ 50.000 pode usar automaticamente o total mostrado em Investir. O valor atual considera valorização/desvalorização; o valor aplicado acompanha o custo das posições ainda abertas. Os dois modos excluem caixa e posições já vendidas. Metas antigas continuam manuais.

O progresso é recalculado nas consultas e nas atualizações da carteira, sem gravar um saldo manual para metas automáticas. Compras, vendas e atualizações de cotação alteram o progresso; adicionar dinheiro apenas ao caixa não altera. A meta não reserva nem movimenta dinheiro e pode regredir se o patrimônio cair. Mais de uma meta pode acompanhar a mesma carteira; seus valores não devem ser somados como reservas independentes.

### Rotina, contas e conferência

A Visão geral reúne recebimentos a confirmar, parcelas em aberto e faturas para pagar/conferir em **Pendências para conferir**. **Contas e saldos conferidos** permite cadastrar saldo inicial, entradas/saídas manuais, transferências próprias e conciliação com motivo e prévia da diferença. Esse livro é separado do orçamento; os lançamentos existentes não recebem conta automaticamente.

Em **Investir**, renda fixa possui **Registrar resgate** parcial ou total: informe bruto e impostos/taxas reais. O líquido entra no caixa, o principal é reduzido proporcionalmente e o histórico é preservado. O relatório e o resumo diário incluem o resgate. O vencimento sozinho continua sem encerrar a aplicação.

Em **Cartões**, cada fatura oferece **Registrar estorno** e **Conferir total**. Estornos preservam compras e pagamentos; crédito em uma fatura já paga fica identificado para conferência. Não há transferência automática desse crédito. Conferir o total do extrato mostra a diferença, sem alterar compras ou marcar pagamento.

A projeção de dívidas pagas segue o mês da data efetiva, inclusive antecipações e atrasos; parcelas abertas permanecem no calendário previsto, com atrasadas reunidas no início do gráfico de saldo aberto. Cotações externas em moeda estrangeira são bloqueadas para evitar mistura com reais: use código BRL ou cotação manual convertida.

O [roteiro de 30 dias e operação](docs/PILOT.md) registra as etapas do piloto e as limitações. O piloto com pessoas reais ainda precisa ser executado. As verificações automáticas estão em `.github/workflows/checks.yml`.

### Início simples e Ganhos e fixos

A primeira aba agora apresenta somente três números principais: **Entrou até agora**, **Saídas do mês** (pagas e previstas) e **Previsão ao fim do mês**. Pendências ficam logo abaixo. Gráficos, voucher, relatório e histórico continuam disponíveis em áreas que você abre quando precisar.

Na nova aba **Ganhos e fixos**, escolha o mês, informe/edite os ganhos e adicione contas mensais por nome, valor e dia. A programação de salário em uma ou duas datas permanece disponível no mesmo lugar. O resumo “Depois dos fixos” desconta apenas fixos em dinheiro; outros gastos ainda precisam ser considerados no Início.

Gastos fixos se repetem automaticamente no planejamento, ajustam dias inexistentes ao último dia do mês e só entram nas saídas confirmadas depois de **Marcar como pago**. O pagamento pode ser desfeito. Editar cria uma configuração válida a partir do mês escolhido, preservando meses anteriores e valores já pagos. Desmarcar **Repetir todo mês** encerra as próximas cobranças. **Não contar neste mês** permite evitar duplicidade quando a mesma conta já foi lançada ou importada; a repetição seguinte continua. Compras no cartão permanecem em Cartões.

As repetições aparecem no histórico e nos limites como o mesmo gasto, sem criar outra despesa ao confirmar pagamento. Pagamentos antecipados/atrasados seguem a data real no fluxo de caixa. Os cadastros e confirmações acompanham o backup JSON e ficam privados por conta.

### Cotações automáticas das posições

Ao abrir Investir, voltar à aba ou manter a carteira visível, o app consulta os valores salvos e tenta atualizar as cotações externas. Consultas automáticas reutilizam uma cotação buscada há menos de cinco minutos e aguardam pelo menos um minuto após falha. O botão **Atualizar taxas e cotações** permite tentar novamente manualmente. São consultados até oito códigos diferentes por ciclo; carteiras maiores continuam nos ciclos seguintes. Duas posições com o mesmo código compartilham a consulta, preservando quantidade, custo e resultado individual.

Ações brasileiras usam Brapi, com Yahoo Finance como alternativa (dois endpoints). O histórico usa Yahoo Finance e tenta Brapi se indisponível. A cobertura, intervalo histórico, atraso e cotas dependem do provedor; nenhum desses serviços equivale a um feed contratado diretamente da B3. A tabela distingue cotação unitária, variação percentual e em reais por unidade no pregão identificado e resultado acumulado desde as compras. O gráfico oferece cotação no período ou resultado pessoal, considerando compras, vendas e proventos registrados.

Para acesso autenticado à Brapi, cadastre **BRAPI_TOKEN** em **Vercel → Settings → Environment Variables** e faça novo deploy. Use um token e plano com acesso aos códigos/períodos desejados. Não coloque o token no navegador, Git ou campos do app. Sem token, o app tenta o acesso permitido pelo provedor e a alternativa Yahoo; se ambos recusarem ou estiverem indisponíveis, o app mostra o erro e preserva a última cotação. Sem nenhuma cotação válida, mostra **Aguardando cotação**, não uma valorização de zero. Os totais que ainda dependem de posições sem cotação usam seu custo como referência, com aviso de resultado incompleto.

Consultar agora não significa que o preço seja de agora: a data do pregão acompanha cada ativo. Desdobramentos, grupamentos, alterações de código e outras operações societárias não ajustam quantidades/custo automaticamente; devem ser conferidos. Os testes de integração de cotações usam respostas simuladas e não comprovam disponibilidade em produção.

### Escolher acompanhamento automático por investimento

A opção **Acompanhar automaticamente** fica disponível no cadastro de todos os tipos de investimento e vem ligada por padrão. Na tabela, **Automático: ligado/desligado** permite mudar essa preferência sem editar quantidade, preço médio ou operações — inclusive em aplicações com resgates já registrados. A escolha é individual por posição, acompanha o backup JSON e não movimenta dinheiro.

Não há uma lista limitada a BBAS3/BPAC11: a rotina consulta os códigos cadastrados em ações, FIIs, ETFs, criptomoedas e outros ativos negociados que as fontes reconheçam. Exemplos de códigos: VALE3, HGLG11, IVVB11 e BTC-BRL. Para códigos brasileiros no Yahoo usa-se o sufixo `.SA`; símbolos internacionais e pares de cripto preservam seu código de negociação. A cobertura, o acesso autenticado e a moeda continuam dependendo da fonte. Cotações em moeda estrangeira sem conversão não são usadas como reais.

Depois de salvar um investimento com acompanhamento ligado, a interface tenta consultar a cotação/índice imediatamente. Durante o uso da aba, continuam valendo cache de cinco minutos, espera após erro, consulta compartilhada para códigos repetidos e lotes limitados. Desligar remove aquela posição das consultas periódicas e preserva o último preço; o botão de atualização manual e a abertura explícita de histórico continuam disponíveis. Ligar/desligar durante uma consulta impede que a resposta antiga sobrescreva a posição.

Em renda fixa, a preferência controla a consulta externa do CDI quando aplicável. O cálculo local pela taxa cadastrada continua sendo uma estimativa, não uma cotação de venda ou marcação a mercado. Ativos sem cotação pública compatível devem usar o valor manual, e um índice indisponível precisa ser preenchido/conferido. A opção não contrata um feed nem torna universal a cobertura dos provedores.

### Detalhes visuais de um ativo

Ao abrir o gráfico de um investimento, a área destaca o último fechamento ou resultado do gráfico e a mudança no período selecionado. Os botões **Cotação/Saldo** e **Meu resultado** alternam a informação; os intervalos 1M, 3M, 6M, 1A, 5A e Tudo preservam a escolha ao alternar a visualização. O fechamento do gráfico e a cotação usada no valor da posição têm referências próprias e podem diferir durante o pregão.

A linha possui preenchimento discreto e referência tracejada de preço médio ou capital. Ao tocar, passar o mouse ou usar as setas do teclado, o balão mostra apenas data e valor. Abertura, máxima, mínima e volume ficam em **Detalhes da data consultada**. **Sua posição** reúne quantidade, valor aplicado, valor da posição e resultado em cartões separados. A mesma apresentação se adapta ao celular e aos gráficos de renda fixa e do relatório.

Atualizações de cotação mantêm o ativo aberto e o período escolhido. Se uma consulta de período falhar, o gráfico anterior permanece disponível com uma opção de tentar novamente. A reorganização visual não modifica preços, operações nem fórmulas financeiras.

### Primeiro uso e dia a dia no Início

O Início agora concentra as ações frequentes. Quem está começando vê uma orientação opcional com uma etapa por vez: informar os ganhos, registrar um gasto e visualizar o resumo. É possível pular os ganhos ou dispensar a orientação. Não é preciso configurar investimentos, metas ou dívidas para começar. Os cadastros existentes e a opção de já dispensar a orientação são respeitados.

O resumo usa barras para comparar ganhos previstos e saídas, explicita o que ainda falta confirmar e mostra a sobra prevista. **Gastei com…** registra um gasto no próprio Início; data e pagamento ficam como opções secundárias, com Hoje/Pix visíveis por padrão. O resumo e os últimos gastos mudam após salvar. Possíveis duplicidades exigem uma escolha explícita antes de repetir. O rascunho pode ser levado ao lançamento completo quando for necessário cartão, parcelamento ou outras opções.

**O que vem agora** reúne vencimentos e recebimentos do mês, permitindo confirmar salário, pagar parcelas, marcar contas fixas e registrar pagamentos de faturas sem navegar para outra aba. As ações usam as mesmas confirmações e registros existentes; não executam pagamentos bancários nem criam outra despesa para a baixa. As três primeiras pendências ficam visíveis e o restante pode ser expandido na mesma tela. Contas fixas também podem ser adicionadas diretamente dali.

A navegação principal mostra **Início**, **Ganhos e fixos**, **Registrar**, **Planejar**, **Investir**, **Dívidas** e **Cartões**, com ícones e nomes clicáveis. Gráficos e limites ficam em Planejar; voucher e conferências complementares, em Ganhos e fixos. Relatório mensal e histórico completo continuam acessíveis no Início, enquanto as informações comuns aparecem sem precisar abrir essas áreas. A experiência foi verificada em navegador com dados de teste; o efeito sobre entendimento e abandono ainda precisa ser medido no piloto com pessoas reais.

### Cotações: mercado fracionário e terceira fonte

Códigos fracionários como `PETR4F` permanecem no cadastro e nas operações. Na consulta de preço e histórico, o app usa o ticker do lote padrão (`PETR4`) como referência e informa isso na carteira: o preço do fracionário pode diferir. Não é necessário excluir ou recadastrar a posição.

Para cotações brasileiras, a ordem automática é **Brapi → Yahoo Finance (dois servidores) → Alpha Vantage**. A terceira fonte usa `GLOBAL_QUOTE` com o símbolo brasileiro terminado em `.SAO`, quando o provedor cobre o ativo. Cadastre `ALPHAVANTAGE_API_KEY` em **Vercel → Settings → Environment Variables**, no ambiente de produção, e faça novo deploy. A chave fica somente no servidor. A Brapi continua usando `BRAPI_TOKEN`. Não compartilhe essas chaves no chat ou em código.

Chaves, cobertura, frequência permitida e eventual contratação de plano dependem dos provedores. As consultas podem fornecer dados atrasados; não são streaming nem garantia de tempo real. A terceira fonte é para a cotação; o histórico continua usando Yahoo/Brapi. Se todas falharem, o app mantém a cotação anterior e sinaliza a falha; sem cotação anterior, mostra pendência.

A integração Alpha Vantage foi verificada com respostas simuladas (sucesso, limite, resposta inválida, chave ausente e símbolo divergente). A política de rede desta sessão não permite uma consulta real ao provedor. Validar cobertura e disponibilidade com a chave do plano na Vercel.
