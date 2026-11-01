class Chat {
    constructor(containerSelector = '.chat-container', color = 'blue', colorText = "white", imgSrc = 'https://cdn.discordapp.com/embed/avatars/0.png', derecha = true, user = 'default-user') {
        this.container = document.querySelector(containerSelector);
        this.color = color;
        this.colorText = colorText;
        this.imgSrc = imgSrc;
        this.derecha = derecha;
        this.user = user;

        // Valores sanitizados para el <style> dinámico (contexto CSS)
        const claseUsuario = this.claseSegura(this.user);
        const colorFondo = this.cssSeguro(this.color, 'transparent');
        const colorTexto = this.cssSeguro(this.colorText, 'inherit');

        // Estilos dinámicos para el personaje (color de fondo, color de texto y colita de bocadillo)
        const dynamicStyle = document.createElement('style');
        dynamicStyle.textContent = `
            .chat-bubble.${claseUsuario} {
                background-color: ${colorFondo};
                color: ${colorTexto};
            }
            .chat-bubble.${claseUsuario}::after {
                content: "";
                position: absolute;
                ${this.derecha ? 'right' : 'left'}: -4px;
                top: 8px;
                width: 10px;
                height: 10px;
                background-color: ${colorFondo};
                ${this.derecha ? 'clip-path: path("M 0 0 Q 0 5 10 3 Q 8 12 0 5 Z")' : 'clip-path: path("M 10 5 Q 2 12 0 3 Q 10 5 10 0 Z")'};
            }
        `;
        document.head.appendChild(dynamicStyle);
    }

    // ---------- Utilidades de seguridad (XSS / inyección) ----------

    // Escapa texto plano para usarlo como contenido o atributo HTML.
    escapeHtml(str) {
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    // Solo acepta caracteres válidos para nombres de clase (se usa en CSS y en atributos class).
    claseSegura(nombre) {
        return String(nombre || '').replace(/[^a-zA-Z0-9_-]/g, '');
    }

    // Solo acepta valores CSS simples: #hex, rgba()/rgb() o colores con nombre.
    cssSeguro(valor, fallback) {
        const str = String(valor || '').trim();
        return /^#(?:[0-9a-fA-F]{3,8})$|^rgba?\([^()]*\)$|^[a-zA-Z]+$/.test(str) ? str : fallback;
    }

    // Solo acepta URLs http(s); bloquea javascript:, data:, vbscript:, etc.
    urlSegura(url) {
        const str = String(url || '').trim();
        return /^https?:\/\//i.test(str) ? str : '';
    }

    // El texto llega ya convertido a HTML seguro desde Python (limpiar_formato_discord,
    // con el contenido de usuario escapado). Se aplica una sanitización mínima: solo
    // etiquetas de la whitelist, sin atributos on* y sin esquemas peligrosos en src/href.
    sanitizarHtmlPermitido(html) {
        const permitidas = ['img', 'div', 'br', 'b', 'i', 'u', 's', 'span', 'code'];
        const patronEtiqueta = /<(\/?)([a-zA-Z][a-zA-Z0-9]*)((?:"[^"]*"|'[^']*'|[^>"])*)>/g;

        return String(html).replace(patronEtiqueta, (completa, cierre, nombre, attrs) => {
            const nombreLower = nombre.toLowerCase();
            if (!permitidas.includes(nombreLower)) return '';

            let attrsLimpios = attrs
                // Fuera los atributos on* (onerror, onclick, ...)
                .replace(/\s+on[a-zA-Z]+\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)/gi, '')
                // Fuera los esquemas peligrosos en src/href
                .replace(/\s(src|href)\s*=\s*("[^"]*"|'[^']*'|[^\s>]+)/gi, (m, _attr, valorBruto) => {
                    const valor = valorBruto.replace(/^["']|["']$/g, '').trim();
                    return /^(javascript|vbscript|data):/i.test(valor) ? '' : m;
                });

            return `<${cierre}${nombreLower}${attrsLimpios}>`;
        });
    }

    // ---------- Render de mensajes ----------

    addMessage(text, attachments = []) {
        const messageElement = document.createElement('div');
        messageElement.classList.add('chat-box');

        let bubbleContent = "";

        // 1. Contenido de texto (ya transformado a HTML desde Python; se re-sanitiza
        //    contra etiquetas/atributos fuera de la whitelist antes de tocar el DOM)
        if (text && String(text).trim().length > 0) {
            const textFormatted = this.sanitizarHtmlPermitido(String(text)).replace(/\n/g, '<br>');
            bubbleContent += `<div class="message-text">${textFormatted}</div>`;
        }

        // 2. Adjuntos (imágenes, stickers, archivos)
        if (attachments && attachments.length > 0) {
            bubbleContent += `<div class="attachments-container">`;

            attachments.forEach(adj => {
                const urlCruda = adj.url || adj;
                const url = this.urlSegura(urlCruda);
                const tipo = adj.tipo || (String(urlCruda).match(/\.(jpeg|jpg|gif|png|webp)(\?.*)?$/i) ? 'imagen' : 'archivo');
                const nombre = this.escapeHtml(adj.filename || "Archivo adjunto");

                if (tipo === 'imagen' || tipo === 'sticker') {
                    if (!url) return;
                    const claseExtra = tipo === 'sticker' ? 'sticker-img' : 'chat-attachment-img';
                    bubbleContent += `<img class="${claseExtra}" src="${this.escapeHtml(url)}" alt="adjunto" onerror="this.style.display='none'">`;
                } else {
                    const href = this.escapeHtml(url || '#');
                    bubbleContent += `
                        <div class="file-card">
                            <div class="file-icon">📄</div>
                            <div class="file-info">
                                <span class="file-name">${nombre}</span>
                                <a href="${href}" target="_blank" rel="noopener noreferrer" class="file-link">Descargar</a>
                            </div>
                        </div>`;
                }
            });
            bubbleContent += `</div>`;
        }

        // Si el mensaje está completamente vacío, no añadir nada
        if (!bubbleContent) {
            return;
        }

        const hasText = Boolean(text && String(text).trim().length > 0);
        const hasAttachments = Boolean(attachments && attachments.length > 0);
        const isMediaOnly = !hasText && hasAttachments;
        const claseUsuario = this.claseSegura(this.user);
        const bubbleClasses = isMediaOnly ? `chat-bubble ${claseUsuario} media-only` : `chat-bubble ${claseUsuario}`;

        const fallbackImg = "https://cdn.discordapp.com/embed/avatars/0.png";
        const avatarSrc = this.escapeHtml(this.urlSegura(this.imgSrc) || fallbackImg);

        if (this.derecha) {
            messageElement.classList.add('blue');
            messageElement.innerHTML = `
                <div class="${bubbleClasses}">
                    ${bubbleContent}
                </div>
                <div class="img-container">
                    <img src="${avatarSrc}" alt="Avatar" onerror="this.onerror=null;this.src='${fallbackImg}';">
                </div>
            `;
        } else {
            messageElement.innerHTML = `
                <div class="img-container">
                    <img src="${avatarSrc}" alt="Avatar" onerror="this.onerror=null;this.src='${fallbackImg}';">
                </div>
                <div class="${bubbleClasses}">
                    ${bubbleContent}
                </div>
            `;
        }

        this.container.appendChild(messageElement);
    }
}

window.Chat = Chat;