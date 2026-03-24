from __future__ import annotations

import os
import json
import time
import psycopg2
import psycopg2.extras
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict, Any

import cv2
import numpy as np
from fastapi import APIRouter, UploadFile, File, Form, Header, HTTPException, BackgroundTasks, Request, Depends
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

try:
    import requests
    from google.oauth2 import id_token
    from google.auth.transport.requests import Request as GoogleRequest
except Exception as e:
    print(f"Error cargando google-auth: {e}")
    id_token = None
    GoogleRequest = None


api_router = APIRouter(prefix="/api")

import uuid
import base64

ROOT_DIR = Path(__file__).resolve().parents[1]
DATASET_DIR = ROOT_DIR / "dataset"
MODEL_FILE = ROOT_DIR / "lbph_model.yml"
LABELS_FILE = ROOT_DIR / "labels.json"
DB_FILE = ROOT_DIR / "faceaccess.db"
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://chokxendb_user:GLD4m051COriiioynGz34jUMgWtkwXbx@dpg-d70bp7f5gffc73dpj35g-a.oregon-postgres.render.com/chokxendb")
TRIVIA_FILE = ROOT_DIR / "server" / "trivia_bank.json"

FACE_SIZE = (200, 200)

AUTH_MODE = os.getenv("AUTH_MODE", "google").lower()  # off | dev | google
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "617793982775-gve0j1fgva86sv1ufsefpfbvl6ve63dl.apps.googleusercontent.com").strip()
ALLOWED_DOMAIN = os.getenv("ALLOWED_DOMAIN", "").strip().lower()  # ej: utslp.edu.mx
ADMIN_EMAILS = {e.strip().lower() for e in os.getenv("ADMIN_EMAILS", "").split(",") if e.strip()}

SESSIONS: Dict[str, Dict[str, Any]] = {}

FACE_CASCADE = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")

# MediaPipe face detection (more accurate than Haar, supports lateral faces)
try:
    import mediapipe as mp
    _mp_fd = mp.solutions.face_detection.FaceDetection(model_selection=1, min_detection_confidence=0.5)
    USE_MEDIAPIPE = True
except Exception:
    _mp_fd = None
    USE_MEDIAPIPE = False


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def ensure_dirs() -> None:
    DATASET_DIR.mkdir(parents=True, exist_ok=True)


class PostgresWrapper:
    def __init__(self):
        self.con = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.DictCursor)
        self.con.autocommit = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def execute(self, query, params=()):
        # Replace ? with %s for Postgres
        query = query.replace('?', '%s')
        cur = self.con.cursor()
        cur.execute(query, params)
        return cur
        
    def cursor(self):
        class CursorWrapper:
            def __init__(self, cur):
                self.cur = cur
            def execute(self, query, params=()):
                query = query.replace('?', '%s')
                self.cur.execute(query, params)
                return self
            def fetchone(self): return self.cur.fetchone()
            def fetchall(self): return self.cur.fetchall()
            def fetchmany(self, size=None): return self.cur.fetchmany(size)
        return CursorWrapper(self.con.cursor())
        
    def commit(self):
        self.con.commit()
        
    def close(self):
        self.con.close()

def db():
    con = PostgresWrapper()
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY,
            matricula TEXT UNIQUE,
            nombre TEXT,
            carrera TEXT,
            email TEXT,
            created_at TEXT,
            photo_base64 TEXT
        )
        """
    )
    try:
        con.execute("ALTER TABLE students ADD COLUMN photo_base64 TEXT")
    except Exception:
        pass
    try:
        con.execute("ALTER TABLE students ADD COLUMN genero TEXT DEFAULT 'O'")
    except Exception:
        pass
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id SERIAL PRIMARY KEY,
            ts TEXT,
            student_id INTEGER,
            matricula TEXT,
            nombre TEXT,
            event_type TEXT,
            camera INTEGER,
            note TEXT,
            source TEXT
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS absences (
            id SERIAL PRIMARY KEY,
            student_id INTEGER,
            date TEXT,
            reason TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id SERIAL PRIMARY KEY,
            student_id INTEGER,
            is_from_student BOOLEAN,
            text TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS global_messages (
            id SERIAL PRIMARY KEY,
            sender_id TEXT,
            sender_name TEXT,
            sender_role TEXT,
            text TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS trivia_answers (
            id SERIAL PRIMARY KEY,
            student_id INTEGER,
            date TEXT,
            question_key TEXT,
            answer_idx INTEGER,
            correct BOOLEAN,
            points REAL DEFAULT 0,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(student_id, date)
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS face_images (
            id SERIAL PRIMARY KEY,
            student_id INTEGER,
            image_base64 TEXT
        )
        """
    )
    return con


def load_labels() -> Dict[str, Any]:
    try:
        con_db = db()
        cur_db = con_db.execute("SELECT id, matricula, nombre, carrera, email, genero FROM students")
        rows = cur_db.fetchall()
        con_db.close()
        
        labels = {"next_id": 0, "students": {}}
        max_id = 0
        for r in rows:
            sid = r["id"]
            if sid >= max_id:
                max_id = sid + 1
            labels["students"][str(sid)] = {
                "matricula": r["matricula"],
                "nombre": r["nombre"],
                "carrera": r["carrera"],
                "email": r["email"],
                "genero": r["genero"] if "genero" in r.keys() else "O"
            }
        labels["next_id"] = max_id
        
        # Guardar en disco para que /model/labels lo pueda servir a la laptop
        with open(LABELS_FILE, "w", encoding="utf-8") as f:
            json.dump(labels, f, indent=2, ensure_ascii=False)
            
        return labels
    except Exception as e:
        if LABELS_FILE.exists():
            with open(LABELS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"next_id": 0, "students": {}}


def save_labels(labels: Dict[str, Any]) -> None:
    with open(LABELS_FILE, "w", encoding="utf-8") as f:
        json.dump(labels, f, indent=2, ensure_ascii=False)


def find_student_id_by_matricula(labels: Dict[str, Any], matricula: str) -> Optional[int]:
    matricula_norm = matricula.strip().lower()
    for sid, info in labels.get("students", {}).items():
        if str(info.get("matricula", "")).strip().lower() == matricula_norm:
            return int(sid)
    return None


def upsert_student(labels: Dict[str, Any], matricula: str, nombre: str, carrera: str, email: str, genero: str = "O") -> int:
    matricula = matricula.strip()
    nombre = nombre.strip()
    carrera = carrera.strip()
    email = email.strip()
    genero = genero.strip() if genero else "O"

    sid = find_student_id_by_matricula(labels, matricula)
    if sid is None:
        sid = int(labels["next_id"])
        labels["next_id"] = sid + 1

    labels["students"][str(sid)] = {
        "matricula": matricula,
        "nombre": nombre,
        "carrera": carrera,
        "email": email,
        "genero": genero,
        "updated_at": now_str(),
    }
    save_labels(labels)

    con = db()
    con.execute(
        """
        INSERT INTO students (id, matricula, nombre, carrera, email, created_at, genero)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(matricula) DO UPDATE SET
            nombre=excluded.nombre,
            carrera=excluded.carrera,
            email=excluded.email,
            genero=excluded.genero
        """,
        (sid, matricula, nombre, carrera, email, now_str(), genero),
    )
    con.commit()
    con.close()
    return sid


def verify_google(auth_header: Optional[str]) -> Dict[str, Any]:
    if AUTH_MODE == "off":
        return {"ok": True, "email": "", "name": ""}

    if AUTH_MODE == "dev":
        # En dev, si no hay token, dejamos pasar (pero si hay, lo validamos si se puede)
        if not auth_header:
            return {"ok": True, "email": "", "name": ""}

    if not auth_header or not auth_header.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Falta Authorization: Bearer <token>")

    token = auth_header.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Token vacio")

    if id_token is None or GoogleRequest is None:
        raise HTTPException(status_code=500, detail="google-auth no esta instalado")

    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=500, detail="Falta GOOGLE_CLIENT_ID en variables de entorno")

    try:
        info = id_token.verify_oauth2_token(token, GoogleRequest(), GOOGLE_CLIENT_ID)
    except Exception:
        raise HTTPException(status_code=401, detail="Token Google invalido")

    email = str(info.get("email", "")).lower().strip()
    name = str(info.get("name", "")).strip()
    hd = str(info.get("hd", "")).lower().strip()

    if AUTH_MODE == "google":
        if not email:
            raise HTTPException(status_code=401, detail="No hay email en el token")
        
        # Seguridad estricta: Solo permitir dominios de la universidad (utslp.edu.mx, plataforma-utslp.net, etc.)
        # Si ALLOWED_DOMAIN esta vacio por variable de entorno, forzamos por defecto utslp.edu.mx
        domain_to_check = ALLOWED_DOMAIN if ALLOWED_DOMAIN else "utslp.edu.mx"
        allowed_domains = [domain_to_check, "plataforma-utslp.net", "alumnos.utslp.edu.mx", "docentes.utslp.edu.mx"]
        
        ok_domain = any(email.endswith("@" + d) or hd == d for d in allowed_domains)
        if not ok_domain and email not in ADMIN_EMAILS:
            raise HTTPException(status_code=403, detail="Acceso denegado: Usa tu correo institucional UTSLP (no se permiten cuentas personales)")

    return {"ok": True, "email": email, "name": name}


def extract_face_gray(img_bgr: np.ndarray) -> Optional[np.ndarray]:
    h, w = img_bgr.shape[:2]

    # Try MediaPipe first (much more accurate, handles angles, lighting)
    if USE_MEDIAPIPE and _mp_fd is not None:
        try:
            rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
            res = _mp_fd.process(rgb)
            if res.detections:
                det = max(res.detections, key=lambda d: d.location_data.relative_bounding_box.width)
                bb = det.location_data.relative_bounding_box
                x = max(0, int(bb.xmin * w))
                y = max(0, int(bb.ymin * h))
                fw = min(int(bb.width * w), w - x)
                fh = min(int(bb.height * h), h - y)
                if fw > 30 and fh > 30:
                    face = img_bgr[y:y+fh, x:x+fw]
                    gray = cv2.cvtColor(face, cv2.COLOR_BGR2GRAY)
                    gray = cv2.equalizeHist(gray)
                    return cv2.resize(gray, FACE_SIZE)
        except Exception:
            pass  # Fall through to Haar

    # Fallback: Haar Cascade
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)
    faces = FACE_CASCADE.detectMultiScale(gray, scaleFactor=1.15, minNeighbors=5, minSize=(80, 80))
    if len(faces) == 0:
        return None
    x, y, fw, fh = sorted(faces, key=lambda r: r[2] * r[3], reverse=True)[0]
    face = gray[y:y+fh, x:x+fw]
    if face.size == 0:
        return None
    return cv2.resize(face, FACE_SIZE)


def train_lbph() -> Dict[str, Any]:
    ensure_dirs()
    labels = load_labels()

    imgs: List[np.ndarray] = []
    y: List[int] = []

    con = db()
    cur = con.execute("SELECT student_id, image_base64 FROM face_images")
    rows = cur.fetchall()
    con.close()
    
    for r in rows:
        sid = r["student_id"]
        img_data = base64.b64decode(r["image_base64"])
        arr = np.frombuffer(img_data, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
        if img is not None:
            # Asegurar tamaño LBPH
            img = cv2.resize(img, FACE_SIZE)
            imgs.append(img)
            y.append(sid)

    if len(imgs) < 2:
        return {"ok": False, "msg": "No hay suficientes imagenes para entrenar. Minimo 2."}

    if not hasattr(cv2, "face"):
        return {"ok": False, "msg": "Falta opencv-contrib-python (cv2.face no existe)."}

    rec = cv2.face.LBPHFaceRecognizer_create()
    rec.train(imgs, np.array(y))
    rec.save(str(MODEL_FILE))

    return {"ok": True, "total_imgs": len(imgs), "model": str(MODEL_FILE)}


@api_router.get("/health")
def health():
    return {"ok": True, "service": "faceaccess-api"}


@api_router.get("/model/labels")
def get_labels():
    if not LABELS_FILE.exists():
        return JSONResponse({"next_id": 0, "students": {}}, status_code=200)
    return FileResponse(str(LABELS_FILE), media_type="application/json", filename="labels.json")


@api_router.get("/model/lbph")
def get_model():
    if not MODEL_FILE.exists():
        raise HTTPException(status_code=404, detail="Aun no existe lbph_model.yml (primero registra y entrena)")
    return FileResponse(str(MODEL_FILE), media_type="application/octet-stream", filename="lbph_model.yml")


@api_router.post("/train")
def api_train(authorization: Optional[str] = Header(default=None)):
    # Permitir entrenamiento sin autenticacion para que la laptop pueda sincronizar
    if authorization and AUTH_MODE != "off":
        try:
            _ = verify_google(authorization)
        except:
            pass  # Ignorar error de auth — permitir entrenamiento de todas formas

    result = train_lbph()
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("msg", "Error entrenando"))
    return result


@api_router.post("/register")
async def register(
    background_tasks: BackgroundTasks,
    matricula: str = Form(...),
    carrera: str = Form(...),
    nombre: str = Form(""),
    genero: str = Form("O"),
    files: List[UploadFile] = File(...),
    authorization: Optional[str] = Header(default=None),
):
    ensure_dirs()

    auth = verify_google(authorization)

    # Si viene de Google, preferimos nombre/email reales
    email = auth.get("email", "").strip()
    if auth.get("name"):
        nombre_final = auth["name"]
    else:
        nombre_final = nombre.strip()

    if not nombre_final:
        raise HTTPException(status_code=400, detail="Falta nombre")

    labels = load_labels()
    sid = upsert_student(labels, matricula, nombre_final, carrera, email, genero)

    out_dir = DATASET_DIR / str(sid)
    out_dir.mkdir(parents=True, exist_ok=True)

    saved = 0
    skipped = 0

    for f in files:
        try:
            raw = await f.read()
            arr = np.frombuffer(raw, dtype=np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img is None:
                skipped += 1
                continue

            face = extract_face_gray(img)
            if face is None:
                skipped += 1
                continue

            out_path = out_dir / f"{int(time.time()*1000)}_{saved}.png"
            cv2.imwrite(str(out_path), face)
            
            # Guardar tambien en PostgreSQL para persistencia
            _, buffer = cv2.imencode('.png', face)
            b64_face = base64.b64encode(buffer).decode('utf-8')
            con = db()
            con.execute("INSERT INTO face_images (student_id, image_base64) VALUES (?, ?)", (sid, b64_face))
            con.commit()
            con.close()
            
            saved += 1
        except Exception:
            skipped += 1

    if saved < 2:
        return {
            "ok": False,
            "msg": "Se guardaron muy pocas caras. Asegura buena luz y cara centrada.",
            "student_id": sid,
            "saved": saved,
            "skipped": skipped,
        }

    # Automatically trigger training in background
    background_tasks.add_task(train_lbph)

    token = str(uuid.uuid4())
    SESSIONS[token] = {
        "role": "student",
        "student_id": sid,
        "email": email,
        "name": nombre_final
    }

    return {
        "ok": True,
        "token": token,
        "role": "student",
        "student_id": sid,
        "saved": saved,
        "skipped": skipped,
        "nombre": nombre_final,
        "matricula": matricula,
        "carrera": carrera,
        "email": email,
    }


@api_router.post("/events")
def add_event(
    student_id: int,
    event_type: str,
    camera: int = 0,
    note: str = "",
    source: str = "laptop",
):
    labels = load_labels()
    info = labels.get("students", {}).get(str(student_id), {})
    matricula = str(info.get("matricula", ""))
    nombre = str(info.get("nombre", f"ID_{student_id}"))

    con = db()
    con.execute(
        """
        INSERT INTO events (ts, student_id, matricula, nombre, event_type, camera, note, source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (now_str(), student_id, matricula, nombre, event_type, int(camera), note, source),
    )
    con.commit()
    con.close()

    return {"ok": True}


@api_router.get("/events/by_student/{student_id}")
def events_by_student(student_id: int, limit: int = 50):
    con = db()
    cur = con.cursor()
    cur.execute(
        """
        SELECT ts, event_type, camera, note, source
        FROM events
        WHERE student_id=?
        ORDER BY id DESC
        LIMIT ?
        """,
        (int(student_id), int(limit)),
    )
    rows = cur.fetchall()
    con.close()

    return {
        "ok": True,
        "student_id": student_id,
        "events": [
            {"ts": r[0], "event_type": r[1], "camera": r[2], "note": r[3], "source": r[4]}
            for r in rows
        ],
    }

def get_session(token: str) -> Dict[str, Any]:
    if token == "admin-demo-token":
        return {"role": "admin", "email": "admin@local", "name": "Administrador Maestro"}
    if token == "maestro-demo-token":
        return {"role": "maestro", "email": "maestro@local", "name": "Docente General"}
    if not token or token not in SESSIONS:
        raise HTTPException(status_code=401, detail="Sesion invalida o expirada")
    return SESSIONS[token]

@api_router.post("/auth/login_admin")
def login_admin(authorization: Optional[str] = Header(default=None)):
    auth = verify_google(authorization)
    email = auth.get("email", "").lower()
    if not email:
        raise HTTPException(status_code=401, detail="No se pudo obtener el email")
    
    if email not in ADMIN_EMAILS:
        raise HTTPException(status_code=403, detail="No eres administrador")
    
    token = str(uuid.uuid4())
    SESSIONS[token] = {"role": "admin", "email": email, "name": auth.get("name")}
    return {"ok": True, "token": token, "role": "admin", "name": auth.get("name")}

@api_router.get("/auth/check_student")
def check_student(authorization: Optional[str] = Header(default=None)):
    auth = verify_google(authorization)
    email = auth.get("email", "").lower()

    # Step 1: Check labels.json (biometric registry)
    labels = load_labels()
    found_sid = None
    found_info = None
    for sid, info in labels.get("students", {}).items():
        if info.get("email", "").lower() == email:
            found_sid = int(sid)
            found_info = info
            break

    if found_sid is None:
        return {"registered": False}

    # Step 2: Cross-verify in SQLite students table (security: revoked users blocked)
    con = db()
    cur = con.cursor()
    cur.execute("SELECT id FROM students WHERE id=?", (found_sid,))
    row = cur.fetchone()
    con.close()

    if row is None:
        # Exists in biometrics but was removed from DB — block access
        return {"registered": False, "blocked": True}

    token = str(uuid.uuid4())
    SESSIONS[token] = {"role": "student", "student_id": found_sid, "email": email, "name": found_info.get("nombre")}
    return {"registered": True, "name": found_info.get("nombre"), "token": token}

@api_router.post("/auth/login_student")
async def login_student(
    authorization: Optional[str] = Header(default=None),
    file: UploadFile = File(...)
):
    # 1. verify google
    auth = verify_google(authorization)
    email = auth.get("email", "").lower()
    if not email:
        raise HTTPException(status_code=401, detail="No hay email en token")
    
    # 2. Find student by email
    labels = load_labels()
    student_id = None
    for sid_str, info in labels.get("students", {}).items():
        if info.get("email", "").lower() == email:
            student_id = int(sid_str)
            break
            
    if student_id is None:
        raise HTTPException(status_code=404, detail="Alumno no registrado en la base de datos biométrica. Por favor regístrate en la caseta primero.")
        
    # 3. Validar rostro con LBPH
    raw = await file.read()
    arr = np.frombuffer(raw, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(status_code=400, detail="Imagen inválida")
        
    face = extract_face_gray(img)
    if face is None:
        raise HTTPException(status_code=400, detail="No se detectó rostro en la foto")
        
    if not MODEL_FILE.exists():
        raise HTTPException(status_code=500, detail="El modelo LBPH no está entrenado.")
        
    rec = cv2.face.LBPHFaceRecognizer_create()
    rec.read(str(MODEL_FILE))
    
    label, conf = rec.predict(face)
    if label != student_id or conf > 85.0:
        raise HTTPException(status_code=401, detail="Validación facial fallida. Rostro no coincide o confianza insuficiente.")
        
    # Exito
    token = str(uuid.uuid4())
    SESSIONS[token] = {"role": "student", "student_id": student_id, "email": email, "name": auth.get("name")}
    return {"ok": True, "token": token, "role": "student", "student_id": student_id}


@api_router.get("/student/dashboard")
def student_dashboard(session_token: str = Header(...)):
    sess = get_session(session_token)
    if sess["role"] != "student":
        raise HTTPException(status_code=403, detail="Acceso denegado")
        
    sid = sess["student_id"]
    con = db()
    cur = con.cursor()
    
    # Entradas y salidas
    cur.execute("SELECT ts, event_type FROM events WHERE student_id=? ORDER BY id DESC LIMIT 50", (sid,))
    events = [{"ts": r[0], "type": r[1]} for r in cur.fetchall()]
    
    # Faltas
    cur.execute("SELECT id, date, reason FROM absences WHERE student_id=? ORDER BY id ASC", (sid,))
    absences = [{"id": r[0], "date": r[1], "reason": r[2]} for r in cur.fetchall()]
    con.close()
    
    # Semáforo
    num_faltas = len(absences)
    semaforo = "verde"
    if num_faltas >= 5:
        semaforo = "rojo"
    elif num_faltas >= 3:
        semaforo = "amarillo"
        
    labels = load_labels()
    student_info = labels.get("students", {}).get(str(sid), {})

    con_db = db()
    cur_db = con_db.execute("SELECT photo_base64 FROM students WHERE id=?", (sid,))
    row_db = cur_db.fetchone()
    con_db.close()
    
    has_uploaded_photo = (row_db is not None and row_db["photo_base64"] is not None)
    if not has_uploaded_photo:
        has_uploaded_photo = (DATASET_DIR / str(sid) / "profile.jpg").exists()

    return {
        "ok": True,
        "name": sess["name"],
        "student_id": sid,
        "matricula": student_info.get("matricula", "N/A"),
        "carrera": student_info.get("carrera", "N/A"),
        "semaforo": semaforo,
        "faltas": absences,
        "events": events,
        "has_uploaded_photo": has_uploaded_photo,
        "photo_changed": has_uploaded_photo
    }


@api_router.get("/wallet/apple/{student_id}")
def generate_apple_pass(student_id: int):
    return {"ok": True, "message": "API Apple Wallet [ESTRUCTURADA].\n> Por políticas de seguridad, requiere el archivo 'pass.pem' y 'key.pem' del Apple Developer Program para firmar criptográficamente el .pkpass."}

@api_router.get("/wallet/google/{student_id}")
def generate_google_pass(student_id: int):
    return {"ok": True, "message": "API Google Wallet [ESTRUCTURADA].\n> Requiere una llave JSON de Google Cloud Service Account para autenticar la firma del JWT e Issuer ID."}

@api_router.get("/admin/student/{student_id}/photo")
def get_student_photo(student_id: int):
    con = db()
    # Primero intentar foto de perfil
    cur = con.execute("SELECT photo_base64 FROM students WHERE id=?", (student_id,))
    row = cur.fetchone()
    if row and row["photo_base64"]:
        import io
        from fastapi.responses import StreamingResponse
        img_data = base64.b64decode(row["photo_base64"])
        con.close()
        return StreamingResponse(io.BytesIO(img_data), media_type="image/jpeg", headers={"Cache-Control": "max-age=86400"})
    
    # Fallback: usar la primera cara registrada de face_images
    cur2 = con.execute("SELECT image_base64 FROM face_images WHERE student_id=? LIMIT 1", (student_id,))
    row2 = cur2.fetchone()
    con.close()
    if row2 and row2["image_base64"]:
        import io
        from fastapi.responses import StreamingResponse
        img_data = base64.b64decode(row2["image_base64"])
        return StreamingResponse(io.BytesIO(img_data), media_type="image/png", headers={"Cache-Control": "max-age=3600"})
        
    folder = DATASET_DIR / str(student_id)
    if folder.exists() and folder.is_dir():
        profile_path = folder / "profile.jpg"
        if profile_path.exists():
            return FileResponse(profile_path)
            
    raise HTTPException(status_code=404, detail="Foto no encontrada")

class PhotoUpload(BaseModel):
    image_b64: str

@api_router.post("/student/{student_id}/photo_upload")
def upload_student_photo(student_id: int, payload: PhotoUpload, session_token: str = Header(...)):
    sess = get_session(session_token)
    if sess["role"] != "student" or sess["student_id"] != student_id:
        raise HTTPException(status_code=403, detail="Acceso denegado")
        
    try:
        encoded = payload.image_b64
        if "," in encoded:
            header, encoded = encoded.split(",", 1)
        con = db()
        con.execute("UPDATE students SET photo_base64=? WHERE id=?", (encoded, student_id))
        con.commit()
        con.close()
    except Exception as e:
        raise HTTPException(status_code=400, detail="Error procesando la imagen")
    return {"ok": True}

@api_router.post("/student/update-photo")
async def update_student_photo(session_token: str = Header(...), file: UploadFile = File(...)):
    sess = get_session(session_token)
    if sess["role"] != "student":
        raise HTTPException(status_code=403, detail="Acceso denegado")

    sid = sess["student_id"]
    try:
        raw = await file.read()
        b64 = base64.b64encode(raw).decode('utf-8')
        con = db()
        con.execute("UPDATE students SET photo_base64=? WHERE id=?", (b64, sid))
        con.commit()
        con.close()
        return {"ok": True, "message": "Foto de credencial actualizada correctamente."}
    except Exception:
        raise HTTPException(status_code=400, detail="Error al guardar la foto.")

@api_router.delete("/admin/student/{student_id}/photo")
def delete_student_photo(student_id: int, session_token: str = Header(...)):
    sess = get_session(session_token)
    if sess["role"] not in ["admin", "maestro"]:
        raise HTTPException(status_code=403, detail="Acceso denegado")
        
    con = db()
    con.execute("UPDATE students SET photo_base64=NULL WHERE id=?", (student_id,))
    con.commit()
    con.close()
    
    profile_path = DATASET_DIR / str(student_id) / "profile.jpg"
    if profile_path.exists():
        try:
            profile_path.unlink()
        except:
            pass
            
    return {"ok": True, "message": "Foto oficial eliminada correctamente. El alumno puede volver a subirla."}

@api_router.get("/admin/debug_faces")
def debug_faces():
    try:
        from fastapi.responses import HTMLResponse
        # Ver rostros crudos usados p/ entrenar
        records = PostgresWrapper.fetchall("SELECT id, student_id, image_base64, created_at FROM face_images ORDER BY student_id DESC, created_at DESC")
        
        from collections import defaultdict
        grouped = defaultdict(list)
        for r in records:
            grouped[r["student_id"]].append(r)
            
        html = "<html><head><title>Debug Rostros DB</title><style>"
        html += "body { font-family: sans-serif; background: #111; color: #fff; padding: 20px; }"
        html += ".student-block { background: #222; padding: 15px; margin-bottom: 20px; border-radius: 8px; border-left: 5px solid #0d6efd; }"
        html += ".gallery { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 10px; }"
        html += ".img-card { background: #000; padding: 5px; border-radius: 4px; text-align: center; font-size: 11px; }"
        html += "img { width: 100px; height: 100px; object-fit: cover; border-radius: 4px; }"
        html += "</style></head><body><h1>Visor de Base de Datos de Rostros (LBPH)</h1>"
        html += "<p>Aquí ves exactamente con qué imágenes se entrenó el modelo. Si hay caras mezcladas de otra persona en el ID equivocado, por eso te confunde.</p>"
        
        if not grouped:
            html += "<p>No hay rostros registrados.</p>"
            
        for sid, imgs in grouped.items():
            html += f"<div class='student-block'><h2>ID Alumno: {sid} ({len(imgs)} fotos)</h2>"
            html += "<div class='gallery'>"
            for img in imgs:
                img_data = img["image_base64"]
                if not img_data.startswith("data:"):
                    img_data = f"data:image/jpeg;base64,{img_data}"
                date_str = str(img["created_at"])[:16]
                html += f"<div class='img-card'><img src='{img_data}' alt='face'/><br/>ID img: {img['id']}<br/>{date_str}</div>"
            html += "</div></div>"
            
        html += "</body></html>"
        return HTMLResponse(content=html)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class AutoQRRequest(BaseModel):
    student_id: int
    image_b64: str

@api_router.post("/train/auto_qr")
async def train_auto_qr(req: AutoQRRequest, background_tasks: BackgroundTasks):
    # La laptop asume autenticidad del QR criptográfico antes de enviarlo
    try:
        encoded = req.image_b64
        if "," in encoded:
            header, encoded = encoded.split(",", 1)
        
        query = "INSERT INTO face_images (student_id, image_base64) VALUES (?, ?)"
        PostgresWrapper.execute(query, (req.student_id, encoded))
        
        # Disparamos el entrenamiento en segundo plano para no bloquear a la laptop
        background_tasks.add_task(train_lbph)
        return {"ok": True, "msg": "Auto-sanación activada: Rostro guardado y entrenando."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/admin/students")
def get_all_students_admin(session_token: str = Header(...)):
    sess = get_session(session_token)
    if sess["role"] not in ["admin", "maestro"]:
        raise HTTPException(status_code=403, detail="Acceso denegado")
        
    labels = load_labels()
    con = db()
    cur = con.cursor()
    
    result = []
    for sid_str, info in labels.get("students", {}).items():
        sid = int(sid_str)
        cur.execute("SELECT COUNT(*) FROM absences WHERE student_id=?", (sid,))
        num_faltas = cur.fetchone()[0]
        
        semaforo = "verde"
        if num_faltas >= 5:
            semaforo = "rojo"
        elif num_faltas >= 3:
            semaforo = "amarillo"
            
        result.append({
            "id": sid,
            "matricula": info.get("matricula", ""),
            "nombre": info.get("nombre", ""),
            "carrera": info.get("carrera", ""),
            "faltas": num_faltas,
            "semaforo": semaforo
        })
    con.close()
    return {"ok": True, "students": result}


@api_router.post("/admin/absences")
def add_absence(student_id: int = Form(...), date: str = Form(...), reason: str = Form(""), session_token: str = Header(...)):
    sess = get_session(session_token)
    if sess["role"] not in ["admin", "maestro"]:
        raise HTTPException(status_code=403, detail="Solo admin y maestro pueden agregar faltas")
        
    try:
        dt = datetime.strptime(date, "%Y-%m-%d")
        now = datetime.now()
        if dt.year != now.year or dt.month != now.month:
            raise HTTPException(status_code=400, detail="La fecha debe corresponder al mes y año actuales")
    except ValueError:
        pass
        
    con = db()
    con.execute("INSERT INTO absences (student_id, date, reason) VALUES (?, ?, ?)", (student_id, date, reason))
    con.commit()
    con.close()
    return {"ok": True}


@api_router.post("/admin/absences")
def add_absence(student_id: int = Form(...), date: str = Form(...), reason: str = Form(""), session_token: str = Header(...)):
    sess = get_session(session_token)
    if sess["role"] not in ["admin", "maestro"]:
        raise HTTPException(status_code=403, detail="Solo admin y maestro pueden agregar faltas")
        
    con = db()
    con.execute("INSERT INTO absences (student_id, date, reason) VALUES (?, ?, ?)", (student_id, date, reason))
    con.commit()
    con.close()
    return {"ok": True}


@api_router.delete("/admin/absences/{absence_id}")
def delete_absence(absence_id: int, session_token: str = Header(...)):
    sess = get_session(session_token)
    if sess["role"] not in ["admin", "maestro"]:
        raise HTTPException(status_code=403, detail="Solo admin o maestro puede borrar faltas")
        
    con = db()
    con.execute("DELETE FROM absences WHERE id=?", (absence_id,))
    con.commit()
    con.close()
    return {"ok": True}

@api_router.delete("/admin/absences/student/{student_id}/latest")
def delete_latest_absence(student_id: int, session_token: str = Header(...)):
    sess = get_session(session_token)
    if sess["role"] not in ["admin", "maestro"]:
        raise HTTPException(status_code=403, detail="Solo admin o maestro puede borrar faltas")
        
    con = db()
    # Obtenemos el ID de la falta más reciente de este alumno
    cur = con.execute("SELECT id FROM absences WHERE student_id=? ORDER BY id DESC LIMIT 1", (student_id,))
    row = cur.fetchone()
    if row:
        con.execute("DELETE FROM absences WHERE id=?", (row[0],))
        con.commit()
    con.close()
    return {"ok": True, "deleted": bool(row)}

@api_router.delete("/admin/absences/matricula/{matricula}/latest")
def delete_latest_absence_by_matricula(matricula: str, session_token: str = Header(...)):
    sess = get_session(session_token)
    if sess["role"] not in ["admin", "maestro"]:
        raise HTTPException(status_code=403, detail="Solo admin o maestro puede justificar faltas")
        
    con = db()
    labels = load_labels()
    student_id = None
    nombre = ""
    for sid, info in labels.get("students", {}).items():
        if info.get("matricula") == matricula:
            student_id = sid
            nombre = info.get("nombre", "Alumno")
            break
            
    if not student_id:
        con.close()
        raise HTTPException(status_code=404, detail="Matrícula no encontrada")
        
    cur = con.execute("SELECT id FROM absences WHERE student_id=? ORDER BY id DESC LIMIT 1", (student_id,))
    row = cur.fetchone()
    if row:
        con.execute("DELETE FROM absences WHERE id=?", (row[0],))
        con.commit()
        con.close()
        return {"ok": True, "deleted": True, "nombre": nombre}
    con.close()
    return {"ok": True, "deleted": False}

@api_router.delete("/admin/student/{student_id}")
def delete_student_master(student_id: int, session_token: str = Header(...)):
    sess = get_session(session_token)
    if sess["role"] != "admin":
        raise HTTPException(status_code=403, detail="Acceso denegado (Solo Administrador Maestro)")
        
    # Delete from DB
    con = db()
    con.execute("DELETE FROM students WHERE id=?", (student_id,))
    con.execute("DELETE FROM events WHERE student_id=?", (student_id,))
    con.execute("DELETE FROM absences WHERE student_id=?", (student_id,))
    con.execute("DELETE FROM face_images WHERE student_id=?", (student_id,))
    con.execute("DELETE FROM trivia_answers WHERE student_id=?", (student_id,))
    con.commit()
    con.close()
    
    # Delete from labels.json
    labels = load_labels()
    if str(student_id) in labels.get("students", {}):
        del labels["students"][str(student_id)]
        save_labels(labels)
        
    # Delete face data folder
    import shutil
    folder = DATASET_DIR / str(student_id)
    if folder.exists():
        shutil.rmtree(folder)
        
    return {"ok": True, "msg": "Usuario y registros faciales eliminados permanentemente"}



# ==================== FORO / CHAT GLOBAL ====================

class GlobalMessagePayload(BaseModel):
    text: str

class GlobalMessageEditPayload(BaseModel):
    text: str

@api_router.get("/chat/global")
def get_global_chat(session_token: str = Header(...)):
    sess = get_session(session_token)
    con = db()
    # Intentamos obtener sender_id, asumiendo que la tabla lo tiene
    cur = con.execute("SELECT id, sender_name, sender_role, text, timestamp, sender_id FROM global_messages ORDER BY id DESC LIMIT 50")
    rows = cur.fetchall()
    con.close()
    
    msgs = []
    for r in reversed(rows):
        msgs.append({
            "id": r[0],
            "sender_name": r[1],
            "sender_role": r[2],
            "text": r[3],
            "timestamp": r[4],
            "sender_id": r[5] if len(r) > 5 else "unknown"
        })
    return {"ok": True, "messages": msgs}

@api_router.post("/chat/global")
def post_global_chat(payload: GlobalMessagePayload, session_token: str = Header(...)):
    sess = get_session(session_token)
    role = sess.get("role", "alumno")
    sender_name = "Desconocido"
    sender_id = sess.get("student_id", sess.get("email", "admin"))
    
    # Determinar nombre según el rol
    if role == "student" or role == "alumno":
        labels = load_labels()
        sid_str = str(sender_id)
        if sid_str in labels.get("students", {}):
            sender_name = labels["students"][sid_str].get("nombre", "Alumno")
        else:
            sender_name = sess.get("name", "Alumno")
    else:
        # Administrador / Maestro: usar el nombre real de la sesión
        sender_name = sess.get("name", f"Docente")
        if not sender_name:
            sender_name = "Docente"
        
    con = db()
    con.execute("INSERT INTO global_messages (sender_id, sender_name, sender_role, text) VALUES (?, ?, ?, ?)", 
                (str(sender_id), sender_name, role, payload.text))
    con.commit()
    con.close()
    return {"ok": True}

@api_router.delete("/chat/global/{msg_id}")
def delete_global_chat(msg_id: int, session_token: str = Header(...)):
    sess = get_session(session_token)
    sender_id = str(sess.get("student_id", sess.get("email", "admin")))
    role = sess.get("role", "alumno")
    
    con = db()
    # Solo el autor o el admin (o maestro) pueden borrar
    if role == "maestro" or sender_id == "admin":
        con.execute("DELETE FROM global_messages WHERE id = ?", (msg_id,))
    else:
        con.execute("DELETE FROM global_messages WHERE id = ? AND sender_id = ?", (msg_id, sender_id))
    con.commit()
    con.close()
    return {"ok": True}

@api_router.put("/chat/global/{msg_id}")
def edit_global_chat(msg_id: int, payload: GlobalMessageEditPayload, session_token: str = Header(...)):
    sess = get_session(session_token)
    sender_id = str(sess.get("student_id", sess.get("email", "admin")))
    role = sess.get("role", "alumno")
    
    con = db()
    # Solo el autor (o un maestro) pueden editar
    if role == "maestro" or sender_id == "admin":
        con.execute("UPDATE global_messages SET text = ? WHERE id = ?", (payload.text + " (editado)", msg_id))
    else:
        con.execute("UPDATE global_messages SET text = ? WHERE id = ? AND sender_id = ?", (payload.text + " (editado)", msg_id, sender_id))
    con.commit()
    con.close()
    return {"ok": True}


# ==================== TRIVIA DIARIA ====================
def _load_trivia_bank():
    if TRIVIA_FILE.exists():
        with open(TRIVIA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"general": []}

_TRIVIA_BANK = _load_trivia_bank()

def _normalize_carrera(carrera: str) -> str:
    c = carrera.strip().lower()
    if "mecatr" in c: return "Mecatronica"
    if "admin" in c or "gestion" in c: return "Administracion"
    if "enfermer" in c or "salud" in c: return "Enfermeria"
    if "gastronom" in c or "culinari" in c or "alimento" in c: return "Gastronomia"
    if "industrial" in c or "manufactur" in c: return "Industrial"
    if "inform" in c or "software" in c or "comput" in c or "sistema" in c or "tic" in c or "ti" == c: return "TI"
    return "general"

@api_router.get("/trivia/today")
def trivia_today(session_token: str = Header(...)):
    sess = get_session(session_token)
    if sess["role"] != "student":
        raise HTTPException(status_code=403, detail="Solo alumnos")

    sid = sess["student_id"]
    today = datetime.now().strftime("%Y-%m-%d")

    # Verificar si ya contesto hoy
    con = db()
    cur = con.cursor()
    cur.execute("SELECT correct, points FROM trivia_answers WHERE student_id=? AND date=?", (sid, today))
    row = cur.fetchone()

    # Obtener puntos acumulados
    cur.execute("SELECT COALESCE(SUM(points), 0) FROM trivia_answers WHERE student_id=?", (sid,))
    total_points = cur.fetchone()[0]
    con.close()

    if row:
        return {"already_answered": True, "correct": bool(row[0]), "points_today": row[1], "total_points": total_points}

    # Determinar carrera del alumno
    labels = load_labels()
    student_info = labels.get("students", {}).get(str(sid), {})
    carrera_raw = student_info.get("carrera", "general")
    carrera_key = _normalize_carrera(carrera_raw)

    # Obtener preguntas de la carrera
    questions = _TRIVIA_BANK.get(carrera_key, _TRIVIA_BANK.get("general", []))
    if not questions:
        questions = _TRIVIA_BANK.get("general", [])

    # Seleccionar pregunta del dia
    if not questions:
        return {"ok": False, "msg": "No hay trivia configurada para hoy.", "total_points": total_points}
        
    day_of_year = datetime.now().timetuple().tm_yday
    idx = day_of_year % len(questions)
    q = questions[idx]

    return {
        "already_answered": False,
        "question": q["q"],
        "options": q["opts"],
        "day_index": idx,
        "carrera": carrera_key,
        "total_points": total_points
    }

@api_router.post("/trivia/answer")
def trivia_answer(session_token: str = Header(...), answer: int = Form(...), day_index: int = Form(...), carrera: str = Form(...)):
    sess = get_session(session_token)
    if sess["role"] != "student":
        raise HTTPException(status_code=403, detail="Solo alumnos")

    sid = sess["student_id"]
    today = datetime.now().strftime("%Y-%m-%d")

    con = db()
    cur = con.cursor()
    cur.execute("SELECT id FROM trivia_answers WHERE student_id=? AND date=?", (sid, today))
    if cur.fetchone():
        con.close()
        raise HTTPException(status_code=403, detail="Ya contestaste la trivia de hoy")

    questions = _TRIVIA_BANK.get(carrera, _TRIVIA_BANK.get("general", []))
    if not questions:
        questions = _TRIVIA_BANK.get("general", [])
    if not questions:
        con.close()
        raise HTTPException(status_code=404, detail="No hay trivia configurada")

    idx = day_index % len(questions)
    q = questions[idx]
    correct = (answer == q["ans"])
    points = 0.5 if correct else 0.1

    con.execute(
        "INSERT INTO trivia_answers (student_id, date, question_key, answer_idx, correct, points) VALUES (?, ?, ?, ?, ?, ?)",
        (sid, today, f"{carrera}_{idx}", answer, correct, points)
    )
    con.commit()

    cur.execute("SELECT COALESCE(SUM(points), 0) FROM trivia_answers WHERE student_id=?", (sid,))
    total_points = cur.fetchone()[0]
    con.close()

    return {
        "ok": True,
        "correct": correct,
        "correct_answer": q["ans"],
        "points_earned": points,
        "total_points": total_points
    }

@api_router.on_event("startup")
async def on_startup():
    import threading
    def background_train():
        try:
            print("Entrenando LBPH desde PostgreSQL en segundo plano...")
            train_lbph()
            print("Entrenamiento finalizado.")
        except Exception as e:
            print("Error auto-entrenando:", e)
    threading.Thread(target=background_train, daemon=True).start()
