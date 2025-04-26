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
        top: 5px;
    }

    /*.chat-bubble.blue {
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
    }*/

    .img-container img {
        width: 35px;
        height: 35px;
        border-radius: 50%;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.3);
    }
`;
document.head.appendChild(style);

// Modificar la clase Chat para aplicar la alineación
/*class ChatOld {
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
}*/
class Chat {
    constructor(containerSelector = '.chat-container', color = 'blue', colorText = "white", imgSrc = 'https://cdn.pixabay.com/photo/2015/10/05/22/37/blank-profile-picture-973460_1280.png', derecha = true, user = 'default-user') {
        this.container = document.querySelector(containerSelector);
        this.color = color;
        this.colorText = colorText;
        this.imgSrc = imgSrc;
        this.derecha = derecha;
        this.user = user;

        // Crear estilos dinámicos
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
                top: 5px;
                width: 10px;
                height: 10px;
                background-color: ${this.color};
                clip-path: path("M 0 0 Q 0 5 10 3 Q 8 12 0 5 Z");
            }
        `;
        document.head.appendChild(dynamicStyle);
    }

    addMessage(text) {
        const messageElement = document.createElement('div');
        messageElement.classList.add('chat-box');

        if (this.derecha) {
            messageElement.classList.add('blue'); // Añadir clase para alinear a la derecha
            messageElement.innerHTML = `
                <div class="chat-bubble ${this.user}">
                    ${text}
                </div>
                <div class="img-container">
                    <img src="${this.imgSrc}" alt="Imagen de perfil">
                </div>
            `;
        } else {
            messageElement.innerHTML = `
                <div class="img-container">
                    <img src="${this.imgSrc}" alt="Imagen de perfil">
                </div>
                <div class="chat-bubble ${this.user}">
                    ${text}
                </div>
            `;
        }

        this.container.appendChild(messageElement);
    }
}
window.Chat = Chat;
// Ejemplo de uso
document.addEventListener('DOMContentLoaded', () => {
    document.getElementById("title").textContent = "Chat";
    window.chat = new Chat('.chat-container', '#2C58E2', 'white', 'https://cdn.pixabay.com/photo/2015/10/05/22/37/blank-profile-picture-973460_1280.png', true, 'user1');
    window.chat2 = new Chat(
        '.chat-container', // Selector del contenedor
        '#FF5733',         // Color de fondo del mensaje
        'black',           // Color del texto
        'https://cdn.discordapp.com/avatars/1365414112984567906/0f7e98004f47de5b79ac1c0c2f6cb74a.png?size=1024', // URL de la imagen de perfil
        false,             // Alineación: `true` para derecha, `false` para izquierda
        'user2'            // Clase única para identificar al usuario
    );
    window.chat3 = new Chat(
        '.chat-container', // Selector del contenedor
        'white',         // Color de fondo del mensaje
        'black',           // Color del texto
        'https://cdn.discordapp.com/avatars/1365414112984567906/0f7e98004f47de5b79ac1c0c2f6cb74a.png?size=1024', // URL de la imagen de perfil
        false,             // Alineación: `true` para derecha, `false` para izquierda
        'user3'            // Clase única para identificar al usuario
    );
    chat.addMessage('Hola, este es un mensaje azul.');
    chat2.addMessage('Hola, este es un mensaje gris.');
    chat3.addMessage('Hola, este es un mensaje gris. 🪙');
    chat.addMessage('¿Cómo estás?');
    chat2.addMessage('Estoy bien, gracias. ¿Y tú? 😀');
    chat3.addMessage('Estoy bien, gracias. ¿Y tú?');
    chat.addMessage('¡Genial! ¿Qué tal tu día? fdsa fdsaf dsaf dsa');
    
});