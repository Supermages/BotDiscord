
import sqlite3

DB_FILE = 'eridubot.sqlite'

def inicializar_base():
    with sqlite3.connect(DB_FILE) as conn:
        cur = conn.cursor()
        cur.execute('''
            CREATE TABLE IF NOT EXISTS Personaje_Tabla (
                personaje_id TEXT PRIMARY KEY,
                nombre TEXT NOT NULL,
                lado TEXT NOT NULL,
                avatar_url TEXT,
                color TEXT DEFAULT '#FFFFFF',
                color_texto TEXT DEFAULT '#000000'
            )
        ''')
        conn.commit()

def obtener_personaje(personaje_id):
    with sqlite3.connect(DB_FILE) as conn:
        cur = conn.cursor()
        cur.execute('SELECT nombre, lado, avatar_url, color, color_texto FROM Personaje_Tabla WHERE personaje_id = ?', (personaje_id,))
        return cur.fetchone()

def guardar_personaje(personaje_id, nombre, lado, avatar_url, color="#FFFFFF", color_texto="#000000"):
    with sqlite3.connect(DB_FILE) as conn:
        cur = conn.cursor()
        cur.execute('''
            INSERT OR REPLACE INTO Personaje_Tabla (personaje_id, nombre, lado, avatar_url, color, color_texto)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (personaje_id, nombre, lado, avatar_url, color, color_texto))
        conn.commit()

def actualizar_personaje(personaje_id, lado=None, color=None, color_texto=None):
    with sqlite3.connect(DB_FILE) as conn:
        cur = conn.cursor()
        if lado:
            cur.execute('UPDATE Personaje_Tabla SET lado = ? WHERE personaje_id = ?', (lado, personaje_id))
        if color:
            cur.execute('UPDATE Personaje_Tabla SET color = ? WHERE personaje_id = ?', (color, personaje_id))
        if color_texto:
            cur.execute('UPDATE Personaje_Tabla SET color_texto = ? WHERE personaje_id = ?', (color_texto, personaje_id))
        conn.commit()

def guardar_tupperbox_webhook(guild_id, webhook_id):
    with sqlite3.connect("eridubot.sqlite") as conn:
        cur = conn.cursor()
        cur.execute('''
            CREATE TABLE IF NOT EXISTS Tupperbox_Webhooks (
                guild_id TEXT PRIMARY KEY,
                webhook_id TEXT NOT NULL
            )
        ''')
        cur.execute('''
            INSERT OR REPLACE INTO Tupperbox_Webhooks (guild_id, webhook_id)
            VALUES (?, ?)
        ''', (str(guild_id), str(webhook_id)))
        conn.commit()

def obtener_tupperbox_webhook(guild_id):
    with sqlite3.connect("eridubot.sqlite") as conn:
        cur = conn.cursor()
        cur.execute('''
            SELECT webhook_id FROM Tupperbox_Webhooks WHERE guild_id = ?
        ''', (str(guild_id),))
        row = cur.fetchone()
        return int(row[0]) if row else None