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

A aba **Investimentos** aceita renda fixa, ações, fundos imobiliários, ETFs, criptomoedas e outros ativos. A atualização consulta primeiro a Brapi para ativos brasileiros, usa o Yahoo Finance como alternativa e busca o CDI na série 12 do Banco Central.

Cada investimento possui uma seta para abrir seu gráfico individual. Ações, FIIs, ETFs e criptomoedas consultam o histórico de mercado no Yahoo Finance somente quando o gráfico é aberto. Renda fixa apresenta uma evolução estimada pela taxa cadastrada. Os períodos disponíveis são 1 mês, 3 meses, 6 meses, 1 ano e 5 anos.

O preenchimento por imagem continua disponível na execução local quando o Tesseract está instalado. A Vercel não inclui o Tesseract; na versão hospedada, esses campos devem ser preenchidos manualmente até uma futura integração com OCR em nuvem.

## Importação de extratos

Na aba **Lançar gasto**, a área **Importar extrato** aceita arquivos CSV, OFX e PDF de até 6 MB e mostra no máximo 500 linhas por vez. O arquivo é processado apenas para gerar uma prévia e não é armazenado. Categorias conhecidas são sugeridas pelo estabelecimento; itens sem correspondência ficam destacados e exigem categoria manual. Comentários, seleção das linhas e categorias podem ser revisados antes da confirmação. Lançamentos duplicados são ignorados durante a importação.

Como layouts de PDF variam entre bancos, CSV ou OFX oferecem resultados mais precisos. A prévia sempre deve ser conferida antes de salvar.

## Limites mensais

A aba **Limites** permite criar categorias personalizadas e definir, editar ou remover o teto de cada categoria por mês. O resumo mostra o limite total, o valor utilizado e o saldo disponível, com alertas em amarelo a partir de 80% e em vermelho ao ultrapassar 100%. O dashboard apresenta o mesmo acompanhamento em barras compactas e os valores são recalculados quando um gasto é criado, editado ou excluído.

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
