"""
Fachada de acceso a datos. La lógica vive en `core/repos/` (un módulo por dominio);
este módulo re-exporta todos los nombres públicos para que los importadores
(`from core.database import ...`) no cambien.

`DB_FILE` sigue siendo una variable de módulo funcional: leerla o asignarla
(`core.database.DB_FILE = ...`) opera sobre la ruta global de `core.repos.base`,
que es la que `conectar()` lee en CADA conexión.
"""
import sys
import types

from core.repos import base as _base
from core.repos.base import (
    get_db_path,
    set_db_path,
    conectar,
    _cache_personajes,
    _cache_webhooks,
    _cache_guild_modo,
)
from core.repos.texto import normalizar_texto, limpiar_termino_busqueda
from core.repos.schema import inicializar_base, _limpiar_filas_huerfanas
from core.repos.personajes import (
    obtener_personaje,
    guardar_personaje,
    actualizar_personaje,
    vincular_owner_personaje,
    obtener_personajes_por_owner,
    obtener_personajes_activos,
    obtener_personajes_vinculados_con_owner,
    obtener_personajes_reserva,
    activar_personaje,
    desactivar_personaje,
    buscar_personaje_por_nombre_db,
    listar_todos_personajes,
    auto_vincular_o_crear_personaje,
    importar_tuppers_batch,
)
from core.repos.guild_config import (
    obtener_limite_personajes,
    establecer_limite_personajes,
    guardar_tupperbox_webhook,
    obtener_tupperbox_webhook,
    set_modo_captura,
    get_modo_captura,
)
from core.repos.catalogo import (
    crear_o_actualizar_item,
    editar_item_catalogo,
    actualizar_script_item,
    asignar_script_item,
    crear_o_actualizar_script,
    obtener_script,
    listar_scripts,
    eliminar_script,
    obtener_item,
    listar_items_catalogo,
    eliminar_item_catalogo,
)
from core.repos.inventario import (
    obtener_inventario_personaje,
    obtener_cantidad_item,
    modificar_cantidad_inventario,
    transferir_item_atomico,
)
from core.repos.recetas import (
    crear_receta,
    obtener_receta,
    listar_recetas,
    eliminar_receta,
)


class _FachadaModulo(types.ModuleType):
    """Mantiene `DB_FILE` sincronizado con `core.repos.base.DB_FILE` en lectura y escritura."""

    @property
    def DB_FILE(self):
        return _base.DB_FILE

    @DB_FILE.setter
    def DB_FILE(self, valor):
        _base.DB_FILE = valor


sys.modules[__name__].__class__ = _FachadaModulo
