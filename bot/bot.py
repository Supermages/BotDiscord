import discord
from discord import app_commands
from discord.ext import commands
import json
import os
from db import inicializar_base, obtener_personaje, guardar_personaje
from captura import generar_captura

# Constantes
EXPORT_FOLDER = "exports"

# Inicializar base de datos y carpetas
inicializar_base()
if not os.path.exists(EXPORT_FOLDER):
    os.makedirs(EXPORT_FOLDER)

# Configuración de intents y bot
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

@tree.command(name="generarchat", description="Genera un chat estilizado a partir de los últimos mensajes de Tupperbox y crea una imagen.")
@app_commands.describe(cantidad="Cantidad de mensajes a exportar (por defecto 20)")
async def generar_chat(interaction: discord.Interaction, cantidad: int = 20):
    await interaction.response.defer(ephemeral=True)

    channel = interaction.channel
    messages = [msg async for msg in channel.history(limit=cantidad)]

    personajes = {}
    mensajes_json = []

    for msg in reversed(messages):
        if not msg.webhook_id:
            continue

        personaje_nombre = msg.author.display_name
        personaje_id = str(msg.author.id)
        avatar_url = str(msg.author.avatar.url) if msg.author.avatar else ""

        personaje = obtener_personaje(personaje_id)

        if not personaje:
            lado = "I"
            guardar_personaje(personaje_id, personaje_nombre, lado, avatar_url)
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

    await interaction.followup.send(file=discord.File(imagen_path), content="✅ ¡Aquí tienes tu chat generado!")

@bot.event
async def on_ready():
    await tree.sync()
    print(f'✅ Bot listo como {bot.user}!')

# Ejecutar bot
api = "API_Bot.txt"
with open(api, "r") as f:
    token = f.read().strip()
bot.run(token)
