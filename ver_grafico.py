#!/usr/bin/env python3
"""
ver_grafico.py — Visão computacional do Profit via ADB
Captura tela do celular, analisa gráfico com IA e envia sinal no Telegram
"""

import subprocess, time, base64, requests, json, os, datetime

# ── CONFIG ────────────────────────────────────────────────────────────────────
CELULAR_IP   = "192.168.200.102"
ADB_PORT     = "5555"
SCREENSHOT   = "/sdcard/profit_screen.png"
LOCAL_IMG    = "/data/data/com.termux/files/home/profit_screen.png"
TELEGRAM_TOKEN = "TELEGRAM_TOKEN_AQUI"
CHAT_ID      = "8255093111"
GEMINI_KEY   = "GEMINI_KEY_AQUI"
GROQ_KEY     = "GROQ_KEY_AQUI"
INTERVALO    = 300  # segundos entre capturas (5 minutos)

# ── FUNÇÕES ───────────────────────────────────────────────────────────────────

def conectar_adb():
    """Conecta via ADB Wi-Fi"""
    r = subprocess.run(["adb", "connect", f"{CELULAR_IP}:{ADB_PORT}"],
                       capture_output=True, text=True)
    ok = "connected" in r.stdout.lower() or "already" in r.stdout.lower()
    print(f"ADB: {'✅ conectado' if ok else '❌ falhou'} — {r.stdout.strip()}")
    return ok

def capturar_tela():
    """Tira screenshot via ADB e baixa para o Termux"""
    subprocess.run(["adb", "shell", "screencap", "-p", SCREENSHOT],
                   capture_output=True)
    subprocess.run(["adb", "pull", SCREENSHOT, LOCAL_IMG],
                   capture_output=True)
    return os.path.exists(LOCAL_IMG)

def imagem_para_base64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()

def analisar_com_gemini(img_b64):
    """Analisa o gráfico com Google Gemini Vision"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_KEY}"
    payload = {
        "contents": [{
            "parts": [
                {"text": """Você é um analista de trading profissional.
Analise este gráfico do Profit (Ibovespa WIN/WINFUT, 5min) e responda EXATAMENTE neste formato:

PRECO: [número]
SINAL: [COMPRA ou VENDA ou AGUARDA]
MOTIVO: [1 linha com motivo técnico]
ESTRATEGIA: [nome da estratégia americana usada]
STOP: [preço do stop]
ALVO: [preço do alvo]

Estratégias disponíveis: Golden Line, Falha na VWAP, Falha da Falha, Golden Line Entre Médias.
Só sinalize COMPRA ou VENDA se tiver setup CLARO. Caso contrário: AGUARDA."""},
                {"inline_data": {"mime_type": "image/png", "data": img_b64}}
            ]
        }]
    }
    try:
        r = requests.post(url, json=payload, timeout=20)
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        return f"ERRO_GEMINI: {e}"

def analisar_com_groq(img_b64):
    """Fallback: analisa com Groq (texto, sem imagem)"""
    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_KEY}"},
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content":
                    "Analise o Ibovespa agora e responda: PRECO: / SINAL: / MOTIVO: / ESTRATEGIA: / STOP: / ALVO:"}],
                "max_tokens": 200
            }, timeout=15)
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"ERRO_GROQ: {e}"

def formatar_sinal(analise, horario):
    """Formata o sinal no padrão do manual"""
    lines = analise.strip().split("\n")
    dados = {}
    for l in lines:
        if ":" in l:
            k, v = l.split(":", 1)
            dados[k.strip().upper()] = v.strip()

    preco    = dados.get("PRECO", "?")
    sinal    = dados.get("SINAL", "AGUARDA").upper()
    motivo   = dados.get("MOTIVO", "")
    estrat   = dados.get("ESTRATEGIA", "")
    stop     = dados.get("STOP", "")
    alvo     = dados.get("ALVO", "")

    if "COMPRA" in sinal:
        emoji = "🟢"
    elif "VENDA" in sinal:
        emoji = "🔴"
    else:
        emoji = "⏳"

    msg = f"{preco}\n\n{emoji} {sinal}\n{motivo}\nEstratégia: {estrat}"
    if stop:  msg += f"\n🛑 Stop: {stop}"
    if alvo:  msg += f"\n🎯 Alvo: {alvo}"
    msg += f"\n\n🕐 {horario}"
    return msg, sinal

def enviar_telegram(msg):
    """Envia mensagem no Telegram"""
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"},
        timeout=10
    )

def enviar_foto_telegram(path, caption=""):
    """Envia foto + sinal no Telegram"""
    with open(path, "rb") as f:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto",
            data={"chat_id": CHAT_ID, "caption": caption, "parse_mode": "Markdown"},
            files={"photo": f},
            timeout=15
        )

# ── LOOP PRINCIPAL ────────────────────────────────────────────────────────────

def main():
    print("🚀 Ver Gráfico iniciado!")
    print(f"📱 Conectando ao celular {CELULAR_IP}:{ADB_PORT}...")

    if not conectar_adb():
        print("❌ Não foi possível conectar via ADB. Verifique o IP e a porta.")
        return

    enviar_telegram("✅ *Ver Gráfico iniciado!*\nCapturando a cada 5 minutos...")
    ultimo_sinal = ""
    capturas = 0

    while True:
        try:
            horario = datetime.datetime.now().strftime("%d/%m %H:%M")
            print(f"\n[{horario}] Capturando tela...")

            if not capturar_tela():
                print("❌ Falha na captura")
                time.sleep(30)
                conectar_adb()
                continue

            capturas += 1
            print(f"✅ Captura {capturas} — analisando com IA...")

            img_b64 = imagem_para_base64(LOCAL_IMG)
            analise = analisar_com_gemini(img_b64)

            if "ERRO" in analise:
                print(f"⚠️ Gemini falhou, usando Groq...")
                analise = analisar_com_groq(img_b64)

            print(f"Análise:\n{analise}")
            msg, sinal = formatar_sinal(analise, horario)

            # Só envia se for COMPRA ou VENDA (não AGUARDA repetido)
            if sinal in ("COMPRA", "VENDA"):
                if sinal != ultimo_sinal:
                    enviar_foto_telegram(LOCAL_IMG, msg)
                    ultimo_sinal = sinal
                    print(f"📤 Sinal enviado: {sinal}")
                else:
                    print(f"⏭️ Mesmo sinal anterior ({sinal}), não reenvia")
            else:
                print("⏳ AGUARDA — não enviado")

        except KeyboardInterrupt:
            print("\n🛑 Encerrado pelo usuário")
            enviar_telegram("🛑 *Ver Gráfico encerrado.*")
            break
        except Exception as e:
            print(f"❌ Erro: {e}")
            time.sleep(30)

        print(f"⏱️ Aguardando {INTERVALO//60} minutos...")
        time.sleep(INTERVALO)

if __name__ == "__main__":
    main()
