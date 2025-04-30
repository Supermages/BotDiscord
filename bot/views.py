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

import discord
from db import actualizar_personaje, obtener_personaje

class EditPersonajeView(discord.ui.View):
    def __init__(self, interaction: discord.Interaction, personaje_id, nombre, lado, color, color_texto, avatar_url):
        super().__init__(timeout=60)
        self.interaction = interaction
        self.personaje_id = personaje_id
        self.nombre = nombre
        self.lado = lado
        self.color = color
        self.color_texto = color_texto
        self.avatar_url = avatar_url
        self.message = None

    async def send_preview(self):
        embed = discord.Embed(
            title=f"{self.nombre} (Vista previa)",
            description=f"Lado: {self.lado}",
            color=int(self.color.replace("#", "0x"), 16)
        )
        embed.add_field(name="Color fondo", value=self.color)
        embed.add_field(name="Color texto", value=self.color_texto)
        embed.set_thumbnail(url=self.avatar_url)

        if self.message:
            await self.message.edit(embed=embed, view=self)
        else:
            # Enviar al MD del usuario
            self.message = await self.interaction.user.send(embed=embed, view=self)

    @discord.ui.button(label="🔄 Cambiar lado", style=discord.ButtonStyle.secondary)
    async def cambiar_lado(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.lado = "D" if self.lado == "I" else "I"
        await self.send_preview()

    @discord.ui.button(label="🎨 Cambiar color fondo", style=discord.ButtonStyle.primary)
    async def cambiar_color_fondo(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ColorModal(self, "color"))

    @discord.ui.button(label="🖋️ Cambiar color texto", style=discord.ButtonStyle.primary)
    async def cambiar_color_texto(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ColorModal(self, "color_texto"))
    
    @discord.ui.button(label="✅ Guardar", style=discord.ButtonStyle.success)
    async def guardar(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            # Actualizar los datos del personaje en la base de datos
            actualizar_personaje(self.personaje_id, lado=self.lado, color=self.color, color_texto=self.color_texto)
            await interaction.response.send_message(content=f"✅ Cambios guardados para {self.nombre}.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(content=f"❌ Error al guardar los cambios: {e}", ephemeral=True)
        finally:
            # Editar el mensaje para eliminar la vista y el embed
            if self.message:
                await self.message.edit(content="✅ Cambios guardados.", embed=None, view=None)
            self.stop()  # Detener la vista

    @discord.ui.button(label="❌ Cancelar", style=discord.ButtonStyle.danger)
    async def cancelar(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.send_message(content="❌ Edición cancelada.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(content=f"❌ Error al cancelar: {e}", ephemeral=True)
        finally:
            # Editar el mensaje para eliminar la vista y el embed
            if self.message:
                await self.message.edit(content="❌ Edición cancelada.", embed=None, view=None)
            self.stop()  # Detener la vista

class ColorModal(discord.ui.Modal):
    def __init__(self, view: EditPersonajeView, tipo: str):
        self.view = view
        self.tipo = tipo
        title = "Color de fondo" if tipo == "color" else "Color de texto"
        super().__init__(title=title)
        self.color_input = discord.ui.TextInput(
            label="Introduce un color en formato HEX (#RRGGBB):",
            placeholder="#FFFFFF",
            required=True,
            max_length=7
        )
        self.add_item(self.color_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        color = self.color_input.value.strip()
        if not color.startswith("#") or len(color) != 7:
            await interaction.response.send_message("❌ Color inválido. Usa formato HEX como `#RRGGBB`.", ephemeral=True)
            return

        if self.tipo == "color":
            self.view.color = color
        else:
            self.view.color_texto = color

        await self.view.send_preview()
