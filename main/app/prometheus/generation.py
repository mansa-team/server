from config import Config
from main.utils.util import log

import pandas as pd
import json
import requests
from datetime import datetime, timedelta
from google import genai
from google.genai import types

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

    def executeWorkflow(self, userQuery, history: list = None):
        self.updateDates()
        log("prometheus", f"Workflow started for: {userQuery}")
        sysPrompt = {}
        modelResponse = {}
        requestContext = []

        formattedHistory = []
        if history:
            formattedHistory = history[-10:] # Last 10 messages for memory

        #
        #$ Stage 1
        #$ Filtering out the user's request prompt to get the API data
        #
        sysPrompt['STAGE 1'] = """
            Data atual: {CURRENT_DATE}
            Ano atual: {CURRENT_YEAR}
            Ano anterior (usar para dados históricos incompletos): {LAST_YEAR}

            Função: Você é um analisador de texto financeiro e conversor para JSON. Sua tarefa é extrair entidades de uma consulta e formatá-las em objetos JSON de busca para uma API de ações.

            REGRA DE VALIDAÇÃO OBRIGATÓRIA (CRITICAL):

            1. Ticker Explícito: Se o usuário mencionar um ticker ou nome de empresa (ex: PETR4, VALE, WEG), use-o.
            2. Ticker Implícito (HERANÇA): Se o usuário NÃO mencionar uma empresa nova, mas a consulta exigir dados (ex: "mostre o lucro", "qual o P/L dela?"), você DEVE olhar o histórico e usar o ÚLTIMO ticker mencionado na conversa.
            3. Se não houver menção explícita E nada no histórico sobre uma empresa, retorne EXCLUSIVAMENTE um array vazio: []

            Se o usuário fizer perguntas genéricas, teóricas, saudações ou não mencionar uma ação específica (ex: "como calcular valor intrínseco", "o que é P/L", "olá", "ajuda"), você deve retornar EXCLUSIVAMENTE um array vazio: []

            NUNCA utilize "N/A", "Desconhecido" ou preencha campos de busca se não houver um ativo identificado.

            Estrutura de Saída Obrigatória (RAW JSON ONLY):
            O resultado deve ser EXCLUSIVAMENTE um array de objetos JSON bruto. É TERMINANTEMENTE PROIBIDO incluir blocos de código markdown (como json ou ), textos explicativos ou introduções. O retorno deve começar com [ e terminar com ].

            Esqueleto do Objeto:
            [
                {
                    "search": "Ticker (formato B3)",
                    "fields": "CAMPOS,SEM,ESPAÇOS",
                    "type": "historical ou fundamental",
                    "date_start": "YYYY-MM-DD ou YYYY",
                    "date_end": "YYYY-MM-DD ou YYYY"
                }
            ]

            REGRA IMPORTANTE PARA DADOS HISTÓRICOS:
            - Se o usuário pedir dados do ano atual ({CURRENT_YEAR}), SEMPRE substitua por {LAST_YEAR} porque os dados de {CURRENT_YEAR} ainda não estão completos.
            - Exemplo: Se o usuário pedir "desde 2025", use "desde 2024" em vez disso.
            - Se o usuário pedir um intervalo que inclui {CURRENT_YEAR}, altere o ano final para {LAST_YEAR}.
            - Exemplos:
                * Input: "gráfico de lucros de 2014 até 2025" → use "2014 até 2024"
                * Input: "lucros de 2025" → use "lucros de 2024"
                * Input: "histórico de dividendos desde 2020" → use "2020 até 2024"

            Lista de Campos Válidos (Strict):
            * historical (Apenas Anos - YYYY): DESPESAS, DIVIDENDOS, DY, LUCRO LIQUIDO, MARGEM BRUTA, MARGEM EBIT, MARGEM EBITDA, MARGEM LIQUIDA, RECEITA LIQUIDA.
            * fundamental (Anos e Datas - YYYY-MM-DD): PRECO, VALOR DE MERCADO, LIQUIDEZ MEDIA DIARIA, P/L, P/VP, P/ATIVOS, P/EBIT, P/CAP. GIRO, P. AT CIR. LIQ., PSR, EV/EBIT, PEG Ratio, PRECO DE GRAHAM, PRECO DE BAZIN, MARG. LIQUIDA, MARGEM BRUTA, MARGEM EBIT, ROE, ROA, ROIC, VPA, LPA, DY, DY MEDIO 5 ANOS, CAGR DIVIDENDOS 5 ANOS, CAGR RECEITAS 5 ANOS, CAGR LUCROS 5 ANOS, RENT 1 DIA, RENT 5 DIAS, RENT 1 MES, RENT 6 MESES, RENT 1 ANO, RENT 5 ANOS, RENT MEDIA 5 ANOS, RENT TOTAL, PATRIMONIO / ATIVOS, PASSIVOS / ATIVOS, LIQ. CORRENTE, DIVIDA LIQUIDA / EBIT, DIV. LIQ. / PATRI., GIRO ATIVOS, NOME, TICKER, SETOR, SUBSETOR, SEGMENTO, SGR, TAG ALONG.

            Instruções Detalhadas:
            1. Identifique a empresa/ticker. Se ausente, retorne [].
            2. Se a busca envolve campos historical e fundamental, crie DOIS objetos JSON distintos.
            3. Se um campo é historical, a data DEVE ser YYYY. Fundamental aceita YYYY-MM-DD.
            4. "fields" deve ser separado por vírgula sem espaços.
            5. NUNCA adicione backticks (```) ou o nome da linguagem na resposta.
            6. Para datas, use SEMPRE o formato YYYY-MM-DD (ex: 2025-12-27) ou YYYY (ex: 2024).
            7. SEMPRE substitua {CURRENT_YEAR} por {LAST_YEAR} em dados históricos.
            8. NÃO INCLUA NENHUM "fields" que não esteja EXPLICIAMENTE incluso na Lista de Campos Válidos

            Exemplos de Comportamento:
            * Input: "Qual foi o preço das ações da WEG ontem?" -> [{"search":"WEGE3","fields":"PRECO","type":"fundamental","date_start":"{Y-M-D}","date_end":"{Y-M-D}"}]
            * Input: "Qual o P/L de PETR4?" -> Output: [{"search":"PETR4","fields":"P/L","type":"fundamental","date_start":"{Y-M-D}","date_end":"{Y-M-D}"}]
            * Input: "Faca um grafico de lucros da wege desde 2014" -> [{"search":"WEGE3","fields":"LUCRO LIQUIDO","type":"historical","date_start":"2014","date_end":"{L_Y}"}]
            * Input: "Histórico de dividendos de VALE3 de 2020 até 2025" -> [{"search":"VALE3","fields":"DIVIDENDOS","type":"historical","date_start":"2020","date_end":"{L_Y}"}]
            * Input: "Como eu posso calcular o valor intrinseco de uma acao" -> Output: []
            * Input: "Oi, pode me ajudar?" -> Output: []
            """.replace("{CURRENT_DATE}", self.currentDate).replace("{CURRENT_YEAR}", str(self.currentYear)).replace("{LAST_YEAR}", str(self.lastYear)).replace("{Y-M-D}", self.currentISODate).replace("{L_Y}", str(self.lastYear))
        # Prepare history for Stage 1 if available
        requestContext = []
        if formattedHistory:
            requestContext.extend(formattedHistory)
        
        requestContext.append(userQuery)

        response = self.client.models.generate_content(
            model='gemini-3.1-flash-lite-preview',
            contents=requestContext,
            config=types.GenerateContentConfig(
                system_instruction=sysPrompt['STAGE 1'],
            )
        )
        modelResponse['STAGE 1'] = response.text
        #print(modelResponse['STAGE 1'])

        #
        #$ Stage 2
        #$ Getting the Stage 1 response data the STOCKS API request that will be used to give further information for the final response
        #
        responseData = """
        [{"search": "WEGE3", "fields": "LUCRO LIQUIDO", "type": "historical", "date_start": "2014", "date_end": "2024"}, {"search": "PETR3", "fields": "LUCRO LIQUIDO", "type": "historical", "date_start": "2014", "date_end": "2024"}]
        """
        #responseData = json.loads(responseData)
        responseData = json.loads(modelResponse['STAGE 1'])
        responseData = pd.DataFrame(responseData)

        APIResponse = {}
        for idx, i in enumerate(responseData.itertuples()):

            headers = {"X-API-Key": Config.STOCKS_API["KEY"]} if Config.STOCKS_API["KEY.SYSTEM"] == "TRUE" else {}
            
            APIResponse[idx] = requests.get(
                f'http://{Config.STOCKS_API["HOST"]}:{Config.STOCKS_API["PORT"]}/stocks/{i.type}',
                params={
                    'search': i.search,
                    'fields': i.fields,
                    'dates': f"{i.date_start},{i.date_end}"
                },
                headers=headers,
                timeout=20
            )


        for idx, response in APIResponse.items():
            json.dumps(response.json().get('data', []), ensure_ascii=False, indent=2)

        APIResponse = [item for apiResponse in APIResponse.values() for item in apiResponse.json().get('data', [])]
        APIResponse = json.dumps(APIResponse, ensure_ascii=False, indent=2)
        #print(APIResponse)

        #
        #$ Stage 3
        #$ Give the final prompt to the model that will generate a markdown/chart response for the user
        #
        sysPrompt['STAGE 3'] = """
        Data atual: {CURRENT_DATE}
        STOCKS API Data:
        {API_RESPONSE}

        Função: Você é o Prometheus, a inteligência financeira da Mansa. Sua missão é atuar como um Analista de Equity Research sênior, entregando uma tese de investimento densa, tecnicamente impecável e visualmente organizada, unindo a filosofia de Value Investing à estratégia de Buy and Hold.

        ---
        DIRETRIZES DE ESCRITA E FORMATAÇÃO (ESTILO PREMIUM):
        1. NARRATIVA COESA: Escreva parágrafos longos e profundos. A transição entre a análise do negócio e o valuation deve ser textual e lógica. Evite listas de tópicos (bullets).
        2. MARKDOWN ESTRUTURANTE: Use subtítulos (###) para marcar as grandes transições da tese. Use **negrito** para enfatizar tickers, indicadores financeiros (ex: **ROE**, **P/L**) e valores monetários. Isso aumenta a escaneabilidade sem quebrar a robustez.
        3. TOM DE MENTORIA TÉCNICA: O vocabulário deve ser sofisticado (ex: "composição de juros", "vieses de mercado", "alocação discricionária"). Seu objetivo é elevar o nível de consciência do investidor, trocando o medo pela análise de fundamentos.
        4. INTEGRAÇÃO DA PERSONA: Não se apresente. Demonstre sua autoridade através da correlação de dados e da profundidade da tese.

        ---
        INSTRUÇÕES DE CONTEÚDO TÉCNICO:
        - LUCROS E GESTÃO: Use a série histórica de lucros como o validador supremo da gestão. Se os lucros crescem, disserte sobre o "Moat" (vantagem competitiva) e a barreira de entrada do setor.
        - EFICIÊNCIA OPERACIONAL: Relacione obrigatoriamente **ROIC** e **Margens** com a decisão de reinvestimento. Explique por que a retenção de lucros em empresas de alta performance é um acelerador de riqueza.
        - VALUATION E SEGURANÇA: Discuta o preço não como um número isolado, mas como uma função da qualidade e previsibilidade do negócio.

        ---
        PROTOCOLO DE VISUALIZAÇÃO (TAG <chart>):
        - Gere o gráfico para ilustrar a evolução dos fundamentos (ex: Lucro Líquido ou Receita).
        - Formato restrito: <chart config='{{"type":"line","data":{{"labels":["..."],"datasets":[{{"label":"...","data":[...]}}]}}}}' />
        - REGRAS: Aspas duplas, sem espaços desnecessários, SEM blocos de código (```) e SEM especificação de cores.

        ---
        ESTRUTURA DA RESPOSTA E REGRAS DE ECONOMIA (OIGATÓRIAS):
        1. RESPOSTAS CURTAS/GENÉRICAS: Se a pergunta do usuário for curta, uma saudação, ou uma dúvida de contexto (ex: "oi", "quem é você?", "de que empresa falamos?"), responda de forma BREVE (máx 2 parágrafos), natural e direta. NUNCA gere a estrutura completa de 3 seções ("### Análise de Tese...") nesses casos.
        2. FOCO NO CONTEXTO: Se o usuário perguntar qual empresa está sendo analisada, diga o nome/ticker baseado no histórico e convide-o a fazer uma pergunta específica sobre os fundamentos dela.
        3. TESES COMPLETAS: Use a estrutura de 3 seções (Análise, Performance, Valuation) APENAS quando houver dados da STOCKS API ({API_RESPONSE}) presentes e o usuário solicitar uma análise profunda.
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
        sysPrompt['STAGE 3'] = sysPrompt['STAGE 3'].replace("{API_RESPONSE}", APIResponse)

        promptContents = formattedHistory + [userQuery]

        response = self.client.models.generate_content(
            model='gemini-3.1-flash-lite-preview',
            contents=promptContents,
            config=types.GenerateContentConfig(
                system_instruction=sysPrompt['STAGE 3'],
                #tools=[types.Tool(google_search=types.GoogleSearch())]
            )
        )
        modelResponse['STAGE 3'] = response.text
        #print(modelResponse['STAGE 3'])

        return modelResponse['STAGE 3']
    
prometheusGenerator = PrometheusGenerator(Config.PROMETHEUS)