import telebot
import imaplib
import email
import re
import threading
import os
from flask import Flask

# 1. TUS DATOS VITALES
TOKEN = 'PEGA_AQUI_TU_TOKEN_DE_TELEGRAM'
MI_CORREO = 'homehubgeminiplus2026@gmail.com'
MI_CLAVE_APP = '8529679226:AAGVia7XKEL8OCStxrJLcoCJsVUfaGrFvbI'

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# 2. BASE DE DATOS AVANZADA DE CLIENTES
usuarios_autorizados = {
    7517314702: {
        "nombre": "William Santa Croz Del",
        "cliente": "True",
        "cuentas": "disney, netflix",
        "expiracion": "Sin límite",
        "correos": ["correo_disney@gmail.com", "correo_netflix@gmail.com"] # Agrega aquí todos los correos de este cliente
    }
}

# Diccionario de palabras clave para que el bot sepa qué buscar según la plataforma
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
    'link': ['restablecer', 'password', 'enlace', 'link']
}

# --- EXTRACTOR INTELIGENTE DE CORREOS ---
def buscar_en_correo(correo_cliente, plataforma, tipo_busqueda='codigo'):
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(MI_CORREO, MI_CLAVE_APP)
        mail.select("inbox")
        
        # Filtrar correos dirigidos a la cuenta del cliente
        status, mensajes = mail.search(None, f'(TO "{correo_cliente}")')
        ids = mensajes[0].split()
        
        if not ids:
            return "📭 No se encontraron correos recientes para esta cuenta."
            
        # Analizar desde el último recibido hacia atrás
        for correo_id in reversed(ids):
            status, datos = mail.fetch(correo_id, "(RFC822)")
            for respuesta in datos:
                if isinstance(respuesta, tuple):
                    mensaje = email.message_from_bytes(respuesta[1])
                    asunto = mensaje['subject'].lower()
                    
                    # Verificar si el correo pertenece a la plataforma solicitada
                    palabras_clave = asuntos_permitidos.get(plataforma, [plataforma])
                    if any(palabra in asunto for palabra in palabras_clave):
                        
                        # Extraer cuerpo del correo
                        contenido = ""
                        if mensaje.is_multipart():
                            for parte in mensaje.walk():
                                if parte.get_content_type() in ["text/plain", "text/html"]:
                                    contenido += parte.get_payload(decode=True).decode(errors='ignore')
                        else:
                            contenido = mensaje.get_payload(decode=True).decode(errors='ignore')
                        
                        if tipo_busqueda == 'link':
                            # Buscar enlaces web (URLs)
                            urls = re.findall(r'https?://[^\s<>"]+', contenido)
                            if urls:
                                return f"🔗 Aquí tienes el enlace encontrado:\n{urls[0]}"
                            return "⚠️ Correo encontrado, pero no se halló ningún enlace válido."
                        else:
                            # Buscar códigos numéricos (4 a 8 dígitos)
                            codigos = re.findall(r'\b\d{4,8}\b', contenido)
                            if codigos:
                                return f"✅ Tu código de {plataforma.upper()} es: `{codigos[-1]}`"
                            
                            # Si no hay código pero es spotify/crunchy, intentar buscar link alternativo
                            urls = re.findall(r'https?://[^\s<>"]+', contenido)
                            if urls:
                                return f"🔗 No encontré código numérico, pero encontré este link de acceso/restablecimiento:\n{urls[0]}"
                            
                            return f"⚠️ Correo de {plataforma.upper()} encontrado, pero no contiene un código numérico."
                            
        return f"📭 No se encontró ningún correo reciente que coincida con {plataforma.upper()}."
    except Exception as e:
        return f"❌ Error al conectar con el servidor de correo: {e}"

# --- HELPER DE VALIDACIÓN ---
def validar_y_procesar(message, plataforma, tipo_busqueda='codigo'):
    id_user = message.from_user.id
    partes = message.text.split()
    
    if len(partes) < 2:
        bot.reply_to(message, f"⚠️ Formato incorrecto. Usa: /{plataforma} correo@gmail.com")
        return

    correo_pedido = partes[1]
    
    if id_user in usuarios_autorizados:
        datos = usuarios_autorizados[id_user]
        if correo_pedido in datos["correos"]:
            bot.reply_to(message, f"⏳ Escaneando bandeja para {correo_pedido} en {plataforma.upper()}...")
            respuesta = buscar_en_correo(correo_pedido, plataforma, tipo_busqueda)
            bot.reply_to(message, respuesta, parse_mode="Markdown")
        else:
            bot.reply_to(message, "🚫 Ese correo no está asociado a tu cuenta de usuario.")
    else:
        bot.reply_to(message, "🚫 No estás registrado como cliente autorizado.")

# --- COMANDOS CONFIGURADOS SEGÚN TU SOLICITUD ---

@bot.message_handler(commands=['start'])
def start(message):
    guia = (
        "🤖 **Comandos para clientes:**\n"
        "/start — Registrarse (solo la primera vez)\n"
        "/info — Ver información de tu usuario\n"
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
        "/apple CORREO — Código de verificación de Apple (requiere autorización)"
    )
    bot.reply_to(message, guia)

@bot.message_handler(commands=['info'])
def info(message):
    id_user = message.from_user.id
    if id_user in usuarios_autorizados:
        u = usuarios_autorizados[id_user]
        txt = (f"**INFO**\n"
               f"Username: {u['nombre']}\n"
               f"ID: `{id_user}` CLIENTE: {u['cliente']} Cuentas: {u['cuentas']} Expiración: {u['expiracion']}")
    else:
        txt = (f"**INFO**\n"
               f"Username: {message.from_user.first_name} {message.from_user.last_name or ''}\n"
               f"ID: `{id_user}` CLIENTE: False Cuentas: Ninguna Expiración: No registrado")
    bot.reply_to(message, txt, parse_mode="Markdown")

@bot.message_handler(commands=['cuentas'])
def ver_cuentas(message):
    id_user = message.from_user.id
    if id_user in usuarios_autorizados:
        u = usuarios_autorizados[id_user]
        correos_lista = "\n• ".join(u["correos"])
        bot.reply_to(message, f"📋 **Tus correos autorizados:**\n• {correos_lista}")
    else:
        bot.reply_to(message, "🚫 No tienes cuentas asignadas.")

# MAPEO DE COMANDOS DE PLATAFORMAS (Llaman a la función inteligente)
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

# COMANDOS ESPECIALES DE LINKS
@bot.message_handler(commands=['hogar'])
def cmd_hogar(message):
    # Libre para cualquier registrado según tu regla
    id_user = message.from_user.id
    if id_user in usuarios_autorizados:
        validar_y_procesar(message, 'netflix', 'link')
    else:
        bot.reply_to(message, "🚫 Debes ser un usuario registrado para usar /hogar.")

@bot.message_handler(commands=['link'])
def cmd_link(message):
    # Formato: /link crunchy correo@gmail.com
    partes = message.text.split()
    if len(partes) < 3:
        bot.reply_to(message, "⚠️ Usa el formato: /link [plataforma] correo@gmail.com")
        return
    plataforma_sub = partes[1].lower()
    correo_sub = partes[2]
    
    # Modificar temporalmente el mensaje para reusar el validador
    message.text = f"/{plataforma_sub} {correo_sub}"
    validar_y_procesar(message, 'link', 'link')

# --- CONFIGURACIÓN DE RESPIRACIÓN EN LA NUBE ---
@app.route('/')
def home(): return "🚀 Sistema Multi-Plataforma Activo"

if __name__ == '__main__':
    threading.Thread(target=lambda: bot.infinity_polling()).start()
    app.run(host="0.0.0.0", port=int(os.environ.get('PORT', 10000)))
