# 🤖 EriduBot - Bot de Rol, Renderizador Visual y Sistema RPG para Discord

**EriduBot** es un bot integral y modular para Discord diseñado para comunidades de rol y servidores interactivos. Integra un motor de renderizado de conversaciones en imágenes visuales de alta fidelidad, un sistema completo de inventarios, economía y crafteo al estilo MythOS, un sistema de tiradas de dados D&D 5e con ventaja/desventaja y críticos, soporte nativo para **Tupperbox**, y una arquitectura optimizada para alta concurrencia.

---

## 🌟 Características Principales

### 📸 1. Renderizado Visual y Captura de Chats
* **Motor Playwright (Chromium Headless)** con escala de dispositivo `2x` para capturas nítidas y sin fondo.
* **Evaluación Atómica por Lotes (Batch IPC)**: Inyección instantánea de mensajes en Chromium en una sola llamada, reduciendo el tiempo de renderizado a ~1.2s en chats extensos.
* **Segmentación Adaptativa**: Algoritmo inteligente que pondera texto largo y adjuntos para dividir conversaciones en imágenes secuenciales legibles.
* **Monitoreo en Tiempo Real**: `/chat generar` con parámetro de duración para vigilar un canal y actualizar automáticamente las imágenes a medida que los personajes rolean.
* **Modos de Captura**: Modo Tupperbox (`TUPPER`) con deducción de autoría en memoria (`TupperMatchEngine`) y modo general (`TODO`).
* **Render Seguro**: El contenido de los mensajes se escapa antes de renderizar, evitando inyección de HTML en las imágenes generadas.

### 🎒 2. Sistema de Inventario y Crafteo (Estilo MythOS)
* **Inventario Interactivo (`/inv ver`)**: Panel con paginación interactiva (`◀`, `▶`), visualización de cantidad, categoría y emojis de ítems.
* **Transferencias Seguras (`/inv transferir`)**: Traspaso atómico de objetos entre personajes con confirmación interactiva en dos pasos.
* **Consumo de Ítems (`/inv usar`)**: Uso de consumibles con control de stock y soporte para scripts de efecto en Lua (sandbox aislado con presupuesto de ~10M instrucciones y timeout de ~15 s: un script malicioso o con bucles no puede colgar el bot).
* **Fórmulas y Crafteo (`/craft`)**: Libro de recetas paginado (`/craft recetas`) y fabricación con deducción automática de materiales (`/craft fabricar`).

### 🎲 3. Sistema de Dados D&D 5e (`/roll` y `/dado`)
* **Expresiones Complejas**: Soporta dados simples (`1d20`), con modificadores (`1d20+5`, `1d20-2`) y fórmulas compuestas (`2d6 + 1d4 + 3`).
* **Ventaja y Desventaja**: Lanza automáticamente dos dados, calcula el mayor o menor y muestra el dado descartado tachado.
* **Críticos y Pifias**: Detección automática de **Nat 20** (Éxito Crítico) con banner dorado y **Nat 1** (Pifia) con banner rojo.
* **Identidad de Personaje**: Parámetro opcional para lanzar dados a nombre de un personaje activo, adoptando su avatar y color personalizado.

### 🎭 4. Gestión de Personajes y Tupperbox (`/pj`)
* **Panel Visual (`/pj panel`)**: Activación y desactivación de personajes mediante menús desplegables para gestionar cupos de rol (por defecto 3 por jugador, configurable por servidor).
* **Editor Interactivo (`/pj editar`)**: Ventanas modales para personalizar nombre, avatar, lado de mensaje (izquierda/derecha) y colores en formato HEX (`#RRGGBB`).
* **Importación Masiva (`/pj importar`)**: Carga directa de copias de seguridad de Tupperbox (`tul!export.json`) a la reserva personal.

### ⚡ 5. Rendimiento, Robustez y Recarga en Caliente
* **SQLite Modo WAL**: `PRAGMA journal_mode=WAL` y `synchronous=NORMAL` para permitir múltiples lecturas simultáneas sin bloqueos de base de datos (`database is locked`).
* **Timeouts de UI Seguros**: Todas las vistas (`discord.ui.View`) implementan `on_timeout()` para deshabilitar botones y selects al expirar la sesión, evitando errores de interacción en Discord.
* **Hot Reload con Validación AST**: Monitor en segundo plano (`HotReloadManager`) que recarga módulos modificados sin reiniciar el bot, filtrando archivos con errores de sintaxis antes de ejecutarlos.
* **Integridad Referencial Garantizada**: Las FOREIGN KEYs se aplican en todas las conexiones SQLite: solo puede otorgarse con `/admin_rpg item_dar` un ítem existente en el catálogo, y borrar un ítem del catálogo elimina en cascada sus copias en inventarios.

---

## 📂 Estructura del Proyecto

```plaintext
BotDiscord/
├── bot.py                  # Punto de entrada y cargador de extensiones
├── requirements.txt        # Dependencias de Python del proyecto
├── Dockerfile              # Contenedor universal para despliegue
├── docker-compose.yml      # Orquestación de contenedor con volumen persistente
├── DEPLOYMENT.md           # Guía completa de despliegue en producción
├── PERMISOS_Y_SEGURIDAD.md # Matriz de permisos y políticas de seguridad
├── .env.example            # Plantilla de variables de entorno
│
├── core/
│   ├── config.py           # Configuración centralizada y rutas
│   ├── database.py         # Persistencia asíncrona SQLite con modo WAL y caché
│   ├── formatters.py       # Limpieza de Markdown y formateo de emojis a <img>
│   └── permissions.py      # Decorador @requiere_admin() para control de acceso
│
├── services/
│   ├── dice_service.py     # Motor de tiradas D&D 5e con ventaja y críticos
│   ├── inventory_service.py# Lógica de propiedad, stock y consumo de objetos
│   ├── crafting_service.py # Verificación y deducción atómica de crafteo
│   ├── tupper_service.py   # Detección de webhooks y motor TupperMatchEngine
│   ├── chat_sync_service.py# Procesamiento de adjuntos y sincronización de mensajes
│   ├── image_service.py    # Segmentación inteligente por peso visual
│   ├── monitor_service.py  # Gestor de tareas asyncio de monitores en vivo
│   ├── hot_reload_service.py# Recarga en caliente con validación sintáctica AST
│   └── lua_service.py      # Sandbox para ejecución de scripts de ítems
│
├── cogs/
│   ├── character_commands.py # Comandos /pj (panel, lista, editar, importar, vincular)
│   ├── chat_commands.py      # Comandos /chat (generar, forzar, monitores, config, spam_ping)
│   ├── crafting_commands.py  # Comandos /craft (recetas, fabricar)
│   ├── dice_commands.py      # Comandos /roll y /dado
│   ├── inventory_commands.py # Comandos /inv (ver, transferir, usar)
│   └── admin_rpg_commands.py # Comandos /admin_rpg (gestión de catálogo y recetas)
│
├── renderer/
│   ├── captura.py          # Singleton de BrowserRenderer (Playwright Chromium)
│   ├── index.html          # Plantilla visual de mensajes
│   ├── mensajes.js         # Constructor JavaScript de burbujas de chat
│   ├── styles.css          # Estilos CSS de burbujas, avatares y contenedores
│   └── fuentes/            # Tipografías integradas
│
├── ui/
│   ├── views.py            # Vistas LadoView y EditPersonajeView con modales
│   ├── character_views.py  # CharacterPanelView con selects interactivos
│   └── inventory_views.py  # InventoryView, TransferConfirmView y RecipesView
│
├── tests/
│   ├── run_all.py          # Ejecutor maestro de la suite de pruebas
│   ├── test_core.py        # Pruebas de configuración, formatters, permisos y DB
│   ├── test_services.py    # Pruebas de dados, inventario, crafteo y Tupperbox
│   ├── test_cogs_integrity.py # Pruebas de comandos, Cogs y seguridad
│   └── test_optimizations.py # Pruebas de modo WAL, concurrencia y renderizado
│
└── data/
    ├── eridubot.sqlite     # Base de datos SQLite
    └── exportaciones/      # Carpeta de capturas generadas y temporales
```

> **Nota sobre rutas de datos**: Todo el estado del bot vive en `data/` (`data/eridubot.sqlite`, `data/exportaciones/`). Si ves un `database.db` o una carpeta `exportaciones/` sueltos en la raíz del repo, son restos históricos en retirada; no se usan.

---

## 🛠️ Tecnologías y Librerías

- **Lenguaje**: [Python 3.11+](https://www.python.org/)
- **Biblioteca de Discord**: [discord.py](https://discordpy.readthedocs.io/) (v2.3+) con soporte completo para `app_commands` (Slash Commands) y Discord UI Components.
- **Motor de Renderizado**: [Playwright para Python](https://playwright.dev/python/) con Chromium Headless.
- **Base de Datos**: [aiosqlite](https://github.com/omnilib/aiosqlite) con SQLite en modo WAL y foreign keys activas.
- **Entorno y Variables**: [python-dotenv](https://github.com/theskumar/python-dotenv).
- **Scripts de Ítems**: [lupa](https://github.com/scoder/lupa) (Lua Sandbox).
- **Frontend del Renderizador**: HTML5, CSS3 moderno y JavaScript Vanilla ES6.

---

## 🚀 Instalación y Puesta en Marcha

### 1. Prerrequisitos
- Python 3.11 o superior instalado.
- Git instalado.

### 2. Clonar el Repositorio
```bash
git clone https://github.com/tu-usuario/BotDiscord.git
cd BotDiscord
```

### 3. Crear y Activar un Entorno Virtual
En Windows (PowerShell):
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

En Linux/macOS:
```bash
python3 -m venv venv
source venv/bin/activate
```

### 4. Instalar Dependencias de Python
```bash
pip install -r requirements.txt
```

### 5. Instalar los Binarios de Chromium para Playwright
```bash
playwright install chromium
```

### 6. Configurar las Variables de Entorno
Copia el archivo `.env.example` a `.env`:
```bash
copy .env.example .env   # En Windows
cp .env.example .env     # En Linux/macOS
```

Edita el archivo `.env` e introduce tu `DISCORD_TOKEN`.

### 7. Iniciar el Bot
```bash
python bot.py
```
Al iniciar, el bot inicializará la base de datos SQLite en modo WAL, arrancará la instancia compartida de Chromium y sincronizará los comandos Slash con Discord.

---

## 🧪 Ejecución de la Suite de Pruebas

El proyecto cuenta con una suite completa de **33 pruebas de regresión** que validan el comportamiento de todas las capas:

```bash
# Ejecutor maestro con reporte formateado
python tests/run_all.py

# O mediante el descubridor estándar de Python
python -m unittest discover tests
```

---

## 🛠️ Desarrollo y Depuración

### Comandos ocultos de administración (prefijo `!`)
Además de los Slash Commands, el bot expone dos comandos con prefijo reservados a administradores (mismo criterio de permisos que `/admin_rpg`):

| Comando | Descripción |
| :--- | :--- |
| `!reload` | Recarga en caliente de extensiones: `!reload todos` recarga todos los cogs, `!reload <modulo>` recarga solo uno. Útil para aplicar cambios de código sin reiniciar el proceso. |
| `!sync [este]` | Sincroniza el árbol de comandos Slash con Discord. Con el argumento `este`, sincroniza solo el servidor actual (más rápido en desarrollo). |

### Logs y diagnóstico
* **Consola**: Todos los eventos se registran en la consola con timestamps (arranque de cogs, errores, recargas, sincronizaciones).
* **Endpoint `/health`**: `GET /health` (requiere `PORT` definida) devuelve estado del bot, identidad y cogs cargados con código 200.

### Recarga automática de archivos
Con `AUTO_RELOAD=true` (desarrollo), el `HotReloadManager` vigila el sistema de archivos y recarga los módulos modificados con validación sintáctica AST previa. **Ojo**: si la variable `PORT` está definida (típico en hosting en la nube), `AUTO_RELOAD` pasa a `false` por defecto, para nunca activar hot-reload en producción.

---

## ⚙️ Variables de Entorno (`.env`)

| Variable | Tipo | Requerido | Descripción | Valor por Defecto |
| :--- | :--- | :---: | :--- | :--- |
| `DISCORD_TOKEN` | String | **Sí** | Token de bot generado en el Discord Developer Portal. | — |
| `ROL_ADMIN` | String | No | Nombre del rol de Discord con privilegios administrativos. | `"Bot Admin"` |
| `TUPPER_WEBHOOK_ID` | String / Int | No | ID estático del webhook de Tupperbox (autodetectable si se omite). | `""` |
| `DATABASE_PATH` | String | No | Ruta del archivo de base de datos SQLite. | `"data/eridubot.sqlite"` |
| `EXPORT_FOLDER` | String | No | Directorio donde se guardan JSONs e imágenes generadas. | `"data/exportaciones"` |
| `MAX_MENSAJES_TOTAL` | Integer | No | Límite máximo de mensajes al solicitar una captura de chat. | `50` |
| `MENSAJES_POR_IMAGEN` | Integer | No | Cantidad de mensajes por cada imagen segmentada. | `10` |
| `AUTO_RELOAD` | Boolean | No | Activa la recarga en caliente de archivos en desarrollo. | `true` |
| `SEARCH_LIMIT` | Integer | No | Límite de mensajes escaneados al regenerar una captura de chat. | `500` |
| `PORT` | Integer | No | Puerto del servidor de healthcheck web (`/health`); en nubes como Render o Koyeb lo inyecta el proveedor. Si está definida, `AUTO_RELOAD` pasa a `false` por defecto (ver nota). | — |

> **Interacción `AUTO_RELOAD` ↔ `PORT`**: el hot-reload está pensado solo para desarrollo. Si `PORT` está definida (señal de entorno de nube/producción), el bot desactiva `AUTO_RELOAD` salvo que la fuerces explícitamente a `true`.

---

## ⌨️ Guía Rápida de Comandos Slash

### 1. Inventario (`/inv`)
| Comando | Acceso | Descripción |
| :--- | :--- | :--- |
| `/inv ver [personaje]` | Público | Muestra el panel interactivo de inventario con paginación. |
| `/inv transferir` | Público | Transfiere objetos entre personajes de forma segura con confirmación. |
| `/inv usar <personaje> <item> [cantidad]` | Público | Consume un ítem del inventario y aplica sus efectos. |

### 2. Crafteo (`/craft`)
| Comando | Acceso | Descripción |
| :--- | :--- | :--- |
| `/craft recetas` | Público | Consulta el libro de fórmulas e ingredientes disponibles. |
| `/craft fabricar <personaje> <receta> [cantidad]` | Público | Fabrica objetos descontando ingredientes del inventario. |

### 3. Dados D&D (`/roll` y `/dado`)
| Comando | Acceso | Descripción |
| :--- | :--- | :--- |
| `/roll [tirada] [modo] [motivo] [personaje] [secreto]` | Público | Lanza dados con soporte para modificadores, ventaja/desventaja y críticos. |
| `/dado ...` | Público | Alias idéntico a `/roll`. |

### 4. Personajes (`/pj`)
| Comando | Acceso | Descripción |
| :--- | :--- | :--- |
| `/pj panel` | Público | Abre el panel visual para activar o desactivar personajes del cupo. |
| `/pj lista` | Público | Consulta tus personajes activos y en reserva. |
| `/pj editar <personaje>` | Público *(dueño)* | Modifica nombre, avatar, lado y colores HEX del personaje. |
| `/pj importar <archivo>` | Público | Importa masivamente personajes desde un archivo `tul!export.json`. |
| `/pj vincular <personaje>` | Público | Activa un personaje de tu reserva personal. |
| `/pj desvincular <personaje>` | Público | Pasa un personaje activo a reserva liberando espacio en tu cupo. |
| `/pj guia` | Público | Muestra la guía interactiva para vincular Tupperbox. |

### 5. Chat y Capturas (`/chat` - Requiere Rol Admin)
| Comando | Acceso | Descripción |
| :--- | :--- | :--- |
| `/chat generar <cantidad> <titulo> [duracion]` | Bot Admin | Genera la conversación en imágenes e inicia el monitor en vivo. |
| `/chat forzar` | Bot Admin | Actualiza manualmente la captura activa en el canal. |
| `/chat monitores` | Bot Admin | Lista los canales con auto-actualización activa. |
| `/chat detener` | Bot Admin | Cancela el monitor activo en el canal actual. |
| `/chat configuracion <modo>` | Bot Admin | Define el modo de captura (`TUPPER` / `TODO`). |
| `/chat spam_ping <usuario> <cantidad>` | Bot Admin | Envía menciones espaciadas de forma controlada. |

### 6. Administración RPG (`/admin_rpg` - Requiere Rol Admin)
| Comando | Acceso | Descripción |
| :--- | :--- | :--- |
| `/admin_rpg item_crear` | Bot Admin | Registra o modifica un ítem en el catálogo maestro. |
| `/admin_rpg item_dar` | Bot Admin | Otorga unidades de un ítem al inventario de un personaje (el ítem debe existir previamente en el catálogo; las claves foráneas lo garantizan). |
| `/admin_rpg item_quitar` | Bot Admin | Retira unidades de un ítem del inventario. |
| `/admin_rpg receta_crear` | Bot Admin | Crea o actualiza una fórmula de crafteo. |
| `/admin_rpg receta_borrar` | Bot Admin | Elimina una fórmula de crafteo del servidor. |
| `/admin_rpg vincular_admin` | Bot Admin | Reasigna la propiedad de un personaje a otro usuario. |
| `/admin_rpg limite_personajes` | Bot Admin | Establece el cupo máximo de personajes activos por usuario. |

---

## 🐳 Despliegue con Docker

El proyecto incluye soporte listo para producción con **Docker y Docker Compose**:

```bash
# Construir e iniciar en segundo plano
docker compose up -d --build

# Ver registros en tiempo real
docker compose logs -f

# Detener el contenedor
docker compose down
```

Para más detalles sobre despliegue en VPS u otros servidores, consulta [DEPLOYMENT.md](DEPLOYMENT.md).

---

## 🛡️ Matriz de Seguridad

Para una descripción detallada de qué comandos están abiertos al público, cuáles requieren el rol `Bot Admin` y cuáles son exclusivos de moderación, consulta [PERMISOS_Y_SEGURIDAD.md](PERMISOS_Y_SEGURIDAD.md).

Consideraciones adicionales:

* **Doble vía de acceso admin**: además del rol configurado en `ROL_ADMIN`, también se considera administrador a cualquier usuario con el permiso de Discord "Administrador" del servidor.
* **Denegaciones efímeras**: los usuarios sin permisos que intenten comandos protegidos reciben una respuesta efímera (solo visible para ellos); ya no se publica ningún embed de denegación en el canal.
