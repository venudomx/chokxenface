// ==================== CONFIGURACIÓN ====================
const API = "/api";

const $ = id => document.getElementById(id);
const sessionToken = localStorage.getItem("fatoken");

// Guard: solo admins
if (!sessionToken || localStorage.getItem("farole") !== "admin") {
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
                <button class="btn-sm" style="background:var(--warning); color:#fff; border:none;" onclick="resetStudentPhoto(${st.id},'${st.nombre}')" title="Borrar foto oficial subida">Reset Foto</button>
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

async function fetchGoogleBooks(query) {
    const container = $("gbooks-results");
    const empty = $("gbooks-empty");
    if (!container || !empty) return;
    
    container.innerHTML = "<p style='color:#aaa; grid-column:1/-1; text-align:center;'>Buscando...</p>";
    empty.style.display = "none";

    try {
        const res = await fetch(`https://www.googleapis.com/books/v1/volumes?q=${encodeURIComponent(query)}&maxResults=12&printType=books`);
        const data = await res.json();

        if (!data.items || data.items.length === 0) {
            container.innerHTML = "";
            empty.textContent = "No se encontraron resultados. Intenta con otro termino.";
            empty.style.display = "block";
            return;
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

// ==================== RESETEO DE FOTO ====================
window.resetStudentPhoto = async (student_id, nombre) => {
    if (!confirm(`¿Estás seguro de borrar la foto de ${nombre}? El alumno tendrá que subir una nueva la próxima vez que inicie sesión.`)) return;
    
    try {
        const res = await fetch(`${API}/admin/student/${student_id}/photo`, {
            method: "DELETE",
            headers: { "session-token": sessionToken }
        });
        const data = await res.json();
        if (res.ok) {
            alert(data.message || "Foto eliminada con éxito.");
        } else {
            alert(data.detail || "Error al eliminar la foto.");
        }
    } catch (e) {
        alert("Error de conexión al servidor.");
    }
};

setTimeout(() => {
    fetchGoogleBooks("educacion didactica pedagogia universidad");
}, 1500);

// ==================== AGREGAR FALTA ====================
window.selectStudent = (id, nombre) => {
    $("admin-falta-id").value = id;
    $("admin-status").textContent = `Alumno seleccionado: ${nombre}`;
    $("admin-falta-id").scrollIntoView({ behavior: "smooth" });
};

$("btn-add-falta").addEventListener("click", async () => {
    const student_id = $("admin-falta-id").value;
    if (!student_id) { $("admin-status").textContent = "Selecciona un alumno de la tabla primero."; return; }

    const date = $("admin-falta-fecha").value || new Date().toISOString().split("T")[0];
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
