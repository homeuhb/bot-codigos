import telebot
import imaplib
import email
import re
import threading
import os
from flask import Flask

# 1. TUS DATOS VITALES
TOKEN = '8529679226:AAGVia7XKEL8OCStxrJLcoCJsVUfaGrFvbI'
MI_CORREO = 'homehubgeminiplus2026@gmail.com'
MI_CLAVE_APP = 'stje qwma xgbw jesn'

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# 2. BASE DE DATOS AVANZADA DE CLIENTES
usuarios_autorizados = {
    7517314702: {
        "nombre": "William Santa Croz Del",
        "cliente": "True",
        "cuentas": "disney, netflix, gemini",
        "expiracion": "Sin límite",
        "correos": ["correo_disney@gmail.com", "correo_netflix@gmail.com", "homehubgeminiplus2026@gmail.com]
    }
}

asuntos_permitidos = {
    'netflix': ['netflix', 'código de inicio de sesión'],
    'disney': ['disney', 'código de verificación'],
    'amazon': ['amazon', 'verificación'],
    'deezer': ['deezer'],
    'vix': ['vix'],
    'max': ['max', 'hbo', 'restablecer'],
    'crunchy': ['crunchyroll'],
    'gpt': ['openai', 'chatgpt'],
    'spotify': ['spotify'],
    'apple': ['apple', 'id de apple'],
    'gemini': ['gemini', 'google', 'verificación de google'],
    'link': ['restablecer', 'password', 'enlace', 'link']
}

# --- EXTRACTOR INTELIGENTE DE CORREOS ---
def buscar_en_correo(correo_cliente, plataforma, tipo_busqueda='codigo'):
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(MI_CORREO, MI_CLAVE_APP)
        mail.select("inbox")
        
        status, mensajes = mail.search(None, f'(TO "{correo_cliente}")')
        ids = mensajes[0].split()
        
        if not ids:
            return "📭 No se encontraron correos recientes para esta cuenta."
            
        for correo_id in reversed(ids):
            status, datos = mail.fetch(correo_id, "(RFC822)")
            for respuesta in datos:
                if isinstance(respuesta, tuple):
                    mensaje = email.message_from_bytes(respuesta[1])
                    asunto = mensaje['subject'].lower()
                    
                    palabras_clave = asuntos_permitidos.get(plataforma, [plataforma])
                    if any(palabra in asunto for palabra in palabras_clave):
                        contenido = ""
                        if mensaje.is_multipart():
                            for parte in mensaje.walk():
                                if parte.get_content_type() in ["text/plain", "text/html"]:
                                    contenido += parte.get_payload(decode=True).decode(errors='ignore')
                        else:
                            contenido = mensaje.get_payload(decode=True).decode(errors='ignore')
                        
                        if tipo_busqueda == 'link':
                            urls = re.findall(r'https?://[^\s<>"]+', contenido)
                            if urls:
                                return f"🔗 Aquí tienes el enlace encontrado:\n{urls[0]}"
                            return "⚠️ Correo encontrado, pero no se halló ningún enlace válido."
                        else:
                            codigos = re.findall(r'\b\d{4,8}\b', contenido)
                            if codigos:
                                return f"✅ Tu código de {plataforma.upper()} es: `{codigos[-1]}`"
                            
                            urls = re.findall(r'https?://[^\s<>"]+', contenido)
                            if urls:
                                return f"🔗 No encontré código numérico, pero encontré este link:\n{urls[0]}"
                            
                            return f"⚠️ Correo de {plataforma.upper()} encontrado, pero sin código numérico."
                            
        return f"📭 No se encontró correo reciente de {plataforma.upper()}."
    except Exception as e:
        return f"❌ Error de servidor: {e}"

def validar_y_procesar(message, plataforma, tipo_busqueda='codigo'):
    id_user = message.from_user.id
    partes = message.text.split()
    
    if len(partes) < 2:
        bot.reply_to(message, f"⚠️ Usa: /{plataforma} correo@gmail.com")
        return

    correo_pedido = partes[1]
    
    if id_user in usuarios_autorizados:
        datos = usuarios_autorizados[id_user]
        if correo_pedido in datos["correos"]:
            bot.reply_to(message, f"⏳ Escaneando bandeja para {correo_pedido} en {plataforma.upper()}...")
            bot.reply_to(message, buscar_en_correo(correo_pedido, plataforma, tipo_busqueda), parse_mode="Markdown")
        else:
            bot.reply_to(message, "🚫 Ese correo no está asociado a tu cuenta.")
    else:
        bot.reply_to(message, "🚫 No estás registrado como cliente autorizado.")

# --- COMANDOS /start Y /info FUSIONADOS Y CON EMOJIS ---
@bot.message_handler(commands=['start', 'info'])
def info_start(message):
    id_user = message.from_user.id
    if id_user in usuarios_autorizados:
        u = usuarios_autorizados[id_user]
        txt = (f"🚀🍿 INFO\n"
               f"🔥 Username: {u['nombre']}\n"
               f"⚡ ID: {id_user} 🗂️ CLIENTE: {u['cliente']} 🌐 Cuentas: {u['cuentas']} 👉 Expiración: {u['expiracion']}")
    else:
        nombre_telegram = f"{message.from_user.first_name} {message.from_user.last_name or ''}".strip()
        txt = (f"🚀🍿 INFO\n"
               f"🔥 Username: {nombre_telegram}\n"
               f"⚡ ID: {id_user} 🗂️ CLIENTE: False 🌐 Cuentas: Ninguna 👉 Expiración: No registrado\n\n"
               f"*(Usa /cmd para ver los comandos)*")
    bot.reply_to(message, txt, parse_mode="Markdown")

# --- NUEVO COMANDO /cmd ACTUALIZADO ---
@bot.message_handler(commands=['cmd'])
def cmd_lista(message):
    guia = (
        "Comandos para clientes:\n"
        "/start — Registrarse (solo la primera vez)\n"
        "/info — Ver información de tu usuario\n"
        "/cmd — Ver esta lista de comandos\n"
        "/cuentas — Ver tus cuentas asociadas\n"
        "/disney CORREO — Consultar CÓDIGO Disney+ (requiere autorización)\n"
        "/netflix CORREO — Consultar CÓDIGO Netflix (requiere autorización)\n"
        "/hogar CORREO — Obtener LINK de Hogar (Netflix) — libre para registrados\n"
        "/link [plataforma] CORREO — Obtener LINK (ej: /link crunchy correo). (requiere autorización)\n"
        "/amazon CORREO — Consultar CÓDIGO Amazon (requiere autorización)\n"
        "/deezer CORREO — Consultar CÓDIGO Deezer (requiere autorización)\n"
        "/vix CORREO — Consultar CÓDIGO Vix (requiere autorización)\n"
        "/max CORREO — Código o LINK de Max (HBO) (requiere autorización)\n"
        "/crunchy CORREO — **Obtiene LINK** de Crunchyroll si no existe OTP (requiere autorización)\n"
        "/gpt CORREO — Consultar CÓDIGO ChatGPT (requiere autorización)\n"
        "/spotify CORREO — Código de inicio; si no hay OTP, intenta devolver LINK (requiere autorización)\n"
        "/apple CORREO — Código de verificación de Apple (requiere autorización)\n"
        "/gemini CORREO — Consultar CÓDIGO Gemini (requiere autorización)"
    )
    bot.reply_to(message, guia, parse_mode="Markdown")

@bot.message_handler(commands=['cuentas'])
def ver_cuentas(message):
    id_user = message.from_user.id
    if id_user in usuarios_autorizados:
        correos = "\n• ".join(usuarios_autorizados[id_user]["correos"])
        bot.reply_to(message, f"📋 **Tus correos:**\n• {correos}", parse_mode="Markdown")
    else:
        bot.reply_to(message, "🚫 No tienes cuentas asignadas.")

# MAPEO DE PLATAFORMAS INCLUYENDO GEMINI
@bot.message_handler(commands=['netflix'])
def cmd_netflix(message): validar_y_procesar(message, 'netflix', 'codigo')
@bot.message_handler(commands=['disney'])
def cmd_disney(message): validar_y_procesar(message, 'disney', 'codigo')
@bot.message_handler(commands=['amazon'])
def cmd_amazon(message): validar_y_procesar(message, 'amazon', 'codigo')
@bot.message_handler(commands=['deezer'])
def cmd_deezer(message): validar_y_procesar(message, 'deezer', 'codigo')
@bot.message_handler(commands=['vix'])
def cmd_vix(message): validar_y_procesar(message, 'vix', 'codigo')
@bot.message_handler(commands=['max'])
def cmd_max(message): validar_y_procesar(message, 'max', 'codigo')
@bot.message_handler(commands=['crunchy'])
def cmd_crunchy(message): validar_y_procesar(message, 'crunchy', 'codigo')
@bot.message_handler(commands=['gpt'])
def cmd_gpt(message): validar_y_procesar(message, 'gpt', 'codigo')
@bot.message_handler(commands=['spotify'])
def cmd_spotify(message): validar_y_procesar(message, 'spotify', 'codigo')
@bot.message_handler(commands=['apple'])
def cmd_apple(message): validar_y_procesar(message, 'apple', 'codigo')
@bot.message_handler(commands=['gemini'])
def cmd_gemini(message): validar_y_procesar(message, 'gemini', 'codigo')

@bot.message_handler(commands=['hogar'])
def cmd_hogar(message):
    if message.from_user.id in usuarios_autorizados:
        validar_y_procesar(message, 'netflix', 'link')
    else:
        bot.reply_to(message, "🚫 Debes ser usuario registrado.")

@bot.message_handler(commands=['link'])
def cmd_link(message):
    partes = message.text.split()
    if len(partes) < 3:
        bot.reply_to(message, "⚠️ Usa: /link [plataforma] correo@gmail.com")
        return
    message.text = f"/{partes[1].lower()} {partes[2]}"
    validar_y_procesar(message, 'link', 'link')

@app.route('/')
def home(): return "🚀 Sistema Multi-Plataforma Activo"

if __name__ == '__main__':
    threading.Thread(target=lambda: bot.infinity_polling()).start()
    app.run(host="0.0.0.0", port=int(os.environ.get('PORT', 10000)))
