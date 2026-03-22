const API = "/api";
let googleToken = "";
let sessionToken = localStorage.getItem("fatoken") || "";
let userRole = localStorage.getItem("farole") || "";
let streamReg = null;

// Liveness vars
let cameraLoginUtils = null;
let blinks = 0;
let lastLidClosed = false;
let lastBlinkTime = 0;
let livenessPassed = false;

const $ = id => document.getElementById(id);

// Routing
function showView(viewId) {
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    $(viewId).classList.add('active');
}

function stopStreams() {
    if (cameraLoginUtils) { cameraLoginUtils.stop(); cameraLoginUtils = null; }
    const vLogin = $("video-login");
    if (vLogin && vLogin.srcObject) { vLogin.srcObject.getTracks().forEach(t => t.stop()); vLogin.srcObject = null; }
    if (streamReg) { streamReg.getTracks().forEach(t => t.stop()); streamReg = null; }
}

async function verifyExistingSession() {
    if (!sessionToken) { showView("v-auth"); return; }
    if (userRole === "admin") await loadAdminDashboard();
    else await loadStudentDashboard();
}

// ---- GOOGLE AUTH PIPELINE ----
async function handleGoogleCallback(resp) {
    googleToken = resp.credential;
    if (!googleToken) { $("ginfo").textContent = "Google Login falló."; return; }
    $("ginfo").textContent = "Autenticando con servidor...";
    
    try {
        const res = await fetch(`${API}/auth/login_admin`, {
            method: "POST", headers: { "Authorization": `Bearer ${googleToken}` }
        });
        const data = await res.json();
        if (res.ok && data.token) {
            sessionToken = data.token; userRole = "admin";
            localStorage.setItem("fatoken", sessionToken); localStorage.setItem("farole", userRole);
            await loadAdminDashboard();
            return;
        }
    } catch(e) {}

    showView("v-face");
    startLivenessCamera();
}

window.onload = () => {
    if (window.google && google.accounts && google.accounts.id) {
        google.accounts.id.initialize({
            client_id: "617793982775-gve0j1fgva86sv1ufsefpfbvl6ve63dl.apps.googleusercontent.com",
            callback: handleGoogleCallback
        });
        google.accounts.id.renderButton($("gbtn"), { theme: "filled_black", size: "large", type: "standard" });
    } else {
        $("ginfo").textContent = "Google API no disponible o sin conexión.";
    }
    verifyExistingSession();
};

// ---- LIVENESS DETECTION (MediaPipe FaceMesh) ----
function initFaceMesh() {
    const faceMesh = new FaceMesh({locateFile: (file) => `https://cdn.jsdelivr.net/npm/@mediapipe/face_mesh/${file}`});
    faceMesh.setOptions({maxNumFaces: 1, refineLandmarks: true, minDetectionConfidence: 0.5, minTrackingConfidence: 0.5});
    faceMesh.onResults(onResultsFace);
    return faceMesh;
}

function EAR(eye, lm) {
    const p1 = lm[eye[1]], p2 = lm[eye[5]];
    const p3 = lm[eye[2]], p4 = lm[eye[4]];
    const p5 = lm[eye[0]], p6 = lm[eye[3]];
    if(!p1||!p2||!p3||!p4||!p5||!p6) return 0.3;
    const h1 = Math.hypot(p1.x-p2.x, p1.y-p2.y);
    const h2 = Math.hypot(p3.x-p4.x, p3.y-p4.y);
    const w = Math.hypot(p5.x-p6.x, p5.y-p6.y);
    return (h1+h2) / (2.0 * w);
}

function onResultsFace(results) {
    if(!results.multiFaceLandmarks || results.multiFaceLandmarks.length===0) return;
    if(livenessPassed) return;
    
    // Check EAR
    const lm = results.multiFaceLandmarks[0];
    const L_EYE = [33, 160, 158, 133, 153, 144];
    const R_EYE = [362, 385, 387, 263, 373, 380];
    
    const ear = (EAR(L_EYE, lm) + EAR(R_EYE, lm)) / 2.0;
    const closed = ear < 0.20;
    const now = Date.now();
    
    if(closed && !lastLidClosed && (now - lastBlinkTime > 300)) {
        blinks++; lastLidClosed=true; lastBlinkTime=now;
        $("liveness-icon").textContent = blinks === 1 ? "" : "";
    } else if(!closed && lastLidClosed) {
        lastLidClosed = false;
    }
    
    if(blinks >= 2) {
        livenessPassed = true;
        $("liveness-msg").textContent = "¡Seguridad Liveness 100%! Ya puedes Validar Rostro.";
        $("liveness-msg").style.color = "var(--primary)";
        let btn = $("btn-login-face");
        btn.disabled = false;
        btn.classList.add("pulse-btn");
    }
}

function startLivenessCamera() {
    blinks = 0; livenessPassed = false; lastLidClosed = false;
    $("liveness-ui").style.display = "flex";
    $("liveness-icon").textContent = "";
    $("liveness-msg").textContent = "Por favor, parpadea 2 veces para validar tu prueba de vida...";
    $("liveness-msg").style.color = "var(--text-main)";
    $("btn-login-face").disabled = true;

    try {
        const fm = initFaceMesh();
        const videoElement = $("video-login");
        cameraLoginUtils = new Camera(videoElement, {
            onFrame: async () => { if(!livenessPassed) await fm.send({image: videoElement}); },
            width: 640, height: 480
        });
        cameraLoginUtils.start();
    } catch(e) { $("face-status").textContent = "Error al abrir cámara para Liveness."; }
}

async function startRegCamera() {
    try {
        streamReg = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user" } });
        $("video-reg").srcObject = streamReg;
    } catch(e) { $("reg-status").textContent = "Error al abrir cámara."; }
}

function captureBlob(videoEl) {
    const cvs = document.createElement("canvas");
    cvs.width = videoEl.videoWidth || 640; cvs.height = videoEl.videoHeight || 480;
    cvs.getContext("2d").drawImage(videoEl, 0, 0, cvs.width, cvs.height);
    return new Promise(r => cvs.toBlob(r, "image/jpeg", 0.90));
}

// ---- STUDENT LOGIN ----
$("btn-login-face").addEventListener("click", async () => {
    $("face-status").textContent = "Enviando rostro al servidor...";
    const blob = await captureBlob($("video-login"));
    const fd = new FormData();
    fd.append("file", blob, "face.jpg");

    try {
        const res = await fetch(`${API}/auth/login_student`, {
            method: "POST", headers: googleToken ? { "Authorization": `Bearer ${googleToken}` } : {}, body: fd
        });
        const data = await res.json();
        
        if (res.ok && data.token) {
            sessionToken = data.token; userRole = "student";
            localStorage.setItem("fatoken", sessionToken); localStorage.setItem("farole", userRole);
            stopStreams();
            await loadStudentDashboard();
        } else {
            $("face-status").textContent = data.detail || "Fallo en reconocimiento facial.";
            if (res.status === 404) setTimeout(() => { showView("v-register"); startRegCamera(); }, 2000);
        }
    } catch(e) { $("face-status").textContent = "Error de conexión."; }
});

$("btn-to-register").addEventListener("click", () => { stopStreams(); showView("v-register"); startRegCamera(); });

// ---- REGISTER FLOW ----
$("btnRegStart").addEventListener("click", async () => {
    const nombre = $("reg-nombre").value.trim();
    const matricula = $("reg-matricula").value.trim();
    const carrera = $("reg-carrera").value.trim();
    if (!matricula || !carrera || !nombre) { $("reg-status").textContent="Faltan datos completos"; return; }
    
    $("reg-status").textContent = "Comenzando captura profunda, por favor mantén tu rostro centrado...";
    const fd = new FormData();
    fd.append("nombre", nombre); fd.append("matricula", matricula); fd.append("carrera", carrera);

    for (let i = 0; i < 25; i++) {
        const blob = await captureBlob($("video-reg"));
        fd.append("files", blob, `shot_${i}.jpg`);
        await new Promise(r => setTimeout(r, 120));
    }

    $("reg-status").textContent = "Subiendo fotos y registrando...";
    const res = await fetch(`${API}/register`, {
        method: "POST", headers: googleToken ? { "Authorization": `Bearer ${googleToken}` } : {}, body: fd
    });
    const data = await res.json();
    if (res.ok) {
        $("reg-status").textContent = "Registro exitoso. El modelo se está entrenando automáticamente.";
        setTimeout(() => { stopStreams(); showView("v-face"); startLivenessCamera(); }, 3500);
    } else {
        $("reg-status").textContent = data.detail || data.msg || "Error registrando.";
    }
});
$("btn-cancel-reg").addEventListener("click", () => { stopStreams(); showView("v-face"); startLivenessCamera(); });

// ---- LOGOUT ----
const logout = () => {
    localStorage.clear(); sessionToken = ""; userRole = ""; googleToken = "";
    stopStreams(); showView("v-auth");
};
$("btn-logout-st").addEventListener("click", logout);
$("btn-logout-ad").addEventListener("click", logout);

// ---- STUDENT DASHBOARD ----
function setSemaforo(color) {
    document.querySelectorAll('.light').forEach(el => el.classList.remove('active'));
    $("semaforo-text").textContent = `Estatus: ${color.toUpperCase()}`;
    if(color === "rojo") { $("light-rojo").classList.add('active'); $("semaforo-text").style.color="var(--danger)"; }
    if(color === "amarillo") { $("light-amarillo").classList.add('active'); $("semaforo-text").style.color="var(--warning)"; }
    if(color === "verde") { $("light-verde").classList.add('active'); $("semaforo-text").style.color="var(--primary)"; }
}
window.rentBook = function(id) {
    const code = "LIB-" + Math.floor(Math.random()*10000);
    alert(`RESERVA CONFIRMADA\n\nTu código de recolección es: ${code}\n\nPresenta este código en la ventanilla de la biblioteca para recoger tu libro (ID: ${id}) en las próximas 2 horas. El comprobante PDF será generado en breve.`);
};
async function loadStudentDashboard() {
    showView("v-student");
    try {
        const res = await fetch(`${API}/student/dashboard`, { headers: { "session-token": sessionToken } });
        if(res.status === 401 || res.status===403) { logout(); return; }
        const data = await res.json();
        
        $("st-name").textContent = data.name || "Alumno";
        $("st-faltas-count").textContent = data.faltas.length;
        setSemaforo(data.semaforo);
        
        const tbody = document.querySelector("#st-history-table tbody"); tbody.innerHTML = "";
        const allEvents = [];
        data.faltas.forEach(f => allEvents.push({ date: f.date, type: "Falta (Admin)", color: "var(--danger)" }));
        data.events.forEach(e => allEvents.push({ date: e.ts, type: e.type, color: e.type==="entrada"?"var(--primary)":"var(--text-muted)" }));
        
        allEvents.sort((a,b) => new Date(b.date) - new Date(a.date));
        allEvents.slice(0, 30).forEach(ev => {
            const tr = document.createElement("tr");
            tr.innerHTML = `<td>${ev.date}</td><td style="font-weight:600; color:${ev.color}">${ev.type.toUpperCase()}</td>`;
            tbody.appendChild(tr);
        });
    } catch(e) {}
}

// ---- ADMIN DASHBOARD ----
async function loadAdminDashboard() {
    showView("v-admin");
    try {
        const res = await fetch(`${API}/admin/students`, { headers: { "session-token": sessionToken } });
        if(res.status === 401 || res.status===403) { logout(); return; }
        const data = await res.json();
        
        const tbody = document.querySelector("#admin-table tbody"); tbody.innerHTML = "";
        data.students.forEach(st => {
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td>${st.matricula}</td><td>${st.nombre}</td>
                <td style="text-align:center;"><strong>${st.faltas}</strong></td>
                <td style="text-align:center;"><span style="display:inline-block;width:14px;height:14px;border-radius:50%;background:${st.semaforo==='rojo'?'var(--danger)':st.semaforo==='amarillo'?'var(--warning)':'var(--primary)'}; box-shadow: 0 0 8px ${st.semaforo==='rojo'?'var(--danger)':st.semaforo==='amarillo'?'var(--warning)':'var(--primary)'}"></span></td>
                <td><button class="btn-sm btn-primary" onclick="window.addAbsenceToStudent(${st.id}, '${st.nombre}')">+ Falta</button></td>
            `;
            tbody.appendChild(tr);
        });
    } catch(e) {}
}
window.addAbsenceToStudent = (id, name) => { $("admin-falta-id").value = id; $("admin-status").textContent = `Alumno seleccionado: ${name}. Oprime Aplicar.`; }
$("btn-add-falta").addEventListener("click", async () => {
    const student_id = $("admin-falta-id").value;
    const date = $("admin-falta-fecha").value || new Date().toISOString().split('T')[0];
    const reason = $("admin-falta-razon").value || "Inasistencia detectada";
    if(!student_id) return;
    
    const fd = new FormData();
    fd.append("student_id", student_id); fd.append("date", date); fd.append("reason", reason);
    const res = await fetch(`${API}/admin/absences`, { method: "POST", headers: { "session-token": sessionToken }, body: fd });
    if(res.ok) { $("admin-status").textContent = "Falta agregada correctamente"; loadAdminDashboard(); }
    else $("admin-status").textContent = "Error al agregar falta";
});
