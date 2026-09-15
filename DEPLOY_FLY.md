# 🚀 Guía de Despliegue en Fly.io para EriduBot

Fly.io es la plataforma moderna ideal para bots de Discord: permite correr contenedores Docker completos con **almacenamiento persistente** para que tu base de datos SQLite nunca se borre, y utiliza constructores remotos en la nube (no necesitas tener Docker abierto en tu PC).

---

## 📋 Paso 1: Iniciar Sesión en Fly.io

Abre una ventana de **PowerShell** en tu ordenador y ejecuta:

```powershell
fly auth login
```
*(O si aún no tienes cuenta: `fly auth signup`).*

Se abrirá tu navegador web para iniciar sesión (puedes entrar con tu cuenta de GitHub o correo electrónico). Una vez completado, verás en tu terminal:
`Successfully logged in as tu_correo@...`

---

## ⚙️ Paso 2: Crear la Aplicación en Fly.io

Desde la carpeta del proyecto en PowerShell:

```powershell
cd "c:\Users\nicol\Desktop\Bot Discord\BotDiscord"
fly launch --no-deploy
```

- Si te pregunta si deseas copiar la configuración existente, dile que **Yes** (`Y`).
- Te pedirá un nombre para la aplicación (debe ser único a nivel global, ej: `eridubot-supermages` o similar).
- Selecciona la región más cercana a ti (ej: `mad` para Madrid, `ams` para Ámsterdam, etc.).

---

## 💾 Paso 3: Crear el Volumen de Disco Persistente (Para la Base de Datos SQLite)

Este paso garantiza que todos los personajes, ítems del catálogo y crafteos se guarden de forma permanente en un disco NVMe de Fly.io:

```powershell
fly volumes create eridu_data --size 1 --region mad
```
*(Sustituye `mad` por la región que elegiste si fue otra).*

---

## 🔑 Paso 4: Configurar los Secretos y el Token de Discord

Configura tu token de Discord de forma segura y encriptada (no se guarda en ningún archivo visible):

```powershell
fly secrets set DISCORD_TOKEN="tu_token_de_discord_aqui" ROL_ADMIN="Bot Admin"
```

---

## 🚀 Paso 5: Desplegar el Bot

Lanza el despliegue a la nube:

```powershell
fly deploy
```

Fly.io construirá la imagen en sus servidores remotos (instalando Chromium, Playwright y Python), montará el disco persistente y pondrá el bot online en Discord.

---

### 📊 Comandos de Control Útiles:

- **Ver el bot funcionando en vivo (Logs)**:
  ```powershell
  fly logs
  ```

- **Ver el estado de la máquina**:
  ```powershell
  fly status
  ```

- **Reiniciar el bot**:
  ```powershell
  fly apps restart
  ```

- **Actualizar cambios futuros**:
  Cada vez que hagas cambios en el código, simplemente ejecuta:
  ```powershell
  fly deploy
  ```
