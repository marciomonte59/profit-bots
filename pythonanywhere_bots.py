"""
pythonanywhere_bots.py - Sistema Profit Trading Bots
Hospedado no PythonAnywhere (marciomonte)

Bots:
  @ProfitAnalise_bot    → /webhook_analise   (GPT-4-omni - leitura + sinal final)
  @ProfitSinal_bot      → /webhook_sinal     (sinal limpo para copiar)
  @ProfitEstrategia_bot → /webhook_estrategia (gerencia estratégias)
  @ProfitSentiBot       → /webhook_sentimento (sentimento do mercado)
"""

import os, json, logging, requests, threading, re
from datetime import datetime
from flask import Flask, request, jsonify

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ── Tokens ─────────────────────────────────────────────────────────────────────
TOKEN_ANALISE    = "os.environ.get("TOKEN_ANALISE","")"
TOKEN_SINAL      = "os.environ.get("TOKEN_SINAL","")"
TOKEN_ESTRATEGIA = "os.environ.get("TOKEN_ESTRATEGIA","")"
TOKEN_SENTI      = "os.environ.get("TOKEN_SENTI","")"

# ── API Keys ───────────────────────────────────────────────────────────────────
OPENAI_KEY       = os.environ.get("OPENAI_KEY", "os.environ.get("OPENAI_KEY","")")
TWELVE_DATA_KEY  = "os.environ.get("TWELVE_KEY","")"
BRAPI_TOKEN      = os.environ.get("BRAPI_TOKEN", "os.environ.get("BRAPI_TOKEN","")")
FINNHUB_KEY      = "os.environ.get("FINNHUB_KEY","")"
FRED_KEY         = "os.environ.get("FRED_KEY","")"
GROQ_KEY         = "os.environ.get("GROQ_KEY","")"   # Groq - LLaMA 3.3 70B (gratuito, ultra-rápido)
OPENROUTER_KEY   = "os.environ.get("OPENROUTER_KEY","")"  # OpenRouter - +400 IAs (gratuito)
GEMINI_KEY       = os.environ.get("GEMINI_KEY", os.environ.get("GEMINI_KEY",""))

# ─── Chaves por função ────────────────────────────────────────────────────────
# Bot Mãe (Analise) - Gemini Vision p/ imagens + rotação automática
GEMINI_KEYS = [
    os.environ.get("GEMINI_KEY",""),   # AI Studio principal
    os.environ.get("GEMINI_KEY",""),   # Google Cloud Mestra
]
_gemini_key_idx = 0

# Google Custom Search - pesquisa de notícias/mercado
GOOGLE_SEARCH_KEY = os.environ.get("GEMINI_KEY","")  # Google Search Trading  # Google Search Trading
GOOGLE_CLOUD_KEY  = os.environ.get("GEMINI_KEY","")  # Google Cloud Mestra (backup)
GOOGLE_SEARCH_CX  = "37d00a591d34f45d4"  # ProfitBots Trading Finance  # Search Engine ID

def get_gemini_key():
    global _gemini_key_idx
    return GEMINI_KEYS[_gemini_key_idx % len(GEMINI_KEYS)]

def rotate_gemini_key():
    global _gemini_key_idx
    _gemini_key_idx += 1
    logger.warning(f"Gemini: chave {_gemini_key_idx % len(GEMINI_KEYS) + 1}/{len(GEMINI_KEYS)}")

# ─── Comunicação entre bots (Bot Mãe chama os filhos) ────────────────────────
def chamar_bot(token_destino, chat_id, mensagem):
    """Bot Mae envia mensagem para outro bot via Telegram."""
    try:
        requests.post(
            f"https://api.telegram.org/bot{token_destino}/sendMessage",
            json={"chat_id": chat_id, "text": mensagem, "parse_mode": "Markdown"},
            timeout=10
        )
    except Exception as e:
        logger.error(f"chamar_bot: {e}")

def google_custom_search(query, num=5):
    """Busca noticias: RSS (sem chave) + Finnhub + Google Custom Search como fallback."""
    import xml.etree.ElementTree as ET
    resultados = []
    ticker = query.split()[0].upper()

    # 1. RSS InfoMoney especifico para o ticker
    try:
        rss_urls = [
            f"https://www.infomoney.com.br/?s={ticker}&feed=rss",
            "https://www.infomoney.com.br/feed/",
            "https://moneytimes.com.br/feed/",
            "https://br.investing.com/rss/news.rss",
        ]
        for url in rss_urls:
            req = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
            root = ET.fromstring(req.content)
            for item in root.findall(".//item")[:5]:
                t = item.find("title")
                if t is not None and t.text:
                    titulo = t.text.strip()
                    if ticker in titulo.upper() or len(resultados) < 2:
                        resultados.append(titulo)
            if len(resultados) >= num:
                break
    except Exception as e:
        logger.error(f"RSS: {e}")

    # 2. Finnhub noticias gerais de mercado
    if len(resultados) < num:
        try:
            r = requests.get(
                "https://finnhub.io/api/v1/news",
                params={"category": "general", "token": FINNHUB_KEY},
                timeout=5
            )
            for n in r.json()[:3]:
                h = n.get("headline", "")
                if h:
                    resultados.append(h[:80])
        except Exception as e:
            logger.error(f"Finnhub news: {e}")

    # 3. Google Custom Search como fallback (quando propagar)
    if not resultados:
        for key in [GOOGLE_SEARCH_KEY, GOOGLE_CLOUD_KEY]:
            try:
                params = {"key": key, "cx": GOOGLE_SEARCH_CX, "q": query, "num": num}
                r = requests.get("https://www.googleapis.com/customsearch/v1", params=params, timeout=10)
                items = r.json().get("items", [])
                if items:
                    return [it.get("title", "") for it in items if it.get("title")]
            except Exception as e:
                logger.error(f"Custom Search: {e}")

    return resultados[:num]

# ─── Rotação de chaves Gemini (alterna quando quota estourar) ─────────────────
GEMINI_KEYS = [
    os.environ.get("GEMINI_KEY",""),   # AI Studio principal
    os.environ.get("GEMINI_KEY",""),   # Google Cloud Mestra
]
_gemini_key_idx = 0

def get_gemini_key():
    """Retorna chave Gemini ativa e rotaciona se necessario."""
    global _gemini_key_idx
    return GEMINI_KEYS[_gemini_key_idx % len(GEMINI_KEYS)]

def rotate_gemini_key():
    """Passa para proxima chave Gemini."""
    global _gemini_key_idx
    _gemini_key_idx += 1
    logger.warning(f"Gemini: rotacionando para chave {_gemini_key_idx % len(GEMINI_KEYS) + 1}/{len(GEMINI_KEYS)}")

# ── Chat ID ────────────────────────────────────────────────────────────────────
CHAT_ID_MARCIO = "8255093111"

# Arquivos de persistencia
HISTORICO_FILE = "/home/marciomonte/historico_operacoes.json"
MEMORIA_FILE   = "/home/marciomonte/memoria_conversas.json"

# Estrategias (arquivo local)
ESTRATEGIAS_FILE = os.path.join(os.path.dirname(__file__), "estrategias.json")

def calcular_indicadores_yahoo(ticker, interval="5m"):
    """Calcula EMA9, MA20, RSI14 via Yahoo Finance - sem gastar credito de API."""
    try:
        mapa = {
            "IBOV": "%5EBVSP", "BVSP": "%5EBVSP",
            "WIN":  "WIN1%21", "WDO":  "WDO1%21",
            "DXY":  "DX-Y.NYB", "SP500": "%5EGSPC",
        }
        symbol = mapa.get(ticker.upper(), ticker + ".SA")
        url = f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}"
        r = requests.get(url, params={"interval": interval, "range": "1d"},
                        headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
        result = r.json().get("chart", {}).get("result", [{}])[0]
        meta   = result.get("meta", {})
        closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
        closes = [c for c in closes if c is not None]
        if len(closes) < 5:
            return {}

        def ema(prices, n):
            k = 2/(n+1)
            e = prices[0]
            for p in prices[1:]: e = p*k + e*(1-k)
            return round(e, 2)

        def ma(prices, n):
            p = prices[-n:]
            return round(sum(p)/len(p), 2) if p else None

        def rsi(prices, n=14):
            p = prices[-(n+1):]
            if len(p) < 2: return None
            gains  = [max(p[i]-p[i-1], 0) for i in range(1, len(p))]
            losses = [max(p[i-1]-p[i], 0) for i in range(1, len(p))]
            ag = sum(gains)/len(gains) if gains else 0
            al = sum(losses)/len(losses) if losses else 0
            if al == 0: return 100
            return round(100 - (100/(1+ag/al)), 1)

        res = {
            "preco": meta.get("regularMarketPrice", closes[-1]),
            "ema9":  ema(closes, 9)  if len(closes) >= 9  else None,
            "ma20":  ma(closes, 20)  if len(closes) >= 20 else None,
            "ma200": ma(closes, 200) if len(closes) >= 200 else None,
            "rsi14": rsi(closes)     if len(closes) >= 15 else None,
        }

        # Sinal automatico das medias
        p = res["preco"]
        if p and res.get("ema9") and res.get("ma20"):
            if p > res["ma20"] and p > res["ema9"]:
                res["tendencia_medias"] = "ALTA (preco acima de EMA9 e MA20)"
            elif p < res["ma20"] and p < res["ema9"]:
                res["tendencia_medias"] = "BAIXA (preco abaixo de EMA9 e MA20)"
            else:
                res["tendencia_medias"] = "LATERAL (preco entre as medias)"

        # Nivel RSI
        if res.get("rsi14"):
            rsi_v = res["rsi14"]
            if rsi_v > 70: res["rsi_nivel"] = "SOBRECOMPRADO"
            elif rsi_v < 30: res["rsi_nivel"] = "SOBREVENDIDO"
            else: res["rsi_nivel"] = "neutro"

        return res
    except Exception as e:
        logger.error(f"calcular_indicadores_yahoo({ticker}): {e}")
        return {}


# ── Módulo de Cálculos Matemáticos ────────────────────────────────────────────

def calcular_fibonacci(preco_min, preco_max):
    """Calcula níveis de Fibonacci entre mínima e máxima."""
    diff = preco_max - preco_min
    niveis = {
        "0.0%":   preco_max,
        "23.6%":  preco_max - diff * 0.236,
        "38.2%":  preco_max - diff * 0.382,
        "50.0%":  preco_max - diff * 0.500,
        "61.8%":  preco_max - diff * 0.618,
        "78.6%":  preco_max - diff * 0.786,
        "100%":   preco_min,
        "161.8%": preco_min - diff * 0.618,
    }
    return niveis

def calcular_distancias(preco, ema9=None, ma20=None, ma200=None, vwap=None):
    """Calcula distância em pontos e % do preço a cada média."""
    resultado = {}
    medias = {"EMA9": ema9, "MA20": ma20, "MA200": ma200, "VWAP": vwap}
    for nome, val in medias.items():
        if val and val > 0:
            dist_pts = preco - val
            dist_pct = (dist_pts / val) * 100
            posicao = "ACIMA" if dist_pts > 0 else "ABAIXO"
            resultado[nome] = {
                "valor": val,
                "distancia_pts": round(abs(dist_pts), 2),
                "distancia_pct": round(abs(dist_pct), 3),
                "posicao": posicao
            }
    return resultado

def calcular_risco_retorno(entrada, stop, alvo1, alvo2=None):
    """Calcula R:R e valida se a operação tem qualidade mínima."""
    risco = abs(entrada - stop)
    retorno1 = abs(alvo1 - entrada)
    rr1 = round(retorno1 / risco, 2) if risco > 0 else 0
    resultado = {
        "risco_pts": round(risco, 2),
        "retorno_alvo1_pts": round(retorno1, 2),
        "rr_alvo1": rr1,
        "qualidade": "EXCELENTE" if rr1 >= 3 else "BOA" if rr1 >= 2 else "FRACA" if rr1 >= 1.5 else "RUIM"
    }
    if alvo2:
        retorno2 = abs(alvo2 - entrada)
        resultado["retorno_alvo2_pts"] = round(retorno2, 2)
        resultado["rr_alvo2"] = round(retorno2 / risco, 2) if risco > 0 else 0
    return resultado

def calcular_score_confluencia(preco, sinal, ema9=None, ma20=None, ma200=None, vwap=None):
    """
    Calcula score de confluência das médias.
    COMPRA: quanto mais médias abaixo do preço, maior o score.
    VENDA: quanto mais médias acima do preço, maior o score.
    Retorna: score (0-4), nivel (FORTE/MODERADO/FRACO), medias_alinhadas
    """
    pontos = 0
    medias_alinhadas = []
    medias = {"EMA9": ema9, "MA20": ma20, "MA200": ma200, "VWAP": vwap}

    for nome, val in medias.items():
        if val and val > 0:
            if sinal == "COMPRA" and preco > val:
                pontos += 1
                medias_alinhadas.append(nome)
            elif sinal == "VENDA" and preco < val:
                pontos += 1
                medias_alinhadas.append(nome)

    nivel = "FORTE" if pontos >= 3 else "MODERADO" if pontos == 2 else "FRACO"
    return {
        "score": pontos,
        "nivel": nivel,
        "medias_alinhadas": medias_alinhadas,
        "recomendacao": "OPERAR" if pontos >= 2 else "AGUARDAR"
    }

def formatar_calculos_para_prompt(preco, ema9=None, ma20=None, ma200=None, vwap=None,
                                   minima=None, maxima=None, sinal_previsto=None):
    """Monta bloco de cálculos para enriquecer o prompt da IA."""
    linhas = ["\n=== CALCULOS MATEMATICOS ==="]

    # Distâncias
    dists = calcular_distancias(preco, ema9, ma20, ma200, vwap)
    if dists:
        linhas.append("Distâncias do preço às médias:")
        for nome, d in dists.items():
            linhas.append(f"  {nome}: {d['posicao']} por {d['distancia_pts']:.0f}pts ({d['distancia_pct']:.2f}%)")

    # Fibonacci
    if minima and maxima and minima > 0 and maxima > 0:
        fibs = calcular_fibonacci(minima, maxima)
        linhas.append(f"Fibonacci ({minima:.0f} → {maxima:.0f}):")
        for nivel, val in fibs.items():
            marker = " ← PRÓXIMO" if abs(preco - val) < (maxima - minima) * 0.05 else ""
            linhas.append(f"  {nivel}: {val:.0f}{marker}")

    # Confluência
    if sinal_previsto and sinal_previsto in ["COMPRA", "VENDA"]:
        conf = calcular_score_confluencia(preco, sinal_previsto, ema9, ma20, ma200, vwap)
        linhas.append(f"Confluência ({sinal_previsto}): {conf['score']}/4 — {conf['nivel']}")
        linhas.append(f"  Médias alinhadas: {', '.join(conf['medias_alinhadas']) if conf['medias_alinhadas'] else 'nenhuma'}")
        linhas.append(f"  Recomendação: {conf['recomendacao']}")

    return "\n".join(linhas)

def formatar_indicadores(ticker, dados):
    """Formata os indicadores para incluir no prompt da IA."""
    if not dados:
        return ""
    linhas = [f"\nIndicadores tecnicos {ticker} [tempo real]:"]
    if dados.get("ema9"):   linhas.append(f"  EMA9:  {dados['ema9']:,.2f}")
    if dados.get("ma20"):   linhas.append(f"  MA20:  {dados['ma20']:,.2f}")
    if dados.get("ma200"):  linhas.append(f"  MA200: {dados['ma200']:,.2f}")
    if dados.get("rsi14"):
        linhas.append(f"  RSI14: {dados['rsi14']} ({dados.get('rsi_nivel','')})")
    if dados.get("tendencia_medias"):
        linhas.append(f"  Tendencia: {dados['tendencia_medias']}")
    return "\n".join(linhas)

def buscar_focus_bcb():
    """Boletim Focus - API oficial BCB, sem chave, atualizado toda segunda."""
    base = "https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata"
    resultado = {}
    try:
        # IPCA
        r = requests.get(f"{base}/ExpectativasMercadoAnuais",
            params={"$top":"1","$filter":"Indicador eq 'IPCA' and baseCalculo eq 0",
                    "$orderby":"Data desc","$format":"json","$select":"Indicador,Data,Mediana,Media"},
            headers={"Accept":"application/json"}, timeout=10)
        item = r.json().get("value",[{}])[0]
        if item:
            resultado["ipca_mediana"] = item.get("Mediana")
            resultado["ipca_media"]   = item.get("Media")
            resultado["focus_data"]   = item.get("Data")

        # PIB
        r = requests.get(f"{base}/ExpectativasMercadoAnuais",
            params={"$top":"1","$filter":"Indicador eq 'PIB Total' and baseCalculo eq 0",
                    "$orderby":"Data desc","$format":"json","$select":"Indicador,Data,Mediana"},
            headers={"Accept":"application/json"}, timeout=10)
        item = r.json().get("value",[{}])[0]
        if item: resultado["pib_mediana"] = item.get("Mediana")

        # Cambio
        r = requests.get(f"{base}/ExpectativasMercadoAnuais",
            params={"$top":"1","$filter":"Indicador eq 'C\u00e2mbio' and baseCalculo eq 0",
                    "$orderby":"Data desc","$format":"json","$select":"Indicador,Data,Mediana"},
            headers={"Accept":"application/json"}, timeout=10)
        item = r.json().get("value",[{}])[0]
        if item: resultado["cambio_mediana"] = item.get("Mediana")

        # SELIC proxima reuniao
        r = requests.get(f"{base}/ExpectativasMercadoSelic",
            params={"$top":"1","$orderby":"Data desc","$format":"json",
                    "$select":"Reuniao,Data,Mediana"},
            headers={"Accept":"application/json"}, timeout=10)
        item = r.json().get("value",[{}])[0]
        if item:
            resultado["selic_reuniao"] = item.get("Reuniao")
            resultado["selic_mediana"] = item.get("Mediana")

    except Exception as e:
        logger.error(f"buscar_focus_bcb: {e}")
    return resultado

def formatar_focus(dados):
    """Formata o Boletim Focus para incluir no prompt ou enviar ao usuario."""
    if not dados:
        return ""
    linhas = [f"\nBoletim Focus BCB ({dados.get('focus_data','')}) - Expectativas mercado:"]
    if dados.get("ipca_mediana"):
        linhas.append(f"  IPCA 2026: {dados['ipca_mediana']}% (mediana) | {dados['ipca_media']}% (media)")
    if dados.get("pib_mediana"):
        linhas.append(f"  PIB 2026:  {dados['pib_mediana']}% (mediana)")
    if dados.get("cambio_mediana"):
        linhas.append(f"  Dolar 2026: R$ {dados['cambio_mediana']} (mediana)")
    if dados.get("selic_reuniao"):
        linhas.append(f"  SELIC {dados['selic_reuniao']}: {dados['selic_mediana']}% (mediana)")
    return "\n".join(linhas)

def buscar_commodities():
    """Commodities em tempo real via Yahoo Finance - sem chave."""
    ativos = {
        "WTI":     "CL=F",
        "Brent":   "BZ=F",
        "Ouro":    "GC=F",
        "Prata":   "SI=F",
        "Cobre":   "HG=F",
        "MinerioFe": "TIO=F",
        "GasNat":  "NG=F",
    }
    resultado = {}
    for nome, symbol in ativos.items():
        try:
            r = requests.get(
                f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}",
                params={"interval": "1d", "range": "1d"},
                headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
            meta = r.json()["chart"]["result"][0]["meta"]
            preco = meta.get("regularMarketPrice")
            var   = meta.get("regularMarketChangePercent", 0)
            if preco:
                resultado[nome] = {"preco": preco, "var": round(var, 2)}
        except Exception as e:
            logger.error(f"commodity {nome}: {e}")
    return resultado

def buscar_fred_macro():
    """Dados macro EUA via FRED - Federal Reserve, sem custo adicional."""
    FRED_KEY = "os.environ.get("FRED_KEY","")"
    base = "https://api.stlouisfed.org/fred/series/observations"
    series = {
        "juros_fed": "DFF",          # Fed Funds diário (mais atualizado)
        "cpi_eua":   "CPIAUCSL",     # CPI EUA
        "desemprego":"UNRATE",       # Desemprego EUA
        "wti_fred":  "DCOILWTICO",   # WTI spot semanal
        "brent_fred":"DCOILBRENTEU", # Brent spot semanal
        "minerio":   "PIORECRUSDM",  # Minério de ferro mensal
    }
    resultado = {}
    for chave, sid in series.items():
        try:
            r = requests.get(base, params={
                "series_id": sid, "api_key": FRED_KEY,
                "file_type": "json", "limit": 1, "sort_order": "desc"
            }, timeout=8)
            obs = r.json().get("observations", [{}])[0]
            val = obs.get("value")
            if val and val != ".":
                resultado[chave] = {"valor": float(val), "data": obs.get("date", "")}
        except Exception as e:
            logger.error(f"FRED {sid}: {e}")
    return resultado

def formatar_macro_global(commodities, fred):
    """Formata contexto macro global para o prompt da IA."""
    linhas = ["\nContexto macro global (tempo real):"]

    # Petróleo - impacto direto na Petrobras/Ibovespa
    wti   = commodities.get("WTI",   {}).get("preco")
    brent = commodities.get("Brent", {}).get("preco")
    if wti:
        var = commodities["WTI"].get("var", 0)
        linhas.append(f"  WTI:   USD {wti:.2f} ({var:+.2f}%)")
    if brent:
        var = commodities["Brent"].get("var", 0)
        linhas.append(f"  Brent: USD {brent:.2f} ({var:+.2f}%)")

    # Minério de ferro - impacto direto na Vale
    minerio = commodities.get("MinerioFe", {}).get("preco")
    if minerio:
        var = commodities["MinerioFe"].get("var", 0)
        linhas.append(f"  Minério Fe: USD {minerio:.2f} ({var:+.2f}%)")

    # Ouro e cobre
    ouro  = commodities.get("Ouro",  {}).get("preco")
    cobre = commodities.get("Cobre", {}).get("preco")
    if ouro:   linhas.append(f"  Ouro:  USD {ouro:.2f}/oz")
    if cobre:  linhas.append(f"  Cobre: USD {cobre:.3f}/lb")

    # FRED - juros e desemprego EUA
    juros = fred.get("juros_fed", {}).get("valor")
    desem = fred.get("desemprego", {}).get("valor")
    if juros: linhas.append(f"  Juros Fed: {juros}% ({fred['juros_fed']['data']})")
    if desem: linhas.append(f"  Desemprego EUA: {desem}%")

    return "\n".join(linhas) if len(linhas) > 1 else ""

# Funcoes de memoria de conversa
def salvar_memoria(chat_id, ativo, timeframe, sinal, resumo):
    try:
        mem = {}
        if os.path.exists(MEMORIA_FILE):
            with open(MEMORIA_FILE) as f:
                mem = json.load(f)
        key = str(chat_id)
        if key not in mem:
            mem[key] = []
        mem[key].append({
            "hora": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "ativo": ativo,
            "timeframe": timeframe,
            "sinal": sinal,
            "resumo": resumo[:300]
        })
        mem[key] = mem[key][-20:]  # manter so as 20 ultimas
        with open(MEMORIA_FILE, "w") as f:
            json.dump(mem, f, ensure_ascii=False)
    except Exception as e:
        logger.error(f"salvar_memoria: {e}")

def carregar_memoria(chat_id):
    try:
        if os.path.exists(MEMORIA_FILE):
            with open(MEMORIA_FILE) as f:
                mem = json.load(f)
            historico = mem.get(str(chat_id), [])
            if historico:
                linhas = [f"{h['hora']} | {h['ativo']} {h['timeframe']} | {h['sinal']} | {h['resumo']}" for h in historico[-5:]]
                return "Ultimas analises:\n" + "\n".join(linhas)
    except Exception as e:
        logger.error(f"carregar_memoria: {e}")
    return ""



# ── OpenAI client ──────────────────────────────────────────────────────────────
try:
    import openai as _openai
    openai_client = _openai.OpenAI(api_key=OPENAI_KEY)
except Exception:
    openai_client = None

# ── Estratégias base (metodologia Americana) ────────────────────────────────────
ESTRATEGIAS_BASE = """AMERICANA 1 - Golden Line (9:0-11:0):
COMPRA: Barra1 verde fechando ACIMA de MA200+MA20+EMA9+VWAP+GoldenLine. Barra2 verde volume menor. Entrada: máxima Barra2. Stop: 150pts. Alvos Fib 61.8%/100%/161.8%.
VENDA: Espelho - Barra1 vermelha fechando ABAIXO de todas as médias.

AMERICANA 2 - Falha na VWAP:
COMPRA: Médias alinhadas venda mas Barra1 falhou (verde+pavio). Aguardar fechar ACIMA VWAP. Entrada VWAP. Stop 150pts.
VENDA: Médias alinhadas compra mas Barra1 falhou (vermelha+pavio). Abaixo VWAP. Stop 150pts.

AMERICANA 3 - Falha da Falha:
Tomou stop na Am2 → fluxo voltou forte → VIRE A MÃO.
COMPRA: entrada máxima candle do stop. VENDA: entrada mínima. Stop 200pts. Alvo Fib 161.8%.

AMERICANA 4 - Golden Line Entre Médias:
COMPRA: GoldenLine abaixo → toque → entrada GL → Alvo MA200. Stop 150pts. R:R mínimo 1:4.
VENDA: GoldenLine acima → toque → entrada GL → Alvo MA200.

AMERICANA 5 - Reentrada Pullback:
COMPRA: 1ª média abaixo (EMA9/VWAP) → entrada → Alvo: Fib anterior. Stop 150pts.
VENDA: 1ª média acima → entrada → Alvo: Fib anterior.

ORDER BLOCK + VAR:
COMPRA: Barra verde fecha ACIMA do OB. Médias alinhadas. VAR: volume verde > volume vermelho anterior. Entrada máxima. Stop 150pts.
VENDA: Barra vermelha fecha ABAIXO do OB. Volume vermelho > verde. Entrada mínima. Stop 150pts.
REENTRADA: Preço bate EMA9 → barra confirma → volume confirma → entrada. Stop 150pts.

CANDLE DOMINANTE 60min:
Após 30min de pregão o candle dominante começa a se definir. Barra Elefante ≥250pts? EMA9 com ângulo ~45°? Pullback na EMA9 dentro do range? Entrada limitada. Rompimento de nível-chave? Aguardar candle fechar fora.

FIBONACCI VAR:
Retrações 23.6%/38.2%/50%/61.8%/78.6% do impulso. Toque + EMA9 alinhada + candle fechado = entrada. Stop 150pts. Alvo 161.8%.

REGRAS GERAIS: Horário 9:0-11:0. Gráfico 5min. Break-even +80pts. Máx 3 operações/dia. Não operar médias emboladas."""


# ══════════════════════════════════════════════════════════════════════════════
# UTILITÁRIOS
# ══════════════════════════════════════════════════════════════════════════════

TELEGRAM_API = "https://api.telegram.org"
MACRODROID_RELAY = "https://trigger.macrodroid.com/98076b41-4e7d-4f03-b417-876c3bad96fc/relay_telegram"

def send_telegram(token, chat_id, text, parse_mode="Markdown"):
    """Envia mensagem para o Telegram - tenta direto, fallback MacroDroid."""
    import requests as req
    # Tentativa 1: Telegram direto
    try:
        r = req.post(
            f"{TELEGRAM_API}/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode},
            timeout=15
        )
        if r.status_code == 200:
            return
        logger.error(f"send_telegram direto: {r.status_code} {r.text[:100]}")
    except Exception as e:
        logger.error(f"send_telegram direto: {e}")
    # Tentativa 2: MacroDroid como ponte
    try:
        req.post(
            MACRODROID_RELAY,
            json={"token": token, "chat_id": chat_id, "text": text, "parse_mode": parse_mode},
            timeout=15
        )
    except Exception as e:
        logger.error(f"send_telegram macrodroid: {e}")


def jpeg_para_png(imagem_bytes):
    """Converte bytes JPEG para PNG usando stdlib pura (sem PIL)."""
    try:
        import struct, zlib as _zlib
        # Tentar PIL primeiro (mais fiel)
        import PIL.Image, io
        img = PIL.Image.open(io.BytesIO(imagem_bytes))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        # Fallback: retornar os bytes originais se PIL falhar
        return imagem_bytes

def groq_visao(prompt, imagem_bytes=None):
    """Groq llama-4-scout com visao - aceita PNG base64."""
    try:
        import base64 as _b64
        headers = {"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"}
        content = [{"type": "text", "text": prompt}]
        if imagem_bytes:
            # Converter para PNG se necessario (Groq so aceita PNG)
            png_bytes = jpeg_para_png(imagem_bytes)
            b64_img = _b64.b64encode(png_bytes).decode()
            content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_img}"}})
        body = {
            "model": "meta-llama/llama-4-scout-17b-16e-instruct",
            "messages": [{"role": "user", "content": content}],
            "max_tokens": 800
        }
        import httpx
        with httpx.Client() as hx:
            resp = hx.post("https://api.groq.com/openai/v1/chat/completions",
                           headers=headers, json=body, timeout=35)
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.error(f"groq_visao: {e}")
        return None

def gpt4o(prompt, imagem_bytes=None):
    """GPT Vision."""
    try:
        import openai, httpx
        client = openai.OpenAI(
            api_key=OPENAI_KEY,
            http_client=httpx.Client()
        )
        if imagem_bytes:
            import base64 as b64
            img_b64 = b64.b64encode(imagem_bytes).decode()
            msgs = [{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}
            ]}]
        else:
            msgs = [{"role": "user", "content": prompt}]
        response = client.chat.completions.create(
            model="gpt-4o", messages=msgs,
            max_tokens=800 if imagem_bytes else 600
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"GPT-4o: {e}")
        return None

def gemini(prompt, imagem_bytes=None):
    """Google Gemini - rotacao automatica de chaves + fallback GPT-4-omni com imagem."""
    import base64 as b64lib

    # Tentar todas as chaves Gemini via SDK
    for tentativa in range(len(GEMINI_KEYS)):
        chave = get_gemini_key()
        try:
            import google.generativeai as genai
            genai.configure(api_key=chave)
            model = genai.GenerativeModel("gemini-2.0-flash")
            if imagem_bytes:
                import PIL.Image, io
                img = PIL.Image.open(io.BytesIO(imagem_bytes))
                response = model.generate_content([prompt, img])
            else:
                response = model.generate_content(prompt)
            texto = response.text.strip()
            if texto:
                return texto
        except Exception as e:
            err = str(e)
            logger.error(f"Gemini SDK chave {tentativa+1}: {err[:80]}")
            rotate_gemini_key()

        # Fallback REST com mesma chave (imagem via base64)
        try:
            body = {"contents":[{"parts":[{"text": prompt}]}]}
            if imagem_bytes:
                b64_img = b64lib.b64encode(imagem_bytes).decode()
                body["contents"][0]["parts"].append(
                    {"inline_data": {"mime_type": "image/jpeg", "data": b64_img}}
                )
            import httpx
            with httpx.Client(transport=httpx.HTTPTransport(proxy=None)) as hx:
                resp = hx.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={chave}",
                    json=body, timeout=30)
            d = resp.json()
            if resp.status_code == 200 and "candidates" in d:
                return d["candidates"][0]["content"]["parts"][0]["text"].strip()
            rotate_gemini_key()
        except Exception as e2:
            logger.error(f"Gemini REST {tentativa+1}: {e2}")
            rotate_gemini_key()
            continue

    # Gemini esgotado - se tem imagem, GPT-4o é o unico fallback valido
    if imagem_bytes:
        logger.warning("Gemini esgotado com imagem - tentando GPT-4o...")
        return gpt4o(prompt, imagem_bytes)

    # Sem imagem - pode usar Groq/OpenRouter
    logger.warning("Gemini esgotado (sem imagem) - usando Groq...")
    try:
        import httpx
        headers = {"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"}
        body = {
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 800
        }
        with httpx.Client() as hx:
            resp = hx.post("https://api.groq.com/openai/v1/chat/completions",
                           headers=headers, json=body, timeout=30)
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as eg:
        logger.error(f"Groq fallback: {eg}")
        return None



# ══════════════════════════════════════════════════════════════════════════════
# RODÍZIO DE IAs - nunca usa a mesma IA duas vezes seguidas
# Ordem: Groq → Gemini → OpenRouter/DeepSeek → OpenRouter/Mistral → GPT-4o
# Créditos são distribuídos automaticamente entre todas as IAs gratuitas
# ══════════════════════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════════════════════
# FAILOVER PROFISSIONAL DE APIs - Gerenciador de Estados
# Implementa: array de chaves, índice ativo, cooldown, log de falhas,
#             retry automático, alerta Telegram em falha crítica
# ══════════════════════════════════════════════════════════════════════════════

import time as _time_module

# ── Estado global do Failover ──────────────────────────────────────────────
_FAILOVER_STATE = {
    "Groq/LLaMA":         {"falhas": 0, "ultimo_erro": 0, "cooldown": 60,  "status": "ok"},
    "Gemini Flash":        {"falhas": 0, "ultimo_erro": 0, "cooldown": 120, "status": "ok"},
    "OpenRouter/DeepSeek": {"falhas": 0, "ultimo_erro": 0, "cooldown": 60,  "status": "ok"},
    "OpenRouter/Mistral":  {"falhas": 0, "ultimo_erro": 0, "cooldown": 60,  "status": "ok"},
    "GPT-4o":              {"falhas": 0, "ultimo_erro": 0, "cooldown": 300, "status": "ok"},
}
_FAILOVER_LOG = []        # histórico das últimas 50 falhas
_rodizio_idx  = 0         # índice do rodízio
_RODIZIO_IAS  = [
    {"nome": "Groq/LLaMA",         "tipo": "groq",       "modelo": "llama-3.3-70b-versatile"},
    {"nome": "Gemini Flash",        "tipo": "gemini",     "modelo": "gemini-2.0-flash"},
    {"nome": "OpenRouter/DeepSeek", "tipo": "openrouter", "modelo": "deepseek/deepseek-r1"},
    {"nome": "OpenRouter/Mistral",  "tipo": "openrouter", "modelo": "mistralai/mistral-7b-instruct"},
    {"nome": "GPT-4o",              "tipo": "openai",     "modelo": "gpt-4o"},
]

def _registrar_falha(nome_ia, erro):
    """Registra falha no estado e no log. Ativa cooldown se necessario."""
    global _FAILOVER_LOG
    agora = _time_module.time()
    estado = _FAILOVER_STATE.get(nome_ia)
    if not estado:
        return
    estado["falhas"] += 1
    estado["ultimo_erro"] = agora
    # Após 3 falhas consecutivas → cooldown obrigatório
    if estado["falhas"] >= 3:
        estado["status"] = "cooldown"
        logger.warning(f"🔴 Failover: {nome_ia} entrou em COOLDOWN ({estado['cooldown']}s)")
    _FAILOVER_LOG.append({
        "ia": nome_ia, "erro": str(erro)[:100],
        "hora": _time_module.strftime("%H:%M:%S")
    })
    _FAILOVER_LOG = _FAILOVER_LOG[-50:]  # manter só as últimas 50

def _registrar_sucesso(nome_ia):
    """Reseta o contador de falhas apos sucesso."""
    estado = _FAILOVER_STATE.get(nome_ia)
    if estado:
        if estado["falhas"] > 0:
            logger.info(f"✅ Failover: {nome_ia} voltou a funcionar")
        estado["falhas"] = 0
        estado["status"] = "ok"

def _ia_disponivel(nome_ia):
    """Verifica se a IA esta disponivel (fora do cooldown)."""
    estado = _FAILOVER_STATE.get(nome_ia)
    if not estado:
        return True
    if estado["status"] == "cooldown":
        # Verificar se o cooldown já expirou
        agora = _time_module.time()
        if agora - estado["ultimo_erro"] > estado["cooldown"]:
            estado["status"] = "ok"
            estado["falhas"] = 0
            logger.info(f"🟢 Failover: {nome_ia} saiu do cooldown - testando novamente")
            return True
        return False
    return True

def _alerta_falha_critica():
    """Envia alerta Telegram quando TODAS as IAs falharam."""
    try:
        log_resumo = " | ".join([
            f"{e['ia']}: {e['erro'][:30]}" for e in _FAILOVER_LOG[-5:]
        ])
        msg = (
            "🚨 FALHA CRÍTICA - TODAS AS IAs FALHARAM\n\n"
            "Nenhuma IA respondeu após 5 tentativas.\n\n"
            f"Últimas falhas:\n{log_resumo}\n\n"
            "Bots temporariamente fora de serviço. Verificar APIs."
        )
        requests.post(
            f"https://api.telegram.org/bot{TOKEN_ANALISE}/sendMessage",
            json={"chat_id": CHAT_ID_MARCIO, "text": msg},
            timeout=10
        )
    except Exception as e:
        logger.error(f"Alerta falha crítica: {e}")

def _chamar_ia_unica(ia, prompt):
    """Executa uma chamada para uma IA especifica e retorna resultado ou None."""
    tipo = ia["tipo"]
    nome = ia["nome"]
    try:
        resultado = None
        if tipo == "groq":
            import httpx
            headers = {"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"}
            body = {"model": "llama-3.3-70b-versatile",
                    "messages": [{"role": "user", "content": prompt}], "max_tokens": 700}
            with httpx.Client() as hx:
                resp = hx.post("https://api.groq.com/openai/v1/chat/completions",
                               headers=headers, json=body, timeout=30)
            if resp.status_code == 429:
                raise Exception("429 Rate limit Groq")
            resultado = resp.json()["choices"][0]["message"]["content"].strip()

        elif tipo == "gemini":
            resultado = gemini(prompt)
            if not resultado:
                raise Exception("Gemini retornou vazio")

        elif tipo == "openrouter":
            import httpx
            headers = {
                "Authorization": f"Bearer {OPENROUTER_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://marciomonte.pythonanywhere.com",
                "X-Title": "ProfitBots-Trading"
            }
            body = {"model": ia["modelo"],
                    "messages": [{"role": "user", "content": prompt}], "max_tokens": 700}
            with httpx.Client() as hx:
                resp = hx.post("https://openrouter.ai/api/v1/chat/completions",
                               headers=headers, json=body, timeout=30)
            if resp.status_code in [429, 503]:
                raise Exception(f"{resp.status_code} OpenRouter")
            resultado = resp.json()["choices"][0]["message"]["content"].strip()

        elif tipo == "openai":
            resultado = gpt4o(prompt)
            if not resultado:
                raise Exception("GPT-4o retornou vazio")

        if resultado:
            _registrar_sucesso(nome)
            return resultado
        raise Exception("Resultado vazio")

    except Exception as e:
        _registrar_falha(nome, e)
        logger.warning(f"⚠️ Failover: {nome} falhou - {e}")
        return None

def openrouter_texto(prompt, modelo="deepseek/deepseek-r1"):
    """Chama OpenRouter diretamente (compatibilidade)."""
    import httpx
    try:
        headers = {
            "Authorization": f"Bearer {OPENROUTER_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://marciomonte.pythonanywhere.com",
            "X-Title": "ProfitBots-Trading"
        }
        body = {"model": modelo,
                "messages": [{"role": "user", "content": prompt}], "max_tokens": 600}
        with httpx.Client() as hx:
            resp = hx.post("https://openrouter.ai/api/v1/chat/completions",
                           headers=headers, json=body, timeout=30)
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.error(f"OpenRouter {modelo}: {e}")
        return None

def groq_texto(prompt):
    """Chama Groq diretamente (compatibilidade)."""
    import httpx
    try:
        headers = {"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"}
        body = {"model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}], "max_tokens": 600}
        with httpx.Client() as hx:
            resp = hx.post("https://api.groq.com/openai/v1/chat/completions",
                           headers=headers, json=body, timeout=30)
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.error(f"Groq: {e}")
        return None

def chamar_ia_rodizio(prompt, imagem_bytes=None):
    """
    FAILOVER PROFISSIONAL - Gerenciador de Estados completo.
    - Com imagem: Gemini → GPT-4-omni (únicos com vision)
    - Sem imagem: rodízio Groq→Gemini→OpenRouter→GPT-4-omni
    - Cooldown automático após 3 falhas consecutivas
    - Alerta Telegram se TODAS falharem
    - Log completo de falhas
    """
    global _rodizio_idx

    # COM IMAGEM - só Gemini e GPT-4o suportam vision
    if imagem_bytes:
        resultado = gemini(prompt, imagem_bytes)
        if resultado:
            return resultado
        logger.warning("Failover vision: Gemini falhou, tentando GPT-4o...")
        resultado = gpt4o(prompt, imagem_bytes)
        if resultado:
            return resultado
        _alerta_falha_critica()
        return None

    # SEM IMAGEM - rodízio com failover completo
    tentativas_total = len(_RODIZIO_IAS)
    tentativas_feitas = 0

    for _ in range(tentativas_total):
        ia = _RODIZIO_IAS[_rodizio_idx % len(_RODIZIO_IAS)]
        _rodizio_idx += 1
        nome = ia["nome"]

        # Verificar cooldown
        if not _ia_disponivel(nome):
            logger.info(f"⏸️ Failover: {nome} em cooldown - pulando")
            continue

        logger.info(f"🔄 Failover: tentando {nome} ({tentativas_feitas+1}/{tentativas_total})")
        tentativas_feitas += 1

        resultado = _chamar_ia_unica(ia, prompt)
        if resultado:
            logger.info(f"✅ Failover: {nome} respondeu com sucesso")
            return resultado

    # Todas falharam
    logger.error("❌ Failover CRÍTICO: todas as IAs falharam!")
    _alerta_falha_critica()
    return None

@app.route("/failover_status", methods=["GET"])
def failover_status():
    """Endpoint para monitorar o status do failover em tempo real."""
    status = {}
    for ia in _RODIZIO_IAS:
        nome = ia["nome"]
        estado = _FAILOVER_STATE.get(nome, {})
        disponivel = _ia_disponivel(nome)
        status[nome] = {
            "disponivel": disponivel,
            "falhas": estado.get("falhas", 0),
            "status": estado.get("status", "ok"),
        }
    return {
        "failover": status,
        "ultimas_falhas": _FAILOVER_LOG[-5:],
        "rodizio_idx": _rodizio_idx % len(_RODIZIO_IAS),
        "proxima_ia": _RODIZIO_IAS[_rodizio_idx % len(_RODIZIO_IAS)]["nome"]
    }



# ── Integração Interna dos Bots (sem mensagens visíveis) ──────────────────────

def consultar_sentimento_interno():
    """
    Busca o último sentimento de mercado do ProfitSentiBot — internamente,
    sem enviar nenhuma mensagem visível ao usuário.
    Retorna: string resumida ou None
    """
    try:
        # Lê o arquivo de sentimento salvo pelo webhook_sentimento
        sent_file = os.path.join(os.path.dirname(__file__), "ultimo_sentimento.json")
        if os.path.exists(sent_file):
            with open(sent_file) as f:
                data = json.load(f)
            idade_min = (time.time() - data.get("timestamp", 0)) / 60
            if idade_min <= 120:  # só usa se tiver até 2h de idade
                return data.get("resumo", None)
    except Exception as e:
        logger.error(f"consultar_sentimento_interno: {e}")
    return None

def consultar_estrategia_interna(leitura_tecnica, sentimento=""):
    """
    Consulta o ProfitEstrategia internamente para escolher a melhor estratégia.
    Não envia mensagem — apenas retorna o dict da estratégia escolhida.
    """
    try:
        return escolher_estrategia_local(leitura_tecnica, sentimento)
    except Exception as e:
        logger.error(f"consultar_estrategia_interna: {e}")
        return {"estrategia_nome": "N/A", "estrategia_conteudo": "", "confianca": "N/A"}

def consultar_historico_interno(chat_id, ativo=None):
    """
    Consulta o histórico de operações do ProfitSinal internamente.
    Retorna: string com últimas 3 operações relevantes ou None
    """
    try:
        return buscar_memoria(chat_id, ativo)
    except Exception as e:
        logger.error(f"consultar_historico_interno: {e}")
    return None

def salvar_sentimento_para_outros_bots(resumo_sentimento):
    """
    Salva o sentimento atual em arquivo para que ProfitAnalise possa ler.
    Chamado pelo webhook_sentimento após gerar análise.
    """
    try:
        sent_file = os.path.join(os.path.dirname(__file__), "ultimo_sentimento.json")
        with open(sent_file, "w") as f:
            json.dump({
                "resumo": resumo_sentimento,
                "timestamp": time.time()
            }, f)
    except Exception as e:
        logger.error(f"salvar_sentimento_para_outros_bots: {e}")

def extrair_valores_da_leitura(leitura_tecnica):
    """
    Extrai valores numéricos da leitura técnica (texto do OCR)
    para alimentar os cálculos matemáticos.
    """
    import re
    resultado = {}
    padroes = {
        "preco":   r"PRECO[:\s]+([0-9][\d\.,]+)",
        "ema9":    r"EMA9[:\s]+([0-9][\d\.,]+)",
        "ma20":    r"MA20[:\s]+([0-9][\d\.,]+)",
        "ma200":   r"MA200[:\s]+([0-9][\d\.,]+)",
        "vwap":    r"VWAP[:\s]+([0-9][\d\.,]+)",
        "maxima":  r"MAXIMA[:\s]+([0-9][\d\.,]+)",
        "minima":  r"MINIMA[:\s]+([0-9][\d\.,]+)",
    }
    for campo, padrao in padroes.items():
        m = re.search(padrao, leitura_tecnica, re.IGNORECASE)
        if m:
            try:
                val_str = m.group(1).replace(".", "").replace(",", ".")
                resultado[campo] = float(val_str)
            except Exception:
                pass
    return resultado

def consenso_ia(prompt_tecnica, prompt_sinal, imagem_bytes=None):
    """Cruza GPT-4-omni + Gemini e retorna analise balanceada."""
    import concurrent.futures

    # Executar os dois em paralelo
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        fut_gpt    = executor.submit(gpt4o,   prompt_tecnica, imagem_bytes)
        fut_gemini = executor.submit(gemini,  prompt_tecnica, imagem_bytes)
        res_gpt    = fut_gpt.result()
        res_gemini = fut_gemini.result()

    # Se um falhar, usa o outro
    if not res_gpt and not res_gemini:
        return None, None, None
    if not res_gpt:
        return res_gemini, None, "gemini"
    if not res_gemini:
        return res_gpt, None, "gpt4o"

    # Cruzar os dois com GPT-4o como árbitro
    prompt_cruzamento = f"""Dois modelos de IA analisaram o mesmo gráfico de forma independente.

═══ ANÁLISE GPT-4-omni ═══
{res_gpt}

═══ ANÁLISE GEMINI ═══
{res_gemini}

Sua tarefa:
1. Identifique os PONTOS EM COMUM (ambos concordam)
2. Identifique as DIVERGÊNCIAS (opiniões diferentes)
3. Gere uma ANÁLISE CONSENSUAL unindo os melhores insights dos dois
4. Indique o NÍVEL DE CONFIANÇA: ALTO (concordam), MÉDIO (divergência leve), BAIXO (divergência forte)

Responda em formato estruturado - seja objetivo e preciso."""

    consenso = gpt4o(prompt_cruzamento)
    return res_gpt, res_gemini, consenso


def extrair_sinal_gemini(texto):
    """Extrai sinal COMPRA/VENDA/AGUARDA do texto do Gemini."""
    if not texto:
        return "AGUARDA"
    t = texto.upper()
    if "COMPRA" in t:
        return "COMPRA"
    elif "VENDA" in t:
        return "VENDA"
    return "AGUARDA"


def extrair_sinal(texto):
    if not texto:
        return "AGUARDA"
    t = texto.upper()
    if "COMPRA" in t: return "COMPRA"
    if "VENDA" in t:  return "VENDA"
    return "AGUARDA"


# ══════════════════════════════════════════════════════════════════════════════
# ESTRATÉGIAS - Local (sem Render)
# ══════════════════════════════════════════════════════════════════════════════

def load_estrategias():
    try:
        if os.path.exists(ESTRATEGIAS_FILE):
            with open(ESTRATEGIAS_FILE) as f:
                return json.load(f)
    except:
        pass
    return {}


def save_estrategias(data):
    try:
        with open(ESTRATEGIAS_FILE, "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"save_estrategias: {e}")


def escolher_estrategia_local(leitura_tecnica, sentimento_info):
    """
    Cerebro do ProfitAnalise — escolhe a melhor estrategia automaticamente.

    Prioridade:
    1. IFR visivel + extremo (<30 ou >70) → Double Check IFR
    2. IFR visivel + neutro + pullback VWAP → Pullback VWAP
    3. Gap + IFR extremo → Sweep de Liquidez
    4. 3+ medias alinhadas + candle expressivo → Modo Expansao
    5. Medias mistas → Modo Retracao
    6. EMA9 e MA20 a 45° → Alinhamento 9/20
    7. Candle expressivo em nivel historico → Memoria Kitta
    8. Nivel horizontal claro → Suporte e Resistencia
    9. IFR NAO visivel → NUNCA usar Double Check IFR
    """
    import re as _re
    try:
        ests = load_estrategias()
        ests_extra = ""
        if ests:
            ests_extra = "\n\nESTRATEGIAS CADASTRADAS (manual do trader):\n"
            for nome, conteudo in ests.items():
                ests_extra += f"\n--- {nome} ---\n{conteudo[:400]}\n"

        classif = sentimento_info.get("classificacao", "NEUTRO")
        score   = sentimento_info.get("score", 0)

        # Detectar IFR na leitura
        tem_ifr = bool(_re.search(r"IFR|RSI", leitura_tecnica, _re.IGNORECASE))
        val_ifr = 50
        m_ifr = _re.search(r"IFR[:\s]+(\d+)", leitura_tecnica, _re.IGNORECASE)
        if m_ifr:
            try:
                val_ifr = int(m_ifr.group(1))
            except Exception:
                pass
        ifr_extremo = val_ifr < 30 or val_ifr > 70

        # Detectar alinhamento das medias
        acima  = len(_re.findall(r"ACIMA",  leitura_tecnica, _re.IGNORECASE))
        abaixo = len(_re.findall(r"ABAIXO", leitura_tecnica, _re.IGNORECASE))
        medias_alinhadas = acima >= 3 or abaixo >= 3

        # Detectar gap
        tem_gap = bool(_re.search(r"gap|abertura.*distante|abre.*longe", leitura_tecnica, _re.IGNORECASE))

        ifr_str = f"SIM — valor: {val_ifr}" if tem_ifr else "NAO visivel — NAO usar Double Check IFR"
        alinhadas_str = "SIM" if medias_alinhadas else "NAO"
        gap_str = "SIM" if tem_gap else "NAO"

        prompt = (
            "Voce e o cerebro de um sistema de trading profissional.\n"
            "Analise a leitura tecnica e escolha UMA estrategia. Siga a logica abaixo OBRIGATORIAMENTE.\n\n"
            "=== LEITURA TECNICA DO GRAFICO ===\n"
            f"{leitura_tecnica}\n\n"
            "=== CONTEXTO DE MERCADO ===\n"
            f"Sentimento: {classif} (score: {score:+d})\n"
            f"IFR visivel no grafico: {ifr_str}\n"
            f"3+ medias alinhadas: {alinhadas_str}\n"
            f"Gap de abertura: {gap_str}\n\n"
            "=== REGRAS DE ESCOLHA (siga NESTA ORDEM) ===\n"
            "=== IFR CORRETO (WIN/WDO 5min, RSI nao estocastico) ===\n"
            "COMPRA: IFR abaixo de 80 = autorizado | IFR acima de 80 = BLEFE, nao entra\n"
            "VENDA: IFR acima de 20 = autorizado | IFR abaixo de 20 = NAO VENDER, vai stopar\n"
            "PERNADA COMPRA: IFR abaixo de 20 + medias compra = Double Check, aumentar lotes\n"
            "PERNADA VENDA: IFR acima de 80 + medias venda = Double Check, aumentar lotes\n"
            "BLEFE: MA20 acima da EMA9 em modo compra = nao entrar\n\n"
            "=== ESCOLHA DA ESTRATEGIA (siga nesta ordem) ===\n"
            "1. IFR visivel + abaixo 20 + medias compra = Double Check Compra de Pernada\n"
            "2. IFR visivel + acima 80 + medias venda = Double Check Venda de Pernada\n"
            "3. IFR visivel + acima 80 + modo expansao = Modo Expansao Venda Sweep\n"
            "4. IFR visivel + abaixo 80 + modo expansao + VWAP = Modo Expansao Compra VWAP\n"
            "5. IFR visivel + 20-80 + medias alinhadas compra = Modo Retracao Compra\n"
            "6. IFR visivel + 20-80 + medias alinhadas venda = Modo Retracao Venda\n"
            "7. IFR nao visivel + medias compra = Modo Retracao Compra\n"
            "8. IFR nao visivel + medias venda = Modo Retracao Venda\n"
            "9. Preco entre medias sem direcao = Mercado Burro AGUARDA\n"
            "10. NUNCA usar Double Check sem IFR visivel no grafico\n\n"
            "=== ESTRATEGIAS DISPONIVEIS ===\n"
            f"{ESTRATEGIAS_BASE}{ests_extra}\n\n"
            "Responda APENAS em JSON valido:\n"
            "{\n"
            '  "estrategia_nome": "nome exato da estrategia escolhida",\n'
            '  "estrategia_conteudo": "regras especificas para ESTE grafico em 3-4 linhas",\n'
            '  "criterios_atendidos": "criterios do grafico que justificam a escolha",\n'
            '  "confianca": "Alta|Media|Baixa",\n'
            f'  "ifr_ativou_double_check": {str(tem_ifr and ifr_extremo).lower()}\n'
            "}"
        )

        resp = chamar_ia_rodizio(prompt)
        if resp:
            resp = resp.strip()
            if resp.startswith("```"):
                resp = _re.sub(r"```[a-z]*\n?", "", resp).strip().rstrip("`").strip()
            m_json = _re.search(r"\{.*\}", resp, _re.DOTALL)
            if m_json:
                return json.loads(m_json.group(0))
    except Exception as e:
        logger.error(f"escolher_estrategia_local: {e}")

    return {
        "estrategia_nome": "Alinhamento 9/20 — Tendencia",
        "estrategia_conteudo": "EMA9 e MA20 alinhadas com inclinacao ~45 graus. Entrada no pullback. Stop 150pts.",
        "criterios_atendidos": "fallback padrao",
        "confianca": "Media",
        "ifr_ativou_double_check": False
    }


# ══════════════════════════════════════════════════════════════════════════════
# SENTIMENTO DO MERCADO - Local (sem Render)
# ══════════════════════════════════════════════════════════════════════════════

def coletar_sentimento_local():
    """Coleta sentimento do mercado usando as APIs disponiveis no PythonAnywhere."""
    d = {}
    score = 0

    # IBOV (Yahoo Finance - sem token)
    try:
        yf = requests.get(
            "https://query1.finance.yahoo.com/v8/finance/chart/%5EBVSP?interval=1d&range=2d",
            headers={"User-Agent": "Mozilla/5.0"}, timeout=10).json()
        meta = yf.get("chart",{}).get("result",[{}])[0].get("meta",{})
        preco = meta.get("regularMarketPrice", 0)
        prev  = meta.get("previousClose", 0) or meta.get("chartPreviousClose", 0)
        d["ibov_preco"] = preco
        d["ibov_var"]   = round((preco/prev - 1)*100, 2) if prev else 0
        if d["ibov_var"] > 0.5:    score += 2
        elif d["ibov_var"] > 0:    score += 1
        elif d["ibov_var"] < -0.5: score -= 2
        else:                       score -= 1
    except Exception as e:
        logger.error(f"IBOV Yahoo: {e}")
        d.update({"ibov_var": 0, "ibov_preco": 0})

    # USD/BRL (Twelve Data)
    try:
        td = requests.get(
            f"https://api.twelvedata.com/quote?symbol=USD/BRL&apikey={TWELVE_DATA_KEY}", timeout=10
        ).json()
        d["dolar_preco"] = float(td.get("close") or 0)
        d["dolar_var"]   = float(td.get("percent_change") or 0)
        if d["dolar_var"] < -0.2:  score += 1
        elif d["dolar_var"] > 0.3: score -= 1
    except:
        d.update({"dolar_preco": 0, "dolar_var": 0})

    # EMA9 + RSI USD/BRL (Twelve Data)
    try:
        v = requests.get(f"https://api.twelvedata.com/ema?symbol=USD/BRL&period=9&interval=5min&outputsize=1&apikey={TWELVE_DATA_KEY}", timeout=10).json().get("values", [{}])
        d["ema9"] = float(v[0].get("ema") or 0) if v else 0
    except:
        d["ema9"] = 0
    try:
        v = requests.get(f"https://api.twelvedata.com/rsi?symbol=USD/BRL&period=14&interval=1h&outputsize=1&apikey={TWELVE_DATA_KEY}", timeout=10).json().get("values", [{}])
        d["rsi"] = float(v[0].get("rsi") or 0) if v else 0
    except:
        d["rsi"] = 0

    # Juros Fed (FRED)
    try:
        obs = requests.get(f"https://api.stlouisfed.org/fred/series/observations?series_id=FEDFUNDS&api_key={FRED_KEY}&file_type=json&limit=1&sort_order=desc", timeout=10).json().get("observations", [{}])
        d["juros_fed"] = float(obs[0].get("value") or 0) if obs else 0
        if d["juros_fed"] >= 5: score -= 1
    except:
        d["juros_fed"] = 0

    # WTI (Yahoo Finance - tempo real, gratuito)
    try:
        yf_wti = requests.get(
            "https://query2.finance.yahoo.com/v8/finance/chart/CL%3DF?interval=1d&range=2d",
            headers={"User-Agent": "Mozilla/5.0"}, timeout=10).json()
        meta_wti = yf_wti.get("chart",{}).get("result",[{}])[0].get("meta",{})
        d["wti"] = float(meta_wti.get("regularMarketPrice") or 0)
        d["brent"] = 0
        try:
            yf_brent = requests.get(
                "https://query2.finance.yahoo.com/v8/finance/chart/BZ%3DF?interval=1d&range=2d",
                headers={"User-Agent": "Mozilla/5.0"}, timeout=8).json()
            meta_brent = yf_brent.get("chart",{}).get("result",[{}])[0].get("meta",{})
            d["brent"] = float(meta_brent.get("regularMarketPrice") or 0)
        except: pass
        if d["wti"] > 90: score -= 1
    except:
        d["wti"] = 0
        d["brent"] = 0

    if score >= 3:    classif = "BULLISH 🟢"
    elif score <= -3: classif = "BEARISH 🔴"
    else:             classif = "NEUTRO 🟡"

    return {"score": score, "classificacao": classif, "dados": d}


def montar_abertura_mercado():
    """Analise de abertura no formato profissional narrativo."""
    from datetime import datetime
    agora    = datetime.now()
    dias_pt  = ["segunda-feira","terça-feira","quarta-feira","quinta-feira","sexta-feira","sábado","domingo"]
    meses_pt = ["janeiro","fevereiro","março","abril","maio","junho","julho","agosto","setembro","outubro","novembro","dezembro"]
    data_str = f"{agora.day} de {meses_pt[agora.month-1]} de {agora.year} ({dias_pt[agora.weekday()]})"

    # ── Coleta de dados ──────────────────────────────────────────────────────
    d = {}

    # IBOV
    try:
        yf = requests.get(
            "https://query1.finance.yahoo.com/v8/finance/chart/%5EBVSP?interval=1d&range=2d",
            headers={"User-Agent": "Mozilla/5.0"}, timeout=10).json()
        meta = yf.get("chart",{}).get("result",[{}])[0].get("meta",{})
        preco = meta.get("regularMarketPrice", 0)
        prev  = meta.get("previousClose", 0) or meta.get("chartPreviousClose", 0)
        d["ibov_preco"] = preco
        d["ibov_ant"]   = prev
        d["ibov_var"]   = round((preco/prev - 1)*100, 2) if prev else 0
        d["ibov_max"]   = meta.get("regularMarketDayHigh", preco)
        d["ibov_min"]   = meta.get("regularMarketDayLow", preco)
    except Exception as e:
        logger.error(f"IBOV: {e}")
        d.update({"ibov_preco":0,"ibov_var":0,"ibov_max":0,"ibov_min":0,"ibov_ant":0})

    # Ações destaque
    try:
        # Ações via Yahoo Finance (sem token)
        acoes_tickers = ["VALE3.SA","PETR4.SA","ITUB4.SA","BBDC4.SA","WEGE3.SA"]
        altas_tmp = []; baixas_tmp = []
        for ticker in acoes_tickers:
            try:
                yf2 = requests.get(
                    f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=2d",
                    headers={"User-Agent": "Mozilla/5.0"}, timeout=5).json()
                m2 = yf2.get("chart",{}).get("result",[{}])[0].get("meta",{})
                p2 = m2.get("regularMarketPrice",0); pv2 = m2.get("previousClose",0)
                if p2 and pv2:
                    var2 = round((p2/pv2-1)*100,2)
                    nome = ticker.replace(".SA","")
                    if var2 > 0: altas_tmp.append(f"{nome} ({var2:+.2f}%)")
                    else: baixas_tmp.append(f"{nome} ({var2:+.2f}%)")
            except: pass
        d["maiores_altas"]  = altas_tmp[:3]
        d["maiores_baixas"] = baixas_tmp[:3]
    except:
        d["maiores_altas"]  = []
        d["maiores_baixas"] = []

    # Dólar
    try:
        td = requests.get(f"https://api.twelvedata.com/quote?symbol=USD/BRL&apikey={TWELVE_DATA_KEY}", timeout=10).json()
        d["dolar_preco"] = float(td.get("close") or 0)
        d["dolar_var"]   = float(td.get("percent_change") or 0)
        d["dolar_open"]  = float(td.get("open") or 0)
    except:
        d.update({"dolar_preco":0,"dolar_var":0,"dolar_open":0})

    # WTI + Brent (Yahoo Finance - tempo real, gratuito)
    try:
        yf_wti = requests.get(
            "https://query2.finance.yahoo.com/v8/finance/chart/CL%3DF?interval=1d&range=2d",
            headers={"User-Agent": "Mozilla/5.0"}, timeout=10).json()
        meta_wti = yf_wti.get("chart",{}).get("result",[{}])[0].get("meta",{})
        d["wti"] = float(meta_wti.get("regularMarketPrice") or 0)
        wti_prev = float(meta_wti.get("chartPreviousClose") or d["wti"])
        d["wti_var"] = round((d["wti"]/wti_prev-1)*100, 2) if wti_prev else 0
    except:
        d["wti"] = 0
        d["wti_var"] = 0
    try:
        yf_brent = requests.get(
            "https://query2.finance.yahoo.com/v8/finance/chart/BZ%3DF?interval=1d&range=2d",
            headers={"User-Agent": "Mozilla/5.0"}, timeout=8).json()
        meta_b = yf_brent.get("chart",{}).get("result",[{}])[0].get("meta",{})
        d["brent"] = float(meta_b.get("regularMarketPrice") or 0)
    except:
        d["brent"] = 0

    # Juros Fed
    try:
        obs = requests.get(f"https://api.stlouisfed.org/fred/series/observations?series_id=FEDFUNDS&api_key={FRED_KEY}&file_type=json&limit=1&sort_order=desc", timeout=10).json().get("observations",[{}])
        d["juros_fed"] = float(obs[0].get("value") or 0) if obs else 0
    except:
        d["juros_fed"] = 0

    # Calendário macro - via Finnhub news + Alpha Vantage sentiment (economic_calendar bloqueado no free)
    agenda = []
    try:
        # Alpha Vantage: top notícias macro do dia
        av_news = requests.get(
            f"https://www.alphavantage.co/query?function=NEWS_SENTIMENT&topics=economy_macro&limit=5&apikey=os.environ.get("ALPHAVANTAGE_KEY","")",
            timeout=12).json().get("feed", [])
        for n in av_news[:5]:
            titulo = n.get("title","")
            sent   = n.get("overall_sentiment_label","Neutral")
            hora   = n.get("time_published","")[:13].replace("T"," ")
            emoji  = "🟢" if "Bull" in sent else ("🔴" if "Bear" in sent else "🟡")
            if titulo:
                agenda.append(f"{emoji} [{hora[-5:]}] {titulo[:80]}")
    except Exception as e:
        logger.warning(f"AlphaVantage calendar: {e}")
    # Finnhub news de alto impacto como complemento
    try:
        fn_news = requests.get(
            f"https://finnhub.io/api/v1/news?category=general&minId=0&token={FINNHUB_KEY}",
            timeout=10).json()
        keywords_imp = ["fed","fomc","cpi","ppi","payroll","gdp","juros","inflacao","inflation","rate","iran","oil"]
        for n in fn_news[:30]:
            h = n.get("headline","").lower()
            if any(k in h for k in keywords_imp):
                import datetime as _dt
                _hora = _dt.datetime.fromtimestamp(n["datetime"], tz=_dt.timezone(_dt.timedelta(hours=-3))).strftime("%H:%M")
                agenda.append(f"📰 [{_hora}] {n['headline'][:80]}")
            if len(agenda) >= 8:
                break
    except Exception as e:
        logger.warning(f"Finnhub news calendar: {e}")

    # Notícias - Finnhub (principal) + Google News RSS (fallback automático)
    noticias = []
    keywords = ["brazil","brasil","ibovespa","ibov","real","brl","petrobras","vale","emergente","fed","rate","iran","oil","petróleo","dólar","bolsa"]

    # Fonte 1: Finnhub
    try:
        for n in requests.get(f"https://finnhub.io/api/v1/news?category=general&minId=0&token={FINNHUB_KEY}", timeout=12).json()[:50]:
            h = n.get("headline","")
            if h and any(k in h.lower() for k in keywords):
                noticias.append(f"[Finnhub] {h}")
            if len(noticias) >= 4:
                break
    except Exception as e:
        logger.warning(f"Finnhub falhou: {e}")

    # Fonte 2: Google News RSS (fallback se Finnhub nao trouxer suficiente)
    if len(noticias) < 3:
        try:
            from xml.etree import ElementTree as ET
            queries = ["ibovespa+bolsa+brasileira", "mercado+financeiro+brasil", "dolar+real+hoje"]
            for q in queries:
                rss = requests.get(
                    f"https://news.google.com/rss/search?q={q}&hl=pt-BR&gl=BR&ceid=BR:pt-419",
                    headers={"User-Agent": "Mozilla/5.0"}, timeout=10).text
                root = ET.fromstring(rss)
                for item in root.findall(".//item")[:5]:
                    titulo = item.find("title")
                    if titulo is not None and titulo.text:
                        t = titulo.text.replace(" - Google News","").strip()
                        if t not in noticias and len(noticias) < 6:
                            noticias.append(f"[Google News] {t}")
                if len(noticias) >= 5:
                    break
        except Exception as e:
            logger.warning(f"Google News RSS falhou: {e}")

    # Fonte 3: Finnhub noticias forex (segundo fallback)
    if len(noticias) < 2:
        try:
            for n in requests.get(f"https://finnhub.io/api/v1/news?category=forex&minId=0&token={FINNHUB_KEY}", timeout=8).json()[:20]:
                h = n.get("headline","")
                if h and len(noticias) < 4:
                    noticias.append(f"[Forex] {h}")
        except:
            pass

    # ── Narrativa GPT-4o ──────────────────────────────────────────────────────
    ibov_dir = "alta" if d.get("ibov_var",0) >= 0 else "queda"
    dol_dir  = "queda" if d.get("dolar_var",0) < 0 else "alta"
    ibov_sinal = "+" if d.get("ibov_var",0) >= 0 else ""
    dol_sinal  = "+" if d.get("dolar_var",0) >= 0 else ""

    # Usar GPT-4o para gerar narrativa fluida no estilo CM Capital
    prompt_narrativa = f"""Você é um analista financeiro sênior de uma corretora brasileira de alto nível.
Escreva uma análise de abertura de mercado PROFISSIONAL e NARRATIVA para hoje, {data_str}.

DADOS DISPONÍVEIS:
- Ibovespa ontem: {ibov_dir} de {abs(d.get('ibov_var',0)):.2f}%, fechou em {d.get('ibov_preco',0):,.0f} pts (máx: {d.get('ibov_max',0):,.0f} | mín: {d.get('ibov_min',0):,.0f})
- Maiores altas de ontem: {', '.join(d.get('maiores_altas',[])) or 'N/D'}
- Maiores baixas de ontem: {', '.join(d.get('maiores_baixas',[])) or 'N/D'}
- Dólar: {dol_dir} de {abs(d.get('dolar_var',0)):.2f}%, cotado a R$ {d.get('dolar_preco',0):.4f}
- WTI: US$ {d.get('wti',0):.2f}/barril
- Juros Fed: {d.get('juros_fed',0):.2f}%
- Notícias relevantes: {chr(10).join(noticias) if noticias else 'Sem notícias de destaque'}
- Agenda do dia: {chr(10).join(agenda) if agenda else 'Sem eventos de alto impacto'}

FORMATO OBRIGATÓRIO (narrativa corrida, sem bullet points, parágrafos completos):

🇧🇷 Cenário Nacional
[2-3 parágrafos sobre o Ibovespa, ações de destaque, macro brasil - fluido e informativo]

🌎 Cenário Internacional
[2 parágrafos sobre dólar, Wall Street, geopolítica, fluxo para emergentes]

🌽 Commodities
[1-2 parágrafos sobre petróleo, minério de ferro, outros relevantes]

📆 Agenda Econômica do Dia
[Parágrafo narrativo sobre os principais eventos do dia e o que esperar]

📍 Conclusão
[1-2 parágrafos de conclusão profissional - o que monitorar, riscos e oportunidades - SEM dar sinal de compra/venda]

REGRAS:
- Narrativa fluida como uma análise de corretora de alto nível
- Nunca mencionar corretoras reais pelo nome
- Dados precisos e concretos
- Profissional mas acessível
- Máximo 600 palavras no total"""

    try:
        narrativa = chamar_ia_rodizio(prompt_narrativa)
        if not narrativa:
            raise Exception("GPT-4o sem resposta")
    except:
        # Fallback: narrativa manual com os dados
        ibov_txt = f"O Ibovespa encerrou o pregão anterior em {ibov_dir} de {abs(d.get('ibov_var',0)):.2f}%, aos {d.get('ibov_preco',0):,.0f} pontos."
        narrativa = f"""🇧🇷 Cenário Nacional
{ibov_txt} {"Maiores altas: " + ", ".join(d.get("maiores_altas",[])) + "." if d.get("maiores_altas") else ""} {"Maiores baixas: " + ", ".join(d.get("maiores_baixas",[])) + "." if d.get("maiores_baixas") else ""}

🌎 Cenário Internacional
O dólar operou em {dol_dir} de {abs(d.get('dolar_var',0)):.2f}%, cotado a R$ {d.get('dolar_preco',0):.4f}. {"Dólar mais fraco favorece o fluxo para emergentes." if d.get("dolar_var",0) < 0 else "Dólar em alta pressiona os mercados emergentes."}

🌽 Commodities
Petróleo WTI: US$ {d.get('wti',0):.2f}/barril. {"Acima de US$ 90, mantém pressão inflacionária global." if d.get("wti",0) > 90 else "Abaixo de US$ 90, aliviando custos."}

📆 Agenda Econômica do Dia
{"Sem eventos de alto impacto confirmados para hoje." if not agenda else chr(10).join(agenda)}

📍 Conclusão
O pregão começa com sinais mistos. Monitore o comportamento do Ibovespa na primeira hora e aguarde confirmação antes de posicionar. Atenção redobrada aos eventos macro do dia."""

    # Montar mensagem final
    msg  = f"📌 *Abertura de Mercado – {data_str}*\n\n"
    msg += narrativa
    msg += f"\n\n_Atualizado: {agora.strftime('%d/%m/%Y %H:%M')}_"
    return msg


def load_historico():
    try:
        if os.path.exists(HISTORICO_FILE):
            with open(HISTORICO_FILE) as f:
                return json.load(f)
    except:
        pass
    return []

def save_historico(data):
    try:
        # Manter apenas os últimos 200 registros
        if len(data) > 200:
            data = data[-200:]
        with open(HISTORICO_FILE, "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"save_historico: {e}")

def registrar_operacao(chat_id, sinal, estrategia, leitura, sentimento, entrada, stop, alvo):
    """Registra uma operacao para aprendizado futuro."""
    hist = load_historico()
    op = {
        "id":         len(hist) + 1,
        "timestamp":  datetime.now().isoformat(),
        "chat_id":    str(chat_id),
        "sinal":      sinal,
        "estrategia": estrategia,
        "leitura":    leitura[:300] if leitura else "",
        "sentimento": sentimento,
        "entrada":    entrada,
        "stop":       stop,
        "alvo":       alvo,
        "resultado":  None,  # preenchido depois com /acertou ou /errou
        "horario":    datetime.now().strftime("%H:%M"),
        "dia_semana": datetime.now().strftime("%A"),
    }
    hist.append(op)
    save_historico(hist)
    return op["id"]

def atualizar_resultado(op_id, resultado, preco_saida=None):
    """Atualiza resultado de uma operacao: acerto, erro ou parcial."""
    hist = load_historico()
    for op in hist:
        if op.get("id") == op_id:
            op["resultado"] = resultado
            if preco_saida:
                op["preco_saida"] = preco_saida
            save_historico(hist)
            return True
    return False

def gerar_contexto_aprendizado(estrategia_nome=None, sinal_tipo=None, horario=None):
    """Gera contexto de aprendizado com base no historico real."""
    hist = load_historico()
    if len(hist) < 3:
        return ""

    # Filtrar operações com resultado conhecido
    com_resultado = [o for o in hist if o.get("resultado") in ["acerto", "erro", "parcial"]]
    if not com_resultado:
        return ""

    # Calcular taxa de acerto geral
    acertos = sum(1 for o in com_resultado if o.get("resultado") == "acerto")
    taxa_geral = acertos / len(com_resultado) * 100

    # Taxa por estratégia (se fornecida)
    contexto = f"📊 HISTÓRICO DE APRENDIZADO ({len(com_resultado)} ops com resultado):\n"
    contexto += f"Taxa geral de acerto: {taxa_geral:.0f}%\n"

    if estrategia_nome:
        est_ops = [o for o in com_resultado if estrategia_nome.lower() in o.get("estrategia","").lower()]
        if est_ops:
            est_acertos = sum(1 for o in est_ops if o.get("resultado") == "acerto")
            taxa_est = est_acertos / len(est_ops) * 100
            contexto += f"Estratégia '{estrategia_nome}': {taxa_est:.0f}% ({len(est_ops)} ops)\n"

    # Padrões recentes (últimas 5 ops)
    recentes = com_resultado[-5:]
    if recentes:
        contexto += "\nÚltimas operações:\n"
        for op in recentes:
            emoji = "✅" if op.get("resultado") == "acerto" else "❌" if op.get("resultado") == "erro" else "⚡"
            contexto += f"{emoji} {op.get('sinal','?')} | {op.get('estrategia','?')[:25]} | {op.get('horario','?')}\n"

    return contexto

def montar_prompt_analise(leitura, sentimento, estrategia, contexto_aprendizado, texto_extra=""):
    """Monta prompt inteligente e fluido para o GPT-4-omni."""
    classif = sentimento.get("classificacao", "NEUTRO")
    score   = sentimento.get("score", 0)
    d       = sentimento.get("dados", {})

    prompt = f"""Você é um trader expert no mercado brasileiro com mais de 10 anos de experiência.
Analise TUDO abaixo e dê um sinal COMPLETO e PRECISO - nunca informação vazia.

═══ LEITURA TÉCNICA DO GRÁFICO ═══
{leitura}

═══ SENTIMENTO DO MERCADO ═══
{classif} (score {score:+d})
IBOV: {d.get('ibov_preco',0):,.0f} ({d.get('ibov_var',0):+.2f}%)
USD/BRL: R$ {d.get('dolar_preco',0):.4f} ({d.get('dolar_var',0):+.2f}%)
WTI: US$ {d.get('wti',0):.2f} | Juros Fed: {d.get('juros_fed',0):.2f}%

═══ ESTRATÉGIA SELECIONADA ═══
{estrategia.get('estrategia_nome','N/A')} - Confiança: {estrategia.get('confianca','N/A')}
{estrategia.get('estrategia_conteudo','')}
Critérios atendidos: {estrategia.get('criterios_atendidos','N/A')}

{f"═══ CONTEXTO EXTRA ═══\n{texto_extra}" if texto_extra else ""}

{f"═══ APRENDIZADO ═══\n{contexto_aprendizado}" if contexto_aprendizado else ""}

═══ REGRAS DE RESPOSTA ═══
1. NUNCA dê "AGUARDA" sem explicar O QUÊ aguardar e POR QUÊ
2. Se lateral: descreva os limites do range e o gatilho para operar
3. Se tendência clara: entre com convicção, explique cada critério
4. Se notícia próxima: mencione e ajuste tamanho de posição
5. Seja FLUIDO como um trader falando para outro trader - não robótico
6. Formato OBRIGATÓRIO de resposta:

CENÁRIO: [descreva o que está acontecendo no gráfico em 2 linhas - fluido]
SETUP: [qual padrão está formado ou por que NÃO está]
ENTRADA: [preço exato ou "aguardar X acontecer"]
STOP: [preço ou "não operar"]
ALVO 1: [preço - Fibonacci]
ALVO 2: [preço - Fibonacci]
SINAL: [COMPRA / VENDA / AGUARDA]
MOTIVO: [1 linha direta - por que esse sinal agora]
ATENÇÃO: [algo importante - notícia, horário, risco]"""

    return prompt

@app.route("/webhook_sentimento", methods=["POST"])
def webhook_sentimento():
    try:
        data    = request.json or {}
        message = data.get("message", {})
        chat_id = message.get("chat", {}).get("id")
        text    = (message.get("text") or "").strip()
        if not chat_id:
            return "ok", 200
        if text == "/start":
            send_telegram(TOKEN_SENTI, chat_id,
                "📊 *ProfitSentiBot ativo!*\n\n"
                "Use /s ou /sentimento para ver a análise de abertura do mercado.\n\n"
                "Ou cole qualquer relatório/notícia de mercado que eu analiso e opino! 🧠")
            return "ok", 200
        if text in ["/s", "/sentimento", "/abertura"]:
            send_telegram(TOKEN_SENTI, chat_id, "⏳ Coletando dados do mercado...")
            try:
                msg = montar_abertura_mercado()
                send_telegram(TOKEN_SENTI, chat_id, msg)
            except Exception as e:
                send_telegram(TOKEN_SENTI, chat_id, f"❌ Erro: {e}")
            return "ok", 200

        # ── Resposta inteligente a textos longos (relatórios, notícias, análises) ──
        if text and len(text) > 80:
            def analisar_texto():
                send_telegram(TOKEN_SENTI, chat_id, "🧠 Analisando o cenário com a IA...")
                sent = coletar_sentimento_local()
                d    = sent.get("dados", {})
                ibov_str = f"{d.get('ibov_preco',0):,.0f} pts ({d.get('ibov_var',0):+.2f}%)"
                dol_str  = f"R$ {d.get('dolar_preco',0):.4f} ({d.get('dolar_var',0):+.2f}%)"
                wti_str  = f"US$ {d.get('wti',0):.2f}"
                prompt = (
                    "Você é um analista de mercado sênior brasileiro, direto como um trader experiente.\n\n"
                    "O usuário enviou este relatório de mercado:\n" + text[:3000] + "\n\n"
                    "Dados atuais em tempo real:\n"
                    f"- Ibovespa: {ibov_str}\n"
                    f"- Dólar: {dol_str}\n"
                    f"- WTI: {wti_str}\n\n"
                    "Com base no relatório e nos dados reais, responda como trader:\n"
                    "1. O QUE ISSO SIGNIFICA para o Ibovespa hoje (alta, baixa, lateral?)\n"
                    "2. PRINCIPAIS RISCOS do dia\n"
                    "3. OPORTUNIDADES - setores ou ativos favorecidos\n"
                    "4. VIÉS DO DIA - comprador, vendedor ou neutro?\n"
                    "5. 1 FRASE FINAL resumindo o humor do mercado\n\n"
                    "Seja direto, objetivo, sem enrolação."
                )
                resposta = chamar_ia_rodizio(prompt)
                if resposta:
                    msg_final = f"🔵 *Análise do Cenário*\n\n{resposta}\n\n_Análise via IA - não é recomendação de investimento_"
                    salvar_sentimento_para_outros_bots(msg_final)  # integração interna
                    send_telegram(TOKEN_SENTI, chat_id, msg_final)
                else:
                    send_telegram(TOKEN_SENTI, chat_id, "❌ Erro ao analisar. Tente novamente.")
            threading.Thread(target=analisar_texto, daemon=True).start()

        return "ok", 200
    except Exception as e:
        logger.error(f"webhook_sentimento: {e}")
        return "ok", 200


@app.route("/sentimento", methods=["GET"])
def endpoint_sentimento():
    try:
        return jsonify(coletar_sentimento_local())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ══════════════════════════════════════════════════════════════════════════════
# BOT 3 - @ProfitEstrategia_bot  → /webhook_estrategia
# ══════════════════════════════════════════════════════════════════════════════


@app.route("/webhook_estrategia", methods=["POST"])
def webhook_estrategia():
    try:
        data    = request.json or {}
        message = data.get("message", {})
        chat_id = message.get("chat", {}).get("id")
        text    = (message.get("text") or "").strip()
        if not chat_id:
            return "ok", 200

        ests = load_estrategias()

        if text == "/start":
            send_telegram(TOKEN_ESTRATEGIA, chat_id,
                "📋 *ProfitEstrategia_bot ativo!*\n\n"
                "Comandos:\n"
                "/list - listar estratégias\n"
                "/ver NOME - ver detalhes\n"
                "/del NOME - remover\n\n"
                "Para *adicionar*, simplesmente envie o texto da estratégia - salvo automaticamente!\n"
                "Exemplo: _Americana 1: compra quando barra fecha acima de todas as médias..._")
            return "ok", 200

        if text in ["/list", "/listar"]:
            if not ests:
                send_telegram(TOKEN_ESTRATEGIA, chat_id,
                    "📋 Nenhuma estratégia cadastrada ainda.\n\nEnvie o texto da estratégia que salvo automaticamente!")
            else:
                msg = f"📋 *Estratégias cadastradas ({len(ests)}):*\n\n"
                for i, nome in enumerate(ests, 1):
                    msg += f"{i}. {nome}\n"
                msg += "\n/ver NOME para detalhes"
                send_telegram(TOKEN_ESTRATEGIA, chat_id, msg)
            return "ok", 200

        if text.startswith("/ver "):
            nome = text[5:].strip()
            if nome in ests:
                send_telegram(TOKEN_ESTRATEGIA, chat_id, f"📌 *{nome}*\n\n{ests[nome]}")
            else:
                # Busca parcial
                encontrados = [n for n in ests if nome.lower() in n.lower()]
                if encontrados:
                    send_telegram(TOKEN_ESTRATEGIA, chat_id, f"📌 *{encontrados[0]}*\n\n{ests[encontrados[0]]}")
                else:
                    send_telegram(TOKEN_ESTRATEGIA, chat_id, f"❌ '{nome}' não encontrada.\n\n/list para ver todas.")
            return "ok", 200

        if text.startswith("/del "):
            nome = text[5:].strip()
            encontrados = [n for n in ests if nome.lower() in n.lower()]
            if encontrados:
                del ests[encontrados[0]]
                save_estrategias(ests)
                send_telegram(TOKEN_ESTRATEGIA, chat_id, f"✅ *{encontrados[0]}* removida.\nTotal: {len(ests)} estratégias.")
            else:
                send_telegram(TOKEN_ESTRATEGIA, chat_id, f"❌ '{nome}' não encontrada.")
            return "ok", 200

        # Qualquer outro texto = salvar como estratégia automaticamente
        if text and len(text) > 10 and not text.startswith("/"):
            def salvar_estrategia():
                try:
                    send_telegram(TOKEN_ESTRATEGIA, chat_id, "⏳ Processando estratégia...")

                    # GPT-4o extrai nome e formata a estratégia
                    prompt = f"""Você é um especialista em trading. O trader enviou uma estratégia abaixo.

TEXTO DO TRADER:
{text}

Faça:
1. Extraia ou crie um NOME curto e descritivo para esta estratégia (máximo 4 palavras)
2. Organize e complete o conteúdo de forma clara e profissional
3. Se precisar de informações técnicas adicionais (horário, indicadores, stop, alvo), complete com base no seu conhecimento de trading
4. Mantenha fiel à intenção do trader

Responda em JSON:
{{
  "nome": "Nome da Estratégia",
  "conteudo": "Conteúdo organizado e completo da estratégia"
}}"""

                    resp = gpt4o(prompt)
                    if resp:
                        import json as json_mod
                        resp_clean = resp.strip()
                        if resp_clean.startswith("```"):
                            import re as re_mod
                            resp_clean = re_mod.sub(r"```[a-z]*\n?", "", resp_clean).strip().rstrip("```").strip()
                        data_est = json_mod.loads(resp_clean)
                        nome_est = data_est.get("nome", f"Estratégia {len(ests)+1}")
                        conteudo_est = data_est.get("conteudo", text)
                    else:
                        # Fallback: usar primeira linha como nome
                        linhas = text.split('\n')
                        nome_est = linhas[0][:40].strip()
                        conteudo_est = text

                    # Verificar se nome já existe
                    if nome_est in ests:
                        nome_est = f"{nome_est} v{len([n for n in ests if nome_est in n])+1}"

                    ests_atual = load_estrategias()
                    ests_atual[nome_est] = conteudo_est
                    save_estrategias(ests_atual)

                    send_telegram(TOKEN_ESTRATEGIA, chat_id,
                        f"✅ *{nome_est}* salva!\n\n"
                        f"📋 Prévia:\n{conteudo_est[:200]}{'...' if len(conteudo_est)>200 else ''}\n\n"
                        f"Total: {len(ests_atual)} estratégias cadastradas.\n"
                        f"/ver {nome_est} para ver completa.")
                except Exception as e:
                    logger.error(f"salvar_estrategia: {e}")
                    send_telegram(TOKEN_ESTRATEGIA, chat_id, f"❌ Erro ao salvar: {str(e)[:100]}")

            threading.Thread(target=salvar_estrategia, daemon=True).start()

        return "ok", 200
    except Exception as e:
        logger.error(f"webhook_estrategia: {e}")
        return "ok", 200

@app.route("/get_all", methods=["GET"])
def get_all():
    return jsonify(load_estrategias())


@app.route("/escolher_estrategia", methods=["POST"])
def escolher_estrategia():
    try:
        data   = request.json or {}
        leitura = data.get("leitura_tecnica", "")
        sent    = data.get("sentimento", {})
        result  = escolher_estrategia_local(leitura, sent)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── ADB WiFi + Gemini Vision ────────────────────────────────────────────────
ANDROID_IP   = "192.168.200.102"
ANDROID_PORT = 5555

def adb_screenshot():
    try:
        import subprocess
        subprocess.run(["adb","connect",f"{ANDROID_IP}:{ANDROID_PORT}"],
            capture_output=True, timeout=10)
        r = subprocess.run(
            ["adb","-s",f"{ANDROID_IP}:{ANDROID_PORT}","exec-out","screencap","-p"],
            capture_output=True, timeout=20)
        return r.stdout if r.returncode == 0 and r.stdout else None
    except Exception as e:
        logger.error(f"ADB: {e}")
        return None

def gemini_vision_tela(image_bytes, pergunta=None):
    import base64
    if not pergunta:
        pergunta = (
            "Analise esta tela do celular Android e descreva em detalhes:\n"
            "1. Qual app está aberto\n"
            "2. O que está sendo exibido\n"
            "3. Informações importantes visíveis\n"
            "4. Se for gráfico de trading: tendência, suporte, resistência e sinal COMPRA/VENDA/AGUARDA"
        )
    try:
        b64 = base64.b64encode(image_bytes).decode()
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_KEY}"
        r = requests.post(url, json={"contents":[{"parts":[
            {"inline_data":{"mime_type":"image/png","data":b64}},
            {"text": pergunta}
        ]}]}, timeout=30)
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        logger.error(f"Gemini Vision: {e}")
        return None

# ══════════════════════════════════════════════════════════════════════════════
# BOT 1 - @ProfitAnalise_bot  → /webhook_analise
# Fluxo: GPT-4o lê gráfico → sentimento local → estratégia local → GPT-4o sinal
# ══════════════════════════════════════════════════════════════════════════════


def transcrever_voz_groq(audio_bytes, ext="ogg"):
    """Transcreve audio usando Groq Whisper (gratuito, ultra-rapido)."""
    try:
        import io
        files = {"file": (f"audio.{ext}", io.BytesIO(audio_bytes), "audio/ogg")}
        data_f = {"model": "whisper-large-v3-turbo", "language": "pt", "response_format": "text"}
        r = requests.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {GROQ_KEY}"},
            files=files, data=data_f, timeout=30
        )
        if r.status_code == 200:
            return r.text.strip()
        logger.error(f"Groq Whisper: {r.status_code} {r.text[:100]}")
        return None
    except Exception as e:
        logger.error(f"transcrever_voz_groq: {e}")
        return None

def interpretar_comando_voz(texto):
    """
    Mapeia texto transcrito para comandos do bot.
    Retorna (comando, texto_extra) ou (None, texto_original).
    """
    if not texto:
        return None, texto
    t = texto.lower().strip()

    # Wi-Fi
    if any(p in t for p in ["wifi", "wi-fi", "wi fi", "internet", "conexão", "rede"]):
        if any(p in t for p in ["velocidade", "rápido", "lento", "mbps", "banda"]):
            return "/velocidade", texto
        if any(p in t for p in ["ping", "latência", "latencia", "ms "]):
            return "/ping", texto
        if any(p in t for p in ["relatório", "relatorio", "completo", "tudo da rede"]):
            return "/relatorio", texto
        return "/wifi", texto

    # Análise de mercado / sinal
    if any(p in t for p in ["sinal", "análise", "analise", "compra", "venda", "aguarda",
                              "ibovespa", "bovespa", "mercado", "tendência", "tendencia",
                              "gráfico", "grafico", "suporte", "resistência", "resistencia"]):
        return "/analise_voz", texto

    # Sentimento
    if any(p in t for p in ["sentimento", "cenário", "cenario", "macro", "risk on", "risk off"]):
        return "/sentimento", texto

    # Estratégia
    if any(p in t for p in ["estratégia", "estrategia", "estratégias", "estrategias"]):
        return "/estrategia_voz", texto

    # Histórico / performance
    if any(p in t for p in ["histórico", "historico", "performance", "acerto", "taxa", "resultado"]):
        return "/historico", texto

    # Pergunta geral para IA
    return "/pergunta_voz", texto

@app.route("/diag", methods=["GET"])
def diag():
    import requests as req2, urllib.request, json as json2, ssl
    results = {}

    # GET tests
    for name, url in {"telegram_get": "https://api.telegram.org", "macrodroid_get": "https://trigger.macrodroid.com/"}.items():
        try:
            r = req2.get(url, timeout=6)
            results[name] = r.status_code
        except Exception as e:
            results[name] = str(e)[:80]

    # POST via urllib (evita proxy do requests)
    try:
        TOKEN = "os.environ.get("TOKEN_ANALISE","")"
        data = json2.dumps({"chat_id": 8255093111, "text": "✅ Bot respondendo! Conexão restabelecida.", "parse_mode": "Markdown"}).encode()
        ctx = ssl.create_default_context()
        req3 = urllib.request.Request(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            data=data, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req3, context=ctx, timeout=12) as resp:
            results["telegram_post_urllib"] = resp.status
    except Exception as e:
        results["telegram_post_urllib"] = str(e)[:120]

    return jsonify(results)

@app.route("/webhook_analise", methods=["POST"])
def webhook_analise():
    try:
        data    = request.json or {}
        message = data.get("message", {})
        chat_id = message.get("chat", {}).get("id")
        text    = (message.get("text") or "").strip()
        photo   = message.get("photo")
        caption = (message.get("caption") or "").strip()
        voice   = message.get("voice") or message.get("audio")
        video   = message.get("video") or message.get("video_note")

        if not chat_id:
            return "ok", 200

        # ── Vídeo → extrai áudio e transcreve ───────────────────────────────
        if video and not text and not photo and not voice:
            send_telegram(TOKEN_ANALISE, chat_id, "🎬 Vídeo recebido! Transcrevendo áudio...")
            def _processar_video():
                try:
                    file_id   = video["file_id"]
                    file_info = requests.get(
                        f"https://api.telegram.org/bot{TOKEN_ANALISE}/getFile?file_id={file_id}",
                        timeout=10).json()
                    file_path = file_info["result"]["file_path"]
                    video_bytes = requests.get(
                        f"https://api.telegram.org/file/bot{TOKEN_ANALISE}/{file_path}",
                        timeout=60).content
                    ext = file_path.split(".")[-1] if "." in file_path else "mp4"
                    transcrito = transcrever_voz_groq(video_bytes, ext)
                    if not transcrito:
                        send_telegram(TOKEN_ANALISE, chat_id, "❌ Não consegui transcrever o vídeo.")
                        return
                    send_telegram(TOKEN_ANALISE, chat_id, f"🗣️ *Transcrição:*\n\n_{transcrito}_")
                    # Interpretar e responder com IA
                    cmd, conteudo = interpretar_comando_voz(transcrito)
                    if cmd == "/pergunta_voz":
                        prompt = (
                            f"Você é um assistente financeiro especializado no mercado brasileiro. "
                            f"O usuário enviou um vídeo com o seguinte conteúdo:\n\n\"{conteudo}\"\n\n"
                            f"Responda de forma clara, direta e útil."
                        )
                        resposta = chamar_ia_rodizio(prompt)
                        send_telegram(TOKEN_ANALISE, chat_id, f"🤖 *Resposta:*\n\n{resposta or 'Não obtive resposta.'}")
                except Exception as e:
                    logger.error(f"processar_video: {e}")
                    send_telegram(TOKEN_ANALISE, chat_id, "❌ Erro ao processar o vídeo.")
            threading.Thread(target=_processar_video, daemon=True).start()
            return "ok", 200

        # ── Áudio / Voz ─────────────────────────────────────────────────────
        if voice and not text and not photo:
            send_telegram(TOKEN_ANALISE, chat_id, "🎙️ Áudio recebido! Transcrevendo...")
            try:
                file_id   = voice["file_id"]
                file_info = requests.get(
                    f"https://api.telegram.org/bot{TOKEN_ANALISE}/getFile?file_id={file_id}",
                    timeout=10).json()
                file_path = file_info["result"]["file_path"]
                audio_bytes = requests.get(
                    f"https://api.telegram.org/file/bot{TOKEN_ANALISE}/{file_path}",
                    timeout=20).content
                ext = file_path.split(".")[-1] if "." in file_path else "ogg"
            except Exception as e:
                logger.error(f"download_voice: {e}")
                send_telegram(TOKEN_ANALISE, chat_id, "❌ Não consegui baixar o áudio.")
                return "ok", 200

            transcrito = transcrever_voz_groq(audio_bytes, ext)
            if not transcrito:
                send_telegram(TOKEN_ANALISE, chat_id, "❌ Não consegui transcrever. Tente novamente ou envie por texto.")
                return "ok", 200

            send_telegram(TOKEN_ANALISE, chat_id, f"🗣️ *Você disse:* _{transcrito}_")

            # Interpretar o que foi dito e redirecionar
            cmd, conteudo = interpretar_comando_voz(transcrito)

            if cmd == "/wifi":
                text = "/wifi"
            elif cmd == "/velocidade":
                text = "/velocidade"
            elif cmd == "/ping":
                text = "/ping"
            elif cmd == "/relatorio":
                text = "/relatorio"
            elif cmd == "/historico":
                text = "/historico"
            elif cmd == "/sentimento":
                # Redirecionar pro bot de sentimento
                send_telegram(TOKEN_ANALISE, chat_id, "🌡️ Consultando sentimento do mercado...")
                def _sent_voz():
                    sent = coletar_sentimento_local()
                    msg = montar_abertura_mercado() if sent else "❌ Erro ao coletar sentimento."
                    send_telegram(TOKEN_ANALISE, chat_id, msg)
                threading.Thread(target=_sent_voz, daemon=True).start()
                return "ok", 200
            elif cmd == "/analise_voz":
                # Análise textual sem imagem
                send_telegram(TOKEN_ANALISE, chat_id, "🧠 Analisando com IA...")
                def _analise_voz():
                    prompt = (
                        f"Você é um trader profissional. O trader perguntou por voz:\n\n"
                        f"\"{conteudo}\"\n\n"
                        f"Responda de forma direta e objetiva como trader para trader. "
                        f"Contexto: mercado brasileiro, Ibovespa. "
                        f"Se pedir sinal, dê COMPRA/VENDA/AGUARDA com justificativa curta."
                    )
                    resposta = chamar_ia_rodizio(prompt)
                    send_telegram(TOKEN_ANALISE, chat_id,
                        f"🤖 *Resposta da IA:*\n\n{resposta or 'Não obtive resposta. Tente novamente.'}")
                threading.Thread(target=_analise_voz, daemon=True).start()
                return "ok", 200
            elif cmd == "/pergunta_voz":
                # Pergunta geral para IA
                send_telegram(TOKEN_ANALISE, chat_id, "🧠 Processando sua pergunta...")
                def _pergunta_voz():
                    prompt = (
                        f"Você é um assistente financeiro especializado em mercado brasileiro. "
                        f"O usuário perguntou por voz:\n\n\"{conteudo}\"\n\n"
                        f"Responda de forma clara, direta e útil."
                    )
                    resposta = chamar_ia_rodizio(prompt)
                    send_telegram(TOKEN_ANALISE, chat_id,
                        f"🤖 *Resposta:*\n\n{resposta or 'Não obtive resposta.'}")
                threading.Thread(target=_pergunta_voz, daemon=True).start()
                return "ok", 200
            elif cmd == "/estrategia_voz":
                text = "/estrategias"
            # Se mapeou para comando de texto, deixa cair nos handlers abaixo

        if text == "/start":
            send_telegram(TOKEN_ANALISE, chat_id,
                "📊 *ProfitAnalise_bot ativo!*\n\n"
                "Envie uma imagem do gráfico e receba o sinal.\n\n"
                "📱 *Leitura de tela:*\n"
                "/ver - captura e analisa a tela do celular\n"
                "/ver [pergunta] - captura com pergunta específica\n"
                "/ip 192.168.x.x - configura o IP do celular\n\n"
                "📶 *Wi-Fi:*\n"
                "/wifi - status + ping + IP da rede\n"
                "/velocidade - teste de velocidade\n"
                "/ping - latência com Google\n"
                "/relatorio - relatório completo da rede\n\n"
                "Após o sinal: /acertou N ou /errou N")
            return "ok", 200

        # ── Comandos Wi-Fi ───────────────────────────────────────────────────
        import socket as _sock, subprocess as _subp, time as _tm

        def _wifi_ping(host="8.8.8.8"):
            try:
                r = _subp.run(["ping","-c","4",host], capture_output=True, text=True, timeout=15)
                for line in r.stdout.split("\n"):
                    if "min/avg/max" in line or "rtt" in line:
                        parts = line.split("=")[-1].strip().split("/")
                        if len(parts) >= 2:
                            return float(parts[1])
            except: pass
            return None

        def _wifi_ip_ext():
            try:
                return requests.get("https://api.ipify.org?format=json", timeout=5).json()["ip"]
            except: return "N/A"

        def _wifi_ip_int():
            try:
                s = _sock.socket(_sock.AF_INET, _sock.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80)); ip = s.getsockname()[0]; s.close(); return ip
            except: return "N/A"

        def _wifi_velocidade():
            try:
                start = _tm.time()
                r = requests.get("http://speedtest.tele2.net/10MB.zip", stream=True, timeout=30)
                total = 0
                for chunk in r.iter_content(1024 * 1024):
                    total += len(chunk)
                    if total >= 5 * 1024 * 1024: break
                elapsed = _tm.time() - start
                return round((total * 8) / (elapsed * 1_000_000), 1)
            except: return None

        if text == "/wifi":
            send_telegram(TOKEN_ANALISE, chat_id, "📶 Verificando rede...")
            ping = _wifi_ping()
            ip_ext = _wifi_ip_ext()
            ip_int = _wifi_ip_int()
            p = f"{ping:.1f}ms" if ping else "N/A"
            if ping:
                if ping < 50: q = "🟢 Excelente"
                elif ping < 100: q = "🟡 Boa"
                elif ping < 200: q = "🟠 Regular"
                else: q = "🔴 Ruim"
            else: q = "❌ Sem resposta"
            send_telegram(TOKEN_ANALISE, chat_id,
                f"📶 *Status da Rede*\n\n"
                f"📡 Ping: `{p}` - {q}\n"
                f"🌐 IP Externo: `{ip_ext}`\n"
                f"🏠 IP Interno: `{ip_int}`\n"
                f"🕒 {datetime.now().strftime('%H:%M:%S')}")
            return "ok", 200

        if text == "/ping":
            send_telegram(TOKEN_ANALISE, chat_id, "📡 Testando latência...")
            ping = _wifi_ping("8.8.8.8")
            if ping:
                if ping < 50: e, q = "🟢", "Excelente"
                elif ping < 100: e, q = "🟡", "Boa"
                elif ping < 200: e, q = "🟠", "Regular"
                else: e, q = "🔴", "Ruim"
                send_telegram(TOKEN_ANALISE, chat_id,
                    f"📡 *Ping*\n\n{e} `{ping:.1f}ms` - {q}\n"
                    f"Servidor: Google DNS (8.8.8.8)\n"
                    f"🕒 {datetime.now().strftime('%H:%M:%S')}")
            else:
                send_telegram(TOKEN_ANALISE, chat_id, "❌ Não foi possível medir o ping.")
            return "ok", 200

        if text == "/velocidade":
            send_telegram(TOKEN_ANALISE, chat_id, "⚡ Testando velocidade... (até 30s)")
            def _medir_vel():
                speed = _wifi_velocidade()
                if speed:
                    e = "🟢 Ótimo" if speed >= 50 else ("🟡 Bom" if speed >= 20 else "🔴 Lento")
                    send_telegram(TOKEN_ANALISE, chat_id,
                        f"⚡ *Velocidade de Download*\n\n{e}: `{speed} Mbps`\n"
                        f"🕒 {datetime.now().strftime('%H:%M:%S')}")
                else:
                    send_telegram(TOKEN_ANALISE, chat_id, "❌ Não foi possível testar. Use /ping para verificar.")
            threading.Thread(target=_medir_vel, daemon=True).start()
            return "ok", 200

        if text == "/relatorio":
            send_telegram(TOKEN_ANALISE, chat_id, "📊 Gerando relatório da rede...")
            def _relatorio():
                try:
                    r_ok = requests.get("https://www.google.com", timeout=5); status = "✅ Online"
                except: status = "❌ Offline"
                ip_ext = _wifi_ip_ext()
                ip_int = _wifi_ip_int()
                ping = _wifi_ping()
                p = f"{ping:.1f}ms" if ping else "N/A"
                qual = ("🟢 Excelente" if ping < 50 else ("🟡 Boa" if ping < 100 else ("🟠 Regular" if ping < 200 else "🔴 Ruim"))) if ping else "N/A"
                send_telegram(TOKEN_ANALISE, chat_id,
                    f"📊 *Relatório da Rede*\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"🌐 Status: {status}\n"
                    f"📤 IP Externo: `{ip_ext}`\n"
                    f"🏠 IP Interno: `{ip_int}`\n"
                    f"📡 Ping: `{p}` - {qual}\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"🕒 {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n\n"
                    f"💡 Use /velocidade para testar a banda")
            threading.Thread(target=_relatorio, daemon=True).start()
            return "ok", 200

        # ── Configurar IP do celular ─────────────────────────────────────────
        if text.startswith("/ip "):
            novo_ip = text.split("/ip ", 1)[1].strip()
            global ANDROID_IP
            ANDROID_IP = novo_ip
            send_telegram(TOKEN_ANALISE, chat_id,
                f"✅ IP configurado: *{novo_ip}*\nAgora use /ver para capturar a tela!")
            return "ok", 200

        # ── Captura de tela + Gemini Vision ─────────────────────────────────
        if text.startswith("/ver"):
            pergunta_extra = text[4:].strip() if len(text) > 4 else None
            send_telegram(TOKEN_ANALISE, chat_id, "📸 Capturando tela do celular...")
            if ANDROID_IP == "SEU_IP_AQUI":
                send_telegram(TOKEN_ANALISE, chat_id,
                    "⚠️ *IP não configurado!*\n\n"
                    "Me manda o IP do seu A56:\n"
                    "Configurações → WiFi → toca na rede → IP\n\n"
                    "Exemplo: `/ip 192.168.1.100`")
                return "ok", 200
            img = adb_screenshot()
            if not img:
                send_telegram(TOKEN_ANALISE, chat_id,
                    "❌ Não conectei ao celular.\n\n"
                    "Verifique:\n1. WiFi ligado\n2. Depuração WiFi ativa\n"
                    "3. IP correto com /ip 192.168.x.x")
                return "ok", 200
            send_telegram(TOKEN_ANALISE, chat_id, "🧠 Analisando com Gemini Vision...")
            analise = gemini_vision_tela(img, pergunta_extra)
            if analise:
                requests.post(f"https://api.telegram.org/bot{TOKEN_ANALISE}/sendPhoto",
                    files={"photo": ("tela.png", img, "image/png")},
                    data={"chat_id": chat_id, "caption": "📱 Tela capturada"},
                    timeout=30)
                send_telegram(TOKEN_ANALISE, chat_id, f"🔍 *Análise:*\n\n{analise}")
            else:
                send_telegram(TOKEN_ANALISE, chat_id, "❌ Erro na análise. Tente novamente.")
            return "ok", 200

        # Feedback de aprendizado
        if text.startswith("/acertou") or text.startswith("/errou"):
            partes = text.split()
            resultado = "acerto" if text.startswith("/acertou") else "erro"
            if len(partes) >= 2 and partes[1].isdigit():
                op_id = int(partes[1])
                ok = atualizar_resultado(op_id, resultado)
                hist = load_historico()
                com_res = [o for o in hist if o.get("resultado") in ["acerto","erro"]]
                acertos = sum(1 for o in com_res if o.get("resultado") == "acerto")
                taxa = acertos/len(com_res)*100 if com_res else 0
                emoji_r = "✅" if resultado == "acerto" else "❌"
                send_telegram(TOKEN_ANALISE, chat_id,
                    f"{emoji_r} Op #{op_id} registrada como *{resultado}*!\n\n"
                    f"📊 Taxa de acerto: {taxa:.0f}% ({len(com_res)} ops)" if ok
                    else f"❌ Op #{op_id} não encontrada.")
            else:
                send_telegram(TOKEN_ANALISE, chat_id, "Use: /acertou 5 ou /errou 5")
            return "ok", 200

        if text in ["/historico", "/stats"]:
            hist = load_historico()
            com_res = [o for o in hist if o.get("resultado") in ["acerto","erro"]]
            total = len(hist)
            if not com_res:
                send_telegram(TOKEN_ANALISE, chat_id,
                    f"📊 {total} operações registradas\nNenhum resultado confirmado ainda.\n\nUse /acertou N ou /errou N após cada sinal.")
            else:
                acertos = sum(1 for o in com_res if o.get("resultado") == "acerto")
                taxa = acertos/len(com_res)*100
                msg = f"📊 *PERFORMANCE*\n\n"
                msg += f"Total ops: {total} | Com resultado: {len(com_res)}\n"
                msg += f"Taxa de acerto: {taxa:.0f}% ({acertos}/{len(com_res)})\n\n"
                ests = {}
                for op in com_res:
                    e = op.get("estrategia","?")[:25]
                    if e not in ests: ests[e] = {"a":0,"t":0}
                    ests[e]["t"] += 1
                    if op.get("resultado") == "acerto": ests[e]["a"] += 1
                msg += "*Por estratégia:*\n"
                for e, v in sorted(ests.items(), key=lambda x: x[1]["a"]/x[1]["t"], reverse=True):
                    msg += f"• {e}: {v['a']/v['t']*100:.0f}% ({v['t']} ops)\n"
                send_telegram(TOKEN_ANALISE, chat_id, msg)
            return "ok", 200

        if not photo and not (text and len(text) > 0):
            return "ok", 200

        # ── Qualquer texto curto → resposta inteligente com IA ───────────────
        if not photo and text and len(text) <= 80:
            def _resposta_texto():
                send_telegram(TOKEN_ANALISE, chat_id, "🤖 Pensando...")
                prompt = (
                    f"Você é um assistente de trading e mercado financeiro brasileiro. "
                    f"Responda de forma direta e útil. Contexto: Ibovespa, day trade, análise técnica.\n\n"
                    f"Usuário disse: \"{text}\"\n\n"
                    f"Se for uma saudação, responda com simpatia e diga que está pronto para ajudar. "
                    f"Se for uma dúvida técnica, responda com precisão. "
                    f"Se não entender, peça para repetir."
                )
                resposta = chamar_ia_rodizio(prompt)
                send_telegram(TOKEN_ANALISE, chat_id, resposta or "Pode repetir? Não entendi bem.")
            threading.Thread(target=_resposta_texto, daemon=True).start()
            return "ok", 200

        # ── Texto longo (relatório/análise de mercado) → raciocina como analista ──
        if not photo and text and len(text) > 80:
            def analisar_relatorio():
                send_telegram(TOKEN_ANALISE, chat_id, "🧠 Lendo o relatório e raciocínando com IA...")
                sent = coletar_sentimento_local()
                d    = sent.get("dados", {})
                est  = load_estrategias()
                nomes_est = ", ".join(list(est.keys())[:5]) if est else "Americanas, Fibonacci VAR"
                ibov_str2 = f"{d.get('ibov_preco',0):,.0f} pts ({d.get('ibov_var',0):+.2f}%)"
                dol_str2  = f"R$ {d.get('dolar_preco',0):.4f} ({d.get('dolar_var',0):+.2f}%)"
                wti_str2  = f"US$ {d.get('wti',0):.2f}"
                prompt = (
                    "Você é um trader institucional sênior com 20 anos de experiência no mercado brasileiro.\n\n"
                    "O usuário enviou este relatório de mercado:\n" + text[:3000] + "\n\n"
                    "Dados atuais:\n"
                    f"- Ibovespa: {ibov_str2}\n"
                    f"- Dólar: {dol_str2}\n"
                    f"- WTI: {wti_str2}\n"
                    f"- Estratégias: {nomes_est}\n\n"
                    "Analise como trader, não como economista:\n"
                    "1. IMPACTO NO IBOVESPA - abertura e durante o dia?\n"
                    "2. IMPACTO NO DÓLAR - tendência para o câmbio?\n"
                    "3. IMPACTO NAS COMMODITIES - petróleo, minério, agro?\n"
                    "4. SETORES FAVORECIDOS - ações/setores que ganham?\n"
                    "5. SETORES PREJUDICADOS - o que evitar?\n"
                    "6. VIÉS DO PREGÃO - comprador ou vendedor? Horário de volatilidade?\n"
                    "7. SINAL MACRO - RISK ON ou RISK OFF?\n\n"
                    "Seja direto. Fale como trader experiente para outro trader."
                )
                resposta = chamar_ia_rodizio(prompt)
                if resposta:
                    msg_final = (
                        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        "📊 *ANÁLISE DO RELATÓRIO*\n"
                        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"{resposta}\n\n"
                        "_Envie a foto do gráfico para o sinal de entrada_"
                    )
                    send_telegram(TOKEN_ANALISE, chat_id, msg_final)
                else:
                    send_telegram(TOKEN_ANALISE, chat_id, "❌ Erro ao analisar. Tente novamente.")
            threading.Thread(target=analisar_relatorio, daemon=True).start()
            return "ok", 200

        def processar():
            try:
                # sem mensagem de espera - responde direto com a analise

                # ── Baixar imagem ────────────────────────────────────────────
                imagem_bytes = None
                texto_extra  = caption if caption else text
                if photo:
                    try:
                        file_id   = photo[-1]["file_id"]
                        file_info = requests.get(
                            f"https://api.telegram.org/bot{TOKEN_ANALISE}/getFile?file_id={file_id}",
                            timeout=10).json()
                        file_path = file_info["result"]["file_path"]
                        imagem_bytes = requests.get(
                            f"https://api.telegram.org/file/bot{TOKEN_ANALISE}/{file_path}",
                            timeout=20).content
                    except Exception as e:
                        logger.error(f"download_img: {e}")

                # PASSO 1: Ler TODOS os elementos visuais da captura de tela
                send_telegram(TOKEN_ANALISE, chat_id, "Analisando...")

                aviso_sem_imagem = ""
                if not imagem_bytes:
                    aviso_sem_imagem = "\n⚠️ Nenhuma imagem recebida - analise baseada apenas em texto."

                prompt_tecnica = (
                    "Voce e um especialista em leitura de graficos de trading com visao computacional apurada.\n"
                    "Analise a imagem inteira com ZOOM MENTAL — examine cada regiao: cabecalho, eixo de preco, legenda das medias, painel de volume, candles.\n\n"
                    "LEIA E TRANSCREVA EXATAMENTE, numero por numero, o que esta visivel:\n\n"
                    "ATIVO: nome ou codigo exato — leia o cabecalho/titulo da janela (ex: WINM26, PETR4, IBOV, EUR/USD, BTC/USD)\n"
                    "TIMEFRAME: intervalo do grafico (ex: 5min, 15min, 1h, D, 1S) — leia o seletor de periodo\n"
                    "PRECO ATUAL: numero exato no eixo direito ou label flutuante (ex: 131.250)\n"
                    "ABERTURA: se visivel no OHLC ou cabecalho\n"
                    "MAXIMA: valor exato visivel\n"
                    "MINIMA: valor exato visivel\n"
                    "FECHAMENTO ANTERIOR: se visivel\n"
                    "VARIACAO: percentual exato (ex: +0.35% ou -1.2%)\n\n"
                    "MEDIAS MOVEIS — leia o valor numerico exato de cada legenda colorida:\n"
                    "  EMA9 (linha vermelha fina): valor numerico exato | posicao: ACIMA ou ABAIXO do preco\n"
                    "  MA20 (linha azul): valor numerico exato | posicao: ACIMA ou ABAIXO do preco\n"
                    "  MA200 (linha preta): valor numerico exato | posicao: ACIMA ou ABAIXO do preco\n"
                    "  VWAP (linha tracejada/colorida): valor numerico exato | posicao: ACIMA ou ABAIXO do preco\n"
                    "  OUTRAS MEDIAS: se houver, nome e valor\n\n"
                    "ULTIMO CANDLE (o mais recente, direita do grafico):\n"
                    "  - Cor: VERDE (alta) ou VERMELHO (baixa)\n"
                    "  - Tamanho do corpo: GRANDE (>70% do range) / MEDIO / PEQUENO / DOJI (<20%)\n"
                    "  - Sombra superior: tem? proporcional ao corpo?\n"
                    "  - Sombra inferior: tem? proporcional ao corpo?\n"
                    "  - Padrao reconhecivel: martelo, enforcado, engolfo, estrela, doji, etc\n\n"
                    "VOLUME: numero exato do ultimo candle | comparado com media: ALTO / NORMAL / BAIXO\n"
                    "SUPORTE mais proximo abaixo do preco: nivel exato visivel (linha horizontal, fundo anterior)\n"
                    "RESISTENCIA mais proxima acima do preco: nivel exato visivel\n"
                    "IFR/RSI: valor numerico se houver painel separado | nivel: sobrecomprado(>70) / neutro / sobrevendido(<30)\n"
                    "OUTROS INDICADORES: MACD, Bandas de Bollinger, estocástico — se visivel, descreva\n\n"
                    + (f"Informacao adicional do usuario: {texto_extra}\n\n" if texto_extra else "") +
                    "REGRAS ABSOLUTAS:\n"
                    "- Leia TODOS os numeros das legendas das medias — eles estao escritos na tela\n"
                    "- NUNCA invente ou estime valores — se nao conseguir ler, escreva: nao legivel na imagem\n"
                    "- NUNCA escreva 'aproximadamente' ou 'em torno de' — numero exato ou nao legivel\n"
                    "- Se o grafico for de ativo internacional (S&P, DXY, BTC, EUR/USD), identifique normalmente\n"
                    "- ACIMA = media esta acima do preco atual | ABAIXO = media esta abaixo do preco atual\n"
                    "- Se a imagem estiver cortada ou escura, descreva o que da pra ver e sinalize"
                )

                # LEITURA DA IMAGEM - Rodízio sequencial
                # Ordem: Gemini → GPT-4o → Groq → OpenRouter
                # Cada IA usa até acabar crédito, depois passa pra próxima automaticamente
                leitura_tecnica = None
                img_url = None
                if imagem_bytes:
                    # Hospedar imagem em URL pública para IAs que aceitam URL (Groq, OpenRouter)
                    try:
                        img_url, _ = salvar_imagem_temp(imagem_bytes)
                        logger.info(f"Imagem hospedada: {img_url}")
                    except Exception as e_img:
                        logger.error(f"salvar_imagem_temp: {e_img}")

                    leitura_tecnica, ia_usada = ler_imagem_rodizio(
                        prompt_tecnica, imagem_bytes, img_url
                    )
                    if ia_usada:
                        logger.info(f"Leitura feita por: {ia_usada}")
                else:
                    # Sem imagem - rodízio texto
                    leitura_tecnica = (
                        gemini(prompt_tecnica) or
                        gpt4o(prompt_tecnica) or
                        chamar_ia_rodizio(prompt_tecnica)
                    )

                if not leitura_tecnica:
                    send_telegram(TOKEN_ANALISE, chat_id, "Nao consegui ler o grafico. Reenvie a foto.")
                    return

                # PASSO 2: Identificar o ativo com múltiplas estratégias
                import re as _re
                ticker_encontrado = None
                dados_reais = ""

                # 2a. Regex direto no texto da IA
                m = _re.search(r'\b(WIN[A-Z]\d{2}|WDO[A-Z]\d{2}|[A-Z]{4}[0-9]{1,2}|IBOV|IBOVESPA|PETR4|VALE3|ITUB4|BBDC4|ABEV3)\b',
                               leitura_tecnica, _re.IGNORECASE)
                if m:
                    ticker_encontrado = m.group(1).upper()

                # 2b. Se não achou, tentar identificar pelo nome/preço via IA
                if not ticker_encontrado:
                    try:
                        prompt_id = (
                            f"Com base nessa analise de grafico:\n{leitura_tecnica[:400]}\n\n"
                            "Responda APENAS o ticker/codigo do ativo (ex: PETR4, WINM26, VALE3, IBOV). "
                            "Se for mini-indice responda WIN. Se for mini-dolar responda WDO. "
                            "Responda so o codigo, nada mais."
                        )
                        ticker_ia = (gemini(prompt_id) or chamar_ia_rodizio(prompt_id) or "").strip().upper()
                        ticker_ia = _re.sub(r'[^A-Z0-9]', '', ticker_ia)[:8]
                        if ticker_ia:
                            ticker_encontrado = ticker_ia
                            logger.info(f"Ticker identificado por IA: {ticker_ia}")
                    except Exception as e_id:
                        logger.error(f"identificar_ticker_ia: {e_id}")

                # 2c. Se ainda não achou, buscar na web pelo preço visível
                if not ticker_encontrado:
                    try:
                        preco_m = _re.search(r'(?:preco|price|ultimo|last)[^\d]*(\d[\d\.,]+)', leitura_tecnica, _re.IGNORECASE)
                        if preco_m:
                            preco_str = preco_m.group(1).replace(',','.')
                            res_web = google_custom_search(f'ativo bolsa Brasil preco {preco_str} hoje', num=2)
                            if res_web:
                                for txt in res_web:
                                    m2 = _re.search(r'\b([A-Z]{4}[0-9]{1,2}|WIN[A-Z]\d{2})\b', txt)
                                    if m2:
                                        ticker_encontrado = m2.group(1)
                                        logger.info(f"Ticker via web: {ticker_encontrado}")
                                        break
                    except Exception as e_web:
                        logger.error(f"buscar_ticker_web: {e_web}")

                # 2d. Buscar cotação real (Brapi para ações BR, Yahoo para futuros)
                try:
                    if ticker_encontrado:
                        # Futuros WIN/WDO - usar Yahoo Finance
                        if ticker_encontrado.startswith("WIN") or ticker_encontrado.startswith("WDO"):
                            yf_symbol = "^BVSP" if "WIN" in ticker_encontrado else "BRL=X"
                            r_yf = requests.get(
                                f"https://query2.finance.yahoo.com/v8/finance/chart/{yf_symbol}",
                                params={"interval":"1m","range":"1d"},
                                headers={"User-Agent":"Mozilla/5.0"}, timeout=8)
                            meta = r_yf.json()["chart"]["result"][0]["meta"]
                            preco = meta.get("regularMarketPrice")
                            if preco:
                                dados_reais = f"\nDados reais {ticker_encontrado}: {preco:,.0f} pts"
                        else:
                            # Ações BR - Brapi
                            r_b = requests.get(
                                f"https://brapi.dev/api/quote/{ticker_encontrado}",
                                params={"token": BRAPI_TOKEN}, timeout=8).json()
                            res_b = r_b.get("results", [{}])[0]
                            preco  = res_b.get("regularMarketPrice")
                            var    = res_b.get("regularMarketChangePercent", 0)
                            maxima = res_b.get("regularMarketDayHigh")
                            minima = res_b.get("regularMarketDayLow")
                            if preco:
                                dados_reais = f"\nDados reais {ticker_encontrado}: R$ {preco:,.2f} ({var:+.2f}%)"
                                if maxima: dados_reais += f" | Max: {maxima:,.2f}"
                                if minima: dados_reais += f" | Min: {minima:,.2f}"
                except Exception as e_b:
                    logger.error(f"cotacao_real: {e_b}")

                # PASSO 2a-extra: Integração interna — sentimento do mercado (silencioso)
                sentimento_interno = consultar_sentimento_interno()
                if sentimento_interno:
                    dados_reais += f"\nSentimento de mercado (ProfitSenti): {sentimento_interno}"

                # PASSO 2b: Indicadores tecnicos via Yahoo Finance (EMA9, MA20, RSI14)
                indicadores_txt = ""
                try:
                    if ticker_encontrado:
                        inds = calcular_indicadores_yahoo(ticker_encontrado, interval="5m")
                        indicadores_txt = formatar_indicadores(ticker_encontrado, inds)
                        if indicadores_txt:
                            dados_reais += indicadores_txt
                except Exception as e_ind:
                    logger.error(f"indicadores_yahoo: {e_ind}")

                # PASSO 2d-extra: Cálculos matemáticos automáticos (Fibonacci, R:R, Confluência)
                try:
                    vals = extrair_valores_da_leitura(leitura_tecnica or "")
                    if vals.get("preco"):
                        calculos_txt = formatar_calculos_para_prompt(
                            preco   = vals.get("preco", 0),
                            ema9    = vals.get("ema9"),
                            ma20    = vals.get("ma20"),
                            ma200   = vals.get("ma200"),
                            vwap    = vals.get("vwap"),
                            minima  = vals.get("minima"),
                            maxima  = vals.get("maxima"),
                        )
                        if calculos_txt:
                            dados_reais += calculos_txt
                except Exception as e_calc:
                    logger.error(f"calculos_matematicos: {e_calc}")

                # PASSO 2e: Buscar na web para confirmar/enriquecer o ativo identificado
                info_web_ativo = ""
                try:
                    if ticker_encontrado:
                        query_web = f"{ticker_encontrado} cotacao hoje bolsa"
                        res_web2 = google_custom_search(query_web, num=3)
                        if res_web2:
                            info_web_ativo = " | ".join(res_web2[:2])
                    elif leitura_tecnica:
                        # Sem ticker - busca pelo preco visivel para identificar o ativo
                        preco_m2 = _re.search(r'PRECO[:\s]+([0-9][\d\.,]+)', leitura_tecnica, _re.IGNORECASE)
                        if preco_m2:
                            q = f"ativo bolsa preco {preco_m2.group(1)} mini contrato B3"
                            res_web2 = google_custom_search(q, num=2)
                            if res_web2:
                                info_web_ativo = " | ".join(res_web2[:2])
                                # Tentar extrair ticker do resultado web
                                for txt_w in res_web2:
                                    mw = _re.search(r'\b(WIN[A-Z]\d{2}|WDO[A-Z]\d{2}|[A-Z]{4}[0-9]{1,2})\b', txt_w)
                                    if mw and not ticker_encontrado:
                                        ticker_encontrado = mw.group(1)
                                        break
                except Exception as e_w2:
                    logger.error(f"busca_web_ativo: {e_w2}")

                # PASSO 3: Noticias
                noticias = ""
                try:
                    if ticker_encontrado:
                        res_g = google_custom_search(ticker_encontrado + " bolsa hoje", num=3)
                        if res_g:
                            noticias = " | ".join(res_g[:3])
                except Exception as e_gs:
                    logger.error(f"google_search: {e_gs}")

                # PASSO 3b: Boletim Focus BCB + Commodities + FRED macro global
                try:
                    focus_dados = buscar_focus_bcb()
                    focus_txt = formatar_focus(focus_dados)
                    if focus_txt:
                        noticias += focus_txt
                except Exception as e_focus:
                    logger.error(f"focus_bcb: {e_focus}")

                try:
                    commodities = buscar_commodities()
                    fred_dados  = buscar_fred_macro()
                    macro_txt   = formatar_macro_global(commodities, fred_dados)
                    if macro_txt:
                        noticias += macro_txt
                except Exception as e_macro:
                    logger.error(f"macro_global: {e_macro}")

                # PASSO 4: Estrategia e contexto
                est = escolher_estrategia_local(leitura_tecnica, {})
                contexto_aprendizado = gerar_contexto_aprendizado(horario=datetime.now().strftime("%H:%M"))
                classif = "N/A"
                score = 0
                d = {}

                # Carregar memoria de conversas anteriores
                memoria_anterior = carregar_memoria(chat_id)

                prompt_sinal = f"""Voce e um trader profissional de day trade. Analise e responda EXATAMENTE no formato abaixo, sem adicionar nada fora dele.

=== DADOS DO GRAFICO ===
{leitura_tecnica}

=== DADOS REAIS DE MERCADO ===
{dados_reais if dados_reais else "indisponivel — usar dados do grafico"}

=== CONTEXTO MACRO ===
{noticias if noticias else "sem noticias relevantes no momento"}

=== ESTRATEGIA DE REFERENCIA ===
{est.get("estrategia_nome","N/A")}: {est.get("estrategia_conteudo","")[:300]}

=== HISTORICO ===
{memoria_anterior if memoria_anterior else "primeira analise desta sessao"}

INSTRUCOES DE ANALISE (siga esta logica, nao repita na resposta):
1. Identifique o ativo e preco EXATO da leitura — nunca use valor diferente
2. Verifique posicao de CADA media: preco ACIMA ou ABAIXO — nunca inverta
3. Avalie o ultimo candle: cor, tamanho, sombras — isso define forca ou fraqueza
4. Verifique confluencia: quantas medias apontam para o mesmo lado?
   - 3 ou 4 medias alinhadas = sinal forte
   - 2 medias = sinal moderado
   - Medias mistas = AGUARDA
5. Defina suporte e resistencia pelos niveis visiveis no grafico
6. Calcule entrada, stop e alvo baseado na estrategia e nos niveis reais
   - Stop maximo: 150 pontos para WIN/WDO | 2% para acoes
   - Alvo minimo: risco/retorno 1:2 ou melhor
7. Se nao houver confluencia clara = AGUARDA (nunca force sinal)

FORMATO OBRIGATORIO (responda APENAS isso, linha por linha):

[ATIVO] | [PRECO EXATO] | [TIMEFRAME]
EMA9 [ACIMA/ABAIXO] | MA20 [ACIMA/ABAIXO] | MA200 [ACIMA/ABAIXO] | VWAP [ACIMA/ABAIXO]
Candle: [COR] | [TAMANHO] | [PADRAO se houver]
Suporte: [numero] | Resistencia: [numero]
Tendencia: [ALTA/BAIXA/LATERAL] — [motivo objetivo em 1 linha]
[COMPRA/VENDA/AGUARDA] — Entrada: [numero] | Stop: [numero] | Alvo 1: [numero] | Alvo 2: [numero]
[apenas o numero da entrada na ultima linha — para copiar rapido]

REGRAS DE OURO:
- Preco MAIOR que media = preco ACIMA da media (nao inverta)
- NUNCA use o mesmo valor para entrada e stop
- NUNCA force COMPRA ou VENDA sem confluencia de pelo menos 2 medias
- NUNCA adicione texto fora do formato — zero explicacoes, zero emojis, zero markdown
- Se a imagem nao permitir leitura precisa = responda: IMAGEM ILEGIVEL — reenvie com melhor resolucao"""

                resp  = gemini(prompt_sinal) or chamar_ia_rodizio(prompt_sinal) or gpt4o(prompt_sinal)
                sinal = extrair_sinal(resp)

                # Enviar analise no @ProfitAnalise_bot
                send_telegram(TOKEN_ANALISE, chat_id, resp or "Nao consegui gerar analise. Tente novamente.")

                # Salvar na memoria para retomar depois
                import re as _rem
                tf_m = _rem.search(r'TIMEFRAME[:\s]+(\S+)', leitura_tecnica or "")
                timeframe_encontrado = tf_m.group(1) if tf_m else "?"
                salvar_memoria(chat_id, ticker_encontrado or "?", timeframe_encontrado, sinal, (resp or "")[:200])

                # Registrar
                import re as re_mod
                m_entrada = re_mod.search(r"ENTRADA[:\s]+([\d.,]+)", resp or "")
                m_stop    = re_mod.search(r"STOP[:\s]+([\d.,]+)", resp or "")
                m_alvo1   = re_mod.search(r"ALVO 1[:\s]+([\d.,]+)", resp or "")
                m_alvo2   = re_mod.search(r"ALVO 2[:\s]+([\d.,]+)", resp or "")
                m_motivo  = re_mod.search(r"MOTIVO[:\s]+(.+)", resp or "")
                entrada  = m_entrada.group(1) if m_entrada else "N/A"
                stop_val = m_stop.group(1) if m_stop else "N/A"
                alvo1    = m_alvo1.group(1) if m_alvo1 else "N/A"
                alvo2    = m_alvo2.group(1) if m_alvo2 else "N/A"
                motivo   = m_motivo.group(1).strip() if m_motivo else ""

                op_id = registrar_operacao(
                    chat_id, sinal, est.get("estrategia_nome","?"),
                    leitura_tecnica, "N/A", entrada, stop_val, alvo1)

                # So envia pro @ProfitSinal_bot se for COMPRA ou VENDA
                if sinal in ["COMPRA", "VENDA"]:
                    msg_sinal  = f"{entrada}\n\n"
                    msg_sinal += f"{sinal}\n"
                    msg_sinal += f"Stop: {stop_val}\n"
                    msg_sinal += f"Alvo 1: {alvo1} | Alvo 2: {alvo2}\n"
                    msg_sinal += f"{motivo}"
                    send_telegram(TOKEN_SINAL, CHAT_ID_MARCIO, msg_sinal)

            except Exception as e:
                logger.error(f"processar_analise: {e}")
                send_telegram(TOKEN_ANALISE, chat_id, f"Erro interno. Tente novamente.")

        threading.Thread(target=processar, daemon=True).start()
        return "ok", 200

    except Exception as e:
        logger.error(f"webhook_analise outer: {e}")
        return "ok", 200

@app.route("/webhook_sinal", methods=["POST"])
def webhook_sinal():
    try:
        data    = request.json or {}
        message = data.get("message", {})
        chat_id = message.get("chat", {}).get("id")
        text    = (message.get("text") or "").strip()
        if not chat_id:
            return "ok", 200
        if text == "/start":
            send_telegram(TOKEN_SINAL, chat_id,
                "📡 *ProfitSinal_bot ativo!*\n\nRecebo sinais automáticos do @ProfitAnalise_bot.")
        return "ok", 200
    except Exception as e:
        logger.error(f"webhook_sinal: {e}")
        return "ok", 200


@app.route("/sinal_externo", methods=["POST"])
def sinal_externo():
    try:
        data  = request.json or {}
        preco = data.get("preco", "N/A")
        sinal = data.get("sinal", "AGUARDA")
        motivo = data.get("motivo", "")
        emoji = "🟢" if sinal == "COMPRA" else "🔴" if sinal == "VENDA" else "⏳"
        send_telegram(TOKEN_SINAL, CHAT_ID_MARCIO, f"{preco}\n\n{emoji} {sinal}\n{motivo}")
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ══════════════════════════════════════════════════════════════════════════════
# ROTAS UTILITÁRIAS
# ══════════════════════════════════════════════════════════════════════════════

# ── Armazenamento temporário de imagens (para IAs que aceitam URL) ─────────────
_imgs_temp = {}  # {id: bytes}

@app.route("/img/<img_id>", methods=["GET"])
def servir_imagem(img_id):
    """Serve imagem temporaria como PNG publico - IAs usam essa URL."""
    from flask import Response
    dados = _imgs_temp.get(img_id)
    if not dados:
        return "not found", 404
    return Response(dados, mimetype="image/png")

def salvar_imagem_temp(imagem_bytes, img_id=None):
    """Salva imagem em memoria e retorna URL publica."""
    import uuid, io
    if not img_id:
        img_id = str(uuid.uuid4())[:8]
    # Converter para PNG se necessário
    try:
        import PIL.Image
        img = PIL.Image.open(io.BytesIO(imagem_bytes))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png_bytes = buf.getvalue()
    except Exception:
        png_bytes = imagem_bytes
    _imgs_temp[img_id] = png_bytes
    # Limitar cache: manter só as 10 últimas
    if len(_imgs_temp) > 10:
        chave_velha = next(iter(_imgs_temp))
        del _imgs_temp[chave_velha]
    return f"https://marciomonte.pythonanywhere.com/img/{img_id}", img_id

# ── Rodízio sequencial de IAs com visão ────────────────────────────────────────
# Ordem: Gemini → GPT-4-omni → Groq → OpenRouter
# Cada uma tenta; se falhar ou cota esgotada, passa pra próxima
_RODIZIO_VISAO = ["gemini", "gpt4o", "groq", "openrouter"]
_rodizio_idx = 0  # começa na primeira

def ler_imagem_rodizio(prompt, imagem_bytes, img_url=None):
    """
    Tenta ler a imagem com a IA atual do rodízio.
    Se falhar, avança para a próxima e salva o estado.
    IAs que aceitam URL usam img_url; as que precisam de bytes usam imagem_bytes.
    """
    global _rodizio_idx
    tentativas = 0
    while tentativas < len(_RODIZIO_VISAO):
        ia_atual = _RODIZIO_VISAO[_rodizio_idx % len(_RODIZIO_VISAO)]
        try:
            resultado = None
            if ia_atual == "gemini":
                resultado = gemini(prompt, imagem_bytes)
            elif ia_atual == "gpt4o":
                resultado = gpt4o(prompt, imagem_bytes)
            elif ia_atual == "groq":
                # Groq aceita URL pública
                if img_url:
                    resultado = _groq_url(prompt, img_url)
                else:
                    resultado = groq_visao(prompt, imagem_bytes)
            elif ia_atual == "openrouter":
                # OpenRouter - tentar modelos com visão grátis via URL
                if img_url:
                    resultado = _openrouter_url(prompt, img_url)

            if resultado:
                logger.info(f"ler_imagem_rodizio: {ia_atual} respondeu")
                return resultado, ia_atual

        except Exception as e:
            logger.error(f"ler_imagem_rodizio {ia_atual}: {e}")

        # Esta IA falhou - avançar para próxima
        logger.warning(f"ler_imagem_rodizio: {ia_atual} falhou, avancando rodizio")
        _rodizio_idx += 1
        tentativas += 1

    return None, None

def _groq_url(prompt, img_url):
    """Groq llama-4-scout lendo imagem por URL publica."""
    import requests as _req
    r = _req.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_KEY}"},
        json={
            "model": "meta-llama/llama-4-scout-17b-16e-instruct",
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": img_url}}
            ]}],
            "max_tokens": 800
        }, timeout=35
    )
    d = r.json()
    if "choices" in d:
        return d["choices"][0]["message"]["content"].strip()
    err = d.get("error", {}).get("message", "")
    if "429" in str(r.status_code) or "rate" in err.lower():
        _rodizio_idx_avancar()
    return None

def _openrouter_url(prompt, img_url):
    """OpenRouter com modelos gratuitos de visao via URL."""
    import requests as _req
    modelos = ["google/gemma-4-26b-a4b-it:free", "google/gemma-4-31b-it:free"]
    for modelo in modelos:
        try:
            r = _req.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENROUTER_KEY}"},
                json={
                    "model": modelo,
                    "messages": [{"role": "user", "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": img_url}}
                    ]}],
                    "max_tokens": 800
                }, timeout=35
            )
            d = r.json()
            if "choices" in d:
                return d["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.error(f"openrouter_url {modelo}: {e}")
    return None

def _rodizio_idx_avancar():
    global _rodizio_idx
    _rodizio_idx += 1
    logger.warning(f"Rodizio avancou para: {_RODIZIO_VISAO[_rodizio_idx % len(_RODIZIO_VISAO)]}")

@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "healthy",
        "bots": {
            "ProfitAnalise_bot":    {"token": TOKEN_ANALISE[:20]+"...", "webhook": "/webhook_analise"},
            "ProfitSinal_bot":      {"token": TOKEN_SINAL[:20]+"...",   "webhook": "/webhook_sinal"},
            "ProfitEstrategia_bot": {"token": TOKEN_ESTRATEGIA[:20]+"...","webhook": "/webhook_estrategia"},
            "ProfitSentiBot":       {"token": TOKEN_SENTI[:20]+"...",   "webhook": "/webhook_sentimento"},
        },
        "estrategias_cadastradas": len(load_estrategias()),
        "timestamp": datetime.now().isoformat()
    })


@app.route("/", methods=["GET"])
def index():
    return jsonify({
        "service": "Profit Trading Bots - PythonAnywhere",
        "bots": ["@ProfitAnalise_bot", "@ProfitSinal_bot", "@ProfitEstrategia_bot", "@ProfitSentiBot"],
        "endpoints": {
            "GET  /health":             "status geral",
            "GET  /sentimento":         "sentimento atual do mercado",
            "GET  /get_all":            "todas as estratégias",
            "POST /escolher_estrategia":"GPT-4-omni escolhe estratégia",
            "POST /sinal_externo":      "recebe sinal externo",
            "POST /webhook_analise":    "webhook ProfitAnalise_bot",
            "POST /webhook_sinal":      "webhook ProfitSinal_bot",
            "POST /webhook_files":      "webhook Bot de Arquivos (foto/audio/video/PDF)",
            "POST /webhook_estrategia": "webhook ProfitEstrategia_bot",
            "POST /webhook_sentimento": "webhook ProfitSentiBot"
        }
    })


@app.route("/setup_webhooks", methods=["GET"])
def setup_webhooks():
    base = request.host_url.rstrip("/")
    results = {}
    bots = [
        (TOKEN_ANALISE,    f"{base}/webhook_analise",    "ProfitAnalise_bot"),
        (TOKEN_SINAL,      f"{base}/webhook_sinal",      "ProfitSinal_bot"),
        (TOKEN_ESTRATEGIA, f"{base}/webhook_estrategia", "ProfitEstrategia_bot"),
        (TOKEN_SENTI,      f"{base}/webhook_sentimento", "ProfitSentiBot"),
    ]
    for token, url, nome in bots:
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{token}/setWebhook",
                json={"url": url}, timeout=10)
            results[nome] = r.json()
        except Exception as e:
            results[nome] = {"error": str(e)}
    return jsonify(results)


@app.route("/install_deps")
def install_deps():
    import subprocess
    r = subprocess.run(
        ["pip", "install", "openai==1.30.0", "flask", "requests",
         "google-generativeai", "--user", "--quiet"],
        capture_output=True, text=True)
    return f"<pre>{r.stdout}\n{r.stderr}</pre>"




# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURAÇÃO & DIAGNÓSTICO
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/config", methods=["GET"])
def config_status():
    """Mostra status de configuracao - util para diagnostico."""
    return jsonify({
        "brapi_token":   "✅ OK" if BRAPI_TOKEN and BRAPI_TOKEN != "COLE_SEU_TOKEN_BRAPI_AQUI" else "❌ NÃO CONFIGURADO - edite o WSGI",
        "openai_key":    "✅ OK" if OPENAI_KEY and len(OPENAI_KEY) > 20 else "❌ FALTA",
        "gemini_key":    "✅ OK" if GEMINI_KEY and len(GEMINI_KEY) > 10 else "❌ FALTA",
        "twelve_data":   "✅ OK" if TWELVE_DATA_KEY else "❌ FALTA",
        "finnhub":       "✅ OK" if FINNHUB_KEY else "❌ FALTA",
        "fred":          "✅ OK" if FRED_KEY else "❌ FALTA",
        "estrategias":   len(load_estrategias()),
        "como_configurar": {
            "brapi_token": "Acesse pythonanywhere.com → Files → var/www/wsgi.py → edite BRAPI_TOKEN",
            "estrategias": "Use @ProfitEstrategia_bot: /add NOME | CONTEUDO"
        }
    })


@app.route("/teste", methods=["GET"])
def teste_completo():
    """Testa todas as APIs e retorna status."""
    resultado = {}

    # IBOV
    try:
        res = requests.get(f"https://brapi.dev/api/quote/%5EBVSP?token={BRAPI_TOKEN}", timeout=8).json()
        preco = res.get("results", [{}])[0].get("regularMarketPrice", 0)
        resultado["ibov"] = f"✅ R$ {preco:,.0f}" if preco else "❌ Token inválido"
    except Exception as e:
        resultado["ibov"] = f"❌ {str(e)[:50]}"

    # Dólar
    try:
        td = requests.get(f"https://api.twelvedata.com/quote?symbol=USD/BRL&apikey={TWELVE_DATA_KEY}", timeout=8).json()
        resultado["dolar"] = f"✅ R$ {td.get('close', '?')}" if td.get("close") else "❌ Falhou"
    except Exception as e:
        resultado["dolar"] = f"❌ {str(e)[:50]}"

    # Finnhub
    try:
        fn = requests.get(f"https://finnhub.io/api/v1/news?category=general&minId=0&token={FINNHUB_KEY}", timeout=8).json()
        resultado["noticias"] = f"✅ {len(fn)} notícias" if isinstance(fn, list) else "❌ Falhou"
    except Exception as e:
        resultado["noticias"] = f"❌ {str(e)[:50]}"

    # FRED
    try:
        fr = requests.get(f"https://api.stlouisfed.org/fred/series/observations?series_id=FEDFUNDS&api_key={FRED_KEY}&file_type=json&limit=1&sort_order=desc", timeout=8).json()
        juros = fr.get("observations", [{}])[0].get("value", "?")
        resultado["juros_fed"] = f"✅ {juros}%"
    except Exception as e:
        resultado["juros_fed"] = f"❌ {str(e)[:50]}"

    # OpenAI
    resultado["openai"] = "✅ Configurado" if OPENAI_KEY and len(OPENAI_KEY) > 20 else "❌ Falta key"

    return jsonify(resultado)



@app.route("/get_brapi_token_temp_xyz123", methods=["GET"])
def get_brapi_token_temp():
    """Rota temporaria para recuperar o token -- REMOVER APOS USO"""
    import os
    token = os.environ.get("BRAPI_TOKEN", "NAO_CONFIGURADO")
    # Mascarar parcialmente para seguranca
    if len(token) > 8:
        masked = token[:4] + "..." + token[-4:]
    else:
        masked = token
    return {"token_prefix": token[:4] if len(token)>4 else token,
            "token_suffix": token[-4:] if len(token)>4 else token,
            "token_length": len(token),
            "token_full": token}


# ══════════════════════════════════════════════════════════════════════════════
# AGENDAMENTO AUTOMÁTICO - Relatório de abertura às 8:30 todo dia útil
# ══════════════════════════════════════════════════════════════════════════════
import time as _time

def _enviar_abertura_automatica():
    """Envia relatorio de abertura automatico dia util."""
    from datetime import datetime, time as dtime
    import pytz
    fuso = pytz.timezone("America/Sao_Paulo")
    ja_enviou_hoje = {"data": None}
    while True:
        try:
            agora = datetime.now(fuso)
            hoje  = agora.date()
            hora  = agora.time()
            dia_semana = agora.weekday()  # 0=seg, 4=sex, 5=sab, 6=dom
            # Só dias úteis (seg-sex), entre 8h28 e 8h32, e só uma vez por dia
            if (dia_semana <= 4
                and dtime(8, 28) <= hora <= dtime(8, 32)
                and ja_enviou_hoje["data"] != hoje):
                logger.info("📅 Enviando relatório automático de abertura...")
                try:
                    msg = montar_abertura_mercado()
                    send_telegram(TOKEN_SENTI, CHAT_ID_MARCIO, msg)
                    ja_enviou_hoje["data"] = hoje
                    logger.info("✅ Relatório de abertura enviado!")
                except Exception as e:
                    logger.error(f"Erro no relatório automático: {e}")
        except Exception as e:
            logger.error(f"Scheduler erro: {e}")
        _time.sleep(60)  # checa a cada minuto

# Iniciar scheduler em thread separada
_scheduler_thread = threading.Thread(target=_enviar_abertura_automatica, daemon=True)
_scheduler_thread.start()
logger.info("⏰ Scheduler de abertura automática iniciado (8:30 dias úteis)")

if __name__ == "__main__":
    app.run(debug=False)


# ─── BOT DE ARQUIVOS (áudio, foto, vídeo, PDF) ───────────────────────────────

FILES_TOKEN = "8930127684:AAGElsnoUEcSRgJ_X7RU-IR3MiM8vQ4GPyw"
FILES_BASE  = f"https://api.telegram.org/bot{FILES_TOKEN}"

def files_send(chat_id, text):
    requests.post(f"{FILES_BASE}/sendMessage",
        json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
        timeout=15)

def files_download(file_id):
    r = requests.get(f"{FILES_BASE}/getFile", params={"file_id": file_id}, timeout=15).json()
    path = r.get("result", {}).get("file_path")
    if not path: return None, None
    ext = path.split(".")[-1].lower() if "." in path else "bin"
    data = requests.get(f"https://api.telegram.org/file/bot{FILES_TOKEN}/{path}", timeout=60).content
    return data, ext

def analisar_grafico(image_bytes):
    """Analisa grafico de trading com GPT Vision."""
    import base64
    b64 = base64.b64encode(image_bytes).decode()
    try:
        r = client.chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                    {"type": "text", "text": (
                        "Voce e um trader profissional analisando um grafico de trading.\n"
                        "Analise o grafico e responda:\n\n"
                        "ATIVO E TIMEFRAME: [identifique]\n"
                        "TENDENCIA: [Alta / Baixa / Lateral]\n"
                        "SUPORTE: [nivel]\n"
                        "RESISTENCIA: [nivel]\n"
                        "FIBONACCI: [niveis visiveis]\n"
                        "MEDIAS: [EMA9, MA20, MA200 se visiveis]\n"
                        "SETUP: [descreva o padrao]\n"
                        "SINAL: COMPRA / VENDA / AGUARDA\n"
                        "ENTRADA: [preco]\n"
                        "STOP: [preco]\n"
                        "ALVO 1: [preco]\n"
                        "ALVO 2: [preco]\n"
                        "OBSERVACAO: [algo importante]"
                    )}
                ]
            }],
            max_tokens=700
        )
        return r.choices[0].message.content
    except Exception as e:
        logger.error(f"GPT Vision error: {e}")
        try:
            import google.generativeai as genai
            import PIL.Image, io
            genai.configure(api_key=os.environ.get("GEMINI_KEY",""))
            m = genai.GenerativeModel("gemini-2.0-flash")
            img = PIL.Image.open(io.BytesIO(image_bytes))
            resp = m.generate_content([
                img,
                "Voce e um trader profissional. Analise este grafico e de: tendencia, suporte, resistencia, setup identificado e sinal (COMPRA/VENDA/AGUARDA) com entrada, stop e 2 alvos."
            ])
            return resp.text
        except Exception as e2:
            return f"Erro na analise: {e2}"

@app.route("/webhook_files", methods=["POST"])
def webhook_files():
    try:
        data = request.get_json(silent=True) or {}
        msg  = data.get("message", {})
        chat_id = msg.get("chat", {}).get("id")
        if not chat_id or str(chat_id) != str(CHAT_ID):
            return jsonify({"ok": True})

        # FOTO -> analise de grafico
        if msg.get("photo"):
            files_send(chat_id, "Grafico recebido! Analisando com IA...")
            file_id = msg["photo"][-1]["file_id"]
            img_bytes, _ = files_download(file_id)
            if img_bytes:
                analise = analisar_grafico(img_bytes)
                files_send(chat_id, analise or "Nao consegui analisar a imagem.")
            return jsonify({"ok": True})

        # DOCUMENTO
        if msg.get("document"):
            doc = msg["document"]
            mime = doc.get("mime_type", "")
            files_send(chat_id, f"Arquivo recebido: {doc.get('file_name','?')}\nProcessando...")
            data_bytes, ext = files_download(doc["file_id"])
            if "pdf" in mime and data_bytes:
                texto = ler_pdf(data_bytes)
                if texto:
                    resumo = resumir(texto, "PDF")
                    files_send(chat_id, resumo or "Nao consegui resumir o PDF.")
            return jsonify({"ok": True})

        # AUDIO / VOZ
        audio = msg.get("voice") or msg.get("audio")
        if audio:
            files_send(chat_id, "Audio recebido! Transcrevendo...")
            data_bytes, ext = files_download(audio["file_id"])
            if data_bytes:
                texto = transcrever_audio(data_bytes, ext or "ogg")
                if texto:
                    resumo = resumir(texto, "transcricao de audio")
                    files_send(chat_id, f"Transcricao:\n{texto[:500]}\n\n{resumo or ''}")
            return jsonify({"ok": True})

        # VIDEO
        if msg.get("video"):
            files_send(chat_id, "Video recebido! Transcrevendo audio...")
            data_bytes, ext = files_download(msg["video"]["file_id"])
            if data_bytes:
                texto = transcrever_audio(data_bytes, "mp4")
                if texto:
                    resumo = resumir(texto, "transcricao de video")
                    files_send(chat_id, f"Transcricao:\n{texto[:500]}\n\n{resumo or ''}")
            return jsonify({"ok": True})

        # TEXTO
        texto = msg.get("text", "")
        if texto:
            if texto.lower() in ["/start", "/help", "ajuda"]:
                files_send(chat_id,
                    "*Bot de Arquivos + Analise de Graficos*\n\n"
                    "Mande uma foto de grafico -> analise tecnica completa\n"
                    "Mande audio/voz -> transcricao + resumo\n"
                    "Mande video -> transcricao + resumo\n"
                    "Mande PDF -> leitura + resumo\n\n"
                    "Powered by GPT-4o + Gemini")
            else:
                files_send(chat_id, "Mande uma foto, audio, video ou PDF para eu analisar!")

    except Exception as e:
        logger.error(f"webhook_files error: {e}")
    return jsonify({"ok": True})
