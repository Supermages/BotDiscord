import discord
from discord import app_commands
from core.config import Config


class PermisoDenegado(discord.app_commands.CheckFailure):
    """CheckFailure lanzada por requiere_admin cuando el usuario no tiene permisos.

    Lleva el atributo `mensaje` para que el gestor global de errores de bot.py
    pueda responder de forma efímera con un texto claro.
    """
    def __init__(self, mensaje: str = "No tienes el rol requerido para usar este comando."):
        self.mensaje = mensaje
        super().__init__(mensaje)


def es_admin(member: discord.Member | discord.User) -> bool:
    """Comprueba si el miembro tiene permisos administrativos.

    Pasa si:
      (a) tiene el permiso de Discord `administrator` o `manage_guild`, o
      (b) algún rol se llama exactamente igual que Config.ROL_ADMIN, o
      (c) Config.ROL_ADMIN es numérico y algún rol tiene ese ID.
    Los usuarios fuera de un servidor (DMs, interaction.user no Member) se deniegan.
    """
    if not isinstance(member, discord.Member):
        return False

    permisos = member.guild_permissions
    if permisos.administrator or permisos.manage_guild:
        return True

    rol_admin = (Config.ROL_ADMIN or "").strip()
    if not rol_admin:
        return False

    rol_admin_id = int(rol_admin) if rol_admin.isdigit() else None
    for role in member.roles:
        if role.name == rol_admin:
            return True
        if rol_admin_id is not None and role.id == rol_admin_id:
            return True
    return False


def requiere_admin():
    """Decorador de Discord app_commands que valida si el usuario tiene el rol administrativo requerido.

    Si no los tiene lanza PermisoDenegado; el gestor global on_tree_error de bot.py
    la convierte en una respuesta efímera al usuario. No envía nada al canal.
    """
    async def predicate(interaction: discord.Interaction):
        if not es_admin(interaction.user):
            raise PermisoDenegado("No tienes el rol requerido para usar este comando.")
        return True
    return app_commands.check(predicate)
