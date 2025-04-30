import discord
from discord import app_commands
from discord.ext import commands
import os
import datetime
import json
from db import inicializar_base, obtener_personaje, guardar_personaje, actualizar_personaje
from views import LadoView, EditPersonajeView
from captura import generar_captura

TUPPERBOX_WEBHOOK_ID = 1365408923808563361
EXPORT_FOLDER = "exportaciones"
ROL_REQUERIDO = "Bot Admin"

inicializar_base()
if not os.path.exists(EXPORT_FOLDER):
    os.makedirs(EXPORT_FOLDER)

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

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

def tiene_rol_admin(user: discord.Member):
    return any(role.name == ROL_REQUERIDO for role in user.roles)

async def rechazar_usuario(interaction: discord.Interaction):
    msg = await interaction.channel.send("❌ No tienes permisos para usar este comando.")
    await msg.delete(delay=5)

@tree.command(name="generarchat", description="Genera un chat con los últimos mensajes de Tupperbox y crea una imagen.")
@app_commands.describe(cantidad="Cantidad de mensajes a exportar", title="Título del chat")
async def generarchat(interaction: discord.Interaction, cantidad: int = 20, title: str = "chat"):
    if not isinstance(interaction.user, discord.Member) or not tiene_rol_admin(interaction.user):
        return await rechazar_usuario(interaction)

    if not interaction.response.is_done():
        await interaction.response.defer()

    channel = interaction.channel
    mensajes_json = []
    tupper_msgs = []

    async for msg in channel.history(limit=100):
        if msg.webhook_id and msg.webhook_id != TUPPERBOX_WEBHOOK_ID:
            tupper_msgs.append(msg)
        if len(tupper_msgs) >= cantidad:
            break

    for msg in reversed(tupper_msgs[:cantidad]):
        personaje_nombre = msg.author.display_name
        personaje_id = str(msg.author.name).replace(" ", "_") + str(msg.author.id)
        avatar_url = str(msg.author.avatar.url) if msg.author.avatar else "https://cdn.pixabay.com/photo/2015/10/05/22/37/blank-profile-picture-973460_1280.png"

        personaje = obtener_personaje(personaje_id)

        if not personaje:
            try:
                view = LadoView(interaction.user.id, personaje_id, personaje_nombre, avatar_url)
                await interaction.user.send(f"📢 ¿Dónde quieres colocar a **{personaje_nombre}**?", view=view)
                await view.wait()
                lado = view.lado or "I"
                color = "#2C58E2" if lado == "D" else "#FFFFFF"
                color_texto = "#FFFFFF" if lado == "D" else "#000000"
                guardar_personaje(personaje_id, personaje_nombre, lado, avatar_url, color, color_texto)
            except discord.Forbidden:
                print(f"[⚠️] No se pudo enviar DM a {interaction.user.display_name}.")
                continue
        else:
            nombre_db, lado, avatar_db, color, color_texto = personaje
            if avatar_db != avatar_url:
                guardar_personaje(personaje_id, personaje_nombre, lado, avatar_url, color, color_texto)

        mensajes_json.append({
            "Personaje": personaje_id,
            "Mensaje": msg.content
        })

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
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
    print(f"[📝] JSON guardado: {json_filename}")

    imagen_path = await generar_captura(chat_json)
    await interaction.followup.send(file=discord.File(imagen_path), content="✅ ¡Aquí tienes tu chat generado!")

@tree.command(name="actualizarchat", description="Actualiza el chat añadiendo nuevos mensajes desde el último guardado.")
async def actualizarchat(interaction: discord.Interaction):
    if not isinstance(interaction.user, discord.Member) or not tiene_rol_admin(interaction.user):
        return await rechazar_usuario(interaction)

    if not interaction.response.is_done():
        await interaction.response.defer()

    channel = interaction.channel
    json_filename = f"{EXPORT_FOLDER}/chat_{channel.id}.json"

    if not os.path.exists(json_filename):
        await interaction.followup.send("❌ No se encontró un archivo JSON para este canal.", ephemeral=True)
        return

    with open(json_filename, "r", encoding="utf-8") as f:
        chat_json = json.load(f)

    mensajes_guardados = chat_json["Chat"]["mensajes"]
    mensajes_guardados_contenido = set(m["Mensaje"] for m in mensajes_guardados)
    nuevos_mensajes = []

    last_id = chat_json["Chat"].get("ultimo_id", None)

    async for msg in channel.history(after=discord.Object(id=last_id)) if last_id else channel.history(limit=100):
        if msg.webhook_id and msg.webhook_id != TUPPERBOX_WEBHOOK_ID:
            if msg.content not in mensajes_guardados_contenido:
                personaje_nombre = msg.author.display_name
                personaje_id = str(msg.author.name).replace(" ", "_") + str(msg.author.id)
                avatar_url = str(msg.author.avatar.url) if msg.author.avatar else "https://cdn.pixabay.com/photo/2015/10/05/22/37/blank-profile-picture-973460_1280.png"
                personaje = obtener_personaje(personaje_id)

                if not personaje:
                    try:
                        view = LadoView(interaction.user.id, personaje_id, personaje_nombre, avatar_url)
                        await interaction.user.send(f"📢 ¿Dónde quieres colocar a **{personaje_nombre}**?", view=view)
                        await view.wait()
                        lado = view.lado or "I"
                        color = "#2C58E2" if lado == "D" else "#FFFFFF"
                        color_texto = "#FFFFFF" if lado == "D" else "#000000"
                        guardar_personaje(personaje_id, personaje_nombre, lado, avatar_url, color, color_texto)
                    except discord.Forbidden:
                        print(f"[⚠️] No se pudo enviar DM a {interaction.user.display_name}.")
                        continue
                else:
                    nombre_db, lado, avatar_db, color, color_texto = personaje
                    if avatar_db != avatar_url:
                        guardar_personaje(personaje_id, personaje_nombre, lado, avatar_url, color, color_texto)

                nuevos_mensajes.append({
                    "Personaje": personaje_id,
                    "Mensaje": msg.content
                })
                chat_json["Chat"]["ultimo_id"] = msg.id

    if nuevos_mensajes:
        chat_json["Chat"]["mensajes"].extend(reversed(nuevos_mensajes))
        chat_json["Chat"]["fecha"] = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        with open(json_filename, "w", encoding="utf-8") as f:
            json.dump(chat_json, f, indent=4, ensure_ascii=False)
        print(f"[🆕] {len(nuevos_mensajes)} nuevos mensajes añadidos.")
    else:
        print("[ℹ️] No hay mensajes nuevos que agregar.")

    imagen_path = await generar_captura(chat_json)
    await interaction.followup.send(file=discord.File(imagen_path), content="✅ ¡Chat actualizado y generado!")

@tree.command(name="editarpersonaje", description="Edita visualmente las propiedades de un personaje.")
@app_commands.describe(nombre="Nombre del personaje (no ID)")
async def editarpersonaje(interaction: discord.Interaction, nombre: str):
    if not isinstance(interaction.user, discord.Member) or not tiene_rol_admin(interaction.user):
        return await rechazar_usuario(interaction)

    await interaction.response.defer()
    personaje = buscar_personaje_por_nombre(nombre)
    if not personaje:
        await interaction.followup.send("❌ No se encontró el personaje.", ephemeral=True)
        return

    personaje_id, nombre, lado, avatar_url, color, color_texto = personaje
    view = EditPersonajeView(interaction, personaje_id, nombre, lado, color, color_texto, avatar_url)
    try:
        await interaction.user.send(f"🔧 Editando personaje: **{nombre}**", view=view)
        await view.send_preview()
    except discord.Forbidden:
        await interaction.followup.send(f"📍 No pude enviarte DM. Aquí tienes la edición.", ephemeral=True)
        await view.send_preview()

@bot.event
async def on_ready():
    await tree.sync()
    print(f'✅ Bot listo como {bot.user}!')

api = "API_Bot.txt"
with open(api, "r") as f:
    token = f.read().strip()
bot.run(token)
