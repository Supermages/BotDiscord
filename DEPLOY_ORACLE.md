# 🚀 Guía de Despliegue en Oracle Cloud Free Tier (Always Free)

Esta guía te muestra paso a paso cómo desplegar **EriduBot** en una máquina virtual gratuita de por vida en Oracle Cloud utilizando Docker y Docker Compose.

---

## 📋 Fase 1: Crear la Cuenta e Instancia en Oracle Cloud

1. **Registro**:
   - Entra a [https://www.oracle.com/cloud/free/](https://www.oracle.com/cloud/free/) y haz clic en **Start for free**.
   - Completa tus datos. En *Home Region*, elige la más cercana a ti (por ejemplo: `Spain Central (Madrid)` o `US East`).
   - Verifica tu tarjeta (Oracle cobra temporalmente ~1€ para verificar y lo reembolsa de inmediato).

2. **Crear la Instancia (Máquina Virtual)**:
   - En el panel principal de Oracle Cloud, ve al menú lateral izquierdo (☰) ➔ **Compute** ➔ **Instances** ➔ **Create Instance**.
   - **Name**: `eridubot-server` (o el que quieras).
   - **Image and shape**:
     - Haz clic en **Edit**.
     - **Image**: Elige **Ubuntu 24.04 LTS** (o 22.04 LTS).
     - **Shape**: Haz clic en **Change Shape** ➔ Elige **Ampere (ARM)**:
       - OCPU: `2` a `4` (Gratis hasta 4 OCPUs).
       - RAM: `8 GB` a `24 GB` (Gratis hasta 24 GB de RAM).
       *(Si por disponibilidad regional no hubiera capacidad en ARM, selecciona la forma AMD `VM.Standard.E2.1.Micro` con 1 GB de RAM).*
   - **Networking**: Deja la VCN por defecto con IP pública asignada (*Assign a public IPv4 address: Yes*).
   - **SSH Keys (Claves SSH - ¡Muy importante!)**:
     - Selecciona **Generate a key pair for me**.
     - Haz clic en **Save Private Key** (se descargará un archivo `.key` o `.pem`, por ejemplo `ssh-key-2026-xx-xx.key`). Guárdalo bien en tu PC.
   - Haz clic en **Create**.
   - Espera 1-2 minutos hasta que el estado pase de amarillo (*Provisioning*) a verde (*Running*).
   - Anota la **Public IP Address** que te asigna la máquina (ej: `129.151.xx.xx`).

---

## 💻 Fase 2: Conectar a la Máquina Virtual por SSH

Abre una terminal de **PowerShell** en tu ordenador Windows y navega hasta la carpeta donde descargaste tu clave `.key` (por ejemplo, en Descargas):

```powershell
cd $HOME\Downloads
```

Conéctate usando el usuario por defecto de Ubuntu (`ubuntu`) y la IP pública de tu instancia:

```powershell
ssh -i .\nombre_de_tu_clave.key ubuntu@TU_IP_PUBLICA
```
*(Si te pregunta `Are you sure you want to continue connecting (yes/no)?`, escribe `yes` y presiona Enter).*

---

## 🐳 Fase 3: Instalar Docker y Docker Compose en la Máquina

Una vez dentro de la terminal de tu servidor Ubuntu, ejecuta estos dos comandos para instalar Docker automáticamente:

```bash
# 1. Actualizar el sistema e instalar Docker oficial
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# 2. Dar permisos a tu usuario sin necesidad de usar 'sudo' siempre
sudo usermod -aG docker $USER
newgrp docker
```

Comprueba que Docker está funcionando:
```bash
docker --version
docker compose version
```

---

## 📥 Fase 4: Descargar y Configurar EriduBot

1. **Clonar tu repositorio**:
```bash
git clone https://github.com/TU_USUARIO/TU_REPOSITORIO.git eridubot
cd eridubot
```

2. **Crear el archivo de configuración `.env`**:
```bash
cp .env.example .env
nano .env
```
Edita tu token de Discord y el rol administrativo. Cuando termines, presiona `CTRL + O`, luego `Enter` para guardar, y `CTRL + X` para salir de `nano`.

3. **(Opcional) Transferir tu base de datos actual desde Windows**:
Si ya tienes personajes creados en local y quieres conservarlos, desde PowerShell en tu ordenador (fuera de la sesión SSH) puedes copiar tu archivo SQLite al servidor:
```powershell
scp -i .\nombre_de_tu_clave.key "c:\Users\nicol\Desktop\Bot Discord\BotDiscord\data\eridubot.sqlite" ubuntu@TU_IP_PUBLICA:/home/ubuntu/eridubot/data/eridubot.sqlite
```

---

## 🚀 Fase 5: Iniciar EriduBot en Segundo Plano

Dentro de la carpeta `/home/ubuntu/eridubot` en el servidor:

```bash
docker compose up -d --build
```

Esto construirá la imagen con Chromium, Playwright, Python y arrancará el bot.

### Comandos útiles en el servidor:

- **Ver logs en tiempo real**:
  ```bash
  docker compose logs -f
  ```
  *(Para salir del visor de logs presiona `CTRL + C`, el bot seguirá funcionando en segundo plano).*

- **Reiniciar el bot**:
  ```bash
  docker compose restart
  ```

- **Detener el bot**:
  ```bash
  docker compose down
  ```

- **Actualizar cambios futuros**:
  ```bash
  git pull
  docker compose up -d --build
  ```

¡Listo! El bot estará conectado 24/7 de forma 100% gratuita y perpetua en la nube.
