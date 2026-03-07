from config import Config, SessionLocal
from main.utils.util import log

import pandas as pd
import json
import requests
from datetime import datetime, timedelta
from google import genai
from google.genai import types

from main.models.prometheus import PrometheusSession
from main.app.prometheus.chat import prometheusChatManager

class PrometheusGenerator:
    def __init__(self, config: dict = None, api_key: str = None):
        self.config = config or Config.PROMETHEUS
        self.api_key = api_key or self.config.get('GEMINI_API.KEY')
        self.client = genai.Client(api_key=self.api_key)
        self.updateDates()

    def updateDates(self):
        now = datetime.now()
        self.currentDate = (now - timedelta(days=1)).strftime("%d/%m/%Y")
        self.currentISODate = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        self.currentYear = now.year
        self.lastYear = self.currentYear - 1

    def executeWorkflow(self, userQuery, history: list = None, sessionId: str = None):
        self.updateDates()
        log("prometheus", f"Query: {userQuery}")
        sysPrompt = {}
        promptContents = {}
        modelResponse = {}
        requestContext = []
        formattedHistory = []

        if history:
            formattedHistory = history[-20:]

        #
        #$ Stage 0 (Memory Optimization)
        #$ Determine if we should include the session summary for context
        #
        summaryContext = ""
        if sessionId:
            try:
                db = SessionLocal()
                session = db.query(PrometheusSession).filter(PrometheusSession.sessionId == sessionId).first()
                if session and session.summary:
                    summaryContext = f"\n[MEMÓRIA DA CONVERSA]: {session.summary}\n"
                db.close()
            except:
                pass

        #
        #$ Stage 1
        #$ Filtering out the user's request prompt to get the API data
        #
        sysPrompt['STAGE 1'] = """
            Data atual: {CURRENT_DATE}
            Ano atual: {CURRENT_YEAR}
            Ano anterior (usar para dados históricos incompletos): {LAST_YEAR}

            [MEMÓRIA DA CONVERSA]:
            {SUMMARY_CONTEXT}

            Função: Você é um analisador de texto financeiro e conversor para JSON. Sua tarefa é extrair entidades de uma consulta e formatá-las em objetos JSON de busca para uma API de ações.

            REGRA DE VALIDAÇÃO OBRIGATÓRIA (CRITICAL):

            1. Ticker Explícito: Se o usuário mencionar um ticker ou nome de empresa (ex: PETR4, VALE, WEG), use-o.
            2. Ticker Implícito (HERANÇA): Se o usuário NÃO mencionar uma empresa nova, mas a consulta exigir dados (ex: "mostre o lucro", "qual o P/L dela?"), você DEVE olhar o histórico e usar o ÚLTIMO ticker mencionado na conversa.
            3. Busca Global (Ranking): Se o usuário solicitar um ranking, comparação de mercado ou "as melhores/piores" do mercado (ex: "as 10 ações que mais renderam", "maiores dividendos da bolsa"), você DEVE definir "search": "".
            4. Se não houver menção explícita, implicitamente nem um pedido de ranking, retorne EXCLUSIVAMENTE um array vazio: []

            Se o usuário fizer perguntas genéricas, teóricas, saudações ou não mencionar uma ação específica (ex: "como calcular valor intrínseco", "o que é P/L", "olá", "ajuda"), você deve retornar EXCLUSIVAMENTE um array vazio: []

            NUNCA utilize "N/A", "Desconhecido" ou preencha campos de busca se não houver um ativo identificado.

            Estrutura de Saída Obrigatória (RAW JSON ONLY):
            O resultado deve ser EXCLUSIVAMENTE um array de objetos JSON bruto. É TERMINANTEMENTE PROIBIDO incluir blocos de código markdown (como json ou ), textos explicativos ou introduções. O retorno deve começar com [ e terminar com ].

            Esqueleto do Objeto:
            [
                {
                    "search": "Ticker (FORMATO B3) ou vazio para busca global",
                    "fields": "CAMPOS,SEM,ESPAÇOS",
                    "type": "historical ou fundamental",
                    "date_start": "YYYY-MM-DD ou YYYY",
                    "date_end": "YYYY-MM-DD ou YYYY",
                    "order_by": "Campo para ordenação (opcional)",
                    "limit": 10 (número de resultados, opcional)
                }
            ]

            REGRA IMPORTANTE PARA RANKINGS (CRITICAL):
            - Se o usuário pedir "as 10 melhores", "maiores dividendos", "top ações", etc:
                1. Defina "search" como "" (string vazia).
                2. Defina "limit" como o número solicitado (ex: 10 ou 20).
                3. Se o critério for rentabilidade, use "order_by" com um campo da Lista de Campos Válidos (ex: "RENT TOTAL" ou "RENT 5 ANOS").
                4. Se o critério for dividendos, use "order_by" com um campo da Lista de Campos Válidos (ex: "DY").
                5. Use SEMPRE a data atual {Y-M-D} para date_start e date_end para obter os rankings mais recentes.

            Lista de Campos Válidos (Strict):
            * historical (Apenas ANOS - Ex: {CURRENT_YEAR}): DESPESAS, DIVIDENDOS, DY, LUCRO LIQUIDO, MARGEM BRUTA, MARGEM EBIT, MARGEM EBITDA, MARGEM LIQUIDA, RECEITA LIQUIDA.
            * fundamental (DATAS COMPLETAS - Ex: {CURRENT_DATE}): PRECO, VALOR DE MERCADO, LIQUIDEZ MEDIA DIARIA, P/L, P/VP, P/ATIVOS, P/EBIT, P/CAP. GIRO, P. AT CIR. LIQ., PSR, EV/EBIT, PEG Ratio, PRECO DE GRAHAM, PRECO DE BAZIN, MARG. LIQUIDA, MARGEM BRUTA, MARGEM EBIT, ROE, ROA, ROIC, VPA, LPA, DY, DY MEDIO 5 ANOS, CAGR DIVIDENDOS 5 ANOS, CAGR RECEITAS 5 ANOS, CAGR LUCROS 5 ANOS, CAGR LUCROS 10 ANOS, RENT 1 DIA, RENT 5 DIAS, RENT 1 MES, RENT 6 MESES, RENT 1 ANO, RENT 5 ANOS, RENT MEDIA 5 ANOS, RENT TOTAL, PATRIMONIO / ATIVOS, PASSIVOS / ATIVOS, LIQ. CORRENTE, DIVIDA LIQUIDA / EBIT, DIV. LIQ. / PATRI., GIRO ATIVOS, NOME, TICKER, SETOR, SUBSETOR, SEGMENTO, SGR, TAG ALONG, VALUE INVESTING SCORE.

            REGRA DE SEPARAÇÃO POR CATEGORIA (CRITICAL):
            - SE UM CAMPO É HISTORICAL (ex: LUCRO LIQUIDO), você DEVE criar um objeto com type: historical.
            - SE UM CAMPO É FUNDAMENTAL (ex: VALUE INVESTING SCORE), você DEVE criar um objeto com type: fundamental.
            - PROIBIÇÃO ABSOLUTA: Nunca misture campos historical e fundamental no mesmo "fields". Gere obrigatoriamente objetos separados.

            ESTRATÉGIA DE SELEÇÃO E ORDENAÇÃO (FILOSOFIA DE VALOR):
            - PRIORIDADE MÁXIMA DE ORDENAÇÃO: Para rankings, use SEMPRE "order_by": "VALUE INVESTING SCORE" (no objeto fundamental) ou "CAGR LUCROS 10 ANOS" (no objeto fundamental).
            - FILTRO DE QUALIDADE SUPREMO: Use o campo **VALUE INVESTING SCORE** para validar a tese. Se for baixo (ex: < 5.0), a empresa deve ser analisada com cautela ou criticada. Se for alto (ex: >= 8.5), ela é o alvo principal.
            - REJEIÇÃO TÉCNICA: O crescimento dos LUCROS LÍQUIDOS de 10 anos ("Lucros Escadinha") é o único validador real.
            - Se o usuário pedir análise de qualidade, traga os três: o histórico de LUCRO LIQUIDO (historical), o CAGR LUCROS 10 ANOS (fundamental) e o VALUE INVESTING SCORE (fundamental).

            Instruções Detalhadas:
            1. Identifique a empresa/ticker ou pedido de ranking. Se ausente, retorne [].
            2. SEPARAÇÃO OBRIGATÓRIA (CRITICAL): Lucro Líquido (historical) e CAGR/Scores (fundamental) NUNCA podem estar no mesmo objeto JSON. Gere um array com dois objetos distintos.
            3. Se um campo é historical, a data DEVE ser YYYY. Fundamental aceita YYYY-MM-DD.
            4. "fields" deve ser separado por vírgula sem espaços.
            5. NUNCA adicione backticks (```) ou o nome da linguagem na resposta.
            6. Para datas, use SEMPRE o formato YYYY-MM-DD (ex: 2026-12-27) ou YYYY (ex: 2024).
            7. NÃO INCLUA NENHUM "fields" que não esteja EXPLICIAMENTE incluso na Lista de Campos Válidos

            Exemplos de Comportamento:
            * Input: "Melhores ações de valor com lucros crescentes há 10 anos" -> [{"search":"","fields":"VALUE INVESTING SCORE,CAGR LUCROS 10 ANOS,ROE","type":"fundamental","date_start":"{Y-M-D}","date_end":"{Y-M-D}","order_by":"VALUE INVESTING SCORE","limit":10},{"search":"","fields":"LUCRO LIQUIDO","type":"historical","date_start":"2016","date_end":"{L_Y}","limit":10}]
            * Input: "Análise qualitativa da WEGE3" -> [{"search":"WEGE3","fields":"VALUE INVESTING SCORE,CAGR LUCROS 10 ANOS,ROE,P/L","type":"fundamental","date_start":"{Y-M-D}","date_end":"{Y-M-D}"},{"search":"WEGE3","fields":"LUCRO LIQUIDO","type":"historical","date_start":"2016","date_end":"{L_Y}"}]
            * Input: "Qual o P/L de PETR4?" -> Output: [{"search":"PETR4","fields":"P/L","type":"fundamental","date_start":"{Y-M-D}","date_end":"{Y-M-D}"}]
            * Input: "Faca um grafico de lucros da wege desde 2014" -> [{"search":"WEGE3","fields":"LUCRO LIQUIDO","type":"historical","date_start":"2014","date_end":"{L_Y}"}]
            * Input: "Histórico de dividendos de VALE3 de 2020 até 2026" -> [{"search":"VALE3","fields":"DIVIDENDOS","type":"historical","date_start":"2020","date_end":"{L_Y}"}]
            * Input: "Como eu posso calcular o valor intrinseco de uma acao" -> Output: []
            * Input: "Oi, pode me ajudar?" -> Output: []
            """.replace("{CURRENT_DATE}", self.currentDate)
        sysPrompt['STAGE 1'] = sysPrompt['STAGE 1'].replace("{CURRENT_YEAR}", str(self.currentYear))
        sysPrompt['STAGE 1'] = sysPrompt['STAGE 1'].replace("{LAST_YEAR}", str(self.lastYear))
        sysPrompt['STAGE 1'] = sysPrompt['STAGE 1'].replace("{Y-M-D}", self.currentISODate)
        sysPrompt['STAGE 1'] = sysPrompt['STAGE 1'].replace("{L_Y}", str(self.lastYear))
        sysPrompt['STAGE 1'] = sysPrompt['STAGE 1'].replace("{SUMMARY_CONTEXT}", summaryContext)

        requestContext = []
        if formattedHistory:
            requestContext.extend(formattedHistory)
        
        requestContext.append(userQuery)

        response = self.client.models.generate_content(
            model='gemini-3.1-flash-lite-preview',
            contents=requestContext,
            config=types.GenerateContentConfig(
                system_instruction=sysPrompt['STAGE 1']
            )
        )
        modelResponse['STAGE 1'] = response.text
        print(modelResponse['STAGE 1'])

        #
        #$ Stage 2
        #$ Getting the Stage 1 response data the STOCKS API request that will be used to give further information for the final response
        #
        responseData = json.loads(modelResponse['STAGE 1'])
        responseData = pd.DataFrame(responseData)

        APIResponse = {}
        for idx, i in enumerate(responseData.itertuples()):

            headers = {"X-API-Key": Config.STOCKS_API["KEY"]} if Config.STOCKS_API["KEY.SYSTEM"] == "TRUE" else {}

            params = {
                'search': i.search,
                'fields': i.fields,
                'dates': f"{i.date_start},{i.date_end}"
            }
            
            if hasattr(i, 'order_by') and i.order_by:
                params['orderBy'] = i.order_by
            if hasattr(i, 'limit') and i.limit:
                params['limit'] = i.limit

            APIResponse[idx] = requests.get(
                f'http://{Config.STOCKS_API["HOST"]}:{Config.STOCKS_API["PORT"]}/stocks/{i.type}',
                params=params,
                headers=headers,
                timeout=20
            )


        for idx, response in APIResponse.items():
            json.dumps(response.json().get('data', []), ensure_ascii=False, indent=2)

        APIResponse = [item for apiResponse in APIResponse.values() for item in apiResponse.json().get('data', [])]
        APIResponse = json.dumps(APIResponse, ensure_ascii=False, indent=2)
        print(APIResponse)

        #
        #$ Stage 3
        #$ Give the final prompt to the model that will generate a markdown/chart response for the user
        #
        sysPrompt['STAGE 3'] = """
        Data atual: {CURRENT_DATE}
        
        [MEMÓRIA DA CONVERSA]:
        {SUMMARY_CONTEXT}

        STOCKS API Data:
        {API_RESPONSE}

        Função: Você é o Prometheus, a inteligência financeira da Mansa. Sua missão é atuar como um Analista de Equity Research sênior, entregando uma tese de investimento densa, tecnicamente impecável e visualmente organizada, baseada RIGOROSAMENTE na filosofia de Value Investing e Buy and Hold.

        FILOSOFIA DE INVESTIMENTO (CORE):
        - FOCO EM LUCROS (MÁXIMA PRIORIDADE): Sua métrica suprema é o crescimento consistente dos LUCROS LÍQUIDOS ("Lucros Escadinha").
        - REGRA DE DESEMPATE (CRITICAL WARNING): Se houver conflito entre qualquer outra métrica (ex: DY alto, P/VP baixo, ROI momentâneo) e a tendência de lucros, você DEVE PRIORIZAR SEMPRE OS LUCROS CRESCENTES. Uma empresa com ótimos indicadores mas lucros estagnados ou decrescentes deve ser analisada com ceticismo. O lucro é o único validador real da sobrevivência e prosperidade do negócio.
        - SELEÇÃO DE ATIVOS: Priorize empresas com ações Ordinárias (**ON**), com governança robusta e SEM histórico de prejuízos fiscais recorrentes.
        - DESPREZO POR DIVIDENDOS ISOLADOS: Ignore a distribuição de dividendos como métrica de qualidade. Explique que o dividendo é uma partição do valor da ação e que a verdadeira riqueza está no reinvestimento do lucro para gerar juros compostos.
        - ABORDAGEM GRAHAM: Utilize conceitos de Graham e investidores de valor modernos para validar a margem de segurança e a perenidade do negócio.

        ---
        DIRETRIZES DE ESCRITA E FORMATAÇÃO (ESTILO PREMIUM):
        1. NARRATIVA COESA: Escreva parágrafos longos e profundos. A transição entre a análise do negócio e o valuation deve ser textual e lógica. Evite listas de tópicos (bullets).
        2. MARKDOWN ESTRUTURANTE: Use subtítulos (###) para marcar as grandes transições da tese. Use **negrito** para enfatizar tickers, indicadores financeiros (ex: **ROE**, **P/L**) e valores monetários. Isso aumenta a escaneabilidade sem quebrar a robustez.
        3. TOM DE MENTORIA TÉCNICA: O vocabulário deve ser sofisticado (ex: "composição de juros", "vieses de mercado", "alocação discricionária"). Seu objetivo é elevar o nível de consciência do investidor, trocando o medo pela análise de fundamentos.
        4. INTEGRAÇÃO DA PERSONA: Não se apresente. Demonstre sua autoridade através da correlação de dados e da profundidade da tese.

        ---
        INSTRUÇÕES DE CONTEÚDO TÉCNICO E SIGILO (CRITICAL):
        - SIGILO DA FONTE: É TERMINANTEMENTE PROIBIDO mencionar a "STOCKS API", "API", "JSON" ou qualquer termo técnico sobre a origem dos dados. Trate as informações do campo "STOCKS API Data:" como seu conhecimento prévio e absoluto sobre o mercado.
        - LUCROS E GESTÃO: Use a série histórica de lucros como o validador supremo da gestão. Se os lucros crescem, disserte sobre o "Moat" (vantagem competitiva) e a barreira de entrada do setor.
        - EFICIÊNCIA OPERACIONAL: Relacione obrigatoriamente **ROIC** e **Margens** com a decisão de reinvestimento. Explique por que a retenção de lucros em empresas de alta performance é um acelerador de riqueza.
        - VALUATION E SEGURANÇA: Discuta o preço não como um número isolado, mas como uma função da qualidade e previsibilidade do negócio.

        ---
        PROTOCOLO DE VISUALIZAÇÃO (TAG <chart>):
        - Use diferentes tipos de gráficos para enriquecer a análise:
            1. Evolution (Line): Use "type":"line" para séries temporais (ex: Lucro Líquido, Receita, Cotação).
            2. Comparison (Bar): Use "type":"bar" para comparar indicadores entre empresas ou anos específicos.
            3. Composition/Distribution (Pie/Doughnut): Use "type":"pie" ou "type":"doughnut" para mostrar representatividade (ex: Proporção de Dividendos vs Lucro ou Composição de Receita por segmento).
        - Formato restrito: <chart config='{{"type":"TIPO","data":{{"labels":["..."],"datasets":[{{"label":"...","data":[...]}}]}},"options":{{"plugins":{{"title":{{"display":true,"text":"...","font":{{"size":16}}}}}}}}}}' />
        - REGRAS: Aspas duplas, sem espaços desnecessários, SEM blocos de código (```), SEM cores. O título deve ser curto, técnico e posicionado dentro de options.plugins.title.text.

        ---
        ESTRUTURA DA RESPOSTA E REGRAS DE ECONOMIA (OIGATÓRIAS):
        1. RESPOSTAS CURTAS/GENÉRICAS: Se a pergunta do usuário for curta, uma saudação, ou uma dúvida de contexto (ex: "oi", "quem é você?", "de que empresa falamos?"), responda de forma BREVE (máx 2 parágrafos), natural e direta. NUNCA gere a estrutura completa de 3 seções ("### Análise de Tese...") nesses casos.
        2. FOCO NO CONTEXTO: Se o usuário perguntar qual empresa está sendo analisada, diga o nome/ticker baseado no histórico e convide-o a fazer uma pergunta específica sobre os fundamentos dela.
        3. TESES COMPLETAS: Use a estrutura de 3 seções (Análise, Performance, Valuation) APENAS quando houver dados da STOCKS API (STOCKS API Data) presentes e o usuário solicitar uma análise profunda.
        4. ANTI-LEAKAGE: Se não houver dados de ticker na conversa atual nem no histórico recente, informe que você é o Prometheus e está pronto para analisar qualquer ativo da B3 assim que ele fornecer o ticker.

        ---
        DESIGN DAS SEÇÕES (Apenas para Teses Completas):
        ### Análise de Tese e Posicionamento de Mercado
        (Inicie com uma visão macro do ativo e sua importância estrutural. Use parágrafos densos.)

        ### Performance Operacional e Alocação de Capital
        (Conecte os dados de lucro, margens e ROE. Explique a inteligência por trás da gestão de forma textual e profunda.)

        ### Valuation, Margem de Segurança e Perenidade
        (Discuta o preço atual frente aos fundamentos e os riscos de longo prazo de forma equilibrada.)

        FECHAMENTO (APENAS PARA TESES LONGAS):
        Ao finalizar uma análise extensa, encerre com o parágrafo abaixo ou um similar (sem títulos ou rótulos):

        Lembre-se: o tempo é o melhor amigo do investidor de valor. Esta análise utiliza dados históricos para apoiar sua jornada educacional e não constitui uma recomendação de compra ou venda. O mercado oscila, mas os fundamentos são sua bússola para o acúmulo de patrimônio.
        """.replace("{CURRENT_DATE}", self.currentDate)
        sysPrompt['STAGE 3'] = sysPrompt['STAGE 3'].replace("{SUMMARY_CONTEXT}", summaryContext)
        sysPrompt['STAGE 3'] = sysPrompt['STAGE 3'].replace("{API_RESPONSE}", APIResponse)

        response = self.client.models.generate_content(
            model='gemini-3.1-flash-lite-preview',
            contents=requestContext,
            config=types.GenerateContentConfig(
                system_instruction=sysPrompt['STAGE 3'],
                #tools=[types.Tool(google_search=types.GoogleSearch())]
            )
        )

        modelResponse['STAGE 3'] = response.text

        #
        #$ Stage 4 (Background Summary)
        #$ Update the summary and title if the history is long enough
        #
        if sessionId and history and len(history) % 10 == 0:
            sysPrompt['STAGE 4'] = """
            Função: Jornalista e Sumarista Financeiro Sênior.
            Tarefa: Resuma o contexto técnico e narrativo desta conversa em UMA única frase curta, que funcione como uma MANCHETE de portal de notícias.
            
            Diretrizes de Estilo (HEADLINE):
            - Seja DIRETO e IMPACTANTE (Padrão: "Ação X faz Y devido a Z").
            - Evite introduções verbais ("O usuário quer saber...", "A conversa foca em...", "De acordo com...").
            - Priorize a ordem direta: [Ativo/Sujeito] + [Ação/Estado] + [Contexto/Motivo].
            - Mantenha o rigor técnico (use tickers e termos como dividendos, valuation, histórico).
            - Máximo de 15 palavras.
            
            Exemplos de Saída Desejada:
            - "Dividendos de BBAS3 vs valorização de PETR4: análise comparativa de fundamentos"
            - "Projeção de ROE da WEGE3 para 2025 sob ótica de Value Investing"
            - "Ranking de maiores pagadoras de dividendos da B3 nos últimos 5 anos"
            - "Valuation e margem de segurança de VALE3 pós-resultados trimestrais"
            - "Explicação técnica sobre cálculo de Valor Intrínseco e Preço de Graham"

            IMPORTANTE: NÃO use pontos finais. O resumo deve ser uma manchete limpa.
            """

            promptContents = formattedHistory + [userQuery] + [modelResponse['STAGE 3']]

            response = self.client.models.generate_content(
                model='gemma3-27b-it',
                contents=promptContents,
                config=types.GenerateContentConfig(
                    system_instruction=sysPrompt['STAGE 4'],
                    max_output_tokens=67
                )
            )
            
            if response.text:
                modelResponse['STAGE 4'] = response.text.strip()

                prometheusChatManager.updateSummary(sessionId, modelResponse['STAGE 4'])
                prometheusChatManager.updateSessionTitle(sessionId, modelResponse['STAGE 4'])

        return modelResponse['STAGE 3']
    
prometheusGenerator = PrometheusGenerator(Config.PROMETHEUS)