import discord
from core.database import guardar_personaje, actualizar_personaje

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
        await guardar_personaje(self.personaje_id, self.personaje_nombre, self.lado, self.avatar_url)
        await interaction.response.edit_message(content=f"✅ {self.personaje_nombre} asignado a **Izquierda**.", view=None)
        self.stop()

    @discord.ui.button(label="➡️ Derecha", style=discord.ButtonStyle.primary)
    async def derecha(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.autor_id:
            await interaction.response.send_message("❌ Este botón no es para ti.", ephemeral=True)
            return
        self.lado = "D"
        await guardar_personaje(self.personaje_id, self.personaje_nombre, self.lado, self.avatar_url)
        await interaction.response.edit_message(content=f"✅ {self.personaje_nombre} asignado a **Derecha**.", view=None)
        self.stop()

class EditPersonajeView(discord.ui.View):
    def __init__(self, interaction: discord.Interaction, personaje_id, nombre, lado, color, color_texto, avatar_url):
        super().__init__(timeout=180)
        self.interaction = interaction
        self.personaje_id = personaje_id
        self.nombre = nombre
        self.lado = lado or "I"
        self.color = color or "#FFFFFF"
        self.color_texto = color_texto or "#000000"
        self.avatar_url = avatar_url or ""
        self.message = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.interaction.user.id:
            await interaction.response.send_message("❌ No puedes interactuar con este menú.", ephemeral=True)
            return False
        return True

    def _generar_embed(self) -> discord.Embed:
        color_val = 0x5865F2
        try:
            color_val = int(self.color.replace("#", ""), 16)
        except Exception:
            pass

        embed = discord.Embed(
            title=f"✏️ Editando: {self.nombre}",
            description="Modifica las propiedades de tu personaje usando los botones inferiores.",
            color=color_val
        )
        embed.add_field(name="👤 Nombre", value=f"**{self.nombre}**", inline=True)
        embed.add_field(name="🆔 Tag / ID", value=f"`{self.personaje_id}` *(Fijo)*", inline=True)
        lado_str = "⬅️ Izquierda (I)" if self.lado == "I" else "➡️ Derecha (D)"
        embed.add_field(name="💬 Lado en Chat", value=lado_str, inline=True)
        embed.add_field(name="🎨 Color Fondo", value=f"`{self.color}`", inline=True)
        embed.add_field(name="🖋️ Color Texto", value=f"`{self.color_texto}`", inline=True)
        
        avatar_val = self.avatar_url if self.avatar_url and self.avatar_url.startswith("http") else "https://cdn.discordapp.com/embed/avatars/0.png"
        embed.set_thumbnail(url=avatar_val)
        embed.set_footer(text="Haz clic en 'Guardar Cambios' para aplicar todas las modificaciones.")
        return embed

    async def send_preview(self, interaction: discord.Interaction = None):
        embed = self._generar_embed()
        if interaction:
            if not interaction.response.is_done():
                await interaction.response.edit_message(embed=embed, view=self)
            else:
                await interaction.edit_original_response(embed=embed, view=self)
        elif self.message:
            await self.message.edit(embed=embed, view=self)
        else:
            if self.interaction.response.is_done():
                self.message = await self.interaction.followup.send(embed=embed, view=self, ephemeral=True)
            else:
                await self.interaction.response.send_message(embed=embed, view=self, ephemeral=True)
                self.message = await self.interaction.original_response()

    @discord.ui.button(label="✏️ Nombre", style=discord.ButtonStyle.primary, row=0)
    async def cambiar_nombre(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(NombreModal(self))

    @discord.ui.button(label="🖼️ Avatar / Foto", style=discord.ButtonStyle.primary, row=0)
    async def cambiar_avatar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AvatarModal(self))

    @discord.ui.button(label="🔄 Alternar Lado", style=discord.ButtonStyle.secondary, row=0)
    async def cambiar_lado(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.lado = "D" if self.lado == "I" else "I"
        await self.send_preview(interaction)

    @discord.ui.button(label="🎨 Color Fondo", style=discord.ButtonStyle.secondary, row=1)
    async def cambiar_color_fondo(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ColorModal(self, "color"))

    @discord.ui.button(label="🖋️ Color Texto", style=discord.ButtonStyle.secondary, row=1)
    async def cambiar_color_texto(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ColorModal(self, "color_texto"))

    @discord.ui.button(label="✅ Guardar Cambios", style=discord.ButtonStyle.success, row=2)
    async def guardar(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await actualizar_personaje(
                self.personaje_id,
                nombre=self.nombre,
                avatar_url=self.avatar_url,
                lado=self.lado,
                color=self.color,
                color_texto=self.color_texto
            )
            embed = discord.Embed(
                title="✅ Personaje Actualizado",
                description=f"¡Los datos de **{self.nombre}** se han guardado exitosamente!",
                color=0x2ECC71
            )
            avatar_val = self.avatar_url if self.avatar_url and self.avatar_url.startswith("http") else "https://cdn.discordapp.com/embed/avatars/0.png"
            embed.set_thumbnail(url=avatar_val)
            embed.add_field(name="👤 Nombre", value=f"**{self.nombre}**", inline=True)
            embed.add_field(name="🆔 Tag / ID", value=f"`{self.personaje_id}`", inline=True)
            lado_str = "⬅️ Izquierda (I)" if self.lado == "I" else "➡️ Derecha (D)"
            embed.add_field(name="💬 Lado en Chat", value=lado_str, inline=True)
            embed.add_field(name="🎨 Color Fondo", value=f"`{self.color}`", inline=True)
            embed.add_field(name="🖋️ Color Texto", value=f"`{self.color_texto}`", inline=True)

            if not interaction.response.is_done():
                await interaction.response.edit_message(embed=embed, view=None)
            else:
                await interaction.edit_original_response(embed=embed, view=None)
            self.stop()
        except Exception as e:
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ Error al guardar los cambios: {e}", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ Error al guardar los cambios: {e}", ephemeral=True)

    @discord.ui.button(label="❌ Cancelar", style=discord.ButtonStyle.danger, row=2)
    async def cancelar(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="❌ Edición Cancelada",
            description=f"No se aplicó ningún cambio a **{self.nombre}**.",
            color=0x95A5A6
        )
        if not interaction.response.is_done():
            await interaction.response.edit_message(embed=embed, view=None)
        else:
            await interaction.edit_original_response(embed=embed, view=None)
        self.stop()

class NombreModal(discord.ui.Modal):
    def __init__(self, view: EditPersonajeView):
        super().__init__(title="Editar Nombre")
        self.view = view
        self.nombre_input = discord.ui.TextInput(
            label="Nombre visible del personaje:",
            default=self.view.nombre[:100],
            placeholder="Ej: Apolo Vanguard",
            required=True,
            max_length=100
        )
        self.add_item(self.nombre_input)

    async def on_submit(self, interaction: discord.Interaction):
        nuevo = self.nombre_input.value.strip()
        if not nuevo:
            return await interaction.response.send_message("❌ El nombre no puede estar vacío.", ephemeral=True)
        self.view.nombre = nuevo
        await self.view.send_preview(interaction)

class AvatarModal(discord.ui.Modal):
    def __init__(self, view: EditPersonajeView):
        super().__init__(title="Editar Foto de Perfil")
        self.view = view
        self.avatar_input = discord.ui.TextInput(
            label="URL de la imagen (Avatar):",
            default=self.view.avatar_url or "",
            placeholder="https://cdn.discordapp.com/... o enlace web",
            required=True,
            max_length=500
        )
        self.add_item(self.avatar_input)

    async def on_submit(self, interaction: discord.Interaction):
        url = self.avatar_input.value.strip()
        if not (url.startswith("http://") or url.startswith("https://")):
            return await interaction.response.send_message("❌ La URL debe comenzar con http:// o https://.", ephemeral=True)
        self.view.avatar_url = url
        await self.view.send_preview(interaction)

class ColorModal(discord.ui.Modal):
    def __init__(self, view: EditPersonajeView, tipo: str):
        self.view = view
        self.tipo = tipo
        title = "Color de Fondo" if tipo == "color" else "Color de Texto"
        super().__init__(title=title)
        def_val = self.view.color if tipo == "color" else self.view.color_texto
        self.color_input = discord.ui.TextInput(
            label="Introduce un color en formato HEX (#RRGGBB):",
            default=def_val,
            placeholder="#FFFFFF",
            required=True,
            max_length=7
        )
        self.add_item(self.color_input)

    async def on_submit(self, interaction: discord.Interaction):
        color = self.color_input.value.strip().upper()
        if not color.startswith("#") or len(color) != 7:
            return await interaction.response.send_message("❌ Color inválido. Usa formato HEX como `#RRGGBB`.", ephemeral=True)

        if self.tipo == "color":
            self.view.color = color
        else:
            self.view.color_texto = color

        await self.view.send_preview(interaction)
