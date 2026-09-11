class Chat {
    constructor(containerSelector = '.chat-container', color = 'blue', colorText = "white", imgSrc = 'https://cdn.discordapp.com/embed/avatars/0.png', derecha = true, user = 'default-user') {
        this.container = document.querySelector(containerSelector);
        this.color = color;
        this.colorText = colorText;
        this.imgSrc = imgSrc;
        this.derecha = derecha;
        this.user = user;

        // Estilos dinámicos para el personaje (color de fondo, color de texto y colita de bocadillo)
        const dynamicStyle = document.createElement('style');
        dynamicStyle.textContent = `
            .chat-bubble.${this.user} {
                background-color: ${this.color};
                color: ${this.colorText};
            }
            .chat-bubble.${this.user}::after {
                content: "";
                position: absolute;
                ${this.derecha ? 'right' : 'left'}: -4px;
                top: 8px;
                width: 10px;
                height: 10px;
                background-color: ${this.color};
                ${this.derecha ? 'clip-path: path("M 0 0 Q 0 5 10 3 Q 8 12 0 5 Z")' : 'clip-path: path("M 10 5 Q 2 12 0 3 Q 10 5 10 0 Z")'};
            }
        `;
        document.head.appendChild(dynamicStyle);
    }

    addMessage(text, attachments = []) {
        const messageElement = document.createElement('div');
        messageElement.classList.add('chat-box');

        let bubbleContent = "";

        // 1. Contenido de texto
        if (text && text.trim().length > 0) {
            const textFormatted = text.replace(/\n/g, '<br>');
            bubbleContent += `<div class="message-text">${textFormatted}</div>`;
        }

        // 2. Adjuntos (imágenes, stickers, archivos)
        if (attachments && attachments.length > 0) {
            bubbleContent += `<div class="attachments-container">`;

            attachments.forEach(adj => {
                const url = adj.url || adj;
                const tipo = adj.tipo || (url.match(/\.(jpeg|jpg|gif|png|webp)(\?.*)?$/i) ? 'imagen' : 'archivo');
                const nombre = adj.filename || "Archivo adjunto";

                if (tipo === 'imagen' || tipo === 'sticker') {
                    const claseExtra = tipo === 'sticker' ? 'sticker-img' : 'chat-attachment-img';
                    bubbleContent += `<img class="${claseExtra}" src="${url}" alt="adjunto" onerror="this.style.display='none'">`;
                } else {
                    bubbleContent += `
                        <div class="file-card">
                            <div class="file-icon">📄</div>
                            <div class="file-info">
                                <span class="file-name">${nombre}</span>
                                <a href="${url}" target="_blank" class="file-link">Descargar</a>
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

        const hasText = Boolean(text && text.trim().length > 0);
        const hasAttachments = Boolean(attachments && attachments.length > 0);
        const isMediaOnly = !hasText && hasAttachments;
        const bubbleClasses = isMediaOnly ? `chat-bubble ${this.user} media-only` : `chat-bubble ${this.user}`;

        const fallbackImg = "https://cdn.discordapp.com/embed/avatars/0.png";

        if (this.derecha) {
            messageElement.classList.add('blue');
            messageElement.innerHTML = `
                <div class="${bubbleClasses}">
                    ${bubbleContent}
                </div>
                <div class="img-container">
                    <img src="${this.imgSrc}" alt="Avatar" onerror="this.onerror=null;this.src='${fallbackImg}';">
                </div>
            `;
        } else {
            messageElement.innerHTML = `
                <div class="img-container">
                    <img src="${this.imgSrc}" alt="Avatar" onerror="this.onerror=null;this.src='${fallbackImg}';">
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