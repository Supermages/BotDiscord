import discord
from core.config import Config
from core.database import (
    obtener_personaje,
    obtener_inventario_personaje,
    modificar_cantidad_inventario,
    transferir_item_atomico,
    obtener_item,
    vincular_owner_personaje,
    obtener_script
)

def es_admin(user: discord.Member | discord.User) -> bool:
    """Comprueba si el usuario tiene el rol administrativo configurado."""
    if isinstance(user, discord.Member):
        return any(r.name == Config.ROL_ADMIN for r in user.roles)
    return False

def puede_gestionar_personaje(user: discord.Member | discord.User, personaje_info: tuple | dict) -> tuple[bool, str]:
    """
    Valida si el usuario tiene permiso para gestionar el personaje en acciones de juego.
    Un personaje SOLO puede gestionarse si está activo (owner_id no es nulo):
    1. Si no tiene owner_id, está inactivo/en reserva (no accesible para jugar).
       - Si creator_id == user.id -> "en_reserva_propia".
       - Si no -> "sin_dueño".
    2. Si tiene owner_id y coincide con el usuario -> "dueño".
    3. Si tiene owner_id y el usuario es Bot Admin -> "admin" (override para moderación).
    4. Si tiene owner_id de otro usuario -> "no_es_dueño".
    """
    owner_id = None
    creator_id = None
    if isinstance(personaje_info, dict):
        owner_id = personaje_info.get("owner_id")
        creator_id = personaje_info.get("creator_id")
    elif isinstance(personaje_info, (tuple, list)):
        if len(personaje_info) >= 8:
            owner_id = personaje_info[6]
            creator_id = personaje_info[7]
        elif len(personaje_info) == 7:
            owner_id = personaje_info[6]
        elif len(personaje_info) == 6:
            owner_id = personaje_info[5]
        else:
            owner_id = personaje_info[-1]

    # Si el personaje no está activo (owner_id es nulo o vacío)
    if not owner_id:
        if creator_id and str(creator_id) == str(user.id):
            return False, "en_reserva_propia"
        return False, "sin_dueño"

    # Si está activo y coincide con el usuario
    if str(owner_id) == str(user.id):
        return True, "dueño"

    # Si está activo y el usuario es administrador
    if es_admin(user):
        return True, "admin"

    return False, "no_es_dueño"

from services.lua_service import lua_engine

async def consumir_item(tupper_tag: str, item_id: str, cantidad: int = 1, user_id: str = "") -> tuple[bool, str, dict | None, list[dict]]:
    """
    Consume un ítem usable del inventario de un personaje y retorna el mensaje de efecto.
    Si el ítem tiene un script Lua asignado, lo ejecuta. Si no, usa la lógica estándar.
    """
    if cantidad <= 0:
        return False, "La cantidad debe ser mayor a 0.", None, []

    item = await obtener_item(item_id)
    if not item:
        return False, f"El ítem '{item_id}' no existe en el catálogo.", None, []

    # Comprobar si el ítem es utilizable (marcado usable o con script asignado)
    es_usable = bool(item.get("es_usable")) or bool(item.get("script_id")) or bool(item.get("script_uso"))
    if not es_usable:
        return False, f"El ítem **{item['nombre']}** no es un objeto consumible ni tiene un script de uso.", None, []

    # 1. Comprobar stock en el inventario del personaje ANTES de cualquier acción o script
    inventario = await obtener_inventario_personaje(tupper_tag)
    disponible = 0
    for it in inventario:
        if (
            it["item_id"].lower() == item_id.lower() or 
            it["item_id"].lower() == item["item_id"].lower() or 
            it["nombre"].lower() == item["nombre"].lower()
        ):
            disponible = it["cantidad"]
            break

    if disponible < cantidad:
        return False, f"Stock insuficiente. No tienes suficientes unidades de **{item['nombre']}** (tienes x{disponible}, necesitas x{cantidad}).", None, []

    # 2. Determinar el script a ejecutar (específico o compartido)
    script_ejecutar = ""
    script_especifico = (item.get("script_uso") or "").strip()
    if script_especifico:
        script_ejecutar = script_especifico
    elif item.get("script_id"):
        shared = await obtener_script(item["script_id"])
        if shared and shared.get("codigo"):
            script_ejecutar = shared["codigo"].strip()

    if script_ejecutar:
        ok, msg, ids_mostrados = lua_engine.ejecutar_script(
            script=script_ejecutar,
            char_input=tupper_tag,
            item_input=item["item_id"],
            cantidad=cantidad,
            user_id=str(user_id)
        )
        if not ok:
            return False, msg, item, []

        # Cargar metadatos de los ítems llamados con display_item()
        items_mostrados_info = []
        for d_id in ids_mostrados:
            d_it = await obtener_item(d_id)
            if d_it:
                items_mostrados_info.append(d_it)

        msg_final = msg if msg else (item.get("mensaje_uso") or f"Has utilizado x{cantidad} de {item['nombre']}.")
        return True, msg_final, item, items_mostrados_info

    # 3. Lógica estándar sin script (descontar y mostrar mensaje)
    await modificar_cantidad_inventario(tupper_tag, item["item_id"], -cantidad)
    msg_uso = item.get("mensaje_uso") or f"Has utilizado x{cantidad} de {item['nombre']}."
    return True, msg_uso, item, []

