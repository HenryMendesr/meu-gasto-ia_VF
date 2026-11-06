# Análise educativa de perfil do investidor

Implementação em 06/11/2026. Não existe um questionário universal da API: instituições adotam perguntas, categorias e critérios próprios. Este formulário é original do app; não é reprodução de um teste de banco nem validação regulatória.

Referências para revisão documental:

- CVM, Resolução 30 (adequação de produtos, serviços e operações ao perfil do cliente): https://conteudo.cvm.gov.br/legislacao/resolucoes/resol030.html
- ANBIMA, Código de Distribuição de Produtos de Investimento e regras de suitability: https://www.anbima.com.br/pt_br/autorregular/codigos/distribuicao-de-produtos-de-investimento.htm

Limitação da pesquisa: a política de rede desta sessão permite destinos de desenvolvimento, mas não os sites da CVM/ANBIMA. Não foi possível conferir os textos oficiais vigentes nem formulários atuais de instituições. Os links são referências para consulta posterior, não fontes acessadas nesta sessão. Revisar a norma consolidada e os documentos atuais antes de qualquer uso regulatório.

## Cobertura

20 perguntas: objetivos e prazo (3), situação financeira (6), experiência e conhecimento (6), tolerância a risco (5). Situação financeira usa faixas e proporções para não exigir valores exatos. Conhecimento combina experiência declarada com três perguntas objetivas sobre marcação a mercado, diversificação e crédito. O usuário deve considerar o montante de seu principal objetivo; objetivos diferentes podem exigir análises diferentes.

## Método interno, versão 1

Respostas ordinais recebem 0–3 pontos. Nas perguntas objetivas, resposta correta recebe 3; erro ou desconhecimento recebe 0. São calculadas médias normalizadas de 0 a 100 para capacidade, conhecimento e tolerância (objetivo integra tolerância). Cada dimensão tem faixas: abaixo de 40 conservador; de 40 a menos de 70 moderado; a partir de 70 arrojado. O perfil final é o menor nível entre as dimensões.

Prazo de até um ano, necessidade de resgatar mais da metade do montante em 12 meses, ausência de reserva, dívidas atrasadas/caras, impacto de perdas em despesas/projetos essenciais e recusa a perdas limitam o perfil a conservador. Diferença de pelo menos 30 pontos entre capacidade e tolerância produz alerta. Esses limiares são escolhas prudenciais do app, sem validação psicométrica ou certificação por regulador. Não prometer precisão estatística.

O servidor valida todas as respostas e recalcula o resultado; classificação enviada pelo cliente não é aceita como resultado. Versão, respostas, índices, razões e data ficam nas preferências da conta, no armazenamento existente. Refazer substitui a avaliação anterior. Após 365 dias ou mudança de versão, a tela solicita revisão; esse período é uma escolha de UX, não declaração de prazo regulatório. Não há recomendação automática de produto ou alocação.

## Validação

`python -m unittest tests.test_suitability` cobre classificação, limites financeiros, conhecimento, respostas inválidas e recálculo no servidor com preservação de outras preferências. Gerar a interface com `python src/build_dashboard.py` após alterar perguntas, HTML, CSS ou JavaScript.
