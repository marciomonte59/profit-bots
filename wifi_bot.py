import os, logging, hashlib, requests, subprocess, datetime, json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

TOKEN       = "8863713291:AAFM2lMJNWlXOVUln87MI5_43aJlcngt3ZM"
ROUTER_IP   = os.environ.get("ROUTER_IP",   "192.168.200.1")
ROUTER_PASS = os.environ.get("ROUTER_PASS", "rocha2022")
CHAT_ID     = int(os.environ.get("CHAT_ID", "8255093111"))
GROQ_KEY    = os.environ.get("GROQ_KEY", "")

logging.basicConfig(level=logging.INFO)

# ── Login roteador ────────────────────────────────────────────────────────────

def get_stok():
    pwd_md5 = hashlib.md5(ROUTER_PASS.encode()).hexdigest()
    try:
        r = requests.post(
            f"http://{ROUTER_IP}/cgi-bin/luci/;stok=/rpc",
            json={"method": "do", "login": {"username": "admin", "password": pwd_md5}},
            headers={"Referer": f"http://{ROUTER_IP}/"},
            timeout=8
        )
        return r.json().get("stok", "")
    except Exception as e:
        logging.error(f"get_stok: {e}")
        return None

def rpc(stok, method, params):
    if not stok:
        return {"error": "sem stok"}
    try:
        r = requests.post(
            f"http://{ROUTER_IP}/cgi-bin/luci/;stok={stok}/rpc",
            json={"method": method, "params": params},
            headers={"Referer": f"http://{ROUTER_IP}/"},
            timeout=8
        )
        return r.json()
    except Exception as e:
        return {"error": str(e)}

# ── IA — Groq LLaMA ──────────────────────────────────────────────────────────

def ia(pergunta, contexto=""):
    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"},
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [
                    {"role": "system", "content": (
                        "Você é um assistente de controle de rede WiFi TP-Link EC220-G5. "
                        "Responda em português, de forma curta e direta. "
                        "Quando o usuário pedir para executar uma ação, responda com a ação no formato: "
                        "ACAO:wifi_on | ACAO:wifi_off | ACAO:wifi5_on | ACAO:wifi5_off | "
                        "ACAO:dispositivos | ACAO:reiniciar | ACAO:status | "
                        "ACAO:bloquear:NOME | ACAO:liberar:NOME | ACAO:agendar_off:HH:MM | ACAO:agendar_on:HH:MM. "
                        "Se for só conversa ou pergunta, responda normalmente sem ACAO. "
                        + (f"Contexto atual da rede: {contexto}" if contexto else "")
                    )},
                    {"role": "user", "content": pergunta}
                ],
                "temperature": 0.3,
                "max_tokens": 300
            },
            timeout=15
        )
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"Erro IA: {e}"

# ── Helpers ───────────────────────────────────────────────────────────────────

def bateria_info():
    try:
        r = subprocess.run(["termux-battery-status"], capture_output=True, text=True, timeout=5)
        d = json.loads(r.stdout)
        return f"{d.get('percentage','?')}% — {d.get('status','?')}"
    except:
        return "N/A"

def ip_externo():
    try:
        return requests.get("https://api.ipify.org", timeout=5).text
    except:
        return "N/A"

def listar_dispositivos(stok):
    data = rpc(stok, "get", {"hosts_info": {"table": "host_info"}})
    hosts = data.get("hosts_info", {}).get("host_info", [])
    if not hosts:
        hosts = data.get("result", {}).get("hosts_info", {}).get("host_info", [])
    return hosts

def teclado_principal():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ WiFi 2.4G ON",  callback_data="wifi_on"),
         InlineKeyboardButton("❌ WiFi 2.4G OFF", callback_data="wifi_off")],
        [InlineKeyboardButton("✅ WiFi 5G ON",    callback_data="wifi5_on"),
         InlineKeyboardButton("❌ WiFi 5G OFF",   callback_data="wifi5_off")],
        [InlineKeyboardButton("📱 Dispositivos",  callback_data="dispositivos"),
         InlineKeyboardButton("📊 Status",        callback_data="status")],
        [InlineKeyboardButton("🔄 Reiniciar",     callback_data="reiniciar"),
         InlineKeyboardButton("🌐 Meu IP",        callback_data="meuip")],
    ])

# ── COMANDOS ──────────────────────────────────────────────────────────────────

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📡 *Bot WiFi — TP-Link EC220-G5*\n\n"
        "Use os botões abaixo ou fale comigo em linguagem natural!\n\n"
        "_Ex: \"desliga o wifi às 22h\", \"quem tá conectado?\", \"bloqueia o vizinho\"_",
        parse_mode="Markdown",
        reply_markup=teclado_principal()
    )

async def menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📡 *Painel WiFi*", parse_mode="Markdown",
        reply_markup=teclado_principal())

async def status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    stok = get_stok()
    ip   = ip_externo()
    bat  = bateria_info()
    rot  = "✅ Online" if stok else "❌ Offline"
    hosts = listar_dispositivos(stok) if stok else []
    await update.message.reply_text(
        f"📡 *Status da Rede*\n\n"
        f"Roteador: {rot}\n"
        f"Dispositivos: {len(hosts)} conectados\n"
        f"IP externo: `{ip}`\n"
        f"🔋 Celular: {bat}\n"
        f"🕐 {datetime.datetime.now().strftime('%d/%m %H:%M')}",
        parse_mode="Markdown", reply_markup=teclado_principal()
    )

async def dispositivos(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    stok = get_stok()
    if not stok:
        await update.message.reply_text("❌ Sem conexão com o roteador.")
        return
    hosts = listar_dispositivos(stok)
    if hosts:
        msg = f"📱 *{len(hosts)} dispositivo(s) conectados:*\n\n"
        for h in hosts[:20]:
            nome = h.get("hostname") or h.get("name") or "Desconhecido"
            ip   = h.get("ip") or ""
            msg += f"• {nome} — `{ip}`\n"
    else:
        msg = "📱 Nenhum dispositivo encontrado."
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=teclado_principal())

async def bloquear(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("⚠️ Use: /bloquear NOME")
        return
    nome = " ".join(ctx.args)
    stok = get_stok()
    if not stok:
        await update.message.reply_text("❌ Sem conexão.")
        return
    hosts = listar_dispositivos(stok)
    mac = next((h.get("mac") for h in hosts if nome.lower() in (h.get("hostname","") or h.get("name","")).lower()), None)
    if not mac:
        await update.message.reply_text(f"❌ '{nome}' não encontrado. Use /dispositivos para ver os nomes.")
        return
    rpc(stok, "set", {"access_control": {"block_list": [{"mac": mac}]}})
    await update.message.reply_text(f"🔒 *{nome}* bloqueado!", parse_mode="Markdown")

async def liberar(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("⚠️ Use: /liberar NOME")
        return
    nome = " ".join(ctx.args)
    stok = get_stok()
    if not stok:
        await update.message.reply_text("❌ Sem conexão.")
        return
    hosts = listar_dispositivos(stok)
    mac = next((h.get("mac") for h in hosts if nome.lower() in (h.get("hostname","") or h.get("name","")).lower()), None)
    if not mac:
        await update.message.reply_text(f"❌ '{nome}' não encontrado.")
        return
    rpc(stok, "set", {"access_control": {"unblock_list": [{"mac": mac}]}})
    await update.message.reply_text(f"✅ *{nome}* liberado!", parse_mode="Markdown")

async def wifi_on(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    stok = get_stok()
    if not stok:
        await update.message.reply_text("❌ Sem conexão com o roteador.")
        return
    rpc(stok, "set", {"wireless": {"enable": True, "band": "2.4GHz"}})
    await update.message.reply_text("✅ WiFi 2.4GHz *LIGADO*!", parse_mode="Markdown", reply_markup=teclado_principal())

async def wifi_off(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    stok = get_stok()
    if not stok:
        await update.message.reply_text("❌ Sem conexão com o roteador.")
        return
    rpc(stok, "set", {"wireless": {"enable": False, "band": "2.4GHz"}})
    await update.message.reply_text("❌ WiFi 2.4GHz *DESLIGADO*!", parse_mode="Markdown", reply_markup=teclado_principal())

async def wifi5_on(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    stok = get_stok()
    if not stok:
        await update.message.reply_text("❌ Sem conexão com o roteador.")
        return
    rpc(stok, "set", {"wireless": {"enable": True, "band": "5GHz"}})
    await update.message.reply_text("✅ WiFi 5GHz *LIGADO*!", parse_mode="Markdown", reply_markup=teclado_principal())

async def wifi5_off(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    stok = get_stok()
    if not stok:
        await update.message.reply_text("❌ Sem conexão com o roteador.")
        return
    rpc(stok, "set", {"wireless": {"enable": False, "band": "5GHz"}})
    await update.message.reply_text("❌ WiFi 5GHz *DESLIGADO*!", parse_mode="Markdown", reply_markup=teclado_principal())

async def reiniciar(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    stok = get_stok()
    if not stok:
        await update.message.reply_text("❌ Sem conexão com o roteador.")
        return
    rpc(stok, "do", {"device": {"reboot": None}})
    await update.message.reply_text("🔄 Roteador reiniciando... aguarde ~30s.")

async def meuip(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🌐 IP externo: `{ip_externo()}`", parse_mode="Markdown")

async def bateria_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🔋 Bateria: {bateria_info()}")

async def screenshot(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📸 Capturando...")
    try:
        subprocess.run(["termux-screenshot", "-f", "/sdcard/screenshot.png"], timeout=10)
        with open("/sdcard/screenshot.png", "rb") as f:
            await update.message.reply_photo(f, caption="📸 Tela atual")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro: {e}")

async def velocidade(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Testando velocidade... aguarde ~30s")
    try:
        subprocess.run(["pip", "install", "speedtest-cli", "-q"], timeout=30)
        r = subprocess.run(["speedtest-cli", "--simple"], capture_output=True, text=True, timeout=60)
        await update.message.reply_text(f"🚀 *Velocidade:*\n\n{r.stdout}", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro: {e}")

async def agendar_off(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("⚠️ Use: /agendar_off HH:MM")
        return
    try:
        h, m = map(int, ctx.args[0].split(":"))
        import pytz
        tz = pytz.timezone("America/Fortaleza")
        ctx.job_queue.run_daily(desligar_job,
            time=datetime.time(hour=h, minute=m, tzinfo=tz),
            chat_id=update.effective_chat.id, name=f"off_{h}:{m}")
        await update.message.reply_text(f"✅ WiFi desliga todo dia às *{ctx.args[0]}*!", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro: {e}")

async def agendar_on(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("⚠️ Use: /agendar_on HH:MM")
        return
    try:
        h, m = map(int, ctx.args[0].split(":"))
        import pytz
        tz = pytz.timezone("America/Fortaleza")
        ctx.job_queue.run_daily(ligar_job,
            time=datetime.time(hour=h, minute=m, tzinfo=tz),
            chat_id=update.effective_chat.id, name=f"on_{h}:{m}")
        await update.message.reply_text(f"✅ WiFi liga todo dia às *{ctx.args[0]}*!", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro: {e}")

async def cancelar(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    for job in ctx.job_queue.jobs():
        job.schedule_removal()
    await update.message.reply_text("✅ Agendamentos cancelados!")

async def desligar_job(ctx: ContextTypes.DEFAULT_TYPE):
    stok = get_stok()
    if stok:
        rpc(stok, "set", {"wireless": {"enable": False, "band": "2.4GHz"}})
        rpc(stok, "set", {"wireless": {"enable": False, "band": "5GHz"}})
    await ctx.bot.send_message(chat_id=ctx.job.chat_id, text="🌙 WiFi desligado automaticamente!")

async def ligar_job(ctx: ContextTypes.DEFAULT_TYPE):
    stok = get_stok()
    if stok:
        rpc(stok, "set", {"wireless": {"enable": True, "band": "2.4GHz"}})
        rpc(stok, "set", {"wireless": {"enable": True, "band": "5GHz"}})
    await ctx.bot.send_message(chat_id=ctx.job.chat_id, text="☀️ WiFi ligado automaticamente!")

# ── IA — mensagem livre ───────────────────────────────────────────────────────

async def mensagem_ia(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    await update.message.reply_text("🤖 Pensando...")

    # Contexto atual da rede para a IA
    stok = get_stok()
    hosts = listar_dispositivos(stok) if stok else []
    contexto = f"{len(hosts)} dispositivos conectados" if hosts else "roteador offline"

    resposta = ia(texto, contexto)

    # IA retornou uma ação?
    if "ACAO:" in resposta:
        linha = [l for l in resposta.split("\n") if "ACAO:" in l][0]
        acao = linha.split("ACAO:")[1].strip()

        if acao == "wifi_on":
            rpc(stok, "set", {"wireless": {"enable": True, "band": "2.4GHz"}})
            await update.message.reply_text("✅ WiFi 2.4GHz ligado!", reply_markup=teclado_principal())
        elif acao == "wifi_off":
            rpc(stok, "set", {"wireless": {"enable": False, "band": "2.4GHz"}})
            await update.message.reply_text("❌ WiFi 2.4GHz desligado!", reply_markup=teclado_principal())
        elif acao == "wifi5_on":
            rpc(stok, "set", {"wireless": {"enable": True, "band": "5GHz"}})
            await update.message.reply_text("✅ WiFi 5GHz ligado!", reply_markup=teclado_principal())
        elif acao == "wifi5_off":
            rpc(stok, "set", {"wireless": {"enable": False, "band": "5GHz"}})
            await update.message.reply_text("❌ WiFi 5GHz desligado!", reply_markup=teclado_principal())
        elif acao == "dispositivos":
            msg = f"📱 *{len(hosts)} dispositivos:*\n\n" + \
                  "".join(f"• {h.get('hostname') or h.get('name','?')} — `{h.get('ip','')}`\n" for h in hosts[:20])
            await update.message.reply_text(msg or "Nenhum encontrado.", parse_mode="Markdown")
        elif acao == "status":
            await update.message.reply_text(
                f"📡 Roteador: {'✅ Online' if stok else '❌ Offline'}\n"
                f"📱 Dispositivos: {len(hosts)}\n🌐 IP: `{ip_externo()}`",
                parse_mode="Markdown", reply_markup=teclado_principal())
        elif acao == "reiniciar":
            rpc(stok, "do", {"device": {"reboot": None}})
            await update.message.reply_text("🔄 Roteador reiniciando...")
        elif acao.startswith("bloquear:"):
            nome = acao.split("bloquear:")[1]
            mac = next((h.get("mac") for h in hosts if nome.lower() in (h.get("hostname","") or "").lower()), None)
            if mac:
                rpc(stok, "set", {"access_control": {"block_list": [{"mac": mac}]}})
                await update.message.reply_text(f"🔒 *{nome}* bloqueado!", parse_mode="Markdown")
            else:
                await update.message.reply_text(f"❌ '{nome}' não encontrado. Use /dispositivos.")
        elif acao.startswith("liberar:"):
            nome = acao.split("liberar:")[1]
            mac = next((h.get("mac") for h in hosts if nome.lower() in (h.get("hostname","") or "").lower()), None)
            if mac:
                rpc(stok, "set", {"access_control": {"unblock_list": [{"mac": mac}]}})
                await update.message.reply_text(f"✅ *{nome}* liberado!", parse_mode="Markdown")
            else:
                await update.message.reply_text(f"❌ '{nome}' não encontrado.")
        elif acao.startswith("agendar_off:"):
            horario = acao.split("agendar_off:")[1]
            h2, m2 = map(int, horario.split(":"))
            ctx.job_queue.run_daily(desligar_job, time=datetime.time(hour=h2, minute=m2), chat_id=update.effective_chat.id)
            await update.message.reply_text(f"✅ WiFi desliga todo dia às *{horario}*!", parse_mode="Markdown")
        elif acao.startswith("agendar_on:"):
            horario = acao.split("agendar_on:")[1]
            h2, m2 = map(int, horario.split(":"))
            ctx.job_queue.run_daily(ligar_job, time=datetime.time(hour=h2, minute=m2), chat_id=update.effective_chat.id)
            await update.message.reply_text(f"✅ WiFi liga todo dia às *{horario}*!", parse_mode="Markdown")
    else:
        # Só resposta em linguagem natural
        await update.message.reply_text(resposta, reply_markup=teclado_principal())

# ── Botões inline ─────────────────────────────────────────────────────────────

async def botao(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    stok = get_stok()

    if query.data == "wifi_on":
        rpc(stok, "set", {"wireless": {"enable": True, "band": "2.4GHz"}})
        await query.edit_message_text("✅ WiFi 2.4GHz *LIGADO*!", parse_mode="Markdown", reply_markup=teclado_principal())
    elif query.data == "wifi_off":
        rpc(stok, "set", {"wireless": {"enable": False, "band": "2.4GHz"}})
        await query.edit_message_text("❌ WiFi 2.4GHz *DESLIGADO*!", parse_mode="Markdown", reply_markup=teclado_principal())
    elif query.data == "wifi5_on":
        rpc(stok, "set", {"wireless": {"enable": True, "band": "5GHz"}})
        await query.edit_message_text("✅ WiFi 5GHz *LIGADO*!", parse_mode="Markdown", reply_markup=teclado_principal())
    elif query.data == "wifi5_off":
        rpc(stok, "set", {"wireless": {"enable": False, "band": "5GHz"}})
        await query.edit_message_text("❌ WiFi 5GHz *DESLIGADO*!", parse_mode="Markdown", reply_markup=teclado_principal())
    elif query.data == "dispositivos":
        hosts = listar_dispositivos(stok) if stok else []
        msg = f"📱 *{len(hosts)} dispositivos:*\n\n" + \
              "".join(f"• {h.get('hostname') or h.get('name','?')} — `{h.get('ip','')}`\n" for h in hosts[:20])
        await query.edit_message_text(msg or "Nenhum encontrado.", parse_mode="Markdown", reply_markup=teclado_principal())
    elif query.data == "status":
        hosts = listar_dispositivos(stok) if stok else []
        await query.edit_message_text(
            f"📡 Roteador: {'✅ Online' if stok else '❌ Offline'}\n"
            f"📱 Dispositivos: {len(hosts)}\n"
            f"🌐 IP: `{ip_externo()}`\n🔋 {bateria_info()}",
            parse_mode="Markdown", reply_markup=teclado_principal())
    elif query.data == "reiniciar":
        rpc(stok, "do", {"device": {"reboot": None}})
        await query.edit_message_text("🔄 Reiniciando... aguarde ~30s.", reply_markup=teclado_principal())
    elif query.data == "meuip":
        await query.edit_message_text(f"🌐 IP: `{ip_externo()}`", parse_mode="Markdown", reply_markup=teclado_principal())

# ── MAIN ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start",        start))
    app.add_handler(CommandHandler("menu",         menu))
    app.add_handler(CommandHandler("status",       status))
    app.add_handler(CommandHandler("dispositivos", dispositivos))
    app.add_handler(CommandHandler("bloquear",     bloquear))
    app.add_handler(CommandHandler("liberar",      liberar))
    app.add_handler(CommandHandler("wifi_on",      wifi_on))
    app.add_handler(CommandHandler("wifi_off",     wifi_off))
    app.add_handler(CommandHandler("wifi5_on",     wifi5_on))
    app.add_handler(CommandHandler("wifi5_off",    wifi5_off))
    app.add_handler(CommandHandler("reiniciar",    reiniciar))
    app.add_handler(CommandHandler("meuip",        meuip))
    app.add_handler(CommandHandler("bateria",      bateria_cmd))
    app.add_handler(CommandHandler("screenshot",   screenshot))
    app.add_handler(CommandHandler("velocidade",   velocidade))
    app.add_handler(CommandHandler("agendar_off",  agendar_off))
    app.add_handler(CommandHandler("agendar_on",   agendar_on))
    app.add_handler(CommandHandler("cancelar",     cancelar))
    app.add_handler(CallbackQueryHandler(botao))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, mensagem_ia))
    print("✅ Bot WiFi + IA iniciado!")
    app.run_polling(drop_pending_updates=True)
