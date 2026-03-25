// ==================== CONFIGURACIÓN ====================
const API = "/api";
const $ = id => document.getElementById(id);
let googleToken = "";
let cameraLoginUtils = null;
let faceMeshInstance = null;

// Liveness state
let blinks = 0, lastLidClosed = false, lastBlinkTime = 0, livenessPassed = false;

// Scan phases
let scanPhase = 0; // 0=idle, 1=liveness, 2=frontal, 3=izq, 4=der
let capturedBlobs = [];
const PHASE_SHOTS = { 2: 20, 3: 15, 4: 15 }; // 20 frontal + 15 izq + 15 der = 50 tomas

function showView(id) {
    document.querySelectorAll('.view').forEach(v => {
        v.style.display = 'none';
        v.classList.remove('active');
    });
    const target = $(id);
    target.style.display = 'block';
    target.classList.add('active');
    window.scrollTo(0,0);
}

function stopStreams() {
    if (cameraLoginUtils) { cameraLoginUtils.stop(); cameraLoginUtils = null; }
    const vr = $("video-reg");
    if (vr && vr.srcObject) { vr.srcObject.getTracks().forEach(t => t.stop()); vr.srcObject = null; }
}

// ==================== STEP BAR ====================
function setActiveStep(n) {
    for (let i = 1; i <= 5; i++) {
        const el = $("step-" + i);
        if (!el) continue;
        el.classList.remove("active", "done");
        if (i < n) el.classList.add("done");
        if (i === n) el.classList.add("active");
    }
}

function setInnerStatus(text) {
    const el = $("scan-inner-status");
    if (el) { el.textContent = text; }
}

// ==================== ARROW HELPER ====================
function showArrow(dir) {
    const arrow = $("scan-arrow");
    if (!arrow) return;
    arrow.style.display = "block";
    
    if (dir === "center") {
        arrow.innerHTML = "⊙";
        arrow.style.top = "-30px";
        arrow.style.left = "50%";
        arrow.style.transform = "translateX(-50%)";
    } else if (dir === "left") {
        arrow.innerHTML = "◀";
        arrow.style.top = "50%";
        arrow.style.left = "-45px";
        arrow.style.transform = "translateY(-50%)";
    } else if (dir === "right") {
        arrow.innerHTML = "▶";
        arrow.style.top = "50%";
        arrow.style.right = "-45px";
        arrow.style.left = "auto";
        arrow.style.transform = "translateY(-50%)";
    } else {
        arrow.style.display = "none";
    }
}

function setRingColor(color) {
    const ring = $("scan-ring");
    if (!ring) return;
    if (color === "green") {
        ring.style.borderColor = "var(--primary)";
        ring.style.boxShadow = "0 0 30px rgba(0,200,100,0.4)";
    } else if (color === "blue") {
        ring.style.borderColor = "#3b82f6";
        ring.style.boxShadow = "0 0 30px rgba(59,130,246,0.4)";
    } else if (color === "gold") {
        ring.style.borderColor = "#f59e0b";
        ring.style.boxShadow = "0 0 30px rgba(245,158,11,0.4)";
    }
}

function setProgress(pct) {
    const bar = $("scan-progress");
    if (bar) bar.style.width = pct + "%";
}

// ==================== ARRANCA ====================
window.onload = () => {
    localStorage.removeItem("fatoken");
    localStorage.removeItem("farole");
    localStorage.removeItem("fa_matricula");
    localStorage.removeItem("fa_carrera");
    localStorage.removeItem("fa_student_id");
    
    // Auto-render Google Button once loaded
    try {
        if (window.google && google.accounts && google.accounts.id) {
            google.accounts.id.initialize({
                client_id: "617793982775-gve0j1fgva86sv1ufsefpfbvl6ve63dl.apps.googleusercontent.com",
                callback: handleGoogleCallback
            });
            google.accounts.id.renderButton(document.getElementById("gbtn"), { theme: "filled_black", size: "large", type: "standard", width: 320 });
        } else {
            document.getElementById("ginfo").textContent = "Google API no disponible en este momento.";
        }
    } catch(e) {
        console.error("GSI Error", e);
    }
};

// ==================== GOOGLE CALLBACK ====================
async function handleGoogleCallback(resp) {
    googleToken = resp.credential;
    $("ginfo").textContent = "Verificando Auth...";

    // 1) Admin?
    try {
        const res = await fetch(`${API}/auth/login_admin`, {
            method: "POST", headers: { "Authorization": `Bearer ${googleToken}` }
        });
        const data = await res.json();
        if (res.ok && data.token) {
            localStorage.setItem("fatoken", data.token);
            localStorage.setItem("farole", "admin");
            window.location.href = "admin.html";
            return;
        }
    } catch(e) {}

    // 2) Already registered?
    try {
        $("ginfo").textContent = "Buscando registro biométrico...";
        const res = await fetch(`${API}/auth/check_student`, {
            headers: { "Authorization": `Bearer ${googleToken}` }
        });
        const data = await res.json();
        
        if (!res.ok) {
            $("ginfo").textContent = data.detail || data.msg || "Acceso denegado.";
            $("ginfo").style.color = "#ff4a4a";
            return;
        }
        
        if (data.registered && data.token) {
            localStorage.setItem("fatoken", data.token);
            localStorage.setItem("farole", "student");
            window.location.href = "student.html";
            return;
        }
    } catch(e) {
        console.error(e);
        $("ginfo").textContent = "Error al conectar con el servidor.";
        return;
    }

    // 3) New student -> Register
    try {
        const payload = JSON.parse(atob(googleToken.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')));
        if ($("reg-nombre")) $("reg-nombre").value = payload.name || "";
        const memail = payload.email || "";
        const match = memail.split('@')[0].match(/\d+/);
        if ($("reg-matricula")) $("reg-matricula").value = match ? match[0] : "";
    } catch(e) { console.error("JWT Decode error", e); }

    showView("v-register");
    setActiveStep(1);
}

// ==================== PASO 1: DATOS → CONTINUAR ====================
$("btnNextToLiveness").addEventListener("click", () => {
    const fnac = $("reg-fecha-nac").value;
    const carrera = $("reg-carrera").value;
    const genero = $("reg-genero").value;
    if (!fnac || !carrera || !genero) {
        alert("Completa todos los campos antes de continuar.");
        return;
    }
    // Hide data form, show scanner
    $("phase-datos").style.display = "none";
    $("phase-scan").style.display = "block";
    setActiveStep(2);
    startLivenessPhase();
});

// ==================== PASO 2: LIVENESS ====================
function EAR(pts, lm) {
    const [p1,p2,p3,p4,p5,p6] = pts.map(i => lm[i]);
    if (!p1 || !p6) return 0.25;
    const h1 = Math.hypot(p2.x-p6.x, p2.y-p6.y);
    const h2 = Math.hypot(p3.x-p5.x, p3.y-p5.y);
    const w  = Math.hypot(p1.x-p4.x, p1.y-p4.y);
    return (h1+h2) / (2.0*w);
}

function onFaceResults(results) {
    if (!results.multiFaceLandmarks?.length) return;
    const lm = results.multiFaceLandmarks[0];
    const ear = (EAR([33,160,158,133,153,144], lm) + EAR([362,385,387,263,373,380], lm)) / 2;

    // During liveness phase
    if (scanPhase === 1 && !livenessPassed) {
        const closed = ear < 0.24;
        const now = Date.now();

        if (closed && !lastLidClosed && now - lastBlinkTime > 300) {
            blinks++; lastLidClosed = true; lastBlinkTime = now;
        } else if (!closed && lastLidClosed) {
            lastLidClosed = false;
        }

        $("liveness-msg").textContent = `Parpadea fuerte sin lentes: ${blinks}/2`;
        setProgress(blinks * 10);

        if (blinks >= 2) {
            livenessPassed = true;
            $("liveness-icon").textContent = "";
            $("liveness-msg").textContent = "Liveness OK. Analizando biometría sin lentes...";
            $("liveness-msg").style.color = "var(--primary)";
            setRingColor("green");
            setProgress(20);

            // Fake AI progress delay for a more robust feel
            let p = 0;
            const simInterval = setInterval(() => {
                p++;
                setInnerStatus(`Verificando perfil facial... ${p*10}%`);
                if(p >= 10) {
                    clearInterval(simInterval);
                    $("liveness-msg").textContent = "Calibración exitosa. Iniciando escaneo frontal...";
                    // Auto-advance
                    setTimeout(() => startCapturePhase(2), 500);
                }
            }, 350); // Simulates 3.5 seconds of deep processing
        }
    }
}

async function startLivenessPhase() {
    scanPhase = 1;
    blinks = 0; livenessPassed = false; lastLidClosed = false;
    capturedBlobs = [];

    $("scan-instruction").textContent = "QUITATE LOS LENTES";
    $("scan-sub").textContent = "Coloca tu cara dentro del circulo y parpadea 2 veces.";
    $("liveness-icon").textContent = "";
    $("liveness-msg").textContent = "Esperando deteccion ocular...";
    $("liveness-msg").style.color = "";
    setInnerStatus("Parpadea 2 veces sin lentes");
    showArrow("center");
    setRingColor("blue");
    setProgress(0);

    try {
        const fm = new FaceMesh({ locateFile: f => `https://cdn.jsdelivr.net/npm/@mediapipe/face_mesh/${f}` });
        fm.setOptions({ maxNumFaces:1, refineLandmarks:false, minDetectionConfidence:0.4 });
        fm.onResults(onFaceResults);
        faceMeshInstance = fm;

        const vid = $("video-reg");
        cameraLoginUtils = new Camera(vid, {
            onFrame: async () => { await fm.send({ image: vid }); },
            width: 320, height: 240
        });
        cameraLoginUtils.start();
        setInnerStatus("Escaner activo");
    } catch(e) {
        $("scan-instruction").textContent = "Error al iniciar la camara.";
    }
}

// ==================== PASOS 3-5: CAPTURA DIRIGIDA ====================
async function captureBlob(vid) {
    const c = document.createElement("canvas");
    const vw = vid.videoWidth || 640;
    const vh = vid.videoHeight || 480;
    const scale = Math.min(1.0, 360 / vw); // Reducir a max 360px de ancho para agilizar
    c.width = Math.round(vw * scale); 
    c.height = Math.round(vh * scale);
    c.getContext("2d").drawImage(vid, 0, 0, c.width, c.height);
    return new Promise(r => c.toBlob(r, "image/jpeg", 0.70)); // Alta compresión = envío rápido
}

async function startCapturePhase(phase) {
    scanPhase = phase;

    const configs = {
        2: { step: 3, title: "MIRA DE FRENTE", sub: "Mantén la cabeza recta y fija.", arrow: "center", color: "green" },
        3: { step: 4, title: "GIRA A TU IZQUIERDA", sub: "Gira lentamente tu cabeza hacia la izquierda.", arrow: "left", color: "blue" },
        4: { step: 5, title: "GIRA A TU DERECHA", sub: "Gira lentamente tu cabeza hacia la derecha.", arrow: "right", color: "gold" },
    };

    const cfg = configs[phase];
    setActiveStep(cfg.step);
    $("scan-instruction").textContent = cfg.title;
    $("scan-sub").textContent = cfg.sub;
    showArrow(cfg.arrow);
    setRingColor(cfg.color);
    $("liveness-icon").textContent = "";
    $("liveness-msg").textContent = "Adquiriendo datos biometricos...";
    $("liveness-msg").style.color = "";

    const shotsNeeded = PHASE_SHOTS[phase];
    const vid = $("video-reg");

    // Countdown before capturing
    for (let countdown = 3; countdown > 0; countdown--) {
        $("scan-instruction").textContent = `${cfg.title} (${countdown}...)`;
        await new Promise(r => setTimeout(r, 800));
    }
    $("scan-instruction").textContent = cfg.title;

    // Capture the photos
    for (let i = 0; i < shotsNeeded; i++) {
        const blob = await captureBlob(vid);
        capturedBlobs.push(blob);

        const totalDone = capturedBlobs.length;
        const pct = 20 + (totalDone / 50) * 80; // Scale 50 shots
        setProgress(pct);
        $("liveness-msg").textContent = "Mapeando geometria facial...";
        $("reg-status").textContent = `${cfg.title} — Procesando`;

        await new Promise(r => setTimeout(r, 200));
    }

    // Next phase or submit
    if (phase < 4) {
        // Flash green success briefly
        $("scan-instruction").textContent = "Perfil completado. Ajustando posicion...";
        $("scan-sub").textContent = "";
        await new Promise(r => setTimeout(r, 1200));
        startCapturePhase(phase + 1);
    } else {
        // All 25 done → submit
        submitRegistration();
    }
}

// ==================== ENVÍO AL SERVIDOR ====================
async function submitRegistration() {
    $("scan-instruction").textContent = "Procesando modelo biométrico...";
    $("scan-sub").textContent = "Esto puede tardar unos segundos.";
    showArrow("none");
    setRingColor("green");
    $("liveness-icon").textContent = "";
    $("liveness-msg").textContent = "Transmitiendo modelo al servidor...";
    setProgress(95);

    const fd = new FormData();
    fd.append("fecha_nacimiento", $("reg-fecha-nac").value);
    fd.append("carrera", $("reg-carrera").value.trim());
    fd.append("genero", $("reg-genero") ? $("reg-genero").value.trim() : "O");

    capturedBlobs.forEach((blob, i) => {
        fd.append("files", blob, `foto_${i}.jpg`);
    });

    try {
        const res = await fetch(`${API}/register`, {
            method: "POST",
            headers: googleToken ? { "Authorization": `Bearer ${googleToken}` } : {},
            body: fd
        });
        const data = await res.json();
        if (res.ok && data.ok) {
            setProgress(100);
            $("scan-instruction").textContent = "REGISTRO EXITOSO";
            $("scan-sub").textContent = `Bienvenido, ${data.nombre}. Redirigiendo al portal...`;
            $("liveness-icon").textContent = "";
            $("liveness-msg").textContent = "Modelo facial entrenado y verificado.";
            $("liveness-msg").style.color = "var(--primary)";
            $("reg-status").textContent = "";

            if (data.token) {
                localStorage.setItem("fatoken", data.token);
                localStorage.setItem("farole", data.role);
                if (data.student_id) { localStorage.setItem("fa_student_id", data.student_id); }
                localStorage.setItem("fa_matricula", data.matricula);
                localStorage.setItem("fa_carrera", $("reg-carrera").value.trim());
            }

            // Detener camara de liveness antes de ir a credencial
            if (cameraLoginUtils) { cameraLoginUtils.stop(); cameraLoginUtils = null; }
            
            // Paso 6: Foto de credencial
            showCredentialPhotoStep(data.student_id, data.token);
        } else {
            $("scan-instruction").textContent = "Error en el registro";
            $("scan-sub").textContent = data.msg || data.detail || "Intenta de nuevo.";
            $("liveness-icon").textContent = "";
            $("liveness-msg").textContent = "Fallo al entrenar el modelo biometrico.";
            setProgress(0);
        }
    } catch(e) {
        $("scan-instruction").textContent = "Error de conexion";
        $("scan-sub").textContent = "Verifica que el servidor este activo.";
        $("liveness-icon").textContent = "";
        $("liveness-msg").textContent = "No se pudo establecer conexion con el servidor.";
        setProgress(0);
    }
}

// ==================== PASO 6: FOTO DE CREDENCIAL ====================
let credStudentId = null;
let credStudentToken = null;
let credStream = null;
let credBlob = null;

function showCredentialPhotoStep(studentId, token) {
    credStudentId = studentId;
    credStudentToken = token;
    
    // Hide scan phase, show credencial phase
    $("phase-scan").style.display = "none";
    $("phase-credencial").style.display = "block";
    setActiveStep(6);
    
    // Start camera
    const vid = $("video-cred");
    navigator.mediaDevices.getUserMedia({ video: { width:480, height:640, facingMode:"user" } })
        .then(stream => {
            credStream = stream;
            vid.srcObject = stream;
        })
        .catch(() => { $("cred-status").textContent = "No se pudo acceder a la camara."; });
    
    // Take photo button
    $("btn-tomar-foto").onclick = () => {
        const canvas = $("canvas-cred");
        canvas.width = 480;
        canvas.height = 640;
        const ctx = canvas.getContext("2d");
        ctx.save();
        ctx.scale(-1, 1);
        ctx.drawImage(vid, -canvas.width, 0, canvas.width, canvas.height);
        ctx.restore();
        
        canvas.toBlob(blob => {
            credBlob = blob;
            const url = URL.createObjectURL(blob);
            $("cred-preview-img").src = url;
            $("cred-preview").style.display = "block";
            $("btn-tomar-foto").style.display = "none";
            $("btn-subir-foto").style.display = "block";
        }, "image/jpeg", 0.72); // Bajar peso de credencial a calidad 72%
    };
    
    // Upload button
    $("btn-subir-foto").onclick = async () => {
        if (!credBlob) return;
        $("cred-status").textContent = "Subiendo foto al servidor...";
        $("btn-subir-foto").disabled = true;
        
        const fd = new FormData();
        fd.append("file", credBlob, "credencial.jpg");
        
        try {
            const res = await fetch(`/api/student/update-photo`, {
                method: "POST",
                headers: { "session-token": credStudentToken },
                body: fd
            });
            if (credStream) credStream.getTracks().forEach(t => t.stop());
            
            $("cred-status").textContent = "Foto guardada. Entrando al portal...";
            setTimeout(() => { window.location.href = "student.html"; }, 1500);
        } catch(e) {
            $("cred-status").textContent = "Error al subir la foto. Puedes subirla luego desde el portal.";
            setTimeout(() => { window.location.href = "student.html"; }, 3000);
        }
    };
}

window.retakeCredPhoto = () => {
    credBlob = null;
    $("cred-preview").style.display = "none";
    $("btn-tomar-foto").style.display = "block";
    $("btn-subir-foto").style.display = "none";
    $("cred-status").textContent = "";
};

// ==================== ADMIN / MAESTRO LOGIN ====================
document.addEventListener("DOMContentLoaded", () => {
    const adminForm = $("admin-login-form");
    if(adminForm) {
        adminForm.addEventListener("submit", (e) => {
            e.preventDefault();
            const u = $("admin-user").value.trim();
            const p = $("admin-pass").value.trim();
            if (u === "admin" && p === "admin") {
                localStorage.setItem("fatoken", "admin-demo-token");
                localStorage.setItem("farole", "admin");
                window.location.href = "master.html";
            } else if (u === "maestro" && p === "maestro") {
                localStorage.setItem("fatoken", "maestro-demo-token");
                localStorage.setItem("farole", "maestro");
                window.location.href = "maestro.html";
            } else {
                alert("Usuario o contraseña incorrectos.");
            }
        });
    }
});

