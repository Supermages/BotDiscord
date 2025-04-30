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
            )
        ''')
        conn.commit()

def obtener_personaje(personaje_id):
    with sqlite3.connect(DB_FILE) as conn:
        cur = conn.cursor()
        cur.execute('SELECT nombre, lado, avatar_url FROM Personaje_Tabla WHERE personaje_id = ?', (personaje_id,))
        return cur.fetchone()

def guardar_personaje(personaje_id, nombre, lado, avatar_url):
    with sqlite3.connect(DB_FILE) as conn:
        cur = conn.cursor()
        cur.execute('''
            INSERT OR REPLACE INTO Personaje_Tabla (personaje_id, nombre, lado, avatar_url)
            VALUES (?, ?, ?, ?)
        ''', (personaje_id, nombre, lado, avatar_url))
        conn.commit()

def actualizar_personaje(personaje_id, lado=None, color=None, color_texto=None):
    with sqlite3.connect(DB_FILE) as conn:
        cur = conn.cursor()
        if lado:
            cur.execute('UPDATE Personaje_Tabla SET lado = ? WHERE personaje_id = ?', (lado, personaje_id))
        if color:
            cur.execute('UPDATE Personaje_Tabla SET color_background = ? WHERE personaje_id = ?', (color, personaje_id))
        if color_texto:
            cur.execute('UPDATE Personaje_Tabla SET color_text = ? WHERE personaje_id = ?', (color_texto, personaje_id))
        conn.commit()
