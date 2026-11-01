from core.repos.base import conectar, _cache_webhooks, _cache_guild_modo

# ==========================================
# CONFIGURACIÓN DEL SERVIDOR Y WEBHOOKS
# ==========================================

async def obtener_limite_personajes(guild_id: str = None) -> int:
    """Obtiene el límite de personajes activos configurado para el servidor (por defecto 3)."""
    if not guild_id:
        return 3
    async with conectar() as db:
        async with db.execute('SELECT limite_personajes FROM Guild_Config WHERE guild_id = ?', (str(guild_id),)) as cursor:
            row = await cursor.fetchone()
            if row and row[0] is not None:
                return int(row[0])
    return 3

async def establecer_limite_personajes(guild_id: str, limite: int):
    """Establece el límite de personajes activos por usuario para el servidor."""
    async with conectar() as db:
        await db.execute('''
            INSERT INTO Guild_Config (guild_id, limite_personajes)
            VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET limite_personajes = excluded.limite_personajes
        ''', (str(guild_id), limite))
        await db.commit()
async def guardar_tupperbox_webhook(guild_id, webhook_id):
    g_id = str(guild_id)
    w_id = str(webhook_id)
    async with conectar() as db:
        await db.execute('''
            INSERT OR REPLACE INTO Tupperbox_Webhooks (guild_id, webhook_id)
            VALUES (?, ?)
        ''', (g_id, w_id))
        await db.commit()
    _cache_webhooks[g_id] = w_id

async def obtener_tupperbox_webhook(guild_id):
    g_id = str(guild_id)
    if g_id in _cache_webhooks:
        return (_cache_webhooks[g_id],)

    async with conectar() as db:
        async with db.execute('SELECT webhook_id FROM Tupperbox_Webhooks WHERE guild_id = ?', (g_id,)) as cursor:
            resultado = await cursor.fetchone()
            if resultado:
                _cache_webhooks[g_id] = resultado[0]
            return resultado

async def set_modo_captura(guild_id, modo):
    g_id = str(guild_id)
    async with conectar() as db:
        await db.execute('''
            INSERT OR REPLACE INTO Guild_Config (guild_id, modo_captura)
            VALUES (?, ?)
        ''', (g_id, modo))
        await db.commit()
    _cache_guild_modo[g_id] = modo

async def get_modo_captura(guild_id):
    g_id = str(guild_id)
    if g_id in _cache_guild_modo:
        return _cache_guild_modo[g_id]

    async with conectar() as db:
        async with db.execute('SELECT modo_captura FROM Guild_Config WHERE guild_id = ?', (g_id,)) as cursor:
            resultado = await cursor.fetchone()
            modo = resultado[0] if resultado else 'TUPPER'
            _cache_guild_modo[g_id] = modo
            return modo