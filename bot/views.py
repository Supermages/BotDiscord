import discord
from db import guardar_personaje

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