// Chat Global (Foro Todos los Usuarios)
const toggleBtn = document.getElementById("chatbot-toggle");
const chatWin = document.getElementById("chatbot-window");
const chatClose = document.getElementById("chatbot-close");
const chatInput = document.getElementById("chat-input");
const chatSend = document.getElementById("chat-send");
const chatMessages = document.getElementById("chat-messages");

let chatInterval = null;
let lastMessageCount = 0;
let unreadMessages = 0;

// Badge de mensajes no leidos (nodo separado para no perder el event listener del boton)
let badgeEl = null;
function getOrCreateBadge() {
    if (!toggleBtn) return null;
    if (!badgeEl) {
        badgeEl = document.createElement("span");
        badgeEl.style.cssText = "position:absolute;top:-4px;right:-4px;background:#dc2626;color:#fff;font-size:10px;font-weight:700;border-radius:50%;width:18px;height:18px;display:none;align-items:center;justify-content:center;pointer-events:none;";
        toggleBtn.appendChild(badgeEl);
    }
    return badgeEl;
}

if (toggleBtn && chatWin) {
    toggleBtn.addEventListener("click", () => {
        chatWin.classList.add("open");
        toggleBtn.style.display = "none";
        unreadMessages = 0;
        const b = getOrCreateBadge();
        if (b) b.style.display = "none";
        if (chatInterval) clearInterval(chatInterval);
        loadMessages();
        chatInterval = setInterval(loadMessages, 3000);
    });

    if (chatClose) {
        chatClose.addEventListener("click", () => {
            chatWin.classList.remove("open");
            toggleBtn.style.display = "flex";
            if (chatInterval) clearInterval(chatInterval);
            chatInterval = setInterval(loadMessages, 5000);
        });
    }

    window.deleteMessage = async function(id) {
        if(!confirm("¿Borrar este mensaje?")) return;
        const sessionToken = localStorage.getItem("fatoken") || localStorage.getItem("fa_session") || "";
        try {
            const res = await fetch(`/api/chat/global/${id}`, {
                method: "DELETE",
                headers: { "session-token": sessionToken }
            });
            if(res.ok) {
                lastMessageCount = 0;
                loadMessages();
            } else {
                alert("No se pudo borrar el mensaje.");
            }
        } catch(e) { console.error(e); }
    };

    window.editMessage = async function(id, oldText) {
        const newText = prompt("Edita tu mensaje:", oldText.replace(" (editado)", ""));
        if(!newText || newText === oldText) return;
        const sessionToken = localStorage.getItem("fatoken") || localStorage.getItem("fa_session") || "";
        try {
            const res = await fetch(`/api/chat/global/${id}`, {
                method: "PUT",
                headers: { "Content-Type": "application/json", "session-token": sessionToken },
                body: JSON.stringify({text: newText})
            });
            if(res.ok) {
                lastMessageCount = 0;
                loadMessages();
            } else {
                alert("No se pudo editar el mensaje.");
            }
        } catch(e) { console.error(e); }
    };

    function addMsg(m, isMe, isAdmin) {
        const d = document.createElement("div");
        d.className = isMe ? "user-msg" : "bot-msg";
        d.style.position = "relative";
        
        const label = document.createElement("div");
        label.style.cssText = "font-size:10px;color:" + (isMe ? "rgba(255,255,255,0.7)" : "#888") + ";margin-bottom:4px;font-weight:bold;";
        label.textContent = m.sender_name + (m.sender_role === "maestro" ? " [Maestro]" : "");
        
        const body = document.createElement("div");
        body.textContent = m.text;
        
        d.appendChild(label);
        d.appendChild(body);
        
        if (isMe || isAdmin) {
            const actions = document.createElement("div");
            actions.style.cssText = "margin-top:6px; display:flex; gap:8px; justify-content:flex-end;";
            
            const btnEdit = document.createElement("button");
            btnEdit.textContent = "✎ Editar";
            btnEdit.style.cssText = "background:none; border:none; color:inherit; font-size:10px; cursor:pointer; opacity:0.8; padding:0; text-decoration:underline;";
            btnEdit.title = "Editar mensaje";
            btnEdit.onclick = () => editMessage(m.id, m.text);
            
            const btnDel = document.createElement("button");
            btnDel.textContent = "🗑 Borrar";
            btnDel.style.cssText = "background:none; border:none; color:" + (isMe ? "#fcd34d" : "#f87171") + "; font-size:10px; cursor:pointer; opacity:0.8; padding:0; text-decoration:underline;";
            btnDel.title = "Eliminar mensaje";
            btnDel.onclick = () => deleteMessage(m.id);
            
            actions.appendChild(btnEdit);
            actions.appendChild(btnDel);
            d.appendChild(actions);
        }

        if (chatMessages) {
            chatMessages.appendChild(d);
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }
    }

    async function loadMessages() {
        // CLAVE CORRECTA: app_auth.js guarda el token bajo la clave 'fatoken', NO 'fa_session'
        const sessionToken = localStorage.getItem("fatoken") || localStorage.getItem("fa_session") || "";
        if (!sessionToken) {
            if (chatMessages) chatMessages.innerHTML = '<p style="text-align:center;color:#666;font-size:12px;margin-top:20px;">Inicia sesion para ver el foro.</p>';
            return;
        }

        try {
            const res = await fetch("/api/chat/global", {
                headers: { "session-token": sessionToken }
            });
            if (!res.ok) {
                console.error("Foro error", res.status);
                return;
            }
            const data = await res.json();
            if (data.ok) {
                const prevCount = lastMessageCount;
                if (data.messages.length !== lastMessageCount || lastMessageCount === 0) {
                    if (chatMessages) chatMessages.innerHTML = "";

                    const myNameEl = document.getElementById("st-name");
                    const myName = myNameEl ? myNameEl.textContent.trim() : "";
                    const myId = String(localStorage.getItem("fa_student_id") || "admin");
                    const myRole = localStorage.getItem("farole") || "";
                    const isAdmin = myRole === "maestro" || myRole === "admin";

                    if (!data.messages || data.messages.length === 0) {
                        if (chatMessages) chatMessages.innerHTML = '<p style="text-align:center;color:#666;font-size:12px;margin-top:20px;">Foro General. Se el primero en escribir.</p>';
                    } else {
                        data.messages.forEach(m => {
                            const isMe = String(m.sender_id) === myId || (myName && m.sender_name && (m.sender_name === myName || m.sender_name.includes(myName)));
                            addMsg(m, isMe, isAdmin);
                        });
                    }

                    // Badge de mensajes no leidos cuando el foro esta cerrado
                    if (!chatWin.classList.contains("open") && data.messages.length > prevCount && prevCount > 0) {
                        unreadMessages += (data.messages.length - prevCount);
                        const b = getOrCreateBadge();
                        if (b) { b.textContent = unreadMessages; b.style.display = "flex"; }
                    }

                    lastMessageCount = data.messages.length;
                }
            }
        } catch (e) {
            console.error("Error cargando foro:", e);
        }
    }

    async function processChat() {
        if (!chatInput) return;
        const txt = chatInput.value.trim();
        if (!txt) return;
        chatInput.value = "";

        const sessionToken = localStorage.getItem("fatoken") || localStorage.getItem("fa_session") || "";
        if (!sessionToken) {
            alert("Sesion no encontrada. Recarga la pagina.");
            return;
        }

        try {
            const res = await fetch("/api/chat/global", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "session-token": sessionToken
                },
                body: JSON.stringify({ text: txt })
            });
            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                console.error("Error enviando:", res.status, err);
                alert("Error al enviar mensaje: " + (err.detail || res.status));
                return;
            }
            const data = await res.json();
            if (data.ok) {
                lastMessageCount = 0;
                loadMessages();
            }
        } catch (e) {
            alert("Error de conexion al foro.");
        }
    }

    if (chatSend) chatSend.addEventListener("click", processChat);
    if (chatInput) chatInput.addEventListener("keydown", e => { if (e.key === "Enter") processChat(); });

    // Sondeo en segundo plano para notificaciones aunque el chat este cerrado
    chatInterval = setInterval(loadMessages, 5000);
}
