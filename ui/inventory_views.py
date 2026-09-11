import math
import discord

CHEST_THUMBNAIL = "https://cdn-icons-png.flaticon.com/512/2855/2855452.png"

class InventoryView(discord.ui.View):
    """
    Vista interactiva con botones para explorar el inventario paginado estilo MythOS.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(timeout=180)
        # Soporte para ambas firmas:
        # 1. InventoryView(items, personaje_nombre, avatar_url, autor_id, items_por_pagina=8)
        # 2. InventoryView(interaction, tupper_tag, nombre, avatar_url, items, items_por_pagina=8)
        if len(args) > 0 and isinstance(args[0], discord.Interaction):
            interaction = args[0]
            self.autor_id = interaction.user.id
            self.personaje_nombre = args[2] if len(args) > 2 else kwargs.get("nombre", "Personaje")
            self.avatar_url = (args[3] if len(args) > 3 and args[3] else kwargs.get("avatar_url")) or "https://cdn.discordapp.com/embed/avatars/0.png"
            self.items = args[4] if len(args) > 4 and isinstance(args[4], list) else kwargs.get("items", [])
            self.items_por_pagina = args[5] if len(args) > 5 else kwargs.get("items_por_pagina", 8)
        else:
            self.items = args[0] if len(args) > 0 and isinstance(args[0], list) else kwargs.get("items", [])
            self.personaje_nombre = args[1] if len(args) > 1 else kwargs.get("personaje_nombre", "Personaje")
            self.avatar_url = (args[2] if len(args) > 2 and args[2] else kwargs.get("avatar_url")) or "https://cdn.discordapp.com/embed/avatars/0.png"
            self.autor_id = args[3] if len(args) > 3 else kwargs.get("autor_id", 0)
            self.items_por_pagina = args[4] if len(args) > 4 else kwargs.get("items_por_pagina", 8)

        self.pagina_actual = 0
        self.total_paginas = max(1, math.ceil(len(self.items) / self.items_por_pagina))
        self.message = None

        self._actualizar_botones()

    def _actualizar_botones(self):
        self.btn_anterior.disabled = (self.pagina_actual == 0)
        self.btn_siguiente.disabled = (self.pagina_actual >= self.total_paginas - 1)

    def generar_embed(self) -> discord.Embed:
        embed = discord.Embed(
            color=0xE67E22 # Naranja estilo MythOS
        )
        embed.set_author(name=self.personaje_nombre, icon_url=self.avatar_url)
        embed.set_thumbnail(url=CHEST_THUMBNAIL)

        if not self.items:
            embed.description = "*El inventario está completamente vacío.*"
        else:
            inicio = self.pagina_actual * self.items_por_pagina
            fin = inicio + self.items_por_pagina
            items_pagina = self.items[inicio:fin]

            lineas = []
            for item in items_pagina:
                lineas.append(f"{item['emoji']} **{item['nombre']}** x{item['cantidad']}")

            embed.description = "\n".join(lineas)

        embed.set_footer(text=f"Página {self.pagina_actual + 1} de {self.total_paginas} • Total de tipos de objetos: {len(self.items)}")
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.autor_id:
            await interaction.response.send_message("❌ Este panel de inventario fue abierto por otro usuario.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary, custom_id="inv_prev")
    async def btn_anterior(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.pagina_actual > 0:
            self.pagina_actual -= 1
            self._actualizar_botones()
            await interaction.response.edit_message(embed=self.generar_embed(), view=self)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary, custom_id="inv_next")
    async def btn_siguiente(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.pagina_actual < self.total_paginas - 1:
            self.pagina_actual += 1
            self._actualizar_botones()
            await interaction.response.edit_message(embed=self.generar_embed(), view=self)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger, custom_id="inv_close")
    async def btn_cerrar(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        try:
            await interaction.message.delete()
        except Exception:
            await interaction.response.edit_message(content="*Inventario cerrado.*", embed=None, view=None)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass


class TransferConfirmView(discord.ui.View):
    """
    Vista de confirmación para transferencias seguras entre jugadores.
    """
    def __init__(self, autor_id: int):
        super().__init__(timeout=60)
        self.autor_id = autor_id
        self.confirmado = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.autor_id:
            await interaction.response.send_message("❌ No puedes responder a esta confirmación.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="✅ Confirmar Transferencia", style=discord.ButtonStyle.success)
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmado = True
        self.stop()
        await interaction.response.defer()

    @discord.ui.button(label="❌ Cancelar", style=discord.ButtonStyle.danger)
    async def cancelar(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmado = False
        self.stop()
        await interaction.response.edit_message(content="❌ Transferencia cancelada.", embed=None, view=None)


class RecipesView(discord.ui.View):
    """
    Vista paginada para consultar las recetas de crafteo del servidor.
    """
    def __init__(self, recetas: list[dict], autor_id: int, recetas_por_pagina: int = 4):
        super().__init__(timeout=180)
        self.recetas = recetas
        self.autor_id = autor_id
        self.recetas_por_pagina = recetas_por_pagina
        self.pagina_actual = 0
        self.total_paginas = max(1, math.ceil(len(recetas) / recetas_por_pagina))

        self._actualizar_botones()

    def _actualizar_botones(self):
        self.btn_anterior.disabled = (self.pagina_actual == 0)
        self.btn_siguiente.disabled = (self.pagina_actual >= self.total_paginas - 1)

    def generar_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="📜 Libro de Recetas de Crafteo",
            description="Aquí puedes consultar los materiales necesarios para fabricar cada objeto.",
            color=0x3498DB
        )

        if not self.recetas:
            embed.description = "*No hay recetas registradas todavía en el servidor.*"
        else:
            inicio = self.pagina_actual * self.recetas_por_pagina
            fin = inicio + self.recetas_por_pagina
            recetas_pagina = self.recetas[inicio:fin]

            for r in recetas_pagina:
                ings_txt = "\n".join([f"  • {ing['emoji']} {ing['nombre']} x{ing['cantidad']}" for ing in r.get("ingredientes", [])])
                desc = f"*{r['descripcion']}*\n" if r.get("descripcion") else ""
                val = f"{desc}**Produce:** {r['resultado_emoji']} {r['resultado_nombre']} x{r['resultado_cantidad']}\n**Ingredientes:**\n{ings_txt}"
                embed.add_field(
                    name=f"🔨 {r['nombre']} (ID: `{r['receta_id']}`)", 
                    value=val, 
                    inline=False
                )

        embed.set_footer(text=f"Página {self.pagina_actual + 1} de {self.total_paginas} • Total de recetas: {len(self.recetas)}")
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.autor_id:
            await interaction.response.send_message("❌ Este menú de recetas fue abierto por otro usuario.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def btn_anterior(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.pagina_actual > 0:
            self.pagina_actual -= 1
            self._actualizar_botones()
            await interaction.response.edit_message(embed=self.generar_embed(), view=self)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def btn_siguiente(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.pagina_actual < self.total_paginas - 1:
            self.pagina_actual += 1
            self._actualizar_botones()
            await interaction.response.edit_message(embed=self.generar_embed(), view=self)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger)
    async def btn_cerrar(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        try:
            await interaction.message.delete()
        except Exception:
            await interaction.response.edit_message(content="*Libro de recetas cerrado.*", embed=None, view=None)
