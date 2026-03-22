// ==================== CONFIGURACIÓN ====================
const API = "/api";

const $ = id => document.getElementById(id);
const sessionToken = localStorage.getItem("fatoken");

// Guard: solo admin supremo
if (!sessionToken || localStorage.getItem("farole") !== "admin") {
    window.location.href = "index.html";
}

$("btn-logout-master").addEventListener("click", () => {
    localStorage.clear(); window.location.href = "index.html";
});

let allStudents = [];

// ==================== CARGAR LISTA ALUMNOS ====================
async function loadMasterStudents() {
    try {
        const res = await fetch(`${API}/admin/students`, {
            headers: { "session-token": sessionToken }
        });
        if (res.status === 401 || res.status === 403) {
            localStorage.clear(); window.location.href = "index.html"; return;
        }
        const data = await res.json();
        allStudents = data.students || [];
        renderMasterTable(allStudents);
    } catch(e) { console.error(e); }
}

function renderMasterTable(students) {
    const tbody = document.querySelector("#master-table tbody");
    if (!students.length) {
        tbody.innerHTML = `<tr><td colspan="5" class="text-center muted">Sin alumnos registrados.</td></tr>`;
        return;
    }
    tbody.innerHTML = students.map(st => `
        <tr>
            <td>${st.id}</td>
            <td>${st.matricula}</td>
            <td><strong>${st.nombre}</strong></td>
            <td class="muted small">${st.carrera || "—"}</td>
            <td>
                <button class="btn-sm btn-primary" onclick="viewPhoto(${st.id}, '${st.nombre}')" style="margin-right: 5px; background:var(--primary); color:#000;">Ver Registro</button>
                <button class="btn-sm btn-danger" onclick="deleteStudent(${st.id}, '${st.nombre}')">Borrar</button>
            </td>
        </tr>
    `).join("");
}

// ==================== BÚSQUEDA ====================
window.filterMaster = (q) => {
    const lower = q.toLowerCase();
    const filtered = allStudents.filter(s =>
        s.nombre.toLowerCase().includes(lower) || s.matricula.toLowerCase().includes(lower)
    );
    renderMasterTable(filtered);
};

// ==================== BORRAR ESTUDIANTE ====================
window.deleteStudent = async (id, nombre) => {
    if(!confirm(`ATENCION: ¿Estás seguro de eliminar PERMANENTEMENTE a ${nombre}?\n\nEsto borrará su registro, su rostro de la base de datos, sus faltas y todo su historial. NO SE PUEDE DESHACER.`)) {
        return;
    }
    
    try {
        const res = await fetch(`${API}/admin/student/${id}`, {
            method: "DELETE",
            headers: { "session-token": sessionToken }
        });
        
        const data = await res.json();
        
        if (res.ok) {
            alert(data.msg || "Usuario eliminado exitosamente.");
            loadMasterStudents();
        } else {
            alert("Error al eliminar: " + (data.detail || "Desconocido"));
        }
    } catch(e) {
        alert("Error de red al intentar eliminar.");
    }
};

// ==================== VER FOTO ====================
window.viewPhoto = (id, nombre) => {
    // Popup dinámico
    const overlay = document.createElement("div");
    overlay.style.position = "fixed";
    overlay.style.inset = "0";
    overlay.style.backgroundColor = "rgba(0,0,0,0.85)";
    overlay.style.zIndex = "9999";
    overlay.style.display = "flex";
    overlay.style.flexDirection = "column";
    overlay.style.alignItems = "center";
    overlay.style.justifyContent = "center";
    overlay.style.backdropFilter = "blur(5px)";
    
    const title = document.createElement("h3");
    title.textContent = `Registro Biométrico: ${nombre}`;
    title.style.color = "#fff";
    title.style.marginBottom = "20px";
    title.style.fontWeight = "600";
    
    const img = document.createElement("img");
    // Se añade un token random para evitar cache al ver
    img.src = `${API}/admin/student/${id}/photo?t=${new Date().getTime()}`;
    img.style.maxWidth = "90%";
    img.style.maxHeight = "60vh";
    img.style.borderRadius = "12px";
    img.style.border = "2px solid rgba(255,255,255,0.2)";
    img.style.boxShadow = "0 10px 40px rgba(0,0,0,0.6)";
    
    const btnClose = document.createElement("button");
    btnClose.textContent = "Cerrar Visor";
    btnClose.className = "btn-secondary";
    btnClose.style.marginTop = "25px";
    btnClose.style.padding = "8px 24px";
    btnClose.onclick = () => document.body.removeChild(overlay);
    
    overlay.appendChild(title);
    overlay.appendChild(img);
    overlay.appendChild(btnClose);
    
    document.body.appendChild(overlay);
};

loadMasterStudents();
