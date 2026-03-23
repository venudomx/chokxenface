// ==================== CONFIGURACIÓN ====================
const API = "/api";

const $ = id => document.getElementById(id);
const sessionToken = localStorage.getItem("fatoken");

// Guard: solo maestros
if (!sessionToken || localStorage.getItem("farole") !== "maestro") {
    window.location.href = "index.html";
}

$("btn-logout-ad").addEventListener("click", () => {
    localStorage.clear(); window.location.href = "index.html";
});

let allStudents = [];

// ==================== CARGAR LISTA ALUMNOS ====================
async function loadStudents() {
    try {
        const res = await fetch(`${API}/admin/students`, {
            headers: { "session-token": sessionToken }
        });
        if (res.status === 401 || res.status === 403) {
            localStorage.clear(); window.location.href = "index.html"; return;
        }
        const data = await res.json();
        allStudents = data.students || [];

        // Stats rápidas
        const total = allStudents.length;
        const rojos = allStudents.filter(s => s.semaforo === "rojo").length;
        const amarillos = allStudents.filter(s => s.semaforo === "amarillo").length;
        const verdes = allStudents.filter(s => s.semaforo === "verde").length;

        $("admin-stats-row").innerHTML = `
            <div class="stat-card"><span class="stat-big">${total}</span><span>Total Alumnos</span></div>
            <div class="stat-card" style="border-color:var(--primary)"><span class="stat-big" style="color:var(--primary)">${verdes}</span><span>🟢 Verde</span></div>
            <div class="stat-card" style="border-color:var(--warning)"><span class="stat-big" style="color:var(--warning)">${amarillos}</span><span>🟡 Amarillo</span></div>
            <div class="stat-card" style="border-color:var(--danger)"><span class="stat-big" style="color:var(--danger)">${rojos}</span><span>🔴 Rojo</span></div>
        `;

        renderTable(allStudents);
    } catch(e) { console.error(e); }
}

function semColor(s) {
    return s==="rojo"?"var(--danger)":s==="amarillo"?"var(--warning)":"var(--primary)";
}

function renderTable(students) {
    const tbody = document.querySelector("#admin-table tbody");
    if (!students.length) {
        tbody.innerHTML = `<tr><td colspan="7" class="text-center muted">Sin alumnos registrados.</td></tr>`;
        return;
    }
    tbody.innerHTML = students.map(st => `
        <tr>
            <td>${st.id}</td>
            <td>${st.matricula}</td>
            <td><strong>${st.nombre}</strong></td>
            <td class="muted small">${st.carrera || "—"}</td>
            <td style="text-align:center;"><strong>${st.faltas}</strong></td>
            <td style="text-align:center;">
                <span style="display:inline-flex;align-items:center;gap:6px;">
                    <span style="width:12px;height:12px;border-radius:50%;background:${semColor(st.semaforo)};box-shadow:0 0 8px ${semColor(st.semaforo)};"></span>
                    ${st.semaforo.toUpperCase()}
                </span>
            </td>
            <td style="display:flex; gap:6px; justify-content:center;">
                <button class="btn-sm btn-primary" onclick="selectStudent(${st.id},'${st.nombre}')" title="Agregar falta manual">+ Falta</button>
            </td>
        </tr>
    `).join("");
}

// ==================== BÚSQUEDA ====================
window.filterAdmin = (q) => {
    const lower = q.toLowerCase();
    const filtered = allStudents.filter(s =>
        s.nombre.toLowerCase().includes(lower) || s.matricula.toLowerCase().includes(lower)
    );
    renderTable(filtered);
};

// ==================== GOOGLE BOOKS API ====================
window.searchGoogleBooks = async function() {
    const query = $("gbooks-query").value.trim();
    if (!query) return;
    await fetchGoogleBooks(query);
};

window.fetchGoogleBooks = async function(query) {
    const container = $("gbooks-results");
    const empty = $("gbooks-empty");
    if (!container || !empty) return;

    container.innerHTML = "<p style='color:#aaa; grid-column:1/-1; text-align:center;'>Buscando...</p>";
    empty.style.display = "none";

    try {
        const res = await fetch(`https://www.googleapis.com/books/v1/volumes?q=${encodeURIComponent(query)}&maxResults=12&printType=books`);
        const data = await res.json();

        if (!data.items || data.items.length === 0) {
            data.items = [
                { volumeInfo: { title: "Pedagogia del Oprimido", authors: ["Paulo Freire"], pageCount: 256, publishedDate: "1968", imageLinks: { thumbnail: "https://books.google.com/books/content?id=vBw-DwAAQBAJ&printsec=frontcover&img=1&zoom=1" }, previewLink: "https://books.google.com.mx/books?id=vBw-DwAAQBAJ" } },
                { volumeInfo: { title: "Didactica General", authors: ["Lidia Mercedes"], pageCount: 300, publishedDate: "2010", imageLinks: { thumbnail: "https://books.google.com/books/content?id=Z3E-DwAAQBAJ&printsec=frontcover&img=1&zoom=1" }, previewLink: "https://books.google.com.mx/books?id=Z3E-DwAAQBAJ" } },
                { volumeInfo: { title: "Evaluacion Educativa", authors: ["Miguel Angel Santos"], pageCount: 288, publishedDate: "2014", imageLinks: { thumbnail: "https://books.google.com/books/content?id=KxE-DwAAQBAJ&printsec=frontcover&img=1&zoom=1" }, previewLink: "https://books.google.com.mx/books?id=KxE-DwAAQBAJ" } }
            ];
        }

        container.innerHTML = data.items.map(item => {
            const info = item.volumeInfo;
            const title = info.title || "Sin titulo";
            const authors = (info.authors || ["Autor desconocido"]).join(", ");
            const thumb = info.imageLinks?.thumbnail || info.imageLinks?.smallThumbnail || "";
            const link = info.previewLink || info.infoLink || "#";
            const pages = info.pageCount ? info.pageCount + " págs" : "";
            const year = info.publishedDate ? info.publishedDate.substring(0, 4) : "";

            return `
                <div style="background:rgba(255,255,255,0.05); border:1px solid rgba(255,255,255,0.1); border-radius:10px; overflow:hidden; display:flex; flex-direction:column; transition:transform 0.2s, box-shadow 0.2s; cursor:pointer;" onclick="window.open('${link}','_blank')" onmouseenter="this.style.transform='translateY(-3px)';this.style.boxShadow='0 8px 20px rgba(0,0,0,0.4)'" onmouseleave="this.style.transform='';this.style.boxShadow=''">
                    <div style="height:180px; background:#1a1a2e; display:flex; align-items:center; justify-content:center; overflow:hidden;">
                        ${thumb ? `<img src="${thumb.replace('http:', 'https:')}" style="height:100%; object-fit:contain;" alt="${title}">` : `<div style="color:#555; font-size:11px; text-align:center; padding:10px;">Sin portada</div>`}
                    </div>
                    <div style="padding:10px; flex:1; display:flex; flex-direction:column;">
                        <p style="margin:0 0 4px; font-size:12px; font-weight:700; color:#e5e7eb; line-height:1.3; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden;">${title}</p>
                        <p style="margin:0; font-size:10px; color:#9ca3af; line-height:1.3;">${authors}</p>
                        <div style="margin-top:auto; padding-top:6px; display:flex; gap:6px; flex-wrap:wrap;">
                            ${year ? `<span style="font-size:9px; background:rgba(255,255,255,0.08); padding:2px 6px; border-radius:4px; color:#94a3b8;">${year}</span>` : ""}
                            ${pages ? `<span style="font-size:9px; background:rgba(255,255,255,0.08); padding:2px 6px; border-radius:4px; color:#94a3b8;">${pages}</span>` : ""}
                        </div>
                    </div>
                </div>
            `;
        }).join("");

    } catch (err) {
        console.error("Error Google Books:", err);
        container.innerHTML = "";
        empty.textContent = "Error al conectar con Google Books. Verifica tu conexión.";
        empty.style.display = "block";
    }
}

setTimeout(() => {
    fetchGoogleBooks("educacion pedagogia");
}, 1500);


// ==================== JUSTIFICAR FALTA RECIENTE POR MATRICULA ====================
if ($("btn-justificar")) {
    $("btn-justificar").addEventListener("click", async () => {
        const mat = $("admin-justificar-mat").value.trim();
        if(!mat) {
            $("justificar-status").textContent = "Por favor ingresa una matrícula.";
            $("justificar-status").style.color = "var(--danger)";
            return;
        }
        
        if (!confirm(`¿Estás seguro de justificar la última inasistencia de la matrícula ${mat}?`)) return;

        $("justificar-status").textContent = "Procesando...";
        $("justificar-status").style.color = "var(--text-muted)";

        try {
            const res = await fetch(`${API}/admin/absences/matricula/${mat}/latest`, {
                method: "DELETE",
                headers: { "session-token": sessionToken }
            });
            const data = await res.json();
            
            if (res.ok && data.deleted) {
                $("justificar-status").textContent = `Se justificó la falta más reciente de ${data.nombre}.`;
                $("justificar-status").style.color = "var(--primary)";
                $("admin-justificar-mat").value = "";
                loadStudents(); // Recargar tabla
            } else if (res.ok && !data.deleted) {
                $("justificar-status").textContent = `El alumno no tiene faltas recientes para justificar.`;
                $("justificar-status").style.color = "var(--warning)";
            } else {
                $("justificar-status").textContent = data.detail || "Error al justificar falta.";
                $("justificar-status").style.color = "var(--danger)";
            }
        } catch(e) {
            $("justificar-status").textContent = "Error de conexión al servidor.";
            $("justificar-status").style.color = "var(--danger)";
        }
    });
}

// ==================== AGREGAR FALTA ====================
window.selectStudent = (id, nombre) => {
    $("admin-falta-id").value = id;
    $("admin-status").textContent = `Alumno seleccionado: ${nombre}`;
    const dateInput = $("admin-falta-fecha");
    if(dateInput) {
        dateInput.value = new Date().toISOString().split("T")[0];
        // Bloquear fecha para que no la puedan cambiar
        dateInput.readOnly = true; 
        dateInput.style.pointerEvents = "none";
        dateInput.style.opacity = "0.7";
    }
};

$("btn-add-falta").addEventListener("click", async () => {
    const student_id = $("admin-falta-id").value;
    if (!student_id) { $("admin-status").textContent = "Selecciona un alumno de la tabla primero."; return; }

    const date = $("admin-falta-fecha").value || new Date().toISOString().split("T")[0];
    
    // Validación de fecha (mes y año actual)
    const [year, month, day] = date.split("-");
    const today = new Date();
    if (parseInt(year) !== today.getFullYear() || parseInt(month) !== (today.getMonth() + 1)) {
        $("admin-status").textContent = "Protocolo de seguridad: Las faltas solo pueden asignarse en el mes y año en curso.";
        $("admin-status").style.color = "var(--danger)";
        return;
    }
    $("admin-status").style.color = "var(--text-muted)";
    
    const reason = $("admin-falta-razon").value.trim() || "Inasistencia";

    const fd = new FormData();
    fd.append("student_id", student_id);
    fd.append("date", date);
    fd.append("reason", reason);

    try {
        const res = await fetch(`${API}/admin/absences`, {
            method: "POST",
            headers: { "session-token": sessionToken },
            body: fd
        });
        if (res.ok) {
            $("admin-status").textContent = "Falta registrada correctamente.";
            $("admin-falta-id").value = "";
            $("admin-falta-razon").value = "";
            loadStudents();
        } else {
            $("admin-status").textContent = "Error al agregar falta.";
        }
    } catch(e) {
        $("admin-status").textContent = "Error de conexión.";
    }
});

loadStudents();

// ==================== AVISOS INSTITUCIONALES ====================
function renderAvisos() {
    const container = $("avisos-container");
    if (!container) return;
    container.innerHTML = `<div style="width: 100%; border-radius:12px; overflow:hidden;"><div style="position: relative; padding-bottom: 56.25%; padding-top: 0; height: 0;"><iframe title="AVISOS UTSLP" frameborder="0" width="1200px" height="675px" style="position: absolute; top: 0; left: 0; width: 100%; height: 100%;" src="https://view.genially.com/66c7db68ccddd20202dc358c" type="text/html" allowscriptaccess="always" allowfullscreen="true" scrolling="yes" allownetworking="all"></iframe></div></div>`;
}
renderAvisos();

// ==================== CREDENCIAL MAESTRO ====================
window.generateMaestroQR = function() {
    try {
        const maestroName = localStorage.getItem("email") || "Docente";
        const nameEl = document.getElementById("maestro-idcard-name");
        if (nameEl) nameEl.textContent = maestroName;
        
        const qrContainer = document.getElementById("maestro-idcard-qrcode");
        if (qrContainer && qrContainer.innerHTML === "") {
            new QRCode(qrContainer, {
                text: "DOCENTE:" + maestroName,
                width: 140,
                height: 140,
                colorDark: "#000",
                colorLight: "#fff",
                correctLevel: QRCode.CorrectLevel.H
            });
        }
    } catch(e) {
        console.error("Error al generar QR de maestro:", e);
    }
};

// ==================== FORO / CHAT GLOBAL ====================
let lastGlobalMessageCount = 0;
let globalChatInterval = null;

async function loadGlobalChat() {
    const container = $("inbox-container");
    if (!container) return;

    try {
        const res = await fetch(`${API}/chat/global`, {
            headers: { "session-token": sessionToken }
        });
        const data = await res.json();
        
        if (data.ok) {
            if (data.messages.length !== lastGlobalMessageCount) {
                container.innerHTML = "";
                
                if (data.messages.length === 0) {
                    container.innerHTML = `<p class="text-center muted">Aún no hay mensajes en el foro general.</p>`;
                } else {
                    data.messages.forEach(m => {
                        const isTeacher = m.sender_role !== "alumno";
                        const bgColor = isTeacher ? "rgba(20, 150, 255, 0.1)" : "rgba(255, 255, 255, 0.05)";
                        const bColor = isTeacher ? "1px solid rgba(20, 150, 255, 0.3)" : "1px solid rgba(255, 255, 255, 0.1)";
                        
                        container.innerHTML += `
                            <div style="background:${bgColor}; border:${bColor}; border-radius:8px; padding:10px;">
                                <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
                                    <strong style="color:${isTeacher ? '#4dffff' : '#e2e8f0'}; font-size:11px;">
                                        ${m.sender_name} ${isTeacher ? '🎓' : ''}
                                    </strong>
                                    <small style="color:#777; font-size:9px;">${new Date(m.timestamp + "Z").toLocaleTimeString()}</small>
                                </div>
                                <div style="color:#cbd5e1; font-size:12px; line-height:1.4;">${m.text}</div>
                            </div>
                        `;
                    });
                }
                lastGlobalMessageCount = data.messages.length;
                container.scrollTop = container.scrollHeight;
            }
        }
    } catch (err) {
        console.error("Error validando chat:", err);
    }
}

window.sendGlobalMessage = async function() {
    const input = $("global-chat-input");
    const txt = input.value.trim();
    if (!txt) return;

    input.value = "";
    
    try {
        const res = await fetch(`${API}/chat/global`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "session-token": sessionToken
            },
            body: JSON.stringify({ text: txt })
        });
        const data = await res.json();
        if (data.ok) {
            lastGlobalMessageCount = 0; // Forzar render
            loadGlobalChat();
        }
    } catch(e) {
        alert("Error de red enviando mensaje.");
    }
};

window.addEventListener("DOMContentLoaded", () => {
    loadGlobalChat();
    globalChatInterval = setInterval(loadGlobalChat, 3000);
});
