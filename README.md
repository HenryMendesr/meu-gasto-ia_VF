# Meu Gasto IA — versão Excel

Controle financeiro pessoal feito em Excel, pensado para funcionar sozinho e ser simples de usar.

![Prévia da planilha](docs/preview.png)

## Baixar e usar

O arquivo pronto está em [`excel/Controle_Gastos_Automatico.xlsm`](excel/Controle_Gastos_Automatico.xlsm).

1. Baixe o arquivo `.xlsm`.
2. Abra pelo Excel para computador.
3. Se o Excel solicitar, habilite as macros do arquivo.
4. Preencha apenas os campos amarelos.

## Funcionalidades

- Cadastro rápido de gastos.
- Exclusão de lançamentos feitos por engano.
- Salário, gastos, saldo e despesas fixas calculados automaticamente.
- Gráficos separados do mês atual e do mês anterior.
- Controle de parcela do carro e gasolina.
- Histórico com até 500 lançamentos.
- Uma única aba visível para facilitar o uso.

## Estrutura

- `excel/`: versão pronta para utilização.
- `src/build.mjs`: criação da planilha, fórmulas, visual e gráficos.
- `src/build_xlsm.py`: inclusão das macros e preparação do `.xlsm`.
- `src/cfb_vba.py` e `src/template.bin`: suporte à montagem do projeto VBA.
- `docs/preview.png`: imagem de demonstração.

## Desenvolvimento

Execute os comandos a partir da raiz do repositório:

```bash
node src/build.mjs
python3 src/build_xlsm.py
python3 src/validate_xlsm.py
```

O primeiro comando gera `build/Controle_Gastos_Automatico.xlsx`. Ele requer Node.js e o pacote privado `@oai/artifact-tool`, que precisa estar disponível no ambiente de geração. O segundo comando inclui as macros e cria a versão final em `excel/`. O terceiro verifica a integridade do arquivo, as fórmulas, a visibilidade das abas, os botões e as macros.

O caminho dos arquivos é calculado a partir da localização dos scripts, portanto os comandos funcionam mesmo quando o repositório estiver em outra pasta.

## Painel web

O painel em [`web/index.html`](web/index.html) funciona sem servidor e pode ser aberto diretamente no navegador. Ele mostra entradas, gastos, saldo, categorias e histórico com filtros.

Depois de atualizar a planilha, gere novamente o painel com:

```bash
python3 src/build_dashboard.py
```

O valor da renda de cada mês pode ser ajustado no próprio painel e fica salvo no navegador utilizado.

> A planilha pronta não precisa de Node.js nem Python. Basta utilizar o Excel para computador.

