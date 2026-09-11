import logging
from core.database import (
    obtener_receta, 
    obtener_inventario_personaje, 
    modificar_cantidad_inventario
)

async def verificar_y_craftear(tupper_tag: str, receta_id: str, cantidad_crafteo: int = 1) -> tuple[bool, str, dict | None]:
    """
    Verifica si el personaje tiene los ingredientes requeridos para craftear una receta.
    Si cumple los requisitos, descuenta los ingredientes y añade el ítem resultante.
    """
    if cantidad_crafteo <= 0:
        return False, "La cantidad a fabricar debe ser mayor a 0.", None

    receta = await obtener_receta(receta_id)
    if not receta:
        return False, f"La receta '{receta_id}' no existe en el sistema.", None

    ingredientes = receta.get("ingredientes", [])
    if not ingredientes:
        return False, "Esta receta no tiene ingredientes configurados.", None

    # Obtener inventario actual del personaje mapeado por item_id
    inventario_raw = await obtener_inventario_personaje(tupper_tag)
    inventario = {item["item_id"].lower(): item["cantidad"] for item in inventario_raw}

    # Verificar si faltan ingredientes
    faltantes = []
    for ing in ingredientes:
        iid = ing["item_id"].lower()
        requerido = ing["cantidad"] * cantidad_crafteo
        posee = inventario.get(iid, 0)
        if posee < requerido:
            faltantes.append(f"• {ing['emoji']} **{ing['nombre']}**: Tienes **{posee}** / Requieres **{requerido}**")

    if faltantes:
        detalle = "\n".join(faltantes)
        return False, f"❌ **Materiales insuficientes para fabricar x{cantidad_crafteo} de {receta['nombre']}:**\n{detalle}", None

    # Ejecutar deducción de ingredientes
    for ing in ingredientes:
        deducir = ing["cantidad"] * cantidad_crafteo
        await modificar_cantidad_inventario(tupper_tag, ing["item_id"], -deducir)

    # Añadir producto fabricado
    total_producido = receta["resultado_cantidad"] * cantidad_crafteo
    await modificar_cantidad_inventario(tupper_tag, receta["resultado_item_id"], total_producido)

    logging.info(f"[Crafteo] {tupper_tag} fabricó x{total_producido} de {receta['resultado_item_id']} usando receta {receta_id}")
    return True, f"¡Has fabricado con éxito **x{total_producido}** de {receta['resultado_emoji']} **{receta['resultado_nombre']}**!", receta
