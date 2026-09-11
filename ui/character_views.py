import discord
from discord import ui
from core.database import (
    obtener_personajes_activos,
    obtener_personajes_reserva,
    obtener_limite_personajes,
    activar_personaje,
    desactivar_personaje
)

class CharacterPanelView(ui.View):
    def __init__(self, user: discord.User | discord.Member, guild_id: str = None):
        super().__init__(timeout=180)
        self.user = user
        self.guild_id = guild_id
        self.activos = []
        self.reserva = []
        self.limite = 3

    async def cargar_datos(self):
        self.limite = await obtener_limite_personajes(self.guild_id)
        self.activos = await obtener_personajes_activos(str(self.user.id))
        self.reserva = await obtener_personajes_reserva(str(self.user.id))
        self._reconstruir_componentes()

    def _reconstruir_componentes(self):
        self.clear_items()

        # 1. Selector para Activar (si hay espacio y hay personajes en reserva)
        if len(self.activos) < self.limite and self.reserva:
            opciones_activar = [
                discord.SelectOption(
                    label=p["nombre"][:100],
                    value=p["tupper_tag"][:100],
                    description=f"Activar en tu cupo ({len(self.activos)}/{self.limite})",
                    emoji="➕"
                )
                for p in self.reserva[:25]
            ]
            sel_activar = ui.Select(
                placeholder=f"➕ Activar personaje ({len(self.activos)}/{self.limite} activos)...",
                options=opciones_activar,
                custom_id="select_activar_personaje"
            )
            sel_activar.callback = self._on_select_activar
            self.add_item(sel_activar)

        # 2. Selector para Desactivar (si tiene personajes activos)
        if self.activos:
            opciones_desactivar = [
                discord.SelectOption(
                    label=p["nombre"][:100],
                    value=p["tupper_tag"][:100],
                    description="Pasar a reserva para liberar espacio",
                    emoji="➖"
                )
                for p in self.activos[:25]
            ]
            sel_desactivar = ui.Select(
                placeholder="➖ Pasar personaje a reserva...",
                options=opciones_desactivar,
                custom_id="select_desactivar_personaje"
            )
            sel_desactivar.callback = self._on_select_desactivar
            self.add_item(sel_desactivar)

        # 3. Botones de acción
        btn_actualizar = ui.Button(label="Actualizar", style=discord.ButtonStyle.secondary, emoji="🔄")
        btn_actualizar.callback = self._on_click_actualizar
        self.add_item(btn_actualizar)

        btn_cerrar = ui.Button(label="Cerrar", style=discord.ButtonStyle.danger, emoji="❌")
        btn_cerrar.callback = self._on_click_cerrar
        self.add_item(btn_cerrar)

    def generar_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="🎭 Panel de Gestión de Personajes",
            description=(
                f"Gestiona qué personajes tienes activos en tu cuenta ({self.user.mention}).\n"
                f"• **Límite activo:** `{len(self.activos)}/{self.limite}` personajes.\n"
                f"• **En reserva:** `{len(self.reserva)}` personajes listos para activar."
            ),
            color=0x3498DB
        )

        if self.activos:
            lista_act = "\n".join([f"• 🛡️ **{p['nombre']}** (`{p['tupper_tag']}`)" for p in self.activos])
            embed.add_field(name=f"✅ Personajes Activos ({len(self.activos)}/{self.limite})", value=lista_act, inline=False)
        else:
            embed.add_field(
                name=f"⚠️ Sin Personajes Activos (0/{self.limite})",
                value="No tienes ningún personaje activo. Usa el menú desplegable abajo para activar uno de tu reserva.",
                inline=False
            )

        if self.reserva:
            nombres_res = [f"`{p['nombre']}`" for p in self.reserva[:12]]
            extra = f" y {len(self.reserva) - 12} más..." if len(self.reserva) > 12 else ""
            embed.add_field(
                name=f"📦 En Reserva ({len(self.reserva)})",
                value=", ".join(nombres_res) + extra,
                inline=False
            )
        else:
            embed.add_field(
                name="📦 Reserva Vacía",
                value="No tienes personajes en reserva. Puedes importarlos con `/pj importar` o escribiendo con ellos con Tupperbox.",
                inline=False
            )

        embed.set_footer(text="EriduBot • Tu inventario se preserva al pasar personajes a la reserva.")
        if self.activos and self.activos[0].get("avatar_url"):
            embed.set_thumbnail(url=self.activos[0]["avatar_url"])

        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Solo el dueño de este panel puede interactuar con él.", ephemeral=True)
            return False
        return True

    async def _on_select_activar(self, interaction: discord.Interaction):
        await interaction.response.defer()
        tupper_tag = interaction.data["values"][0]
        ok, msg, pj_dict = await activar_personaje(str(self.user.id), tupper_tag, self.limite)
        await self.cargar_datos()
        await interaction.edit_original_response(embed=self.generar_embed(), view=self)

    async def _on_select_desactivar(self, interaction: discord.Interaction):
        await interaction.response.defer()
        tupper_tag = interaction.data["values"][0]
        ok, msg = await desactivar_personaje(str(self.user.id), tupper_tag)
        await self.cargar_datos()
        await interaction.edit_original_response(embed=self.generar_embed(), view=self)

    async def _on_click_actualizar(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await self.cargar_datos()
        await interaction.edit_original_response(embed=self.generar_embed(), view=self)

    async def _on_click_cerrar(self, interaction: discord.Interaction):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()
