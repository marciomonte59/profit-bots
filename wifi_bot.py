"""
wifi_bot.py corrigido — TP-Link EC220-G5
Correções:
1. Login: EC220-G5 usa /cgi-bin/luci/login com stok retornado no JSON — não POST na raiz
2. RPC: usa stok válido na URL após login
3. Bloquear/liberar: usa MAC address via access_control com host_info
4. WiFi on/off: endpoint correto para EC220-G5
"""

import os, logging, hashlib, requests, subprocess, datetime, json
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TOKEN       = "8863713291:AAFM2lMJNWlXOVUln87MI5_43aJlcngt3ZM"
ROUTER_IP   = os.environ.get("ROUTER_IP",   "192.168.200.1")
ROUTER_PASS = os.environ.get("ROUTER_PASS", "rocha2022")
CHAT_ID     = int(os.environ.get("CHAT_ID", "8255093111"))

logging.basicConfig(level=logging.INFO)

# ── Login correto — EC220-G5 retorna stok no JSON ────────────────────────────

def get_stok():
    """Faz login e retorna o token stok. Sem stok, nenhum comando funciona."""
    pwd_md5 = hashlib.md5(ROUTER_PASS.encode()).hexdigest()
    try:
        r = requests.post(
            f"http://{ROUTER_IP}/cgi-bin/luci/;stok=/rpc",
            json={"method": "do", "login": {"username": "admin", "password": pwd_md5}},
            headers={"Referer": f"http://{ROUTER_IP}/"},
            timeout=8
        )
        data = r.json()
        stok = data.get("stok", "")
        if stok:
            return stok
    except Exception as e:
        logging.error(f"get_stok: {e}")
    return None

def rpc(stok, method, params):
    """Executa comando no roteador usando stok válido."""
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

# ── Helpers ──────────────────────────────────────────────────────────────────

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

# ── COMANDOS ─────────────────────────────────────────────────────────────────

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📡 *Bot WiFi — TP-Link EC220-G5*\n\n"
        "/status — Status geral\n"
        "/dispositivos — Quem está conectado\n"
        "/bloquear NOME — Bloquear da internet\n"
        "/liberar NOME — Liberar acesso\n"
        "/wifi\\_on — Ligar WiFi 2.4GHz\n"
        "/wifi\\_off — Desligar WiFi 2.4GHz\n"
        "/wifi5\\_on — Ligar WiFi 5GHz\n"
        "/wifi5\\_off — Desligar WiFi 5GHz\n"
        "/reiniciar — Reiniciar roteador\n"
        "/agendar\\_off HH:MM — Desligar no horário\n"
        "/agendar\\_on HH:MM — Ligar no horário\n"
        "/cancelar — Cancelar agendamentos\n"
        "/meuip — IP externo\n"
        "/velocidade — Testar velocidade\n"
        "/bateria — Bateria do celular\n"
        "/screenshot — Capturar tela",
        parse_mode="Markdown"
    )

async def status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Verificando...")
    stok = get_stok()
    ip_ext = ip_externo()
    bat = bateria_info()
    roteador = f"✅ Online — token OK" if stok else "❌ Offline ou senha errada"
    await update.message.reply_text(
        f"📡 *Status*\n\n{roteador}\n🌐 IP: `{ip_ext}`\n🔋 Bateria: {bat}\n"
        f"🕐 {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}",
        parse_mode="Markdown"
    )

async def dispositivos(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Buscando...")
    stok = get_stok()
    if not stok:
        await update.message.reply_text("❌ Sem conexão com o roteador.")
        return
    data = rpc(stok, "get", {"hosts_info": {"table": "host_info"}})
    hosts = data.get("hosts_info", {}).get("host_info", [])
    if not hosts:
        # Tentar estrutura alternativa
        hosts = data.get("result", {}).get("hosts_info", {}).get("host_info", [])
    if hosts:
        msg = f"📱 *{len(hosts)} dispositivo(s):*\n\n"
        for h in hosts[:20]:
            nome = h.get("hostname") or h.get("name") or "Desconhecido"
            ip   = h.get("ip") or ""
            mac  = h.get("mac") or ""
            msg += f"• {nome} `{ip}` `{mac}`\n"
    else:
        msg = "📱 Nenhum dispositivo encontrado ou estrutura diferente."
    await update.message.reply_text(msg, parse_mode="Markdown")

async def bloquear(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("⚠️ Use: /bloquear NOME")
        return
    nome = " ".join(ctx.args)
    stok = get_stok()
    if not stok:
        await update.message.reply_text("❌ Sem conexão com o roteador.")
        return
    # Buscar MAC pelo nome
    data = rpc(stok, "get", {"hosts_info": {"table": "host_info"}})
    hosts = data.get("hosts_info", {}).get("host_info", [])
    mac = None
    for h in hosts:
        if nome.lower() in (h.get("hostname","") or h.get("name","")).lower():
            mac = h.get("mac")
            break
    if not mac:
        await update.message.reply_text(f"❌ Dispositivo '{nome}' não encontrado. Use /dispositivos para ver os nomes.")
        return
    rpc(stok, "set", {"access_control": {"block_list": [{"mac": mac}]}})
    await update.message.reply_text(f"🔒 *{nome}* bloqueado! (`{mac}`)", parse_mode="Markdown")

async def liberar(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("⚠️ Use: /liberar NOME")
        return
    nome = " ".join(ctx.args)
    stok = get_stok()
    if not stok:
        await update.message.reply_text("❌ Sem conexão com o roteador.")
        return
    data = rpc(stok, "get", {"hosts_info": {"table": "host_info"}})
    hosts = data.get("hosts_info", {}).get("host_info", [])
    mac = None
    for h in hosts:
        if nome.lower() in (h.get("hostname","") or h.get("name","")).lower():
            mac = h.get("mac")
            break
    if not mac:
        await update.message.reply_text(f"❌ Dispositivo '{nome}' não encontrado.")
        return
    rpc(stok, "set", {"access_control": {"unblock_list": [{"mac": mac}]}})
    await update.message.reply_text(f"✅ *{nome}* liberado! (`{mac}`)", parse_mode="Markdown")

async def wifi_on(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    stok = get_stok()
    if not stok:
        await update.message.reply_text("❌ Sem conexão.")
        return
    rpc(stok, "set", {"wireless": {"enable": True, "band": "2.4GHz"}})
    await update.message.reply_text("✅ WiFi 2.4GHz *LIGADO*!", parse_mode="Markdown")

async def wifi_off(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    stok = get_stok()
    if not stok:
        await update.message.reply_text("❌ Sem conexão.")
        return
    rpc(stok, "set", {"wireless": {"enable": False, "band": "2.4GHz"}})
    await update.message.reply_text("❌ WiFi 2.4GHz *DESLIGADO*!", parse_mode="Markdown")

async def wifi5_on(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    stok = get_stok()
    if not stok:
        await update.message.reply_text("❌ Sem conexão.")
        return
    rpc(stok, "set", {"wireless": {"enable": True, "band": "5GHz"}})
    await update.message.reply_text("✅ WiFi 5GHz *LIGADO*!", parse_mode="Markdown")

async def wifi5_off(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    stok = get_stok()
    if not stok:
        await update.message.reply_text("❌ Sem conexão.")
        return
    rpc(stok, "set", {"wireless": {"enable": False, "band": "5GHz"}})
    await update.message.reply_text("❌ WiFi 5GHz *DESLIGADO*!", parse_mode="Markdown")

async def reiniciar(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    stok = get_stok()
    if not stok:
        await update.message.reply_text("❌ Sem conexão.")
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
    await update.message.reply_text("⏳ Testando... aguarde ~30s")
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
        ctx.job_queue.run_daily(
            desligar_wifi_job,
            time=datetime.time(hour=h, minute=m),
            chat_id=update.effective_chat.id
        )
        await update.message.reply_text(f"✅ WiFi desliga todo dia às *{ctx.args[0]}*!", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro: {e}")

async def agendar_on(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("⚠️ Use: /agendar_on HH:MM")
        return
    try:
        h, m = map(int, ctx.args[0].split(":"))
        ctx.job_queue.run_daily(
            ligar_wifi_job,
            time=datetime.time(hour=h, minute=m),
            chat_id=update.effective_chat.id
        )
        await update.message.reply_text(f"✅ WiFi liga todo dia às *{ctx.args[0]}*!", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro: {e}")

async def cancelar(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    for job in ctx.job_queue.jobs():
        job.schedule_removal()
    await update.message.reply_text("✅ Agendamentos cancelados!")

async def desligar_wifi_job(ctx: ContextTypes.DEFAULT_TYPE):
    stok = get_stok()
    if stok:
        rpc(stok, "set", {"wireless": {"enable": False, "band": "2.4GHz"}})
        rpc(stok, "set", {"wireless": {"enable": False, "band": "5GHz"}})
    await ctx.bot.send_message(chat_id=ctx.job.chat_id, text="🌙 WiFi desligado automaticamente!")

async def ligar_wifi_job(ctx: ContextTypes.DEFAULT_TYPE):
    stok = get_stok()
    if stok:
        rpc(stok, "set", {"wireless": {"enable": True, "band": "2.4GHz"}})
        rpc(stok, "set", {"wireless": {"enable": True, "band": "5GHz"}})
    await ctx.bot.send_message(chat_id=ctx.job.chat_id, text="☀️ WiFi ligado automaticamente!")

# ── MAIN ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start",        start))
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
    print("✅ Bot WiFi Controller iniciado!")
    app.run_polling()
