import discord
from discord import app_commands
from discord.ext import commands
import json
import os

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# Archivo para guardar las direcciones de los personajes
LADOS_FILE = "personaje_lados.json"

# Cargar lados guardados si existe
if os.path.exists(LADOS_FILE):
    with open(LADOS_FILE, "r", encoding="utf-8") as f:
        personaje_lados = json.load(f)
else:
    personaje_lados = {}

class LadoView(discord.ui.View):
    def __init__(self, autor_id, personaje_id, personaje_nombre):
        super().__init__(timeout=60)
        self.autor_id = autor_id
        self.personaje_id = personaje_id
        self.personaje_nombre = personaje_nombre
        self.lado = None

    @discord.ui.button(label="⬅️ Izquierda", style=discord.ButtonStyle.primary)
    async def izquierda(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.autor_id:
            await interaction.response.send_message("❌ Este botón no es para ti.", ephemeral=True)
            return
        self.lado = "I"
        personaje_lados[self.personaje_id] = "I"
        await self._guardar()
        await interaction.response.edit_message(content=f"✅ {self.personaje_nombre} asignado a **Izquierda**.", view=None)
        self.stop()

    @discord.ui.button(label="➡️ Derecha", style=discord.ButtonStyle.primary)
    async def derecha(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.autor_id:
            await interaction.response.send_message("❌ Este botón no es para ti.", ephemeral=True)
            return
        self.lado = "D"
        personaje_lados[self.personaje_id] = "D"
        await self._guardar()
        await interaction.response.edit_message(content=f"✅ {self.personaje_nombre} asignado a **Derecha**.", view=None)
        self.stop()

    async def _guardar(self):
        with open(LADOS_FILE, "w", encoding="utf-8") as f:
            json.dump(personaje_lados, f, indent=4, ensure_ascii=False)


@tree.command(name="exportarchat", description="Exporta los últimos 20 mensajes del canal hechos por Tupperbox en un archivo JSON.")
async def exportar_chat(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    channel = interaction.channel
    messages = [msg async for msg in channel.history(limit=20)]

    personajes = {}
    mensajes_json = []

    for msg in reversed(messages):
        if not msg.webhook_id or msg.webhook_id == 1365408923808563361:
            continue  # Ignorar mensajes que no sean de Tupperbox

        personaje_nombre = msg.author.display_name
        personaje_id = personaje_nombre.lower().replace(" ", "_")

        # Preguntar lado solo si es un nuevo personaje
        if personaje_id not in personajes:
            avatar_url = str(msg.author.avatar.url) if msg.author.avatar else ""

            if personaje_id not in personaje_lados:
                view = LadoView(interaction.user.id, personaje_id, personaje_nombre)
                await interaction.followup.send(
                    f"📢 ¿Dónde quieres colocar al personaje **{personaje_nombre}**?",
                    view=view,
                    ephemeral=True  # 👈 Esto lo hace privado
                )
                await view.wait()

            lado = personaje_lados.get(personaje_id, "I")  # Por defecto Izquierda si algo falla

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

    with open("chat.json", "w", encoding="utf-8") as f:
        json.dump(chat_json, f, indent=4, ensure_ascii=False)

    await interaction.followup.send(file=discord.File("chat.json"), content="✅ Chat exportado como `chat.json`.")

@bot.event
async def on_ready():
    await tree.sync()
    print(f'✅ Bot listo como {bot.user}!')

# Pega tu token aquí
api = "API_Bot.txt"
with open(api, "r") as f:
    token = f.read().strip()
bot.run(token)
