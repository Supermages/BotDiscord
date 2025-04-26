import discord
from discord import app_commands
from discord.ext import commands
import os
import datetime
import json
from db import inicializar_base, obtener_personaje, guardar_personaje
from captura import generar_captura

# Constantes
TUPPERBOX_WEBHOOK_ID = 1365408923808563361
EXPORT_FOLDER = "exportaciones"

# Inicializar base de datos y carpetas
inicializar_base()
if not os.path.exists(EXPORT_FOLDER):
    os.makedirs(EXPORT_FOLDER)

# Configuración del bot
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

class LadoView(discord.ui.View):
    def __init__(self, autor_id, personaje_id, personaje_nombre, avatar_url):
        super().__init__(timeout=60)
        self.autor_id = autor_id
        self.personaje_id = personaje_id
        self.personaje_nombre = personaje_nombre
        self.avatar_url = avatar_url
        self.lado = None

    @discord.ui.button(label="⬅️ Izquierda", style=discord.ButtonStyle.primary)
    async def izquierda(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.autor_id:
            await interaction.response.send_message("❌ Este botón no es para ti.", ephemeral=True)
            return
        self.lado = "I"
        guardar_personaje(self.personaje_id, self.personaje_nombre, self.lado, self.avatar_url)
        await interaction.response.edit_message(content=f"✅ {self.personaje_nombre} asignado a **Izquierda**.", view=None)
        self.stop()

    @discord.ui.button(label="➡️ Derecha", style=discord.ButtonStyle.primary)
    async def derecha(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.autor_id:
            await interaction.response.send_message("❌ Este botón no es para ti.", ephemeral=True)
            return
        self.lado = "D"
        guardar_personaje(self.personaje_id, self.personaje_nombre, self.lado, self.avatar_url)
        await interaction.response.edit_message(content=f"✅ {self.personaje_nombre} asignado a **Derecha**.", view=None)
        self.stop()

@tree.command(name="generarchat", description="Genera un chat estilizado a partir de los últimos mensajes de Tupperbox y crea una imagen.")
@app_commands.describe(cantidad="Cantidad de mensajes a exportar (por defecto 20)", title="Título del chat")
async def generar_chat(interaction: discord.Interaction, cantidad: int = 20, title: str = "chat"):
    await interaction.response.defer()

    channel = interaction.channel
    messages = [msg async for msg in channel.history(limit=cantidad)]

    mensajes_json = []
    channel_id = str(channel.id)

    for msg in reversed(messages):
        if not msg.webhook_id or msg.webhook_id == TUPPERBOX_WEBHOOK_ID:
            continue

        personaje_nombre = msg.author.display_name
        personaje_id = str(msg.author.name) + str(msg.author.id)
        avatar_url = str(msg.author.avatar.url) if msg.author.avatar else "https://cdn.pixabay.com/photo/2015/10/05/22/37/blank-profile-picture-973460_1280.png"

        personaje = obtener_personaje(personaje_id)

        if not personaje:
            view = LadoView(interaction.user.id, personaje_id, personaje_nombre, avatar_url)
            await interaction.followup.send(
                f"📢 ¿Dónde quieres colocar a **{personaje_nombre}**?",
                view=view,
                ephemeral=True
            )
            await view.wait()
            lado = view.lado or "I"
        else:
            nombre_db, lado, avatar_db = personaje
            if avatar_db != avatar_url:
                guardar_personaje(personaje_id, personaje_nombre, lado, avatar_url)

        mensajes_json.append({
            "Personaje": personaje_id,
            "Mensaje": msg.content
        })

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    chat_json = {
        "Chat": {
            "titulo": title if title != "chat" else channel.name,
            "fecha": timestamp,
            "mensajes": mensajes_json
        }
    }

    # Guardar JSON principal
    json_filename = f"{EXPORT_FOLDER}/chat_{channel_id}.json"
    with open(json_filename, "w", encoding="utf-8") as f:
        json.dump(chat_json, f, indent=4, ensure_ascii=False)

    print(f"[✅] JSON guardado: {json_filename}")

    # Guardar copia histórica
    json_history_filename = f"{EXPORT_FOLDER}/chat_{channel_id}_{timestamp}.json"
    with open(json_history_filename, "w", encoding="utf-8") as f:
        json.dump(chat_json, f, indent=4, ensure_ascii=False)

    print(f"[🗂️] Copia histórica guardada: {json_history_filename}")

    # Crear imagen
    imagen_path = await generar_captura(chat_json)

    # Guardar imagen principal
    final_image_path = f"{EXPORT_FOLDER}/chat_{channel_id}.png"
    os.replace(imagen_path, final_image_path)
    print(f"[📷] Imagen generada: {final_image_path}")

    await interaction.followup.send(
        file=discord.File(final_image_path),
        content="✅ ¡Aquí tienes tu chat generado!",
        ephemeral=False
    )

@tree.command(name="actualizarchat", description="Actualiza el chat añadiendo nuevos mensajes desde el último guardado.")
async def actualizar_chat(interaction: discord.Interaction):
    await interaction.response.defer()

    channel = interaction.channel
    channel_id = str(channel.id)
    json_filename = f"{EXPORT_FOLDER}/chat_{channel_id}.json"

    if not os.path.exists(json_filename):
        await interaction.followup.send("❌ No se encontró un archivo JSON para este canal.", ephemeral=False)
        print(f"[⚠️] No existe JSON para canal {channel_id}")
        return

    with open(json_filename, "r", encoding="utf-8") as f:
        chat_json = json.load(f)

    mensajes_guardados = chat_json["Chat"]["mensajes"]
    mensajes_guardados_contenido = set(m["Mensaje"] for m in mensajes_guardados)

    nuevos_mensajes = []

    async for msg in channel.history(limit=10):
        if not msg.webhook_id or msg.webhook_id == TUPPERBOX_WEBHOOK_ID:
            continue

        if msg.content in mensajes_guardados_contenido:
            continue  # Ya capturado

        personaje_nombre = msg.author.display_name
        personaje_id = str(msg.author.name) + str(msg.author.id)
        avatar_url = str(msg.author.avatar.url) if msg.author.avatar else "https://cdn.pixabay.com/photo/2015/10/05/22/37/blank-profile-picture-973460_1280.png"

        personaje = obtener_personaje(personaje_id)

        if not personaje:
            # Asumimos izquierda si es nuevo y no tenemos base (no pedimos de nuevo)
            guardar_personaje(personaje_id, personaje_nombre, "I", avatar_url)

        nuevos_mensajes.append({
            "Personaje": personaje_id,
            "Mensaje": msg.content
        })

    if nuevos_mensajes:
        print(f"[➕] {len(nuevos_mensajes)} nuevos mensajes añadidos.")
    else:
        print(f"[➕] 0 nuevos mensajes añadidos.")

    chat_json["Chat"]["mensajes"].extend(reversed(nuevos_mensajes))

    # Actualizar fecha
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    chat_json["Chat"]["fecha"] = timestamp

    # Guardar actualizado
    with open(json_filename, "w", encoding="utf-8") as f:
        json.dump(chat_json, f, indent=4, ensure_ascii=False)

    print(f"[✅] JSON actualizado: {json_filename}")

    # Crear imagen
    imagen_path = await generar_captura(chat_json)

    final_image_path = f"{EXPORT_FOLDER}/chat_{channel_id}.png"
    os.replace(imagen_path, final_image_path)
    print(f"[🔄] Imagen regenerada: {final_image_path}")

    await interaction.followup.send(
        file=discord.File(final_image_path),
        content="✅ ¡Chat actualizado y generado!",
        ephemeral=False
    )

@bot.event
async def on_ready():
    await tree.sync()
    print(f'✅ Bot listo como {bot.user}!')

# Ejecutar bot
api = "API_Bot.txt"
with open(api, "r") as f:
    token = f.read().strip()
bot.run(token)
