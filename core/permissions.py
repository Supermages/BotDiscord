import discord
from discord import app_commands
import asyncio
from core.config import Config

def requiere_admin():
    """Decorador de Discord app_commands que valida si el usuario tiene el rol administrativo requerido."""
    async def predicate(interaction: discord.Interaction):
        if not isinstance(interaction.user, discord.Member):
            return False
        if any(role.name == Config.ROL_ADMIN for role in interaction.user.roles):
            return True
        embed = discord.Embed(
            title="❌ Permiso denegado",
            description="No tienes el rol requerido para usar este comando.",
            color=0xFF0000
        )
        msg = await interaction.channel.send(embed=embed)
        await asyncio.sleep(5)
        try:
            await msg.delete()
        except discord.NotFound:
            pass
        return False
    return app_commands.check(predicate)
