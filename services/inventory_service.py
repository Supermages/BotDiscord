import discord
from core.config import Config
from core.database import (
    obtener_personaje,
    obtener_inventario_personaje,
    modificar_cantidad_inventario,
    transferir_item_atomico,
    obtener_item,
    vincular_owner_personaje
)

def es_admin(user: discord.Member | discord.User) -> bool:
    """Comprueba si el usuario tiene el rol administrativo configurado."""
    if isinstance(user, discord.Member):
        return any(r.name == Config.ROL_ADMIN for r in user.roles)
    return False

def puede_gestionar_personaje(user: discord.Member | discord.User, personaje_info: tuple | dict) -> tuple[bool, str]:
    """
    Valida si el usuario tiene permiso para gestionar el personaje.
    Un personaje puede gestionarse si:
    1. El usuario tiene el rol Bot Admin.
    2. El personaje no tiene dueño (en cuyo caso se le ofrece vincularlo).
    3. El usuario es el dueño registrado (owner_id coincide).
    """
    if es_admin(user):
        return True, "admin"

    # tuple: (nombre, lado, avatar_url, color, color_texto, owner_id)
    # o tuple de buscar_personaje_por_nombre_db: (tupper_tag, nombre, lado, avatar_url, color, color_texto, owner_id)
    owner_id = None
    if isinstance(personaje_info, dict):
        owner_id = personaje_info.get("owner_id")
    elif isinstance(personaje_info, (tuple, list)):
        owner_id = personaje_info[-1] # siempre es el último campo

    if not owner_id:
        return False, "sin_dueño"

    if str(owner_id) == str(user.id):
        return True, "dueño"

    return False, "no_es_dueño"

async def consumir_item(tupper_tag: str, item_id: str, cantidad: int = 1) -> tuple[bool, str, dict | None]:
    """
    Consume un ítem usable del inventario de un personaje y retorna el mensaje de efecto.
    """
    if cantidad <= 0:
        return False, "La cantidad debe ser mayor a 0.", None

    item = await obtener_item(item_id)
    if not item:
        return False, f"El ítem '{item_id}' no existe en el catálogo.", None

    if not item.get("es_usable"):
        return False, f"El ítem **{item['nombre']}** no es un objeto consumible.", None

    # Comprobar si el personaje tiene suficiente
    inventario = await obtener_inventario_personaje(tupper_tag)
    disponible = 0
    for it in inventario:
        if it["item_id"].lower() == item_id.lower():
            disponible = it["cantidad"]
            break

    if disponible < cantidad:
        return False, f"Stock insuficiente. Solo tienes x{disponible} de **{item['nombre']}**.", None

    # Descontar del inventario
    await modificar_cantidad_inventario(tupper_tag, item_id, -cantidad)
    msg_uso = item.get("mensaje_uso") or f"Has utilizado x{cantidad} de {item['nombre']}."
    return True, msg_uso, item
