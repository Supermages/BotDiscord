import discord
from discord import app_commands
from discord.ext import commands
import os 
import datetime
import json
import asyncio
import logging
from datetime import timezone
from dotenv import load_dotenv
import re
# --- NUEVOS IMPORTS ---
from core.database import (
    inicializar_base, obtener_personaje, guardar_personaje, 
    obtener_tupperbox_webhook, guardar_tupperbox_webhook,
    buscar_personaje_por_nombre_db,
    set_modo_captura, get_modo_captura
)
from ui.views import LadoView, EditPersonajeView
from renderer.captura import generar_captura

load_dotenv()

load_dotenv()

# Configurar logging
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] [%(levelname)s]: %(message)s')

TOKEN = os.getenv('DISCORD_TOKEN')
TUPPERBOX_WEBHOOK_ID = os.getenv('TUPPER_WEBHOOK_ID')
ROL_REQUERIDO = os.getenv('ROL_ADMIN')

# --- RUTA DE EXPORTACIONES ---
# Definir ruta absoluta para guardar las imágenes en 'data/exportaciones'
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EXPORT_FOLDER = os.path.join(BASE_DIR, 'data', 'exportaciones')
try:
    LIMIT_TOTAL = int(os.getenv('MAX_MENSAJES_TOTAL', 50))
    CHUNK_SIZE = int(os.getenv('MENSAJES_POR_IMAGEN', 10))
except:
    LIMIT_TOTAL = 50
    CHUNK_SIZE = 10
try:
    SEARCH_LIMIT = int(os.getenv('SEARCH_LIMIT', 500))
except:
    SEARCH_LIMIT = 500

active_monitors = {}
file_lock = asyncio.Lock()

if not os.path.exists(EXPORT_FOLDER):
    os.makedirs(EXPORT_FOLDER)

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# ---------------------------- DECORADOR DE PERMISOS ----------------------------

def requiere_admin():
    async def predicate(interaction: discord.Interaction):
        if not isinstance(interaction.user, discord.Member):
            return False
        if any(role.name == ROL_REQUERIDO for role in interaction.user.roles):
            return True
        embed = discord.Embed(
            title="❌ Permiso denegado",
            description="No tienes el rol requerido para usar este comando.",
            color=0xFF0000
        )
        msg = await interaction.channel.send(embed=embed)
        await asyncio.sleep(5)
        await msg.delete()
        return False
    return app_commands.check(predicate)

# En bot.py

def limpiar_formato_discord(texto: str) -> str:
    # 1. Procesar Emojis Personalizados (<:nombre:ID> y <a:nombre:ID>)
    def reemplazo_emoji(match):
        animado, nombre, id_emoji = match.groups()
        ext = "gif" if animado else "png"
        url = f"https://cdn.discordapp.com/emojis/{id_emoji}.{ext}"
        # Insertamos una etiqueta IMG con estilos para que parezca texto
        return f'<img src="{url}" alt=":{nombre}:" style="width: 22px; height: 22px; vertical-align: middle; object-fit: contain;">'

    texto = re.sub(r'<(a?):(\w+):(\d+)>', reemplazo_emoji, texto)

    # 2. Limpieza estándar (la que ya tenías)
    texto = re.sub(r'```.*?```', '', texto, flags=re.DOTALL)
    texto = re.sub(r'`([^`]*)`', r'\1', texto)
    texto = re.sub(r'\*\*\*([^*]+)\*\*\*', r'\1', texto)
    texto = re.sub(r'\*\*([^*]+)\*\*', r'\1', texto)
    texto = re.sub(r'\*([^*]+)\*', r'\1', texto)
    texto = re.sub(r'__([^_]+)__', r'\1', texto)
    texto = re.sub(r'~~([^~]+)~~', r'\1', texto)
    texto = re.sub(r'\|\|([^|]+)\|\|', r'\1', texto)
    
    return texto.strip()

# ---------------------------- UTILIDADES ----------------------------

def buscar_personaje_por_nombre(nombre):
    import sqlite3
    conn = sqlite3.connect("eridubot.sqlite")
    cur = conn.cursor()
    cur.execute("SELECT * FROM Personaje_Tabla")
    for row in cur.fetchall():
        if row[1].lower() == nombre.lower():
            conn.close()
            return row
    conn.close()
    return None

# Reemplaza la función detectar_tupperbox_id actual por esta:

# Reemplaza la función detectar_tupperbox_id completa en bot.py por esta:

async def detectar_tupperbox_id(channel: discord.TextChannel) -> int | None:
    # 1. INTENTO RÁPIDO: Buscar en base de datos
    try:
        # Nota: obtener_tupperbox_webhook devuelve una tupla (webhook_id,) o None
        datos = await obtener_tupperbox_webhook(str(channel.guild.id))
        if datos:
            return int(datos[0]) # Convertimos a int para comparar con discord
    except Exception as e:
        logging.error(f"Error leyendo caché de webhooks: {e}")

    # 2. INTENTO LENTO: Escanear historial (solo si no estaba en DB)
    logging.info(f"Escaneando historial en #{channel.name} para buscar Tupperbox...")
    ids_nombres = {}

    # Escaneamos historial
    async for msg in channel.history(limit=200):
        if not msg.webhook_id:
            continue
        
        # Guardamos qué nombres usa cada ID de webhook
        key = msg.author.id
        nombre = msg.author.name
        
        if key not in ids_nombres:
            ids_nombres[key] = set()
        ids_nombres[key].add(nombre)

    # Analizamos resultados
    for bot_id, nombres in ids_nombres.items():
        # La lógica clave: Si un webhook tiene más de 1 nombre diferente, es Tupperbox
        if len(nombres) > 1:
            logging.info(f"[🎭] Detectado Tupperbox ID: {bot_id}. Guardando en base de datos...")
            
            # 3. GUARDAR EN CACHÉ para el futuro
            await guardar_tupperbox_webhook(str(channel.guild.id), str(bot_id))
            
            return bot_id

    logging.warning(f"[⚠️] No se detectó ningún ID de Tupperbox en {channel.name}")
    return None



async def actualizar_chat_logica(channel, chat_json, solicitante=None):
    mensajes_guardados = chat_json["Chat"]["mensajes"]
    # Usamos un set para evitar duplicados basándonos en el contenido (puedes mejorar esto usando IDs si quieres ser estricto)
    mensajes_guardados_contenido = set(m["Mensaje"] for m in mensajes_guardados)
    nuevos_mensajes = []
    last_id = chat_json["Chat"].get("ultimo_id")

    # 1. OBTENER MODO DE CAPTURA
    # Si falla la lectura, asumimos 'TUPPER' por seguridad
    try:
        modo_captura = await get_modo_captura(channel.guild.id)
    except:
        modo_captura = 'TUPPER'

    tupperbox_id = None

    # 2. LÓGICA DE DETECCIÓN DE ID
    # Solo buscamos el ID si es estrictamente necesario (Modo TUPPER)
    if modo_captura == 'TUPPER':
        tupperbox_id = await detectar_tupperbox_id(channel)
        if not tupperbox_id:
            # Solo retornamos False si estamos en modo Tupper y falló la detección
            logging.warning(f"Monitor: No se detectó ID de Tupperbox en #{channel.name} (Modo estricto).")
            return False

    # 3. DEFINIR ITERADOR (Historial)
    # Si tenemos un último ID, buscamos a partir de ahí (after=last_id va de viejo a nuevo)
    # Si no, cogemos los últimos 100 (limit=100 va de nuevo a viejo)
    if last_id:
        iterator = channel.history(after=discord.Object(id=last_id))
    else:
        iterator = channel.history(limit=100)

    async for msg in iterator:
        # FILTRO: ¿Debemos procesar este mensaje?
        procesar = False
        
        if modo_captura == 'TUPPER':
            # Solo si es webhook y coincide con el ID detectado
            if msg.webhook_id and msg.author.id == tupperbox_id:
                procesar = True
        else:
            # Modo TODO: Procesamos todo excepto al propio bot y comandos que empiecen por "!"
            if msg.author.id != bot.user.id and not msg.content.startswith("!"):
                procesar = True

        # Limpiamos el contenido (incluyendo emojis personalizados)
        contenido_limpio = limpiar_formato_discord(msg.content)

        # Si pasa el filtro y no es duplicado
        if procesar and contenido_limpio not in mensajes_guardados_contenido:
            
            # --- PROCESAMIENTO DEL MENSAJE ---
            personaje_nombre = msg.author.display_name
            # Sanitizar nombre para ID interno
            tupper_tag = re.sub(r'[^a-zA-Z0-9_]', '_', str(msg.author.name))
            
            # Obtener Avatar
            if msg.author.avatar:
                avatar_url = str(msg.author.avatar.url)
            else:
                avatar_url = "https://cdn.discordapp.com/embed/avatars/0.png"
            
            # Buscar en Base de Datos
            personaje = await obtener_personaje(tupper_tag)

            # Si el personaje NO existe en la base de datos...
            if not personaje:
                # En el monitor automático, NO enviamos DMs para no hacer spam masivo.
                # Lo registramos automáticamente a la Izquierda (Blanco).
                lado = "I"
                color, color_texto = "#FFFFFF", "#000000"
                
                # Guardamos en DB
                await guardar_personaje(tupper_tag, personaje_nombre, lado, avatar_url, color, color_texto)
            
        # ... dentro del bucle for msg in ...
        
        # 1. Recogemos adjuntos (Imágenes y Archivos)
        adjuntos = []
        if msg.attachments:
            for a in msg.attachments:
                # Guardamos un objeto con tipo para ayudar al JS
                es_imagen = a.content_type and "image" in a.content_type
                adjuntos.append({
                    "url": a.url,
                    "filename": a.filename,
                    "tipo": "imagen" if es_imagen else "archivo"
                })

        # 2. Recogemos Stickers (Ojo: Lottie/JSON no se verá, solo PNG/APNG)
        if msg.stickers:
            for sticker in msg.stickers:
                # Los stickers suelen ser imágenes, los tratamos como tal
                if sticker.format != discord.StickerFormatType.lottie: # Ignoramos Lottie (animaciones complejas)
                    adjuntos.append({
                        "url": sticker.url,
                        "filename": "sticker.png",
                        "tipo": "sticker"
                    })

        # 3. Recogemos Embeds (GIFs de Tenor/Giphy)
        if msg.embeds:
            for embed in msg.embeds:
                if embed.image and embed.image.url:
                    adjuntos.append({
                        "url": embed.image.url,
                        "filename": "image.png",
                        "tipo": "imagen"
                    })
                # A veces los GIFs salen como 'thumbnail' en ciertos embeds
                elif embed.thumbnail and embed.thumbnail.url:
                     adjuntos.append({
                        "url": embed.thumbnail.url,
                        "filename": "thumbnail.png",
                        "tipo": "imagen"
                    })
            
            # Actualizamos el último ID procesado
            chat_json["Chat"]["ultimo_id"] = msg.id

    # 4. GUARDAR CAMBIOS
    if nuevos_mensajes:
        logging.info(f"Monitor: Se encontraron {len(nuevos_mensajes)} mensajes nuevos en #{channel.name}")
        
        # IMPORTANTE: Ordenación
        # Si usamos 'last_id' (after), Discord nos dio los mensajes de viejo a nuevo -> Append directo.
        # Si NO usamos 'last_id' (limit), Discord nos dio de nuevo a viejo -> Reversed.
        if last_id:
            chat_json["Chat"]["mensajes"].extend(nuevos_mensajes)
        else:
            chat_json["Chat"]["mensajes"].extend(reversed(nuevos_mensajes))

        chat_json["Chat"]["fecha"] = datetime.datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
        return True
    
    return False

async def generar_imagen_segmentada(chat_json, canal_id):
    partes = [
        chat_json["Chat"]["mensajes"][i:i + CHUNK_SIZE]
        for i in range(0, len(chat_json["Chat"]["mensajes"]), CHUNK_SIZE)
    ]

    if not partes:
        raise ValueError("No hay mensajes para generar imagen")

    # Guardar primera parte si hay más de una
    if len(partes) > 1:
        primera_parte = {
            "Chat": {
                "titulo": chat_json["Chat"]["titulo"] + " (parte 1)",
                "fecha": chat_json["Chat"]["fecha"],
                "mensajes": partes[0]
            }
        }
        imagen_path_1 = await generar_captura(primera_parte)
        static_path = f"{EXPORT_FOLDER}/chat_{canal_id}_parte1.png"
        os.replace(imagen_path_1, static_path)
        logging.info(f"[📸] Imagen estática guardada en {static_path}")

    # Generar la parte final actualizable
    ultima_parte = {
        "Chat": {
            "titulo": chat_json["Chat"]["titulo"] + f" (actualizado parte {len(partes)})",
            "fecha": chat_json["Chat"]["fecha"],
            "mensajes": partes[-1]
        }
    }

    imagen_path = await generar_captura(ultima_parte)
    final_path = f"{EXPORT_FOLDER}/chat_{canal_id}.png"
    os.replace(imagen_path, final_path)
    return final_path



# --- MONITOR CHAT CORREGIDO ---
async def monitor_chat(channel, message_id, duration_minutes, solicitante):
    logging.info(f"Monitor iniciado en #{channel.name} ({duration_minutes} min)")
    json_filename = os.path.join(EXPORT_FOLDER, f"chat_{channel.id}.json")
    end_time = datetime.datetime.now(timezone.utc) + datetime.timedelta(minutes=duration_minutes)

    async with file_lock:
        with open(json_filename, "r", encoding="utf-8") as f:
            chat_json = json.load(f)

    while datetime.datetime.now(timezone.utc) < end_time:
        # Buscamos cambios
        cambios = await actualizar_chat_logica(channel, chat_json, solicitante)
        
        if cambios:
            # Recorte de seguridad (Si supera el límite TOTAL del .env, cortamos los viejos)
            if len(chat_json["Chat"]["mensajes"]) > LIMIT_TOTAL:
                chat_json["Chat"]["mensajes"] = chat_json["Chat"]["mensajes"][-LIMIT_TOTAL:]
                logging.info(f"Monitor: Recortando historial a {LIMIT_TOTAL} mensajes.")
            
            # Guardamos JSON actualizado
            async with file_lock:
                with open(json_filename, "w", encoding="utf-8") as f:
                    json.dump(chat_json, f, indent=4, ensure_ascii=False)

            # REGENERAMOS TODAS LAS PARTES
            # (Porque si entra un mensaje nuevo, puede desplazar los textos de todas las imágenes)
            try:
                rutas_imagenes = await generar_imagenes_por_lotes(channel.id, chat_json, chat_json["Chat"]["titulo"])
                archivos_discord = [discord.File(path) for path in rutas_imagenes]

                mensaje = await channel.fetch_message(message_id)
                
                # Editamos el mensaje reemplazando TODOS los adjuntos
                await mensaje.edit(
                    content=f"✅ (Actualizado {datetime.datetime.now().strftime('%H:%M')}) - {len(rutas_imagenes)} partes", 
                    attachments=archivos_discord
                )
                
                # Limpiar
                for path in rutas_imagenes:
                    if os.path.exists(path): os.remove(path)
                
            except discord.NotFound:
                logging.warning("El mensaje del monitor fue borrado. Deteniendo.")
                break
            except Exception as e:
                logging.error(f"Error en ciclo monitor: {e}")

        await asyncio.sleep(60)

    logging.info(f"Monitor finalizado en #{channel.name}")
    active_monitors.pop(channel.id, None)

async def generar_imagenes_por_lotes(channel_id, chat_json, titulo_base):
    mensajes = chat_json["Chat"]["mensajes"]
    # Dividir mensajes en trozos de tamaño CHUNK_SIZE
    chunks = [mensajes[i:i + CHUNK_SIZE] for i in range(0, len(mensajes), CHUNK_SIZE)]
    
    rutas_archivos = []
    
    for i, chunk in enumerate(chunks):
        # Crear un JSON temporal solo con este trozo de mensajes
        parte_json = {
            "Chat": {
                "titulo": f"{titulo_base} (Parte {i+1}/{len(chunks)})",
                "fecha": chat_json["Chat"]["fecha"],
                "mensajes": chunk
            }
        }
        
        # Generar captura de este trozo
        temp_path = await generar_captura(parte_json)
        
        # Renombrar para organizar
        final_path = os.path.join(EXPORT_FOLDER, f"chat_{channel_id}_part{i+1}.png")
        if os.path.exists(final_path): os.remove(final_path)
        os.replace(temp_path, final_path)
        
        rutas_archivos.append(final_path)
        
    return rutas_archivos

# ---------------------------- COMANDOS SLASH ----------------------------

# --- COMANDO GENERARCHAT CORREGIDO ---
@tree.command(name="generarchat", description="Genera un chat segmentado en varias imágenes.")
@app_commands.describe(cantidad="Cantidad total de mensajes", title="Título del chat", duracion="Duración monitor (min)")
@requiere_admin()
async def generarchat(interaction: discord.Interaction, cantidad: int = 20, title: str = "chat", duracion: int = 5):
    # --- 1. LÓGICA ANTI-CONFLICTOS (NUEVO) ---
    channel = interaction.channel
    
    # Verificamos si ya existe un monitor en este canal
    if channel.id in active_monitors:
        old_monitor = active_monitors[channel.id]
        
        # Cancelamos la tarea antigua
        old_monitor["tarea"].cancel()
        
        # (Opcional) Avisamos por log
        logging.info(f"⚠️ Monitor anterior en #{channel.name} detenido para iniciar uno nuevo.")
        
        # Eliminamos la referencia (aunque se sobrescribirá al final, es buena práctica limpiar)
        del active_monitors[channel.id]
        
        # Opcional: Avisar al usuario
        await interaction.channel.send("🔄 Se ha detenido el monitor anterior para iniciar el nuevo.", delete_after=5)
    
    # 1. Validación de seguridad (Límite del .env)
    if cantidad > LIMIT_TOTAL:
        return await interaction.response.send_message(
            f"❌ **Límite excedido.** El máximo permitido es **{LIMIT_TOTAL}** mensajes.", ephemeral=True
        )

    await interaction.response.defer()
    channel = interaction.channel
    
    # 2. Obtenemos el modo
    modo_captura = await get_modo_captura(interaction.guild_id)
    mensajes_a_procesar = []
    
    logging.info(f"GenerarChat: Iniciando. Modo: {modo_captura} | Cantidad: {cantidad}")



    # --- LÓGICA DE SELECCIÓN ---
    if modo_captura == 'TUPPER':
        tupperbox_id = await detectar_tupperbox_id(channel)
        if not tupperbox_id:
            return await interaction.followup.send("❌ No se detectó Tupperbox y el modo es 'Solo Tupper'.")
            
        # CAMBIO: Usamos 'search_depth' en lugar de 100 fijo
        async for msg in channel.history(limit=SEARCH_LIMIT):
            if msg.webhook_id and msg.author.id == tupperbox_id:
                mensajes_a_procesar.append(msg)
            
            # CONDICIÓN DE PARADA: Ya tenemos los que queríamos
            if len(mensajes_a_procesar) >= cantidad:
                break
    else:
        # Modo TODO (La corrección que hicimos antes)
        async for msg in channel.history(limit=SEARCH_LIMIT): # Aplicamos el mismo límite de seguridad aquí también
            if msg.author.id == bot.user.id or msg.content.startswith("!"):
                continue
            mensajes_a_procesar.append(msg)
            if len(mensajes_a_procesar) >= cantidad:
                break

    logging.info(f"GenerarChat: Se procesarán {len(mensajes_a_procesar)} mensajes.")

    # 4. Procesamiento de Datos (Tupper/User, Colores, DB)
    mensajes_json = []
    for msg in reversed(mensajes_a_procesar):
        personaje_nombre = msg.author.display_name
        tupper_tag = re.sub(r'[^a-zA-Z0-9_]', '_', str(msg.author.name)) 
        
        avatar_url = str(msg.author.avatar.url) if msg.author.avatar else "https://cdn.discordapp.com/embed/avatars/0.png"
        
        # Buscar o preguntar (Lógica mantenida de tu código)
        personaje = await obtener_personaje(tupper_tag)
        if not personaje:
            if modo_captura == 'TUPPER' or msg.author.id == interaction.user.id:
                try:
                    view = LadoView(interaction.user.id, tupper_tag, personaje_nombre, avatar_url)
                    aviso = await interaction.followup.send(f"📢 **{personaje_nombre}** nuevo. ¿Lado?", view=view, ephemeral=True)
                    await view.wait()
                    lado = view.lado or "I"
                    await guardar_personaje(tupper_tag, personaje_nombre, lado, avatar_url, "#FFFFFF", "#000000")
                    try: await aviso.delete() 
                    except: pass
                except:
                    lado = "I"
                    await guardar_personaje(tupper_tag, personaje_nombre, lado, avatar_url)
            else:
                await guardar_personaje(tupper_tag, personaje_nombre, "I", avatar_url)

        # Recoger adjuntos
        adjuntos = []
        if msg.attachments:
            for a in msg.attachments:
                # Guardamos un objeto con tipo para ayudar al JS
                es_imagen = a.content_type and "image" in a.content_type
                adjuntos.append({
                    "url": a.url,
                    "filename": a.filename,
                    "tipo": "imagen" if es_imagen else "archivo"
                })

        # 2. Recogemos Stickers (Ojo: Lottie/JSON no se verá, solo PNG/APNG)
        if msg.stickers:
            for sticker in msg.stickers:
                # Los stickers suelen ser imágenes, los tratamos como tal
                if sticker.format != discord.StickerFormatType.lottie: # Ignoramos Lottie (animaciones complejas)
                    adjuntos.append({
                        "url": sticker.url,
                        "filename": "sticker.png",
                        "tipo": "sticker"
                    })

        # 3. Recogemos Embeds (GIFs de Tenor/Giphy)
        if msg.embeds:
            for embed in msg.embeds:
                if embed.image and embed.image.url:
                    adjuntos.append({
                        "url": embed.image.url,
                        "filename": "image.png",
                        "tipo": "imagen"
                    })
                # A veces los GIFs salen como 'thumbnail' en ciertos embeds
                elif embed.thumbnail and embed.thumbnail.url:
                     adjuntos.append({
                        "url": embed.thumbnail.url,
                        "filename": "thumbnail.png",
                        "tipo": "imagen"
                    })

        mensajes_json.append({
            "Personaje": tupper_tag,
            "Mensaje": limpiar_formato_discord(msg.content),
            "Adjuntos": adjuntos # Ahora pasamos una lista de objetos, no solo strings
        })

    # 5. Guardar JSON Maestro
    timestamp = datetime.datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    titulo_real = title if title != "chat" else channel.name
    last_id = mensajes_a_procesar[0].id if mensajes_a_procesar else None
    
    chat_json = {
        "Chat": {
            "titulo": titulo_real,
            "fecha": timestamp,
            "ultimo_id": last_id,
            "mensajes": mensajes_json
        }
    }

    json_filename = os.path.join(EXPORT_FOLDER, f"chat_{channel.id}.json")
    async with file_lock:
        with open(json_filename, "w", encoding="utf-8") as f:
            json.dump(chat_json, f, indent=4, ensure_ascii=False)

    # 6. GENERACIÓN POR LOTES (Aquí ocurre la magia)
    try:
        logging.info("Generando imágenes por lotes...")
        rutas_imagenes = await generar_imagenes_por_lotes(channel.id, chat_json, titulo_real)
        
        archivos_discord = [discord.File(path) for path in rutas_imagenes]
        
        msg = await interaction.followup.send(
            content=f"✅ Chat generado en **{len(rutas_imagenes)} partes**:",
            files=archivos_discord
        )

        # Limpiar archivos generados
        for path in rutas_imagenes:
            if os.path.exists(path): os.remove(path)

        # Guardar ID del mensaje para el monitor
        chat_json["Chat"]["mensaje_id"] = msg.id
        async with file_lock:
            with open(json_filename, "w", encoding="utf-8") as f:
                json.dump(chat_json, f, indent=4, ensure_ascii=False)

        # Iniciar Monitor
        task = asyncio.create_task(monitor_chat(channel, msg.id, duracion, interaction.user))
        active_monitors[channel.id] = {
            "tarea": task, 
            "hasta": datetime.datetime.now(timezone.utc) + datetime.timedelta(minutes=duracion)
        }
        
    except Exception as e:
        logging.error(f"Error generando imágenes: {e}")
        await interaction.followup.send("❌ Hubo un error generando las imágenes.")

@tree.command(name="forzaractualizacion", description="Fuerza la actualización del chat (detecta nuevos mensajes)")
@requiere_admin()
async def forzaractualizacion(interaction: discord.Interaction):
    await interaction.response.defer()
    json_filename = f"{EXPORT_FOLDER}/chat_{interaction.channel.id}.json"

    if not os.path.exists(json_filename):
        embed = discord.Embed(title="❌ Error", description="No se ha generado un chat para este canal.", color=0xFF0000)
        return await interaction.followup.send(embed=embed)

    async with file_lock:
        with open(json_filename, "r", encoding="utf-8") as f:
            chat_json = json.load(f)

    mensaje_id = chat_json["Chat"].get("mensaje_id")
    if not mensaje_id:
        return await interaction.followup.send(embed=discord.Embed(
            title="❌ Error",
            description="No se encontró el mensaje original para actualizar.",
            color=0xFF0000
        ))

    cambios = await actualizar_chat_logica(interaction.channel, chat_json, interaction.user)
    if cambios:
        async with file_lock:
            with open(json_filename, "w", encoding="utf-8") as f:
                json.dump(chat_json, f, indent=4, ensure_ascii=False)

        final_path = await generar_imagen_segmentada(chat_json, interaction.channel.id)

        try:
            msg = await interaction.channel.fetch_message(mensaje_id)
            await msg.edit(content="✅ (Actualizado manual)", attachments=[discord.File(final_path)])
            
            if os.path.exists(final_path):
                os.remove(final_path)
        except discord.NotFound:
            return await interaction.followup.send("❌ No se encontró el mensaje original.")

        await interaction.followup.send(embed=discord.Embed(title="✅ ¡Actualizado!", color=0x00B0F4))
    else:
        await interaction.followup.send(embed=discord.Embed(
            title="⚠️ Sin cambios",
            description="No hubo nuevos mensajes.",
            color=0xFFFF00
        ))

@tree.command(name="listarmonitores", description="Muestra todos los monitores activos.")
@requiere_admin()
async def listarmonitores(interaction: discord.Interaction):
    if not active_monitors:
        embed = discord.Embed(
            title="📭 Monitores activos",
            description="Actualmente no hay ningún monitor activo.",
            color=0xAAAAAA
        )
        return await interaction.response.send_message(embed=embed, ephemeral=True)

    desc = ""
    for canal_id, info in active_monitors.items():
        restante = (info["hasta"] - datetime.datetime.now(timezone.utc)).total_seconds() // 60
        desc += f"• Canal <#{canal_id}> — {int(restante)} min restantes\n"

    embed = discord.Embed(
        title="📡 Monitores activos",
        description=desc,
        color=0x00B0F4
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)
    logging.info("Se listaron los monitores activos")

@tree.command(name="detenermonitor", description="Detiene el monitor en el canal actual.")
@requiere_admin()
async def detenermonitor(interaction: discord.Interaction):
    canal_id = interaction.channel.id
    monitor = active_monitors.get(canal_id)

    if monitor:
        monitor["tarea"].cancel()
        del active_monitors[canal_id]
        embed = discord.Embed(
            title="🛑 Monitor detenido",
            description="El monitor de este canal ha sido detenido correctamente.",
            color=0xFF5733
        )
        logging.info(f"Monitor detenido en canal {canal_id}")
    else:
        embed = discord.Embed(
            title="⚠️ Sin monitor",
            description="Este canal no tiene un monitor activo actualmente.",
            color=0xCCCC00
        )
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="editarpersonaje", description="Edita visualmente las propiedades de un personaje.")
@app_commands.describe(nombre="Nombre del personaje (no ID)")
@requiere_admin()
async def editarpersonaje(interaction: discord.Interaction, nombre: str):
    await interaction.response.defer(ephemeral=True)
    personaje = await buscar_personaje_por_nombre_db(nombre)

    if not personaje:
        embed = discord.Embed(
            title="❌ No encontrado",
            description=f"No se encontró el personaje llamado **{nombre}**.",
            color=0xFF0000
        )
        return await interaction.followup.send(embed=embed, ephemeral=True)

    tupper_tag, nombre, lado, avatar_url, color, color_texto = personaje
    view = EditPersonajeView(interaction, tupper_tag, nombre, lado, color, color_texto, avatar_url)

    try:
        await view.send_preview()
        embed = discord.Embed(
            title="📩 Edición iniciada",
            description="Revisa tus mensajes privados para continuar con la edición.",
            color=0x00B0F4
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        logging.info(f"Vista de edición enviada a {interaction.user.display_name}")
    except discord.Forbidden:
        await interaction.followup.send(
            content=f"📍 No pude enviarte DM. Aquí tienes la edición.",
            ephemeral=True,
            view=view
        )
        logging.warning(f"No se pudo enviar DM a {interaction.user.display_name}, se usó canal")

@tree.command(name="configuracion", description="Configura el modo de captura del bot.")
@app_commands.describe(modo="Elige qué mensajes debe capturar el bot")
@app_commands.choices(modo=[
    app_commands.Choice(name="🎭 Solo Tupperbox (Por defecto)", value="TUPPER"),
    app_commands.Choice(name="📢 Todo el chat (Usuarios y Bots)", value="TODO")
])
@requiere_admin()
async def configuracion(interaction: discord.Interaction, modo: app_commands.Choice[str]):
    await set_modo_captura(interaction.guild_id, modo.value)
    
    texto = "🎭 **Solo Tupperbox**" if modo.value == "TUPPER" else "📢 **Todo el chat**"
    embed = discord.Embed(
        title="⚙️ Configuración Actualizada", 
        description=f"Ahora el bot capturará: {texto}",
        color=0x00FF00
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.event
async def on_ready():
    await inicializar_base()
    await tree.sync()
    logging.info(f"Bot listo como {bot.user}")


bot.run(TOKEN)