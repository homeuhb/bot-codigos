import telebot
import imaplib
import email
import re
import threading
import os
from flask import Flask

# 1. TUS DATOS VITALES (Reemplaza lo que está entre comillas)
TOKEN = '8529679226:AAGVia7XKEL8OCStxrJLcoCJsVUfaGrFvbI'
MI_CORREO = 'homehubgemini2026@gmail.com'
MI_CLAVE_APP = 'stje qwma xgbw jesn'

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# 2. BASE DE DATOS DE USUARIOS (Asignación manual)
# Formato: "usuario_de_telegram": ['correo1@gmail.com', 'correo2@gmail.com']
usuarios_autorizados = {
    "juanito_perez": ['netflix_cliente@gmail.com', 'gpt_cliente@gmail.com'],
    "maria_lopez": ['max_cliente@gmail.com'],
    "Willion_9": ['homehubgeminiplus2026@gmail.com']
}

# --- LA MAGIA PARA LEER CORREOS (IMAP) ---
def obtener_ultimo_codigo(correo_buscado):
    try:
        # Conectarse a Gmail de forma invisible
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(MI_CORREO, MI_CLAVE_APP)
        mail.select("inbox")
        
        # Buscar correos enviados a esa dirección específica
        status, mensajes = mail.search(None, f'(TO "{correo_buscado}")')
        ids_correos = mensajes[0].split()
        
        if not ids_correos:
            return "📭 Aún no ha llegado ningún correo con código a esta cuenta."
            
        # Tomar el último correo (el más reciente)
        ultimo_id = ids_correos[-1]
        status, datos = mail.fetch(ultimo_id, "(RFC822)")
        
        for respuesta in datos:
            if isinstance(respuesta, tuple):
                mensaje = email.message_from_bytes(respuesta[1])
                contenido = ""
                
                # Extraer el texto del correo (incluso si tiene HTML o imágenes)
                if mensaje.is_multipart():
                    for parte in mensaje.walk():
                        if parte.get_content_type() == "text/plain":
                            contenido = parte.get_payload(decode=True).decode(errors='ignore')
                else:
                    contenido = mensaje.get_payload(decode=True).decode(errors='ignore')
                
                # Buscar cualquier número de 4 a 8 dígitos (códigos típicos)
                codigos = re.findall(r'\b\d{4,8}\b', contenido)
                if codigos:
                    return f"✅ El código recién llegado es: {codigos[-1]}"
                else:
                    return "⚠️ Se encontró un correo, pero no parece contener un código numérico."
    except Exception as e:
        return f"❌ Error de conexión: {e}"

# --- COMANDOS DEL BOT ---
@bot.message_handler(commands=['start'])
def inicio(message):
    id_user = message.from_user.id
    usuario = message.from_user.username
    bot.reply_to(message, f"¡Bienvenido!\n\nTu usuario es: {usuario}\nTu ID es: {id_user}\n\nEnvía tu nombre de usuario al administrador para que te asigne tus cuentas.")

@bot.message_handler(commands=['info'])
def info(message):
    bot.reply_to(message, f"👤 Usuario registrado: @{message.from_user.username}\n🔑 ID: {message.from_user.id}")

@bot.message_handler(commands=['linkc'])
def links(message):
    enlaces = (
        "🔗 **Portales de Gestión de Contraseñas:**\n\n"
        "🔴 Netflix: https://www.netflix.com/YourAccountn"
        "🟣 Max: https://auth.max.comn"
        "🟠 Crunchyroll: https://www.crunchyroll.com/es/reset_passwordn"
        "🟢 ChatGPT: https://chat.openai.comn"
        "🔵 Gemini: https://myaccount.google.comn"
        "⚪️ Amazon: https://www.amazon.com/a/settings/approvaln"
        "🐭 Disney+: https://www.disneyplus.com/account"
    )
    bot.reply_to(message, enlaces)

@bot.message_handler(commands=['code'])
def pedir_codigo(message):
    usuario = message.from_user.username
    
    # Separar el comando del correo (ej: /code cuenta@gmail.com)
    partes = message.text.split()
    if len(partes) < 2:
        bot.reply_to(message, "⚠️ Formato incorrecto. Escribe: /code tu_correo_asignado@gmail.com")
        return
        
    correo_pedido = partes[1]
    
    # Sistema de seguridad: Verificar si el usuario existe y si el correo le pertenece
    if usuario in usuarios_autorizados and correo_pedido in usuarios_autorizados[usuario]:
        bot.reply_to(message, f"⏳ Escaneando la bandeja de entrada de la plataforma...\n(Buscando el código para {correo_pedido})")
        respuesta = obtener_ultimo_codigo(correo_pedido)
        bot.reply_to(message, respuesta)
    else:
        bot.reply_to(message, "🚫 Acceso denegado. No tienes permisos para ver códigos de este correo.")

# --- SERVIDOR WEB DE SUPERVIVENCIA (Para que Render no lo borre) ---
@app.route('/')
def home():
    return "🚀 El bot está vivo y funcionando 24/7 en la nube."

def correr_bot():
    bot.infinity_polling()

if __name__ == '__main__':
    # Arrancamos el bot en un hilo secundario
    hilo = threading.Thread(target=correr_bot)
    hilo.start()
    
    # Arrancamos el servidor web para Render
    puerto = int(os.environ.get('PORT', 10000))
    app.run(host="0.0.0.0", port=puerto)
