import discord
from discord import app_commands
from discord.ext import commands
import os
import datetime
import json
import asyncio
import logging
from datetime import timezone
from db import inicializar_base, obtener_personaje, guardar_personaje
from views import LadoView, EditPersonajeView
from captura import generar_captura
import re
from db import obtener_tupperbox_webhook, guardar_tupperbox_webhook

# Configurar logging
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] [%(levelname)s]: %(message)s')

TUPPERBOX_WEBHOOK_ID = 1365408923808563361
EXPORT_FOLDER = "exportaciones"
ROL_REQUERIDO = "Bot Admin"
MAX_MENSAJES_POR_IMAGEN = 10  # Ajustable desde código
active_monitors = {}

inicializar_base()
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

def limpiar_formato_discord(texto: str) -> str:
    import re
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

async def detectar_tupperbox_id(channel: discord.TextChannel) -> int | None:
    ids_nombres = {}

    async for msg in channel.history(limit=200):
        if not msg.webhook_id:
            continue
        key = msg.author.id
        nombre = msg.author.name
        if key not in ids_nombres:
            ids_nombres[key] = set()
        ids_nombres[key].add(nombre)

    for bot_id, nombres in ids_nombres.items():
        if len(nombres) > 1:
            logging.info(f"[🎭] Detectado posible Tupperbox ID: {bot_id} en canal {channel.name}")
            return bot_id

    logging.warning(f"[⚠️] No se detectó ningún ID de Tupperbox en {channel.name}")
    return None



async def actualizar_chat_logica(channel, chat_json, solicitante=None):
    mensajes_guardados = chat_json["Chat"]["mensajes"]
    mensajes_guardados_contenido = set(m["Mensaje"] for m in mensajes_guardados)
    nuevos_mensajes = []
    last_id = chat_json["Chat"].get("ultimo_id")

    # Detectar ID de Tupperbox dinámicamente
    tupperbox_id = await detectar_tupperbox_id(channel)
    if not tupperbox_id:
        logging.warning("No se pudo detectar el ID de Tupperbox.")
        return False

    async for msg in channel.history(after=discord.Object(id=last_id)) if last_id else channel.history(limit=100):
        if msg.webhook_id and msg.author.id == tupperbox_id and msg.content not in mensajes_guardados_contenido:
            personaje_nombre = msg.author.display_name
             # Limpiar nombre: solo letras, números y guion bajo
            tupper_tag = re.sub(r'[^a-zA-Z0-9_]', '_', str(msg.author.name))
            avatar_url = str(msg.author.avatar.url) if msg.author.avatar else "https://cdn.pixabay.com/photo/2015/10/05/22/37/blank-profile-picture-973460_1280.png"
            personaje = obtener_personaje(tupper_tag)

            if not personaje and solicitante:
                try:
                    view = LadoView(solicitante.id, tupper_tag, personaje_nombre, avatar_url)
                    await solicitante.send(f"📢 ¿Dónde quieres colocar a **{personaje_nombre}**?", view=view)
                    await view.wait()
                    lado = view.lado or "I"
                    color = "#2C58E2" if lado == "D" else "#FFFFFF"
                    color_texto = "#FFFFFF" if lado == "D" else "#000000"
                    guardar_personaje(tupper_tag, personaje_nombre, lado, avatar_url, color, color_texto)
                except discord.Forbidden:
                    logging.warning(f"No se pudo enviar DM a {solicitante.display_name}")
                    continue
            elif not personaje:
                continue
            
            adjuntos = []

            # Archivos adjuntos tradicionales
            if msg.attachments:
                adjuntos.extend([a.url for a in msg.attachments])

            # Embeds con imágenes
            if msg.embeds:
                for embed in msg.embeds:
                    if embed.image and embed.image.url:
                        adjuntos.append(embed.image.url)
            
            nuevos_mensajes.append({
                "Personaje": tupper_tag,
                "Mensaje": limpiar_formato_discord(msg.content),
                "Adjuntos": adjuntos
            })
            chat_json["Chat"]["ultimo_id"] = msg.id

    if nuevos_mensajes:
        chat_json["Chat"]["mensajes"].extend(reversed(nuevos_mensajes))
        chat_json["Chat"]["fecha"] = datetime.datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
        return True
    return False

async def generar_imagen_segmentada(chat_json, canal_id):
    partes = [
        chat_json["Chat"]["mensajes"][i:i + MAX_MENSAJES_POR_IMAGEN]
        for i in range(0, len(chat_json["Chat"]["mensajes"]), MAX_MENSAJES_POR_IMAGEN)
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



async def monitor_chat(channel, message_id, duration_minutes, solicitante):
    logging.info(f"Monitor iniciado en #{channel.name} por {duration_minutes} minutos")
    json_filename = f"{EXPORT_FOLDER}/chat_{channel.id}.json"
    end_time = datetime.datetime.now(timezone.utc) + datetime.timedelta(minutes=duration_minutes)

    with open(json_filename, "r", encoding="utf-8") as f:
        chat_json = json.load(f)

    while datetime.datetime.now(timezone.utc) < end_time:
        cambios = await actualizar_chat_logica(channel, chat_json, solicitante)
        if cambios:
            with open(json_filename, "w", encoding="utf-8") as f:
                json.dump(chat_json, f, indent=4, ensure_ascii=False)

            partes = [
                chat_json["Chat"]["mensajes"][i:i + MAX_MENSAJES_POR_IMAGEN]
                for i in range(0, len(chat_json["Chat"]["mensajes"]), MAX_MENSAJES_POR_IMAGEN)
            ]

            ultima_parte = {
                "Chat": {
                    "titulo": chat_json["Chat"]["titulo"] + f" (actualizado parte {len(partes)})",
                    "fecha": chat_json["Chat"]["fecha"],
                    "mensajes": partes[-1]
                }
            }

            imagen_path = await generar_captura(ultima_parte)
            final_path = f"{EXPORT_FOLDER}/chat_{channel.id}.png"
            os.replace(imagen_path, final_path)

            try:
                mensaje = await channel.fetch_message(message_id)
                await mensaje.edit(content="✅ (Actualizado)", attachments=[discord.File(final_path)])
            except discord.NotFound:
                logging.warning("Mensaje original no encontrado para editar")

        await asyncio.sleep(60)

    logging.info(f"Monitor finalizado en #{channel.name}")
    active_monitors.pop(channel.id, None)

# ---------------------------- COMANDOS SLASH ----------------------------

@tree.command(name="generarchat", description="Genera un chat estilizado con monitoreo automático.")
@app_commands.describe(cantidad="Cantidad de mensajes", title="Título del chat", duracion="Duración del monitoreo en minutos")
@requiere_admin()
async def generarchat(interaction: discord.Interaction, cantidad: int = 20, title: str = "chat", duracion: int = 5):
    await interaction.response.defer()
    channel = interaction.channel
    mensajes_json = []
    tupper_msgs = []
    tupperbox_id = await detectar_tupperbox_id(channel)
    if not tupperbox_id:
        return await interaction.followup.send("❌ No se pudo detectar un bot de Tupperbox en este canal.")

    async for msg in channel.history(limit=100):
        if msg.webhook_id and msg.author.id == tupperbox_id:
            tupper_msgs.append(msg)
        if len(tupper_msgs) >= cantidad:
            break

    # filepath: c:\Users\nicol\Downloads\Bot Discord\BotDiscord\bot\bot.py
    for msg in reversed(tupper_msgs[:cantidad]):
        personaje_nombre = msg.author.display_name
        tupper_tag = re.sub(r'[^a-zA-Z0-9_]', '_', str(msg.author.name))
        avatar_url = str(msg.author.avatar.url) if msg.author.avatar else "https://cdn.pixabay.com/photo/2015/10/05/22/37/blank-profile-picture-973460_1280.png"
        personaje = obtener_personaje(tupper_tag)

        if not personaje:
            try:
                view = LadoView(interaction.user.id, tupper_tag, personaje_nombre, avatar_url)
                await interaction.user.send(f"📢 ¿Dónde quieres colocar a **{personaje_nombre}**?", view=view)
                await view.wait()
                lado = view.lado or "I"
                color = "#2C58E2" if lado == "D" else "#FFFFFF"
                color_texto = "#FFFFFF" if lado == "D" else "#000000"
                guardar_personaje(tupper_tag, personaje_nombre, lado, avatar_url, color, color_texto)
            except discord.Forbidden:
                continue
        
        adjuntos = []

        # Archivos adjuntos tradicionales
        if msg.attachments:
            adjuntos.extend([a.url for a in msg.attachments])

        # Embeds con imágenes
        if msg.embeds:
            for embed in msg.embeds:
                if embed.image and embed.image.url:
                    adjuntos.append(embed.image.url)


        mensajes_json.append({
            "Personaje": tupper_tag,
            "Mensaje": limpiar_formato_discord(msg.content),
            "Adjuntos": adjuntos
        })

    timestamp = datetime.datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    last_id = tupper_msgs[0].id if tupper_msgs else None
    chat_json = {
        "Chat": {
            "titulo": title if title != "chat" else channel.name,
            "fecha": timestamp,
            "ultimo_id": last_id,
            "mensajes": mensajes_json
        }
    }

    json_filename = f"{EXPORT_FOLDER}/chat_{channel.id}.json"
    with open(json_filename, "w", encoding="utf-8") as f:
        json.dump(chat_json, f, indent=4, ensure_ascii=False)

    # Generar imagen segmentada
    final_path = await generar_imagen_segmentada(chat_json, channel.id)

    # Enviar parte estática si existe
    parte_estatica = f"{EXPORT_FOLDER}/chat_{channel.id}_parte1.png"
    archivos_a_enviar = []

    if os.path.exists(parte_estatica):
        archivos_a_enviar.append(discord.File(parte_estatica))

    archivos_a_enviar.append(discord.File(final_path))

    msg = await interaction.followup.send(
        content="✅ ¡Aquí tienes tu chat generado!",
        files=archivos_a_enviar
    )

    chat_json["Chat"]["mensaje_id"] = msg.id
    with open(json_filename, "w", encoding="utf-8") as f:
        json.dump(chat_json, f, indent=4, ensure_ascii=False)

    task = asyncio.create_task(monitor_chat(channel, msg.id, duracion, interaction.user))
    active_monitors[channel.id] = {"tarea": task, "hasta": datetime.datetime.now(timezone.utc) + datetime.timedelta(minutes=duracion)}

@tree.command(name="forzaractualizacion", description="Fuerza la actualización del chat (detecta nuevos mensajes)")
@requiere_admin()
async def forzaractualizacion(interaction: discord.Interaction):
    await interaction.response.defer()
    json_filename = f"{EXPORT_FOLDER}/chat_{interaction.channel.id}.json"

    if not os.path.exists(json_filename):
        embed = discord.Embed(title="❌ Error", description="No se ha generado un chat para este canal.", color=0xFF0000)
        return await interaction.followup.send(embed=embed)

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
        with open(json_filename, "w", encoding="utf-8") as f:
            json.dump(chat_json, f, indent=4, ensure_ascii=False)

        final_path = await generar_imagen_segmentada(chat_json, interaction.channel.id)

        try:
            msg = await interaction.channel.fetch_message(mensaje_id)
            await msg.edit(content="✅ (Actualizado manual)", attachments=[discord.File(final_path)])
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
    personaje = buscar_personaje_por_nombre(nombre)

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


@bot.event
async def on_ready():
    await tree.sync()
    logging.info(f"Bot listo como {bot.user}")

api = "API_Bot.txt"
with open(api, "r") as f:
    token = f.read().strip()
bot.run(token)
