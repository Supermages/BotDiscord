// Estilos para los mensajes
const style = document.createElement('style');
style.textContent = `
    .chat-box {
        display: flex;
        align-items: flex-start;
        gap: 10px;
        margin-bottom: 10px;
    }

    .chat-box.blue {
        justify-content: flex-end;
    }

    .chat-bubble {
        padding: 5px 10px;
        border-radius: 12.5px;
        font-size: 14px;
        max-width: 300px;
        position: relative;
    }

    .chat-bubble.blue {
        background-color: #2C58E2;
        color: white;
    }

    .chat-bubble.blue::after {
        content: "";
        position: absolute;
        right: -4px;
        top: 5px;
        width: 10px;
        height: 10px;
        background-color: #2C58E2;
        clip-path: path("M 0 0 Q 0 5 10 3 Q 8 12 0 5 Z");
    }

    .chat-bubble.gray {
        background-color: white;
        color: black;
    }

    .chat-bubble.gray::after {
        content: "";
        position: absolute;
        left: -4px;
        top: 5px;
        width: 10px;
        height: 10px;
        background-color: white;
        clip-path: path("M 10 0 Q 10 5 0 3 Q 2 12 10 5 Z");
    }

    .img-container img {
        width: 35px;
        height: 35px;
        border-radius: 50%;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.3);
    }
`;
document.head.appendChild(style);

// Modificar la clase Chat para aplicar la alineación
class Chat {
    constructor(containerSelector) {
        this.container = document.querySelector(containerSelector);
        this.isNextBlue = true; // Alternar entre azul y gris
    }

    addMessage(text) {
        const messageElement = document.createElement('div');
        messageElement.classList.add('chat-box');

        if (this.isNextBlue) {
            messageElement.classList.add('blue'); // Añadir clase para alinear a la derecha
            messageElement.innerHTML = `
                <div class="chat-bubble blue">
                    ${text}
                </div>
                <div class="img-container">
                    <img src="https://cdn.pixabay.com/photo/2015/10/05/22/37/blank-profile-picture-973460_1280.png" alt="Imagen de perfil">
                </div>
            `;
        } else {
            messageElement.innerHTML = `
                <div class="img-container">
                    <img src="https://cdn.pixabay.com/photo/2015/10/05/22/37/blank-profile-picture-973460_1280.png" alt="Imagen de perfil">
                </div>
                <div class="chat-bubble gray">
                    ${text}
                </div>
            `;
        }

        this.container.appendChild(messageElement);
        this.isNextBlue = !this.isNextBlue; // Alternar el color
    }
}

// Ejemplo de uso
document.addEventListener('DOMContentLoaded', () => {
    const chat = new Chat('.chat-container');

    // Añadir mensajes de ejemplo
    chat.addMessage('Hola, este es un mensaje azul.');
    chat.addMessage('Hola, este es un mensaje gris.');
    chat.addMessage('Otro mensaje azul.');
    chat.addMessage('Otro mensaje gris.');
});