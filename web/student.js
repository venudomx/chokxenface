// ==================== CONFIGURACION ====================
const API = "/api";
const $ = id => document.getElementById(id);
const sessionToken = localStorage.getItem("fatoken");

// Guard: si no hay sesion, volver al login
if (!sessionToken || localStorage.getItem("farole") !== "student") {
    window.location.href = "index.html";
}

// ==================== NAV ====================
$("btn-logout-st").addEventListener("click", () => {
    localStorage.removeItem("fatoken");
    localStorage.removeItem("farole");
    localStorage.removeItem("fa_matricula");
    localStorage.removeItem("fa_carrera");
    localStorage.removeItem("fa_student_id");
    window.location.href = "index.html";
});

// ==================== MODAL MI PERFIL ====================
let photoAlreadyChanged = false;

$("btn-open-profile").addEventListener("click", () => {
    $("profile-nombre").textContent = localStorage.getItem("fa_student_name") || "---";
    $("profile-matricula").textContent = localStorage.getItem("fa_matricula") || "---";
    $("profile-carrera").textContent = localStorage.getItem("fa_carrera") || "---";

    const btn = $("btn-change-photo");
    if (photoAlreadyChanged) {
        btn.disabled = true;
        btn.textContent = "Foto ya actualizada";
        btn.style.opacity = "0.5";
    }
    $("modal-profile").style.display = "flex";
});

$("profile-photo-input").addEventListener("change", async function() {
    const file = this.files[0];
    if (!file) return;
    if (photoAlreadyChanged) {
        $("profile-photo-status").textContent = "Ya cambiaste tu foto. Solo se permite una vez.";
        $("profile-photo-status").style.color = "#ef4444";
        return;
    }
    const fd = new FormData();
    fd.append("file", file);
    $("profile-photo-status").textContent = "Subiendo foto...";
    try {
        const res = await fetch(`${API}/student/update-photo`, {
            method: "POST",
            headers: { "session-token": sessionToken },
            body: fd
        });
        const data = await res.json();
        if (res.ok) {
            photoAlreadyChanged = true;
            $("profile-photo-status").textContent = "Foto actualizada correctamente.";
            $("profile-photo-status").style.color = "var(--primary)";
            $("btn-change-photo").disabled = true;
            $("btn-change-photo").textContent = "Foto ya actualizada";
            $("btn-change-photo").style.opacity = "0.5";
        } else {
            $("profile-photo-status").textContent = data.detail || "Error al subir foto.";
            $("profile-photo-status").style.color = "#ef4444";
        }
    } catch(e) {
        $("profile-photo-status").textContent = "Error de conexion.";
        $("profile-photo-status").style.color = "#ef4444";
    }
});

// ==================== SEMAFORO ====================
function setSemaforo(color) {
    ["rojo","amarillo","verde"].forEach(c => $("light-"+c).classList.remove("active"));
    $("semaforo-text").className = "semaforo-label";
    $("semaforo-text").textContent = `Estatus: ${color.toUpperCase()}`;
    $("light-"+color).classList.add("active");
    $("semaforo-text").style.color = color==="rojo"?"var(--danger)":color==="amarillo"?"var(--warning)":"var(--primary)";
}

// ==================== RACHA DE ASISTENCIA ====================
function calcularRacha(events) {
    const entradas = events
        .filter(e => e.type === "entrada")
        .map(e => e.ts ? e.ts.split(" ")[0] : e.date ? e.date.split(" ")[0] : null)
        .filter(Boolean);

    if (entradas.length === 0) return 0;

    // Dias unicos ordenados descendentemente
    const dias = [...new Set(entradas)].sort((a, b) => b.localeCompare(a));
    let racha = 1;
    for (let i = 0; i < dias.length - 1; i++) {
        const d1 = new Date(dias[i]);
        const d2 = new Date(dias[i + 1]);
        const diff = (d1 - d2) / (1000 * 60 * 60 * 24);
        if (diff === 1) { racha++; } else { break; }
    }
    return racha;
}

function mostrarRacha(racha) {
    $("streak-num").textContent = racha;
    $("st-racha-count").textContent = racha;
    const wrap = $("streak-wrap");

    if (racha === 0) {
        $("streak-label").textContent = "Sin registros aun";
        $("streak-sub").textContent = "Asiste para iniciar tu racha";
        wrap.style.background = "linear-gradient(135deg, rgba(255,255,255,0.05), rgba(255,255,255,0.02))";
        wrap.style.borderColor = "rgba(255,255,255,0.1)";
    } else if (racha >= 10) {
        $("streak-label").textContent = "Racha excepcional";
        $("streak-sub").textContent = `${racha} dias consecutivos de asistencia`;
        wrap.style.background = "linear-gradient(135deg, rgba(251, 191, 36, 0.15), rgba(251, 191, 36, 0.05))";
        wrap.style.borderColor = "rgba(251, 191, 36, 0.4)";
    } else if (racha >= 5) {
        $("streak-label").textContent = "Excelente constancia";
        $("streak-sub").textContent = `${racha} dias seguidos — sigue adelante`;
        wrap.style.background = "linear-gradient(135deg, rgba(74, 222, 128, 0.15), rgba(74, 222, 128, 0.05))";
        wrap.style.borderColor = "rgba(74, 222, 128, 0.4)";
    } else {
        $("streak-label").textContent = "Construyendo habito";
        $("streak-sub").textContent = `${racha} dia(s) consecutivo(s)`;
        wrap.style.background = "linear-gradient(135deg, rgba(56, 189, 248, 0.15), rgba(56, 189, 248, 0.05))";
        wrap.style.borderColor = "rgba(56, 189, 248, 0.4)";
    }
}

// ==================== TRIVIA DEL DIA (API) ====================
async function initTrivia(studentId) {
    if (!studentId) return;

    try {
        const res = await fetch(`${API}/trivia/today`, {
            headers: { "session-token": sessionToken }
        });
        if (!res.ok) return;
        const data = await res.json();

        // Mostrar puntos acumulados desde el servidor
        $("st-utpoints").textContent = (data.total_points || 0).toFixed(1);

        if (data.already_answered) {
            $("trivia-container").style.display = "none";
            $("trivia-done").style.display = "block";
            return;
        }

        // Mostrar pregunta
        $("trivia-q").textContent = data.question;
        const optsEl = $("trivia-opts");
        optsEl.innerHTML = "";

        data.options.forEach((opt, i) => {
            const btn = document.createElement("button");
            btn.className = "trivia-opt";
            btn.textContent = opt;
            btn.addEventListener("click", async () => {
                optsEl.querySelectorAll(".trivia-opt").forEach(b => b.style.pointerEvents = "none");

                try {
                    const fd = new FormData();
                    fd.append("answer", i);
                    fd.append("day_index", data.day_index);
                    fd.append("carrera", data.carrera);
                    const ansRes = await fetch(`${API}/trivia/answer`, {
                        method: "POST",
                        headers: { "session-token": sessionToken },
                        body: fd
                    });
                    const ansData = await ansRes.json();

                    if (ansData.correct) {
                        btn.classList.add("correct");
                        $("trivia-result").textContent = "Correcto! Ganaste 0.5 UTPoints";
                        $("trivia-result").style.color = "var(--primary)";
                    } else {
                        btn.classList.add("wrong");
                        optsEl.querySelectorAll(".trivia-opt")[ansData.correct_answer].classList.add("correct");
                        $("trivia-result").textContent = "Incorrecto. Te llevas 0.1 UTPoints por participar.";
                        $("trivia-result").style.color = "#ef4444";
                    }
                    $("st-utpoints").textContent = (ansData.total_points || 0).toFixed(1);
                } catch(e) {
                    $("trivia-result").textContent = "Error al enviar respuesta.";
                    $("trivia-result").style.color = "#ef4444";
                }

                setTimeout(() => {
                    $("trivia-container").style.display = "none";
                    $("trivia-done").style.display = "block";
                }, 3500);
            });
            optsEl.appendChild(btn);
        });
    } catch(e) {
        console.error("Error cargando trivia:", e);
    }
}

// ==================== FRASE / PENSAMIENTO DEL DIA ====================
const QUOTES = [
    { text: "La disciplina es el puente entre metas y logros.", author: "Jim Rohn" },
    { text: "El exito es la suma de pequenos esfuerzos repetidos dia tras dia.", author: "Robert Collier" },
    { text: "No importa lo lento que vayas, siempre y cuando no te detengas.", author: "Confucio" },
    { text: "Invierte en ti mismo. Tu carrera es el motor de tu riqueza.", author: "Paul Clitheroe" },
    { text: "El conocimiento es poder.", author: "Francis Bacon" },
    { text: "La educacion es el arma mas poderosa que puedes usar para cambiar el mundo.", author: "Nelson Mandela" },
    { text: "El fracaso es simplemente la oportunidad de comenzar de nuevo, esta vez de forma mas inteligente.", author: "Henry Ford" },
    { text: "La unica forma de hacer un gran trabajo es amar lo que haces.", author: "Steve Jobs" },
    { text: "No te compares con nadie en este mundo. Si lo haces, estaras insultando tu propia unicidad.", author: "Bill Gates" },
    { text: "El tiempo que te diviertes malgastando no es tiempo malgastado.", author: "Bertrand Russell" },
    { text: "Aprende como si fueras a vivir para siempre, vive como si fueras a morir manana.", author: "Mahatma Gandhi" },
    { text: "Las personas que tienen exito tienen impulso. Incluso si no tienen razon, mientras avanzan aprenderas algo.", author: "Elon Musk" },
    { text: "El camino hacia el exito y el camino hacia el fracaso son casi exactamente los mismos.", author: "Colin Davis" },
    { text: "Lo que sabes no importa tanto como lo que decides hacer con lo que sabes.", author: "Tony Robbins" },
    { text: "Cree que puedes y ya estaras a medio camino.", author: "Theodore Roosevelt" },
];

function initQuote() {
    const idx = Math.floor(Date.now() / 86400000) % QUOTES.length;
    const q = QUOTES[idx];
    $("quote-text").textContent = `"${q.text}"`;
    $("quote-author").textContent = `— ${q.author}`;
}

// ==================== CARGAR DASHBOARD ====================
async function loadDashboard() {
    try {
        const res = await fetch(`${API}/student/dashboard`, {
            headers: { "session-token": sessionToken }
        });

        if (res.status === 401 || res.status === 403) {
            localStorage.clear(); window.location.href = "index.html"; return;
        }

        const data = await res.json();

        // Nombre
        $("st-name").textContent = data.name || "Alumno";
        $("st-name-nav").textContent = data.name || "Alumno";

        // Guardar datos para credencial virtual y perfil
        if (data.name) localStorage.setItem("fa_student_name", data.name);
        if (data.matricula) localStorage.setItem("fa_matricula", data.matricula);
        if (data.carrera) localStorage.setItem("fa_carrera", data.carrera);
        if (data.student_id) localStorage.setItem("fa_student_id", data.student_id);

        // Verificar si ya cambio foto
        if (data.photo_changed) photoAlreadyChanged = true;

        // Semaforo
        setSemaforo(data.semaforo);

        // Conteos
        $("st-faltas-count").textContent = data.faltas?.length ?? 0;
        const entradas = (data.events || []).filter(e => e.type === "entrada");
        $("st-entradas-count").textContent = entradas.length;

        // Racha
        const racha = calcularRacha(data.events || []);
        mostrarRacha(racha);

        // Iniciar Trivia y Quote con el ID asegurado
        initTrivia(data.student_id);
        initQuote();

        // Historial
        const tbody = document.querySelector("#st-history-table tbody");
        const all = [];
        (data.faltas || []).forEach(f => all.push({ date: f.date, type: "FALTA", color: "var(--danger)" }));
        (data.events || []).forEach(e => all.push({ date: e.ts, type: e.type.toUpperCase(), color: e.type==="entrada"?"var(--primary)":"var(--text-muted)" }));
        all.sort((a,b) => new Date(b.date)-new Date(a.date));

        tbody.innerHTML = all.length === 0
            ? `<tr><td colspan="2" class="text-center muted">Sin registros aun.</td></tr>`
            : all.slice(0,40).map(ev =>
                `<tr><td>${ev.date}</td><td style="font-weight:600;color:${ev.color};">${ev.type}</td></tr>`
              ).join("");

    } catch(e) {
        console.error("Error cargando dashboard:", e);
    }
}

// ==================== INICIALIZAR ====================
loadDashboard();

// ==================== RENTA DE LIBROS CON QR ====================
let currentQR = null;

function rentBook(title, author) {
    const studentName = $("st-name").textContent || "Alumno";
    const dateStr = new Date().toLocaleString();
    const qrData = `LIBRO: ${title}\nAUTOR: ${author}\nALUMNO: ${studentName}\nFECHA: ${dateStr}\nVALIDO: 24hrs`;

    $("ticket-book").textContent = title;
    $("ticket-author").textContent = author;
    
    $("qrcode-container").innerHTML = "";
    
    if (typeof QRCode !== "undefined") {
        currentQR = new QRCode($("qrcode-container"), {
            text: qrData,
            width: 150,
            height: 150,
            colorDark : "#000000",
            colorLight : "#ffffff",
            correctLevel : QRCode.CorrectLevel.H
        });
    } else {
        $("qrcode-container").innerHTML = "<p style='color:red;'>Error cargando QRCode.js</p>";
    }

    $("modal-qr").classList.add("active");
}

function downloadTicketPDF() {
    if (typeof window.jspdf === "undefined") {
        alert("La librería PDF aún se está cargando, intenta en un segundo.");
        return;
    }
    const { jsPDF } = window.jspdf;
    const doc = new jsPDF();
    
    doc.setFontSize(22);
    doc.setFont("helvetica", "bold");
    doc.text("Ficha de Préstamo - UTSLP", 20, 30);
    
    doc.setFontSize(14);
    doc.setFont("helvetica", "normal");
    doc.text(`Libro: ${$("ticket-book").textContent}`, 20, 50);
    doc.text(`Autor: ${$("ticket-author").textContent}`, 20, 60);
    doc.text(`Alumno: ${$("st-name").textContent || "Alumno"}`, 20, 70);
    doc.text(`Fecha Misión: ${new Date().toLocaleString()}`, 20, 80);
    
    const qrCanvas = document.querySelector("#qrcode-container canvas");
    const qrImg = document.querySelector("#qrcode-container img");
    let imgSrc = null;
    if (qrCanvas) {
        imgSrc = qrCanvas.toDataURL("image/png");
    } else if (qrImg && qrImg.src) {
        imgSrc = qrImg.src;
    }
    
    if (imgSrc) {
        doc.addImage(imgSrc, 'PNG', 20, 95, 75, 75);
    }
    
    doc.setFontSize(11);
    doc.setTextColor(100);
    doc.text("Instrucciones:", 20, 185);
    doc.setFontSize(10);
    doc.text("1. Presenta este código QR desde tu celular o impreso en la biblioteca física.", 20, 192);
    doc.text("2. Válido por 24 horas a partir de su emisión.", 20, 198);
    doc.text("3. Devuelve el libro en la fecha establecida para evitar suspensiones.", 20, 204);
    
    const cleanTitle = $("ticket-book").textContent.replace(/[^a-zA-Z0-9]/g, '_');
    doc.save(`boleta_${cleanTitle}.pdf`);
}

// ==================== CREDENCIAL VIRTUAL ====================
let idCardLoaded = false;

window.openVirtualID = function() {
    try {
        const modal = document.getElementById("modal-idcard");
        if (!modal) {
            alert("Error: El HTML del modal no se encontro en la pagina.");
            return;
        }
        
        // Usar ambas formas por seguridad
        modal.style.display = "flex";
        modal.classList.add("active");

        if (idCardLoaded) return;

        // Obtener datos del alumno
        const nombre = $("st-name").textContent || "Alumno";
        const matricula = localStorage.getItem("fa_matricula") || "N/A";
        const carrera = localStorage.getItem("fa_carrera") || "N/A";
        const studentId = localStorage.getItem("fa_student_id") || "";

        // Poblar frente
        $("idcard-name").textContent = nombre;
        $("idcard-matricula").textContent = matricula;
        $("idcard-carrera").textContent = carrera || "Tecnologías de la Información";
        
        // Cargar foto
        const photoUrl = `${API}/admin/student/${studentId}/photo?t=${new Date().getTime()}`;
        if ($("sidebar-profile-img")) { $("sidebar-profile-img").src = photoUrl; $("sidebar-profile-img").style.display = "block"; }
        if ($("idcard-photo")) { $("idcard-photo").src = photoUrl; $("idcard-photo").style.display = "block"; }

        // Control de visibilidad para imagenes
        const profileImg = $("sidebar-profile-img");
        const cardImg = $("idcard-photo");
        if (profileImg) profileImg.style.display = "block";
        if (cardImg) cardImg.style.display = "block";
        
        // Si el motor Python responde bien a las imagenes, se cargaran; si da 404, onerror las ocultara dinamicamente.

        // Generar QR - limpiar primero para evitar duplicados
        const qrContainer = $("idcard-qrcode");
        if (qrContainer) {
            qrContainer.innerHTML = ""; // limpiar siempre
            const generateQR = () => {
                if (typeof QRCode !== "undefined") {
                    new QRCode(qrContainer, {
                        text: `UTSLP-ALUMNO-${matricula}-${studentId}`,
                        width: 90,
                        height: 90,
                        colorDark: "#1a1a1a",
                        colorLight: "#ffffff",
                        correctLevel: QRCode.CorrectLevel.M
                    });
                } else {
                    // Reintentar en 600ms si la libreria aun no cargo
                    setTimeout(generateQR, 600);
                }
            };
            generateQR();
        }

        idCardLoaded = true;
    } catch (error) {
        alert("Error al abrir credencial: " + error.message);
        console.error("Error en openVirtualID:", error);
    }
};

// ==================== WAALET BINDINGS (Reemplazado x Imagen Nativa) ====================
window.downloadCredentialImage = async function() {
    if (typeof html2canvas === 'undefined') {
        alert("Librería de renderizado aún cargando o bloqueada. Revisa tu conexión a internet.");
        return;
    }
    const cardEl = document.getElementById("virtual-id-front");
    if (!cardEl) return;
    
    const origTransform = cardEl.style.transform;
    cardEl.style.transform = "none"; // Evita glitch de perspectiva 3D al renderizar
    
    try {
        const canvas = await html2canvas(cardEl, { 
            scale: window.devicePixelRatio || 2, 
            useCORS: true, 
            backgroundColor: null 
        });
        
        cardEl.style.transform = origTransform;
        
        const a = document.createElement("a");
        a.href = canvas.toDataURL("image/png");
        a.download = `Credencial_UTSLP_${localStorage.getItem("fa_student_id") || "Alumno"}.png`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        
    } catch (e) {
        console.error("Error html2canvas: ", e);
        alert("Hubo un problema al intentar generar la imagen. Intenta de nuevo.");
        cardEl.style.transform = origTransform;
    }
};

window.downloadApplePass = async function() {
    const studentId = localStorage.getItem("fa_student_id");
    try {
        const res = await fetch(`/api/wallet/apple/${studentId}`);
        const data = await res.json();
        alert(data.message);
    } catch(e) {
        alert("Error de conexión al servidor al solicitar pase de Apple Wallet.");
    }
};

window.downloadGooglePass = async function() {
    const studentId = localStorage.getItem("fa_student_id");
    try {
        const res = await fetch(`/api/wallet/google/${studentId}`);
        const data = await res.json();
        alert(data.message);
    } catch(e) {
        alert("Error de conexión al servidor al solicitar pase de Google Wallet.");
    }
};

// ==================== SUBIDA MANUAL DE FOTO ====================
window.uploadStudentPhoto = async function(event) {
    const file = event.target.files[0];
    if (!file) return;
    
    // Validar tipo y tamaño
    if (!file.type.match('image.*')) {
        alert("Por favor selecciona una imagen válida (JPG, PNG).");
        return;
    }
    if (file.size > 2 * 1024 * 1024) {
        alert("La imagen es muy pesada. Máximo 2MB.");
        return;
    }
    
    alert("Subiendo foto oficial, por favor espera...");
    
    const reader = new FileReader();
    reader.onload = async function(e) {
        const base64Img = e.target.result;
        const studentId = localStorage.getItem("fa_student_id");
        
        try {
            const res = await fetch(`${API}/student/${studentId}/photo_upload`, {
                method: "POST",
                headers: { 
                    "Content-Type": "application/json",
                    "session-token": sessionToken 
                },
                body: JSON.stringify({ image_b64: base64Img })
            });
            const data = await res.json();
            
            if (res.ok && data.ok) {
                // Forzar recarga de foto engañando caché
                const newUrl = `${API}/admin/student/${studentId}/photo?t=` + new Date().getTime();
                if ($("sidebar-profile-img")) { $("sidebar-profile-img").src = newUrl; $("sidebar-profile-img").style.display = "block"; }
                if ($("idcard-photo")) { $("idcard-photo").src = newUrl; $("idcard-photo").style.display = "block"; }
                
                // Ocultar botón
                if ($("upload-photo-label")) {
                    $("upload-photo-label").style.display = "none";
                }
                alert("¡Foto subida con éxito! Esta es ahora tu foto oficial permanente.");
            } else {
                alert(data.detail || "Error subiendo la imagen.");
            }
        } catch(e) {
            alert("Error de conexión al intentar subir la imagen.");
        }
    };
    reader.readAsDataURL(file);
};

// ==================== GOOGLE BOOKS API ====================
window.searchGoogleBooks = async function() {
    const query = $("gbooks-query").value.trim();
    if (!query) return;
    await fetchGoogleBooks(query);
};

async function fetchGoogleBooks(query) {
    const container = $("gbooks-results");
    const empty = $("gbooks-empty");
    container.innerHTML = "<p style='color:#aaa; grid-column:1/-1; text-align:center;'>Buscando...</p>";
    empty.style.display = "none";

    try {
        const res = await fetch(`https://www.googleapis.com/books/v1/volumes?q=${encodeURIComponent(query)}&maxResults=12&printType=books`);
        const data = await res.json();

        if (!data.items || data.items.length === 0) {
            // Fallback en caso de cuota excedida o sin resultados
            data.items = [
                { volumeInfo: { title: "Clean Code", authors: ["Robert C. Martin"], pageCount: 464, publishedDate: "2008", imageLinks: { thumbnail: "https://covers.openlibrary.org/b/isbn/9780132350884-M.jpg" }, previewLink: "https://openlibrary.org/works/OL10034255W" } },
                { volumeInfo: { title: "Python Crash Course", authors: ["Eric Matthes"], pageCount: 544, publishedDate: "2019", imageLinks: { thumbnail: "https://covers.openlibrary.org/b/isbn/9781593279288-M.jpg" }, previewLink: "https://openlibrary.org/works/OL19853685W" } },
                { volumeInfo: { title: "Design Patterns", authors: ["Erich Gamma"], pageCount: 416, publishedDate: "1994", imageLinks: { thumbnail: "https://covers.openlibrary.org/b/isbn/9780201633610-M.jpg" }, previewLink: "https://openlibrary.org/works/OL2848983W" } }
            ];
        }

        container.innerHTML = data.items.map(item => {
            const info = item.volumeInfo;
            const title = info.title || "Sin titulo";
            const authors = (info.authors || ["Autor desconocido"]).join(", ");
            const thumb = info.imageLinks?.thumbnail || info.imageLinks?.smallThumbnail || "";
            const link = info.previewLink || info.infoLink || "#";
            const pages = info.pageCount ? info.pageCount + " pags" : "";
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
        container.innerHTML = "";
        empty.textContent = "Error al conectar con Google Books. Verifica tu conexion.";
        empty.style.display = "block";
    }
}

// Cargar libros populares al inicio
setTimeout(() => {
    fetchGoogleBooks("programacion software");
}, 1500);
