# 🛡️ Matriz de Permisos, Comandos y Seguridad - EriduBot

Este documento detalla exhaustivamente qué comandos pueden utilizar los jugadores normales sin necesidad de privilegios especiales y cuáles están estrictamente restringidos al rol administrativo (`Config.ROL_ADMIN`, por defecto: **`Bot Admin`**), así como las capas de seguridad y aislamiento implementadas.

---

## 🔒 Arquitectura de Seguridad y Protecciones Activas

1. **Aislamiento Estricto de Propiedad (Ownership Isolation)**:
   - Los jugadores **únicamente** pueden interactuar, activar, transferir o editar personajes que hayan sido creados por ellos (`creator_id = user_id`) o que tengan asignados en activo (`owner_id = user_id`).
   - El sistema impide que un usuario active personajes huérfanos o de otros jugadores en su reserva.
   - En `/inv transferir`, `/inv usar` y `/inv tirar`, el sistema valida a nivel de base de datos que el personaje emisor pertenezca al usuario que invoca la interacción.

2. **Inviolabilidad del ID Interno (`tupper_tag`)**:
   - En el comando público `/pj editar`, el identificador interno del personaje es **inmutable**. Un jugador puede cambiar su nombre visual, avatar, colores y lado de chat, pero **nunca** el ID, garantizando que no se puedan secuestrar inventarios o romper recetas.

3. **Prevención de Inyecciones SQL**:
   - Todas las consultas a la base de datos SQLite utilizan sentencias preparadas parametrizadas (`?`). No existe concatenación de cadenas en ninguna consulta SQL del proyecto.

4. **Entorno Aislado para Scripts Lua (Sandbox)**:
   - El motor de scripts de ítems (`services/lua_service.py`) corre en un entorno cerrado sin acceso a librerías del sistema operativo (`os`, `io`, `package`, `dofile`, `loadfile`, llamadas a red o acceso al disco).

5. **Protección contra Denegación de Servicio (DoS)**:
   - El motor de dados (`/roll` y `/dado`) impone límites estrictos: máximo 50 dados por tirada y un máximo de 1000 caras por dado.
   - El comando `/chat spam_ping` está protegido por rol administrativo y cuenta con un intervalo forzado de 1.5s entre mensajes.

---

## 👥 1. Comandos Públicos (Para Jugadores / Sin Rol Admin)

Cualquier miembro del servidor puede utilizar estos comandos para gestionar sus propios personajes, jugar y consultar información.

### 🎭 Gestión de Personajes (`/pj`)

| Comando | Parámetros | Descripción | Reglas de Seguridad / Validación |
| :--- | :--- | :--- | :--- |
| `/pj panel` | Ninguno | Abre el panel interactivo con menús desplegables para gestionar personajes activos y reserva. | Solo muestra y permite activar/desactivar personajes que pertenezcan al usuario. |
| `/pj vincular` | `personaje` | Activa un personaje de tu reserva pasándolo a uno de tus 3 cupos activos. | Solo permite activar personajes creados por el propio usuario (`creator_id = user_id`). |
| `/pj desvincular`| `personaje` | Mueve uno de tus personajes activos de vuelta a tu reserva sin perder ítems. | Solo permite desvincular personajes que tengas en uso. |
| `/pj editar` | `personaje`, `[nombre]`, `[avatar]`, `[lado]`, `[color_fondo]`, `[color_texto]` | Abre el editor visual interactivo o actualiza propiedades directamente. | **Validación estricta**: Los jugadores normales **solo** pueden editar personajes propios. El ID interno (`tupper_tag`) no se puede modificar. |
| `/pj lista` | Ninguno | Muestra tu lista de personajes activos actuales y el total de personajes en reserva. | Información privada de tu cuenta. |
| `/pj info` | `personaje` | Muestra la ficha pública de un personaje (nombre, creador, estado activo/reserva). | Consulta pública. |
| `/pj guia` | Ninguno | Muestra una guía paso a paso para aprender a vincular y usar personajes. | Información pública. |

---

### 🎒 Inventario y Objetos (`/inv`)

| Comando | Parámetros | Descripción | Reglas de Seguridad / Validación |
| :--- | :--- | :--- | :--- |
| `/inv ver` | `[personaje]`, `[filtro]` | Consulta la hoja de inventario y cofre de un personaje activo. | Si no se indica personaje, autodetecta el personaje activo principal del usuario. |
| `/inv catalogo` | `[categoria]` | Explora el catálogo de ítems existentes en el servidor. | Consulta de lectura (solo muestra ítems ya registrados por los admins). |
| `/inv usar` | `item`, `[personaje]`, `[cantidad]` | Consume un ítem del inventario y ejecuta su script o efecto. | Solo el dueño del personaje activo puede consumir sus ítems. |
| `/inv transferir`| `de_personaje`, `a_personaje`, `item`, `[cantidad]` | Transfiere materiales o ítems de un personaje a otro. | **Seguridad**: Solo puedes transferir desde un personaje que te pertenezca. Requiere confirmación interactiva mediante botón con timeout. |
| `/inv tirar` | `personaje`, `item`, `[cantidad]` | Descarta o destruye ítems del inventario de tu personaje. | Requiere confirmación mediante botón y solo permite tirar ítems de personajes propios. |

---

### 🔨 Crafteo y Fabricación (`/craft`)

| Comando | Parámetros | Descripción | Reglas de Seguridad / Validación |
| :--- | :--- | :--- | :--- |
| `/craft recetas` | `[categoria]` | Muestra la lista de fórmulas y recetas disponibles en el servidor. | Consulta pública de solo lectura. |
| `/craft detalle` | `receta` | Muestra los ingredientes requeridos y el resultado de una fórmula específica. | Consulta pública de solo lectura. |
| `/craft fabricar`| `receta`, `[personaje]`, `[cantidad]` | Fabrica un objeto consumiendo los materiales requeridos del personaje. | Valida que el personaje pertenezca al usuario, comprueba existencias de materiales y aplica la deducción/entrega atómica en SQLite. |

---

### 🎲 Tiradas de Dados (`/roll` y `/dado`)

| Comando | Parámetros | Descripción | Reglas de Seguridad / Validación |
| :--- | :--- | :--- | :--- |
| `/roll` / `/dado` | `[tirada]`, `[modo]`, `[motivo]`, `[personaje]`, `[secreto]` | Lanza dados al estilo D&D (ej: `1d20+3`, `2d6`), con soporte de Ventaja/Desventaja y detección de Nat 20/Nat 1. | **Público total**: Los jugadores pueden tirar a su nombre o al de su personaje activo. Si se marca `secreto: True`, la respuesta es efímera (solo visible para el jugador). |

---

## 🛡️ 2. Comandos Administrativos (Requieren Rol `Bot Admin`)

Estos comandos están protegidos por el decorador `@requiere_admin()` o comprobaciones directas. Si un usuario sin el rol correspondiente intenta ejecutarlos, el bot rechaza la acción con un mensaje de *"❌ Permiso denegado"*.

### ⚙️ Administración de RPG y Economía (`/admin_rpg`)

| Comando | Parámetros | Propósito |
| :--- | :--- | :--- |
| `/admin_rpg item_crear` | `item_id`, `nombre`, `[emoji]`, `[descripcion]`, `[categoria]`, `[raro]`, `[consumible]`, `[script_id]`, `[script_codigo]` | Crea un nuevo ítem en el catálogo global del servidor. |
| `/admin_rpg item_editar` | `item`, `[nombre]`, `[emoji]`, `[descripcion]`, `[categoria]`, `[raro]`, `[consumible]`, `[script_id]` | Modifica las propiedades de un ítem existente. |
| `/admin_rpg item_eliminar` | `item` | Elimina un ítem del catálogo y de todos los inventarios. |
| `/admin_rpg inv_dar` | `personaje`, `item`, `cantidad` | Otorga ítems directamente al inventario de cualquier personaje. |
| `/admin_rpg inv_quitar` | `personaje`, `item`, `cantidad` | Retira ítems del inventario de cualquier personaje. |
| `/admin_rpg receta_crear` | `receta_id`, `nombre`, `resultado_item`, `resultado_cant`, `ingredientes`, `[categoria]` | Registra una nueva receta de crafteo en el servidor. |
| `/admin_rpg receta_eliminar`| `receta` | Elimina una receta del catálogo de fabricación. |
| `/admin_rpg pj_vincular_forzoso` | `personaje`, `usuario` | Asigna forzosamente un personaje a un usuario de Discord como activo. |
| `/admin_rpg limite_personajes` | `limite` | Configura el cupo máximo de personajes activos por usuario en el servidor (por defecto: 3). |
| `/admin_rpg tuppers_importar` | `archivo_json` | Importa de forma masiva personajes desde una copia de seguridad de Tupperbox. |
| `/admin_rpg script_crear` | `script_id`, `nombre`, `[descripcion]` | Crea un script Lua compartido en la biblioteca global. |
| `/admin_rpg script_editar` | `script` | Abre un editor de código modal para modificar un script Lua existente. |
| `/admin_rpg script_asignar`| `item`, `script` | Asocia o desasocia un script compartido a un ítem del catálogo. |
| `/admin_rpg script_listar` | Ninguno | Lista todos los scripts compartidos registrados en el sistema. |
| `/admin_rpg script_ver` | `script` | Muestra el código fuente Lua de un script compartido. |
| `/admin_rpg script_borrar` | `script` | Elimina un script compartido de la biblioteca. |
| `/admin_rpg script_probar` | `item`, `personaje`, `[cantidad]` | Simula la ejecución de un script Lua en un entorno seguro sin alterar el inventario real. |
| `/admin_rpg recargar` | `[modulo]`, `[sincronizar_arbol]` | Recarga en caliente módulos de código o Cogs sin reiniciar el bot. |

---

### 📸 Captura y Monitoreo de Chat (`/chat`)

| Comando | Parámetros | Propósito |
| :--- | :--- | :--- |
| `/chat generar` | `[cantidad]`, `[title]`, `[duracion]` | Captura los mensajes del canal y genera imágenes segmentadas con Playwright Chromium. |
| `/chat actualizar` | `message_id` | Fuerza una actualización manual de una captura existente en el canal. |
| `/chat monitores` | Ninguno | Lista todos los canales del servidor que tienen monitores automáticos activos. |
| `/chat detener` | Ninguno | Cancela el monitor de auto-actualización del canal actual. |
| `/chat configuracion`| `modo` | Alterna entre capturar únicamente mensajes de Tupperbox (`TUPPER`) o todo el chat (`TODO`). |
| `/chat spam_ping` | `usuario`, `cantidad` | Comando protegido para enviar menciones consecutivas con intervalo seguro. |

---

### 💻 Comandos con Prefijo de Consola (Solo Administradores)

| Comando | Sintaxis | Propósito |
| :--- | :--- | :--- |
| `!reload` | `!reload [modulo]` | Recarga en caliente una extensión o todas las extensiones activas. |
| `!sync` | `!sync [este/global]` | Fuerza la sincronización del árbol de comandos Slash con Discord. |
