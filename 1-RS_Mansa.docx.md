

| Cliente | Mansa S.A. |
| :---- | :---- |
| **Projeto** | Mansa — Plataforma de Investimentos Inteligente |
| **Data** | 12/05/2026 |
| **Versão** | 1.0 |

**Alterações:**

| Data | Versão | Autor | Descrição |
| :---- | :---- | :---- | :---- |
| 12/05/2026 | 1.0 | Heitor de Oliveira Rosa, David Rangel Gomes, Pedro Henrique CIolfi Ferreira, Pedro Luiz de Oliveira Carniello | Versão inicial dos requisitos de software. |

**Índice**

[1 Introdução](#bookmark=id.vkynefatxp8d)  
[2 Escopo](#bookmark=id.12kxda1eeb70)  
[3 Descrição do Projeto](#bookmark=id.i5ohwknz0b06)  
[4 Stakeholders](#bookmark=id.xu7xz7vvid0c)  
[5 Requisitos Funcionais](#bookmark=id.vk2wj6gs0d0s)  
[5.1 — Autenticação e Gerenciamento de Usuários](#bookmark=id.2h2uqxff33dh)  
[5.2 — Stocks API — Dados Financeiros](#bookmark=id.fudatkou7nap)  
[5.3 — Prometheus — Chatbot Financeiro com IA](#bookmark=id.es410zjxwwba)  
[5.4 — Scraper B3 — Coleta de Dados](#bookmark=id.rjqrzx630m7c)  
[5.5 — Thoth — Gestão de Carteiras e Metas](#bookmark=id.dw05bz5qmz5l)  
[5.6 — Ma'at — Algoritmo de Stock Picking](#bookmark=id.yx24chiycew0)  
[5.7 — Ogum — Algo Trading e Automação](#bookmark=id.k8k2mf96p1to)  
[6 Requisitos Não Funcionais](#bookmark=id.deep8hri5bki)  
[6.1 — Usabilidade](#bookmark=id.78vkihs4l5xw)  
[6.2 — Segurança](#bookmark=id.vea3mgmlyy1w)  
[6.3 — Performance](#bookmark=id.8tw8daqoor5w)  
[6.4 — Arquitetura](#bookmark=id.o81pa4t75jfb)  
[7 Observações Gerais](#bookmark=id.dofkg47br9wc)

# **1 Introdução**

Este documento tem como finalidade definir os requisitos do projeto **Mansa** para que seja possível definir prazos, recursos e garantir que todos os envolvidos entendam as necessidades da plataforma.

O Mansa é uma plataforma fintech inovadora criada para ajudar o investidor brasileiro da classe média a entrar com segurança no Mercado de Ações por meio de uma gestão de portfólio inteligente, algorítmica e impulsionada por Inteligência Artificial.

# **2 Escopo**

É considerado escopo deste projeto somente os requisitos listados nesse documento. Qualquer outra necessidade deverá ser considerada como uma nova solicitação (não escopo).

O MVP deve estar concluído até março de 2027 e o projeto finalizado em outubro de 2027\.

# **3 Descrição do Projeto**

Plataforma fintech baseada no ecossistema **MUSA (Mansa's Unsupervised Stocks Analyst)**, composta pelos seguintes subsistemas:

- **Prometheus**: Chatbot imersivo baseado em RAG (Retrieval-Augmented Generation) para suporte decisório, utilizando modelos Google Gemini e Gemma para análise fundamentalista de ativos.  
- **Ma'at**: Algoritmo de recomendação focado em Value Investing e Buy & Hold, capaz de identificar ativos subvalorizados com base em dados históricos e indicadores fundamentalistas.  
- **Thoth**: Sistema de gerenciamento de carteiras, histórico de investimentos, definição de metas financeiras e otimização de carteira com base em modelos customizados baseados no Black-Litterman e similares.  
- **Ogum**: Módulo de trading Quantamental para execução de tarefas agendadas, automação de Dollar-Cost Averaging (DCA) e geração de sinais de compra/venda.  
- **Scraper B3**: Coleta automatizada de dados financeiros de múltiplas fontes (StatusInvest, TradingView, Investidor10, Google News) com cálculo do Investing Score proprietário a partir de um modelo próprio chamado Xangô.  
- **Stocks API**: API de dados financeiros históricos e fundamentalistas do mercado brasileiro (B3), com sistema de chaves de API e cotas por usuário.

  # **4 Stakeholders**

| Nome | Empresa | Responsabilidade | Email |
| :---: | :---: | :---: | :---: |
| Heitor de Oliveira Rosa | Mansa S.A. | Gerente de Projeto | heitorolivrosa@gmail.com |
| Pedro Henrique Ciolfi Ferreira | Mansa S.A. | Desenvolvedor | pedroh.ciolfi@gmail.com |
| Pedro Luiz de Oliveira Carniello | Mansa S.A. | Desenvolvedor | pedroluiz.carniello@gmail.com |
| David Rangel Gomes | Mansa S.A. | Desenvolvedor | david.gomes@programmer.net |
| Classe Média Brasileira | — | Usuário Final / Investidor | — |

  #    **5 Requisitos Funcionais**

## **5.1 — Autenticação e Gerenciamento de Usuários**

Esta funcionalidade visa gerenciar o cadastro, autenticação e permissões dos usuários da plataforma.

Para isto deverá ser desenvolvido um sistema com:

- Registro de usuários com username, email e senha (bcrypt);  
- Autenticação via Google SSO (OAuth);  
- Login com sessões JWT (HS256) armazenadas em cookie HttpOnly;  
- Gerenciamento de sessões com fingerprint de dispositivo (tipo, browser, SO);  
- Hierarquia de permissões: USER, PREMIUM, DEVELOPER\_STARTER, DEVELOPER\_ENTERPRISE, ADMIN;  
- Atribuição de cargos com base na integração de business e integração de pagamentos via Stripe;  
- Visualização e revogação de sessões ativas pelo usuário;  
- Limpeza automática de sessões inativas a cada 12 horas;  
- Rate limiting de 5 requisições/minuto em login e registro.

## **5.2 — Stocks API — Dados Financeiros**

Esta funcionalidade visa disponibilizar dados financeiros do mercado brasileiro (B3) para desenvolvedores e sistemas integrados.

Para isto deverá ser desenvolvida uma API com:

- Sistema de chaves de API (header `X-API-Key`) com geração via endpoint;  
- Cotas de requisição por chave (limite configurável, padrão 5000 requisições / 30 dias);  
- Consulta de **dados históricos** por ticker: dividendos, receita, lucro, margens, dividend yield, preços organizados por ano;  
- Consulta de **dados fundamentalistas** atuais: P/L, P/VP, EV/EBIT, ROE, ROIC, DY, Investing Score;  
- Cache em memória (DataFrame Pandas) atualizado a cada 12 horas;  
- Cache de resultados de consulta com TTL de 5 minutos;  
- Documentação interativa dos endpoints.

## **5.3 — Prometheus — Chatbot Financeiro com IA**

Esta funcionalidade visa prover um assistente financeiro inteligente capaz de analisar ativos da B3 e auxiliar na tomada de decisão de investimentos.

Para isto deverá ser desenvolvido um pipeline de IA em 4 estágios:

1. **Estágio 1** (Gemini Flash Lite): Interpretação da pergunta do usuário e extração de parâmetros de busca estruturados (JSON);  
2. **Estágio 2**: Consulta à Stocks API com os parâmetros extraídos para obter dados reais do ativo;  
3. **Estágio 3** (Gemma 4 31B IT): Geração da análise financeira com formatação Markdown e gráficos Chart.js;  
4. **Estágio 4** (Gemini Flash Lite, a cada 10 mensagens): Atualização automática do resumo/título da sessão.

Funcionalidades adicionais:

- Gerenciamento de sessões de chat (criar, listar, renomear, excluir);  
- Histórico completo por sessão;  
- Rate limiting de 5 requisições/minuto;  
- Requer permissão `USE_PROMETHEUS` (usuário PREMIUM ou superior).

## **5.4 — Scraper B3 — Coleta de Dados**

Esta funcionalidade visa coletar automaticamente dados financeiros de todas as empresas listadas na B3 a partir de múltiplas fontes públicas.

Para isto deverá ser desenvolvido um scraper agendado com:

- Coleta de 50+ indicadores financeiros por ticker: preço, múltiplos, margens, endividamento, liquidez;  
- Coleta de rentabilidade histórica (1 dia a 5 anos);  
- Coleta de histórico de dividendos e dividend yields;  
- Coleta de receita e lucro históricos;  
- Coleta de preços históricos (10 anos);  
- Coleta de notícias via RSS do Google News;  
- Cálculo do **Investing Score** (0-100): pontuação proprietária baseada em crescimento do lucro, consistência, volatilidade, drawdown e liquidez;  
- Fontes: StatusInvest, TradingView, Investidor10, Google News, Oceans14;  
- Agendamento flexível por variável de ambiente;  
- Exportação para banco MySQL (tabela `b3_stocks`) com criação automática de colunas;  
- Suporte a fallback e retry com tenacity.

## **5.5 — Thoth — Gestão de Carteiras e Metas**

Esta funcionalidade visa permitir que o usuário gerencie suas carteiras de investimento e defina metas financeiras de longo prazo.

Para isto deverá ser desenvolvido um módulo com:

- Criação e gerenciamento de múltiplas carteiras;  
- Registro de ativos comprados (ticker, quantidade, preço de compra, data);  
- Acompanhamento de rentabilidade por ativo e por carteira;  
- Definição de metas financeiras (valor alvo, prazo, aporte mensal);  
- Projeção de crescimento com base em retorno histórico;  
- Alertas de proximidade de metas;  
- Requer permissão `USE_THOTH` (usuário USER ou superior).

## **5.6 — Ma'at — Algoritmo de Stock Picking**

Esta funcionalidade visa recomendar ativos subvalorizados com base em fundamentos e estratégias de Value Investing.

Para isto deverá ser desenvolvido um algoritmo com:

- Análise de múltiplos indicadores: P/L, P/VP, EV/EBIT, ROE, ROIC, Dividend Yield;  
- Identificação de ativos com desconto em relação ao valor intrínseco estimado;  
- Ranqueamento de ativos por pontuação de valor (Investing Score);  
- Agrupamento com base na matriz correlacional;  
- Sugestão de preço-alvo, margem de segurança e pesos;  
- Modelos de otimização e criação de portfólios baseado nos modelos matemáticos Black-Litterman, adaptados para se adequar aos algoritmos de scoring de ações e requerimentos específicos das estratégias fundamentalistas da Mansa  
- Requer permissão `USE_MAAT` (usuário USER ou superior).

## **5.7 — Ogum — Algo Trading e Automação**

Esta funcionalidade visa automatizar estratégias de investimento para reduzir o viés emocional e maximizar a estratégia de Buy & Hold.

Para isto deverá ser desenvolvido um módulo com:

- Automação de Dollar-Cost Averaging (DCA) com aportes recorrentes;  
- Otimização de portfólio baseada em risco-retorno;  
- Geração de sinais de compra/venda com base em indicadores técnicos e fundamentalistas;  
- Execução de estratégias agendadas;  
- Histórico de ordens executadas e sinais gerados;  
- Requer permissão `USE_OGUM` (usuário PREMIUM ou superior).


  # **6 Requisitos Não Funcionais**

## **6.1 — Usabilidade**

### **6.1.1 — Interface do Usuário**

A aplicação deverá ser desenvolvida para a WEB utilizando tecnologias modernas que garantam bons níveis de aparência e usabilidade:

- **Front-end Web**: NextJS, React, Tailwind CSS;  
- **Front-end Mobile**: React Native, Tailwind;  
- **Desktop**: Electron, React, Tailwind;  
- Monorepo usando Turborepo e Bun  
- Interface responsiva e adaptável a diferentes dispositivos;  
- Design intuitivo com foco na educação financeira do usuário durante todo o processo.

## **6.2 — Segurança**

- Senhas armazenadas com bcrypt;  
- Tokens JWT (HS256) armazenados em cookies HttpOnly;  
- Rate limiting por endpoint (slowapi);  
- Chaves de API com cotas individuais;  
- Proteção contra ataques CSRF e XSS via CORS configurado;  
- Sessões com expiração de 30 dias e revogação manual;  
- Fingerprint de dispositivo para detecção de sessões suspeitas.

## **6.3 — Performance**

- Cache em memória (DataFrame Pandas) para dados financeiros com refresh a cada 12 horas;  
- Cache de consultas com TTL de 5 minutos;  
- Otimização de consultas MySQL via índices;  
- Múltiplos workers Uvicorn para atender requisições concorrentes;  
- Coleta de dados assíncrona e paralela no scraper.

## **6.4 — Arquitetura**

- **Back-end**: Python 3.14, FastAPI, Uvicorn;  
- **Banco de Dados**: MySQL 8.0 (dual DB: `user_db` \+ `stocks_db`);  
- **ORM**: SQLAlchemy com Alembic para migrações;  
- **Containerização**: Docker com Docker Compose;  
- **Filas**: Celery (planejado) para tarefas assíncronas;  
- **Machine Learning**: PyTorch, XGBoost, Scikit-learn, Scikit-folio;  
- **Vector Store**: Pinecone (planejado) para RAG;  
- **Gateway de Pagamentos:** Stripe  
- **Deployment**: Microsserviços rodando em portas separadas gerenciados por Service Manager.


  # **7 Observações Gerais**

- Os módulos Thoth, Ma'at e Ogum estão documentados como requisitos funcionais baseados no trabalho acadêmico e no Termo de Abertura do Projeto. No MVP atual, apenas as permissões correspondentes (`USE_THOTH`, `USE_MAAT`, `USE_OGUM`) estão implementadas no sistema de papéis; as funcionalidades completas serão desenvolvidas em versões futuras.  
- O sistema de filas Celery e o vector store Pinecone estão planejados para implementação futura.  
- A plataforma é focada exclusivamente no mercado de ações brasileiro (B3).  
- O projeto adota metodologia de camadas: Controller → Service → Model.

