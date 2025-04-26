import discord
from discord import app_commands
from discord.ext import commands
import os
from db import inicializar_base, obtener_personaje, guardar_personaje
from captura import generar_captura

# Constantes
TUPPERBOX_WEBHOOK_ID = 1365408923808563361
EXPORT_FOLDER = "exportaciones"

# Inicializar base de datos y carpetas
inicializar_base()
if not os.path.exists(EXPORT_FOLDER):
    os.makedirs(EXPORT_FOLDER)

# Configuración de intents y bot
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
@app_commands.describe(cantidad="Cantidad de mensajes a exportar (por defecto 20)")
async def generar_chat(interaction: discord.Interaction, cantidad: int = 20):
    await interaction.response.defer(ephemeral=True)

    channel = interaction.channel
    messages = [msg async for msg in channel.history(limit=cantidad)]

    personajes = {}
    mensajes_json = []

    for msg in reversed(messages):
        if not msg.webhook_id or msg.webhook_id == TUPPERBOX_WEBHOOK_ID:
            continue

        personaje_nombre = msg.author.display_name
        personaje_id = str(msg.author.name) + str(msg.author.id)
        avatar_url = str(msg.author.avatar.url) if msg.author.avatar else "https://cdn.pixabay.com/photo/2015/10/05/22/37/blank-profile-picture-973460_1280.png"

        personaje = obtener_personaje(personaje_id)

        if not personaje:
            # Si no existe, pedir lado
            view = LadoView(interaction.user.id, personaje_id, personaje_nombre, avatar_url)
            await interaction.followup.send(
                f"📢 ¿Dónde quieres colocar a **{personaje_nombre}**?",
                view=view,
                ephemeral=True
            )
            await view.wait()
            lado = view.lado or "I"  # Por defecto a Izquierda
        else:
            nombre_db, lado, avatar_db = personaje
            if avatar_db != avatar_url:
                guardar_personaje(personaje_id, personaje_nombre, lado, avatar_url)

        personajes[personaje_id] = {
            "_id": personaje_id,
            "nombre": personaje_nombre,
            "DerOIzq": lado,
            "Avatar": avatar_url
        }

        mensajes_json.append({
            "Personaje": personaje_id,
            "Mensaje": msg.content
        })

    chat_json = {
        "Chat": {
            "titulo": channel.name,
            "personajes": list(personajes.values()),
            "mensajes": mensajes_json
        }
    }

    # Crear imagen usando captura
    imagen_path = await generar_captura(chat_json)

    await interaction.followup.send(
        file=discord.File(imagen_path), 
        content="✅ ¡Aquí tienes tu chat generado!",
        ephemeral=False)

@bot.event
async def on_ready():
    await tree.sync()
    print(f'✅ Bot listo como {bot.user}!')

# Ejecutar bot
api = "API_Bot.txt"
with open(api, "r") as f:
    token = f.read().strip()
bot.run(token)
