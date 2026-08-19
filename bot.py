import os
import re
import json
import logging
import imaplib
import email
from email.header import decode_header
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters
)

# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Cargar variables de entorno
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
SPREADSHEET_NAME = os.environ.get("SPREADSHEET_NAME")
GOOGLE_CREDS_JSON = os.environ.get("GOOGLE_CREDS_JSON")
ADMIN_TELEGRAM_ID = os.environ.get("ADMIN_TELEGRAM_ID")

# Inicializar cliente de Google Sheets
def get_sheets_client():
    if not GOOGLE_CREDS_JSON:
        logger.error("La variable GOOGLE_CREDS_JSON no está configurada.")
        return None
    try:
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive.file",
            "https://www.googleapis.com/auth/drive"
        ]
        creds_dict = json.loads(GOOGLE_CREDS_JSON)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        logger.error(f"Error al conectar con Google Sheets: {e}")
        return None

# Helper para limpiar y normalizar Telegram IDs (int, str, float, 'admin', separadores)
def clean_client_ids(raw_val):
    if raw_val is None:
        return []
    val_str = str(raw_val).strip()
    if not val_str:
        return []
    
    parts = [p.strip() for p in re.split(r'[,;\s]+', val_str) if p.strip()]
    cleaned = []
    for p in parts:
        if p.endswith(".0"):
            p = p[:-2]
        if p.lower() in ["admin", "vendedor"] and ADMIN_TELEGRAM_ID:
            p = str(ADMIN_TELEGRAM_ID).strip()
        if p not in cleaned:
            cleaned.append(p)
    return cleaned

# Buscar cuenta en Google Sheets o archivo local
def find_account_in_sheet(email_address, provider=None):
    client = get_sheets_client()
    if not client:
        # Fallback a archivo JSON local si no hay credenciales de Google Sheets
        local_path = os.path.join(os.path.dirname(__file__), "accounts.json")
        if os.path.exists(local_path):
            try:
                with open(local_path, "r", encoding="utf-8") as f:
                    records = json.load(f)
                    for record in records:
                        record_email = str(record.get("correo_streaming", "")).strip().lower()
                        record_provider = str(record.get("proveedor", "")).strip().lower()
                        if record_email == email_address.strip().lower():
                            if provider and record_provider != provider.lower():
                                continue
                            logger.info(f"Cuenta encontrada en archivo local accounts.json: {email_address} ({record_provider})")
                            return record
            except Exception as e:
                logger.error(f"Error al leer accounts.json local: {e}")
        return None
    try:
        sheet = client.open(SPREADSHEET_NAME).sheet1
        records = sheet.get_all_records()
        for record in records:
            record_email = str(record.get("correo_streaming", "")).strip().lower()
            record_provider = str(record.get("proveedor", "")).strip().lower()
            if record_email == email_address.strip().lower():
                if provider and record_provider != provider.lower():
                    continue
                return record
        return None
    except Exception as e:
        logger.error(f"Error al buscar la cuenta {email_address} en la hoja: {e}")
        return None

# Actualizar asignación de cliente en Google Sheets o archivo local (Soporta múltiples clientes por correo)
def update_account_assignment(email_address, client_id_to_add=None, client_id_to_remove=None):
    email_address = email_address.strip().lower()
    client = get_sheets_client()
    
    # 1. Si no hay Google Sheets, actualizar en el archivo local accounts.json
    if not client:
        local_path = os.path.join(os.path.dirname(__file__), "accounts.json")
        if os.path.exists(local_path):
            try:
                with open(local_path, "r", encoding="utf-8") as f:
                    records = json.load(f)
                
                updated = False
                for record in records:
                    if str(record.get("correo_streaming", "")).strip().lower() == email_address:
                        current_val = str(record.get("cliente_telegram_id", "")).strip()
                        current_ids = [x.strip() for x in current_val.split(",") if x.strip()]
                        
                        if client_id_to_add:
                            if str(client_id_to_add) not in current_ids:
                                current_ids.append(str(client_id_to_add))
                        elif client_id_to_remove:
                            current_ids = [x for x in current_ids if x != str(client_id_to_remove)]
                        else: # Desasignar todos los clientes
                            current_ids = []
                            
                        record["cliente_telegram_id"] = ", ".join(current_ids)
                        updated = True
                
                if updated:
                    with open(local_path, "w", encoding="utf-8") as f:
                        json.dump(records, f, indent=2, ensure_ascii=False)
                    return True, "Asignación actualizada en accounts.json local."
                else:
                    return False, "Correo no encontrado en accounts.json local."
            except Exception as e:
                return False, f"Error actualizando accounts.json: {e}"
        return False, "Google Sheets no configurado y accounts.json no existe."

    # 2. Si Google Sheets está configurado, actualizar allí
    try:
        sheet = client.open(SPREADSHEET_NAME).sheet1
        records = sheet.get_all_records()
        
        headers = sheet.row_values(1)
        col_idx = -1
        for idx, header in enumerate(headers):
            if header.strip().lower() == "cliente_telegram_id":
                col_idx = idx + 1
                break
                
        if col_idx == -1:
            return False, "La columna 'cliente_telegram_id' no existe en la hoja."

        updated = False
        for idx, record in enumerate(records):
            if str(record.get("correo_streaming", "")).strip().lower() == email_address:
                row_idx = idx + 2
                current_val = str(record.get("cliente_telegram_id", "")).strip()
                current_ids = [x.strip() for x in current_val.split(",") if x.strip()]
                
                if client_id_to_add:
                    if str(client_id_to_add) not in current_ids:
                        current_ids.append(str(client_id_to_add))
                elif client_id_to_remove:
                    current_ids = [x for x in current_ids if x != str(client_id_to_remove)]
                else:
                    current_ids = []
                    
                new_val = ", ".join(current_ids)
                sheet.update_cell(row_idx, col_idx, new_val)
                updated = True
                
        if updated:
            return True, "Asignación actualizada exitosamente en Google Sheets."
        else:
            return False, "Correo no encontrado en la hoja de cálculo."
        
    except Exception as e:
        logger.error(f"Error actualizando la hoja: {e}")
        return False, f"Error de conexión con Google Sheets: {e}"

# Obtener lista de todas las cuentas
def get_all_accounts():
    client = get_sheets_client()
    if not client:
        local_path = os.path.join(os.path.dirname(__file__), "accounts.json")
        if os.path.exists(local_path):
            try:
                with open(local_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return []
    try:
        sheet = client.open(SPREADSHEET_NAME).sheet1
        return sheet.get_all_records()
    except Exception:
        return []

# Decodificar el asunto o cuerpo del correo
def safe_decode(payload, charset):
    if charset:
        try:
            return payload.decode(charset, errors="ignore")
        except Exception:
            pass
    return payload.decode("utf-8", errors="ignore")

# Obtener el cuerpo de un mensaje de correo
def get_email_body(msg):
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))
            if content_type == "text/plain" and "attachment" not in content_disposition:
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset()
                body += safe_decode(payload, charset)
            elif content_type == "text/html" and "attachment" not in content_disposition:
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset()
                body += safe_decode(payload, charset)
    else:
        payload = msg.get_payload(decode=True)
        charset = msg.get_content_charset()
        body = safe_decode(payload, charset)
    return body

# Extraer el código OTP usando patrones comunes de texto
def extract_verification_code(body, provider):
    body_clean = body.replace("\r", "").replace("\n", " ")
    
    # 1. Intentar buscar un patrón según el proveedor
    if provider.lower() == "netflix":
        match = re.search(r'(?:c[óo]digo|code)[^\d]*(\b\d{4}\b)', body_clean, re.IGNORECASE)
        if match:
            return match.group(1)
    elif provider.lower() in ["disney", "disneyplus"]:
        match = re.search(r'(?:c[óo]digo|code)[^\d]*(\b\d{6}\b)', body_clean, re.IGNORECASE)
        if match:
            return match.group(1)
            
    # 2. Búsqueda genérica de códigos numéricos comunes (4 a 8 dígitos) cerca de palabras clave
    match_generic = re.search(r'(?:c[óo]digo|code|verification|verificaci[oó]n|otp|seguridad)[^\d]*(\b\d{4,8}\b)', body_clean, re.IGNORECASE)
    if match_generic:
        return match_generic.group(1)
        
    # 3. Si no hay coincidencia exacta, buscar cualquier número de 4, 6 o 8 dígitos aislado
    match_digits = re.findall(r'\b\d{4,8}\b', body_clean)
    if match_digits:
        return match_digits[-1]
        
    return None

# Extraer links importantes del correo (restablecimiento, hogar, contraseña)
def extract_important_links(body):
    """Extrae URLs relevantes del cuerpo del correo: reset de contraseña,
    confirmación de hogar, verificación de dispositivo, etc."""
    body_clean = body.replace("\r", "").replace("\n", " ")
    
    important_keywords = [
        "reset", "restablecer", "password", "contraseña",
        "hogar", "home", "location", "ubicacion", "ubicación",
        "verify", "verificar", "verifica", "confirm", "confirmar",
        "approve", "aprobar", "allow", "permitir",
        "update", "actualizar", "manage", "gestionar",
        "travel", "viaje"
    ]
    
    # Dominios de sistema/notificaciones a ignorar absolutamente
    ignored_domains = [
        'pixel', 'track', '.png', '.jpg', '.gif', '.css', 'unsubscribe', 'open?',
        'google.com', 'gstatic.com', 'microsoft.com', 'live.com', 'secureserver.net', 'accounts.google'
    ]
    
    all_urls = re.findall(r'https?://[^\s<>"]+', body_clean)
    
    important_links = []
    seen = set()
    for url in all_urls:
        url = url.rstrip('"\'>)').rstrip('&nbsp;').rstrip('.').rstrip(',')
        if url in seen:
            continue
        seen.add(url)
        url_lower = url.lower()
        
        # Ignorar links de sistema (Google, Microsoft, imágenes, etc.)
        if any(skip in url_lower for skip in ignored_domains):
            continue
            
        # Incluir si contiene una palabra clave relevante
        if any(kw in url_lower for kw in important_keywords):
            important_links.append(url)
    
    return important_links[:2]  # máximo 2 links relevantes

# Conectarse a IMAP y recuperar el código
def fetch_code_from_imap(imap_server, user, password, provider):
    try:
        mail = imaplib.IMAP4_SSL(imap_server, timeout=15)
        mail.login(user, password)
        mail.select("INBOX")
        
        status, data = mail.search(None, "ALL")
        if status != "OK" or not data[0]:
            mail.logout()
            return "No se encontraron correos en la bandeja de entrada.", None
            
        mail_ids = data[0].split()
        # Buscar en los últimos 10 correos recibidos
        recent_ids = mail_ids[-10:]
        recent_ids.reverse()
        
        latest_sender = ""
        latest_subject = ""
        latest_body = ""
        
        for m_id in recent_ids:
            status, msg_data = mail.fetch(m_id, "(RFC822)")
            if status != "OK":
                continue
                
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    
                    # Extraer asunto
                    subject, encoding = decode_header(msg["Subject"])[0]
                    if isinstance(subject, bytes):
                        subject = subject.decode(encoding or "utf-8", errors="ignore")
                        
                    # Extraer remitente
                    sender, encoding = decode_header(msg["From"])[0]
                    if isinstance(sender, bytes):
                        sender = sender.decode(encoding or "utf-8", errors="ignore")
                    
                    is_relevant = False
                    prov = provider.lower()
                    
                    # Filtros estrictos por proveedor (se descartan correos de Google/Sistema)
                    if prov == "netflix" and ("netflix" in sender.lower() or "netflix" in subject.lower()):
                        is_relevant = True
                    elif prov in ["disney", "disneyplus"] and ("disney" in sender.lower() or "disney" in subject.lower()):
                        is_relevant = True
                    elif (prov in ["prime", "amazon"]) and ("amazon" in sender.lower() or "prime" in sender.lower() or "amazon" in subject.lower() or "prime" in subject.lower()):
                        is_relevant = True
                    elif (prov in ["max", "hbo"]) and ("hbo" in sender.lower() or "max" in sender.lower() or "warnermedia" in sender.lower() or "hbo" in subject.lower() or "max" in subject.lower()):
                        is_relevant = True
                    elif (prov in ["crunchy", "crunchyroll"]) and ("crunchy" in sender.lower() or "crunchyroll" in sender.lower() or "crunchy" in subject.lower()):
                        is_relevant = True
                    elif prov == "paramount" and ("paramount" in sender.lower() or "paramount" in subject.lower()):
                        is_relevant = True
                        
                    if is_relevant:
                        body = get_email_body(msg)
                        latest_sender = sender
                        latest_subject = subject
                        latest_body = body
                        break
            if latest_body:
                break
                
        mail.logout()
        
        if not latest_body:
            return f"No se encontró ningún correo reciente de **{provider.upper()}** en esta cuenta.", None
            
        code = extract_verification_code(latest_body, provider)
        links = extract_important_links(latest_body)
        
        return None, {
            "remitente": latest_sender,
            "asunto": latest_subject,
            "codigo": code,
            "links": links
        }
            
    except imaplib.IMAP4.error as imap_err:
        logger.error(f"Error de autenticación IMAP para {user}: {imap_err}")
        return "Error al iniciar sesión en el correo. Verifica que la contraseña de aplicación sea correcta.", None
    except Exception as e:
        logger.error(f"Error general en IMAP para {user}: {e}")
        return f"Error de conexión con el servidor de correo: {str(e)}", None

# Comando /start
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    welcome_text = (
        f"👋 ¡Hola! Bienvenido al asistente de códigos de streaming.\n\n"
        f"👤 **Tu Telegram ID es:** `{user_id}`\n"
        f"*(Copia este ID y envíaselo a tu vendedor para que te asigne tus cuentas)*\n\n"
        f"📋 Usa `/miscuentas` para ver tus servicios asignados.\n\n"
        f"🔍 **¿Cómo obtener tu código?**\n"
        f"Usa el comando de tu plataforma seguido del correo:\n"
        f"🎥 `/netflix correo@ejemplo.com`\n"
        f"🧞 `/disney correo@ejemplo.com`\n"
        f"📦 `/prime correo@ejemplo.com`\n"
        f"🍿 `/max correo@ejemplo.com`\n"
        f"⛰️ `/paramount correo@ejemplo.com`\n"
        f"⛩️ `/crunchy correo@ejemplo.com`"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

# Comando /info
async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    user_str = f"@{username}" if username else "No configurado"
    info_text = (
        f"👤 **Información del Cliente**\n\n"
        f"🔑 **Telegram ID:** `{user_id}`\n"
        f"🏷️ **Usuario:** `{user_str}`\n\n"
        f"📢 **¿Cómo tener acceso a tus cuentas?**\n"
        f"Copia tu **Telegram ID** y compártelo con tu vendedor. Él asignará tus cuentas (Netflix, Disney, etc.) a tu ID para que puedas consultar sus códigos de verificación de forma segura."
    )
    await update.message.reply_text(info_text, parse_mode="Markdown")

# Comando /miscuentas (para que el cliente consulte sólo sus cuentas asignadas)
async def miscuentas_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id).strip()
    accounts = get_all_accounts()
    
    my_accounts = []
    for acc in accounts:
        client_ids = clean_client_ids(acc.get("cliente_telegram_id", ""))
        if user_id in client_ids:
            my_accounts.append(acc)
            
    if not my_accounts:
        await update.message.reply_text(
            f"📭 **No tienes cuentas asignadas actualmente.**\n\n"
            f"🔑 Tu Telegram ID es: `{user_id}`\n"
            f"Compártelo con tu vendedor para que te asigne tus cuentas de streaming.",
            parse_mode="Markdown"
        )
        return
        
    text = "📱 **Tus Cuentas Asignadas:**\n\n"
    for acc in my_accounts:
        email_str = acc.get("correo_streaming", "N/A")
        provider = str(acc.get("proveedor", "N/A")).upper()
        text += f"• 🎬 **{provider}:** `{email_str}`\n"
        
    example_email = my_accounts[0].get("correo_streaming", "correo@ejemplo.com")
    text += f"\n💡 *Para obtener tu código, usa el comando de tu plataforma seguido del correo.*\nEjemplo: `/{my_accounts[0].get('proveedor', 'netflix').lower()} {example_email}`"
    
    await update.message.reply_text(text, parse_mode="Markdown")

# Procesar búsqueda de correo
async def process_search(update: Update, email_address: str, platform_filter=None):
    email_address = email_address.strip()
    
    if not re.match(r"[^@]+@[^@]+\.[^@]+", email_address):
        await update.message.reply_text("❌ Por favor, ingresa un correo electrónico válido.")
        return

    status_message = await update.message.reply_text(f"🔍 Buscando cuenta para `{email_address}`...")
    
    # Buscar cuenta
    account = find_account_in_sheet(email_address, platform_filter)
    if not account:
        await status_message.edit_text("❌ Este correo no está registrado en el sistema. Consulta con tu vendedor.")
        return
        
    # Validar autorización por Telegram ID (Soporta múltiples clientes por correo y formatos int/str)
    user_id = str(update.message.from_user.id).strip()
    allowed_ids = clean_client_ids(account.get("cliente_telegram_id", ""))
        
    # Permitir que el admin consulte cualquier cuenta para testing o soporte
    is_admin = ADMIN_TELEGRAM_ID and user_id == str(ADMIN_TELEGRAM_ID).strip()
    
    if not is_admin:
        if not allowed_ids:
            await status_message.edit_text("❌ Esta cuenta no tiene clientes asignados en el sistema. Consulta con tu vendedor.")
            return
        if user_id not in allowed_ids:
            await status_message.edit_text(
                f"❌ No tienes permisos para consultar esta cuenta.\n\n"
                f"🔑 Tu Telegram ID es: `{user_id}`\n"
                f"Por favor, pídele a tu vendedor que asocie este ID a tu cuenta de streaming."
            )
            return

    # Validar que el proveedor coincida con la plataforma del comando (opcional, ayuda a evitar errores del cliente)
    sheet_provider = str(account.get("proveedor", "")).strip().lower()
    if platform_filter and sheet_provider and platform_filter.lower() != sheet_provider:
        # Si difieren, advertir al cliente
        await status_message.edit_text(
            f"⚠️ Esta cuenta está registrada en la hoja de cálculo como **{sheet_provider.upper()}**, "
            f"pero usaste el comando para **{platform_filter.upper()}**. Verifica el comando."
        )
        return
        
    provider = platform_filter or sheet_provider or "Streaming"
    imap_server = account.get("servidor_imap")
    user = account.get("correo_streaming")
    password = account.get("clave_correo")
    
    if not imap_server or not user or not password:
        await status_message.edit_text("⚠️ Los datos de conexión de esta cuenta están incompletos en el sistema.")
        return
        
    await status_message.edit_text(f"📥 Conectando al buzón de correo ({provider.upper()})... Buscando código reciente...")
    
    # Buscar correo y código vía IMAP
    error, result = fetch_code_from_imap(imap_server, user, password, provider)
    
    if error:
        await status_message.edit_text(f"❌ {error}", parse_mode="Markdown")
    else:
        code = result.get('codigo')
        links = result.get('links', [])
        
        response_text = (
            f"✅ **{provider.upper()}**\n\n"
            f"📧 **Cuenta:** `{email_address}`\n"
        )
        
        # Si hay un código numérico, enviar SOLO el código
        if code:
            response_text += f"\n🔑 **Código:** `{code}`"
        # Si NO hay código pero SÍ hay enlace (ej. confirmación de hogar / reset), enviar SOLO el enlace
        elif links:
            response_text += "\n🔗 **Enlace de Verificación / Hogar:**\n"
            for link in links:
                response_text += f"{link}\n"
        else:
            response_text += f"\n⚠️ No se detectó un código o enlace en el último correo de {provider.upper()}."
        
        await status_message.edit_text(response_text, parse_mode="Markdown", disable_web_page_preview=True)

# Handlers para plataformas
async def netflix_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Uso: `/netflix correo@ejemplo.com`")
        return
    await process_search(update, context.args[0], "netflix")

async def disney_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Uso: `/disney correo@ejemplo.com`")
        return
    await process_search(update, context.args[0], "disney")

async def prime_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Uso: `/prime correo@ejemplo.com`")
        return
    await process_search(update, context.args[0], "prime")

async def max_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Uso: `/max correo@ejemplo.com`")
        return
    await process_search(update, context.args[0], "max")

async def crunchy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Uso: `/crunchy correo@ejemplo.com`")
        return
    await process_search(update, context.args[0], "crunchyroll")

async def paramount_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Uso: `/paramount correo@ejemplo.com`")
        return
    await process_search(update, context.args[0], "paramount")

# COMANDOS DE ADMINISTRADOR (VENDEDOR)

# Comando /asignar [correo] [telegram_id]
async def asignar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    if not ADMIN_TELEGRAM_ID or user_id != str(ADMIN_TELEGRAM_ID).strip():
        await update.message.reply_text("❌ Este comando solo puede ser utilizado por el Administrador/Vendedor.")
        return
        
    if len(context.args) < 2:
        await update.message.reply_text("❌ Uso: `/asignar [correo] [cliente_telegram_id]`")
        return
        
    email_address = context.args[0]
    client_id = context.args[1]
    
    success, message = update_account_assignment(email_address, client_id_to_add=client_id)
    if success:
        await update.message.reply_text(f"✅ **Asignación Exitosa**\n📧 Cuenta: `{email_address}`\n👤 Cliente Telegram ID añadido: `{client_id}`\n\n*{message}*")
    else:
        await update.message.reply_text(f"❌ **Error al asignar:** {message}")

# Comando /desasignar [correo] [telegram_id_opcional]
async def desasignar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    if not ADMIN_TELEGRAM_ID or user_id != str(ADMIN_TELEGRAM_ID).strip():
        await update.message.reply_text("❌ Este comando solo puede ser utilizado por el Administrador/Vendedor.")
        return
        
    if not context.args:
        await update.message.reply_text("❌ Uso: `/desasignar [correo] [cliente_telegram_id_opcional]`")
        return
        
    email_address = context.args[0]
    client_id = context.args[1] if len(context.args) > 1 else None
    
    success, message = update_account_assignment(email_address, client_id_to_remove=client_id)
    if success:
        if client_id:
            await update.message.reply_text(f"✅ **Desasignación Exitosa**\n📧 Cuenta: `{email_address}`\n👤 Cliente `{client_id}` remoción exitosa.\n\n*{message}*")
        else:
            await update.message.reply_text(f"✅ **Desasignación Completa**\n📧 Cuenta: `{email_address}` (Todos los clientes removidos).\n\n*{message}*")
    else:
        await update.message.reply_text(f"❌ **Error al desasignar:** {message}")

# Comando /cuentas
async def cuentas_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    if not ADMIN_TELEGRAM_ID or user_id != str(ADMIN_TELEGRAM_ID).strip():
        await update.message.reply_text("❌ Este comando solo puede ser utilizado por el Administrador/Vendedor.")
        return
        
    accounts = get_all_accounts()
    if not accounts:
        await update.message.reply_text("📭 No hay cuentas registradas en la base de datos.")
        return
        
    text = "📋 **Listado de Cuentas y Asignaciones:**\n\n"
    for acc in accounts:
        email_str = acc.get("correo_streaming", "N/A")
        provider = str(acc.get("proveedor", "N/A")).upper()
        client = acc.get("cliente_telegram_id", "")
        client_str = f"`{client}`" if client else "_No asignado_"
        text += f"• 📧 {email_str} ({provider}) -> 👤 Cliente: {client_str}\n"
        
    await update.message.reply_text(text, parse_mode="Markdown")

# Comando /clientes (Exclusivo Administrador: Muestra todos los clientes agrupados y sus cuentas)
async def clientes_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id).strip()
    if not ADMIN_TELEGRAM_ID or user_id != str(ADMIN_TELEGRAM_ID).strip():
        await update.message.reply_text("❌ Este comando solo puede ser utilizado por el Administrador/Vendedor.")
        return
        
    accounts = get_all_accounts()
    if not accounts:
        await update.message.reply_text("📭 No hay cuentas registradas en la base de datos.")
        return
        
    clients_map = {}
    unassigned = []
    
    for acc in accounts:
        c_ids = clean_client_ids(acc.get("cliente_telegram_id", ""))
        if not c_ids:
            unassigned.append(acc)
        else:
            for cid in c_ids:
                if cid not in clients_map:
                    clients_map[cid] = []
                clients_map[cid].append(acc)
                
    text = "👥 **Gestión de Clientes y Cuentas Asignadas:**\n\n"
    
    if not clients_map:
        text += "📭 _No hay clientes con cuentas asignadas actualmente._\n\n"
    else:
        for cid, acc_list in clients_map.items():
            is_admin_tag = " ⭐ *(Admin/Vendedor)*" if ADMIN_TELEGRAM_ID and cid == str(ADMIN_TELEGRAM_ID).strip() else ""
            text += f"👤 **Cliente Telegram ID:** `{cid}`{is_admin_tag}\n"
            for acc in acc_list:
                email_str = acc.get("correo_streaming", "N/A")
                provider = str(acc.get("proveedor", "N/A")).upper()
                text += f"  • 🎬 **{provider}:** `{email_str}`\n"
            text += "\n"
            
    if unassigned:
        text += f"📭 **Cuentas Libres en Stock ({len(unassigned)}):**\n"
        for acc in unassigned:
            email_str = acc.get("correo_streaming", "N/A")
            provider = str(acc.get("proveedor", "N/A")).upper()
            text += f"  • 🎬 {provider}: `{email_str}`\n"
        text += "\n"
        
    total_assigned = sum(len(v) for v in clients_map.values())
    text += f"📊 **Resumen:** {len(clients_map)} cliente(s) único(s) | {total_assigned} asignación(es) activa(s)"
    
    await update.message.reply_text(text, parse_mode="Markdown")

# Procesar mensajes de texto directos
async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Por favor, usa el comando de tu plataforma seguido del correo de tu cuenta.\n\n"
        "Ejemplo: `/netflix correo@ejemplo.com`"
    )

# Servidor HTTP ligero para Health Check en Render / Koyeb
def start_health_check_server():
    try:
        import http.server
        import socketserver
        import threading
        
        port = int(os.environ.get("PORT", 8080))
        class HealthCheckHandler(http.server.SimpleHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"Bot is running 24/7!")
            def log_message(self, format, *args):
                pass
                
        def run_server():
            with socketserver.TCPServer(("", port), HealthCheckHandler) as httpd:
                httpd.serve_forever()
                
        t = threading.Thread(target=run_server, daemon=True)
        t.start()
        logger.info(f"Servidor Health Check iniciado en el puerto {port}")
    except Exception as e:
        logger.warning(f"No se pudo iniciar el servidor HTTP de Health Check: {e}")

# Función principal
def main():
    if not TELEGRAM_TOKEN:
        logger.error("La variable TELEGRAM_TOKEN no está configurada.")
        return
        
    start_health_check_server()
        
    # Inicializar la aplicación
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    # Manejadores de comandos del cliente
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("info", info_command))
    app.add_handler(CommandHandler("miscuentas", miscuentas_command))
    
    app.add_handler(CommandHandler("netflix", netflix_command))
    app.add_handler(CommandHandler("disney", disney_command))
    app.add_handler(CommandHandler("prime", prime_command))
    app.add_handler(CommandHandler("amazon", prime_command))
    app.add_handler(CommandHandler("max", max_command))
    app.add_handler(CommandHandler("hbo", max_command))
    app.add_handler(CommandHandler("crunchy", crunchy_command))
    app.add_handler(CommandHandler("crunchyroll", crunchy_command))
    app.add_handler(CommandHandler("paramount", paramount_command))
    
    # Manejadores de comandos del administrador
    app.add_handler(CommandHandler("asignar", asignar_command))
    app.add_handler(CommandHandler("desasignar", desasignar_command))
    app.add_handler(CommandHandler("cuentas", cuentas_command))
    app.add_handler(CommandHandler("clientes", clientes_command))
    
    # Manejador de texto plano (fallback)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler))
    
    logger.info("Bot iniciado. Esperando consultas...")
    app.run_polling()

if __name__ == "__main__":
    main()
