import os
import logging
import hashlib
import requests
import subprocess
import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, JobQueue

TOKEN       = "8863713291:AAFM2lMJNWlXOVUln87MI5_43aJlcngt3ZM"
ROUTER_IP   = os.environ.get("ROUTER_IP",   "192.168.200.1")
ROUTER_PASS = os.environ.get("ROUTER_PASS", "rocha2022")
CHAT_ID     = int(os.environ.get("CHAT_ID", "8255093111"))

logging.basicConfig(level=logging.INFO)

# ── Login no roteador ────────────────────────────────────────────────────────

def get_session():
    s = requests.Session()
    s.headers.update({"Referer": f"http://{ROUTER_IP}/"})
    pwd_md5 = hashlib.md5(ROUTER_PASS.encode()).hexdigest()
    try:
        r = s.post(f"http://{ROUTER_IP}/", data={"username": "admin", "password": pwd_md5}, timeout=5)
        if r.status_code == 200:
            return s
    except:
        pass
    return None

def rpc(s, method, params):
    try:
        r = s.post(f"http://{ROUTER_IP}/cgi-bin/luci/;stok=/rpc",
            json={"method": method, "params": params}, timeout=5)
        return r.json()
    except Exception as e:
        return {"error": str(e)}

# ── Helpers ──────────────────────────────────────────────────────────────────

def bateria():
    try:
        r = subprocess.run(["termux-battery-status"], capture_output=True, text=True, timeout=5)
        import json
        d = json.loads(r.stdout)
        return f"{d.get('percentage','?')}% — {d.get('status','?')}"
    except:
        return "N/A"

def ip_externo():
    try:
        return requests.get("https://api.ipify.org", timeout=5).text
    except:
        return "N/A"

# ── COMANDOS DO BOT ──────────────────────────────────────────────────────────

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📡 *Bot WiFi Controller — TP-Link EC220-G5*\n\n"
        "🔧 *Roteador:*\n"
        "/status — Status completo\n"
        "/wifi\\_on — Ligar WiFi 2.4GHz\n"
        "/wifi\\_off — Desligar WiFi 2.4GHz\n"
        "/wifi5\\_on — Ligar WiFi 5GHz\n"
        "/wifi5\\_off — Desligar WiFi 5GHz\n"
        "/dispositivos — Ver quem está conectado\n"
        "/bloquear NOME — Bloquear dispositivo\n"
        "/liberar NOME — Liberar dispositivo\n"
        "/reiniciar — Reiniciar roteador\n\n"
        "📱 *Celular:*\n"
        "/celular — Status do celular\n"
        "/bateria — Nível da bateria\n"
        "/screenshot — Capturar tela\n\n"
        "⏰ *Automação:*\n"
        "/agendar\\_off HH:MM — Desligar WiFi no horário\n"
        "/agendar\\_on HH:MM — Ligar WiFi no horário\n"
        "/cancelar — Cancelar agendamentos\n\n"
        "🌐 *Internet:*\n"
        "/meuip — Ver IP externo\n"
        "/velocidade — Testar velocidade",
        parse_mode="Markdown"
    )

async def status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Verificando...")
    try:
        s = get_session()
        ip_ext = ip_externo()
        bat    = bateria()
        if s:
            roteador = f"✅ Roteador online em `{ROUTER_IP}`"
        else:
            roteador = f"❌ Roteador offline ou senha errada"
        msg = (
            f"📡 *Status Geral*\n\n"
            f"{roteador}\n"
            f"🌐 IP externo: `{ip_ext}`\n"
            f"🔋 Bateria: {bat}\n"
            f"🕐 Hora: {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro: {e}")

async def wifi_on(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Ligando WiFi 2.4GHz...")
    try:
        s = get_session()
        if not s:
            await update.message.reply_text("❌ Sem conexão com o roteador.")
            return
        rpc(s, "set", {"wireless": {"enable": True, "band": "2.4GHz"}})
        await update.message.reply_text("✅ WiFi 2.4GHz *LIGADO*!", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro: {e}")

async def wifi_off(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Desligando WiFi 2.4GHz...")
    try:
        s = get_session()
        if not s:
            await update.message.reply_text("❌ Sem conexão com o roteador.")
            return
        rpc(s, "set", {"wireless": {"enable": False, "band": "2.4GHz"}})
        await update.message.reply_text("❌ WiFi 2.4GHz *DESLIGADO*!", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro: {e}")

async def wifi5_on(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Ligando WiFi 5GHz...")
    try:
        s = get_session()
        if not s:
            await update.message.reply_text("❌ Sem conexão com o roteador.")
            return
        rpc(s, "set", {"wireless": {"enable": True, "band": "5GHz"}})
        await update.message.reply_text("✅ WiFi 5GHz *LIGADO*!", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro: {e}")

async def wifi5_off(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Desligando WiFi 5GHz...")
    try:
        s = get_session()
        if not s:
            await update.message.reply_text("❌ Sem conexão com o roteador.")
            return
        rpc(s, "set", {"wireless": {"enable": False, "band": "5GHz"}})
        await update.message.reply_text("❌ WiFi 5GHz *DESLIGADO*!", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro: {e}")

async def dispositivos(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Buscando dispositivos...")
    try:
        s = get_session()
        if not s:
            await update.message.reply_text("❌ Sem conexão com o roteador.")
            return
        data = rpc(s, "get", {"hosts_info": {}})
        hosts = data.get("result", {}).get("hosts_info", {}).get("host_info", [])
        if hosts:
            msg = f"📱 *{len(hosts)} dispositivo(s):*\n\n"
            for h in hosts[:20]:
                nome = h.get("hostname") or h.get("name") or "Desconhecido"
                ip   = h.get("ip") or ""
                msg += f"• {nome} — `{ip}`\n"
        else:
            msg = "📱 Nenhum dispositivo encontrado."
        await update.message.reply_text(msg, parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro: {e}")

async def bloquear(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("⚠️ Use: /bloquear NOME_DO_DISPOSITIVO")
        return
    nome = " ".join(ctx.args)
    await update.message.reply_text(f"🔒 Bloqueando *{nome}*...", parse_mode="Markdown")
    try:
        s = get_session()
        if not s:
            await update.message.reply_text("❌ Sem conexão com o roteador.")
            return
        rpc(s, "set", {"access_control": {"block": nome}})
        await update.message.reply_text(f"🔒 *{nome}* bloqueado da internet!", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro: {e}")

async def liberar(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("⚠️ Use: /liberar NOME_DO_DISPOSITIVO")
        return
    nome = " ".join(ctx.args)
    await update.message.reply_text(f"🔓 Liberando *{nome}*...", parse_mode="Markdown")
    try:
        s = get_session()
        if not s:
            await update.message.reply_text("❌ Sem conexão com o roteador.")
            return
        rpc(s, "set", {"access_control": {"unblock": nome}})
        await update.message.reply_text(f"✅ *{nome}* liberado!", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro: {e}")

async def reiniciar(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Reiniciando roteador... Aguarde ~30 segundos.")
    try:
        s = get_session()
        if not s:
            await update.message.reply_text("❌ Sem conexão com o roteador.")
            return
        rpc(s, "do", {"device": {"reboot": None}})
        await update.message.reply_text("✅ Roteador reiniciando!")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro: {e}")

async def celular(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        bat = bateria()
        ip  = ip_externo()
        msg = (
            f"📱 *Status do Celular*\n\n"
            f"🔋 Bateria: {bat}\n"
            f"🌐 IP externo: `{ip}`\n"
            f"🕐 Hora: {datetime.datetime.now().strftime('%d/%m %H:%M')}"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro: {e}")

async def bateria_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    bat = bateria()
    await update.message.reply_text(f"🔋 Bateria: {bat}")

async def screenshot(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📸 Capturando tela...")
    try:
        subprocess.run(["termux-screenshot", "-f", "/sdcard/screenshot.png"], timeout=10)
        with open("/sdcard/screenshot.png", "rb") as f:
            await update.message.reply_photo(f, caption="📸 Screenshot do celular")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro: {e}\nInstale: pkg install termux-api")

async def meuip(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ip = ip_externo()
    await update.message.reply_text(f"🌐 Seu IP externo: `{ip}`", parse_mode="Markdown")

async def velocidade(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Testando velocidade... pode demorar ~30s")
    try:
        subprocess.run(["pip", "install", "speedtest-cli", "-q"], timeout=30)
        r = subprocess.run(["speedtest-cli", "--simple"], capture_output=True, text=True, timeout=60)
        await update.message.reply_text(f"🚀 *Resultado:*\n\n{r.stdout}", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro: {e}")

# ── AGENDAMENTOS ─────────────────────────────────────────────────────────────

async def agendar_off(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("⚠️ Use: /agendar_off HH:MM\nEx: /agendar_off 23:00")
        return
    horario = ctx.args[0]
    try:
        h, m = map(int, horario.split(":"))
        ctx.job_queue.run_daily(
            desligar_wifi_job,
            time=datetime.time(hour=h, minute=m),
            name=f"wifi_off_{horario}",
            chat_id=update.effective_chat.id
        )
        await update.message.reply_text(f"✅ WiFi vai desligar todo dia às *{horario}*!", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Formato inválido. Use HH:MM. Erro: {e}")

async def agendar_on(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("⚠️ Use: /agendar_on HH:MM\nEx: /agendar_on 07:00")
        return
    horario = ctx.args[0]
    try:
        h, m = map(int, horario.split(":"))
        ctx.job_queue.run_daily(
            ligar_wifi_job,
            time=datetime.time(hour=h, minute=m),
            name=f"wifi_on_{horario}",
            chat_id=update.effective_chat.id
        )
        await update.message.reply_text(f"✅ WiFi vai ligar todo dia às *{horario}*!", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Formato inválido. Use HH:MM. Erro: {e}")

async def cancelar(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    jobs = ctx.job_queue.get_jobs_by_name("wifi_off") + ctx.job_queue.get_jobs_by_name("wifi_on")
    for job in ctx.job_queue.jobs():
        job.schedule_removal()
    await update.message.reply_text("✅ Todos os agendamentos cancelados!")

async def desligar_wifi_job(ctx: ContextTypes.DEFAULT_TYPE):
    s = get_session()
    if s:
        rpc(s, "set", {"wireless": {"enable": False, "band": "2.4GHz"}})
        rpc(s, "set", {"wireless": {"enable": False, "band": "5GHz"}})
    await ctx.bot.send_message(chat_id=ctx.job.chat_id,
        text="🌙 WiFi desligado automaticamente!")

async def ligar_wifi_job(ctx: ContextTypes.DEFAULT_TYPE):
    s = get_session()
    if s:
        rpc(s, "set", {"wireless": {"enable": True, "band": "2.4GHz"}})
        rpc(s, "set", {"wireless": {"enable": True, "band": "5GHz"}})
    await ctx.bot.send_message(chat_id=ctx.job.chat_id,
        text="☀️ WiFi ligado automaticamente!")

# ── MAIN ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start",        start))
    app.add_handler(CommandHandler("status",       status))
    app.add_handler(CommandHandler("wifi_on",      wifi_on))
    app.add_handler(CommandHandler("wifi_off",     wifi_off))
    app.add_handler(CommandHandler("wifi5_on",     wifi5_on))
    app.add_handler(CommandHandler("wifi5_off",    wifi5_off))
    app.add_handler(CommandHandler("dispositivos", dispositivos))
    app.add_handler(CommandHandler("bloquear",     bloquear))
    app.add_handler(CommandHandler("liberar",      liberar))
    app.add_handler(CommandHandler("reiniciar",    reiniciar))
    app.add_handler(CommandHandler("celular",      celular))
    app.add_handler(CommandHandler("bateria",      bateria_cmd))
    app.add_handler(CommandHandler("screenshot",   screenshot))
    app.add_handler(CommandHandler("meuip",        meuip))
    app.add_handler(CommandHandler("velocidade",   velocidade))
    app.add_handler(CommandHandler("agendar_off",  agendar_off))
    app.add_handler(CommandHandler("agendar_on",   agendar_on))
    app.add_handler(CommandHandler("cancelar",     cancelar))
    print("✅ Bot WiFi Controller iniciado!")
    app.run_polling()
