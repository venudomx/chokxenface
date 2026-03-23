import os
import json
import time
import random
import hashlib
from datetime import datetime

import cv2
import numpy as np
import tkinter as tk
from tkinter import ttk, messagebox

# ---------------- CONFIG ----------------
APP_TITLE = "Sistema SignUp & LogIn (Biometrico)"
W, H = 1280, 720

# Camara por defecto (0 = webcam laptop, 1 = Camo normalmente)
DEFAULT_CAM_INDEX = 1
MAX_CAM_INDEX_SCAN = 6  # al presionar C cicla 0..5

# Aceptacion de rostro (para que no sea lejos)
AUTH_MIN_FACE_AREA_FRAC = 0.06   # 6% del frame
AUTH_CENTER_BOX_FRAC = 0.70      # rostro dentro del 70% central

# Anti-pantalla/foto (brillo)
BRIGHT_THR = 205
SCREEN_MIN_AREA_FRAC = 0.12
SCREEN_AR_MIN = 0.35
SCREEN_AR_MAX = 2.40

# Liveness (rapido)
EAR_THR = 0.21
EAR_CONSEC_FRAMES = 2
TURN_THR = 0.12  # que tanto se mueve la nariz vs centro

# Registro
SAMPLES_NEED = 25
LBPH_THRESHOLD = 65.0  # menor = mas parecido (ajusta 55-80)

# Rutas
MODEL_DIR = "models"
DB_DIR = "db"
USERS_FILE = os.path.join(DB_DIR, "users.json")
LBPH_FILE = os.path.join(MODEL_DIR, "lbph.yml")
LABELS_FILE = os.path.join(MODEL_DIR, "labels.json")

AUDIO_OK = os.path.join("audio", "ok.wav")
AUDIO_NO = os.path.join("audio", "no.wav")

# ---------------- UTILS ----------------
def ensure_dirs():
    os.makedirs(MODEL_DIR, exist_ok=True)
    os.makedirs(DB_DIR, exist_ok=True)
    os.makedirs("audio", exist_ok=True)

def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default
    return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

# ---------------- AUDIO ----------------
def play_wav(path):
    try:
        import winsound
        if os.path.exists(path):
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
        else:
            winsound.MessageBeep()
    except Exception:
        pass

# ---------------- CAMERA ----------------
def open_cam(idx, w=W, h=H):
    # prueba DSHOW y MSMF con MJPG/YUY2
    for api in (cv2.CAP_DSHOW, cv2.CAP_MSMF):
        cap = cv2.VideoCapture(idx, api)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)

        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        time.sleep(0.12)
        ok, frame = cap.read()
        if ok and frame is not None and frame.mean() > 2:
            return cap

        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"YUY2"))
        time.sleep(0.12)
        ok, frame = cap.read()
        if ok and frame is not None and frame.mean() > 2:
            return cap

        cap.release()
    return None

def center_box_ok(x, y, w, h, fw, fh):
    cx = x + w / 2.0
    cy = y + h / 2.0
    bw = fw * AUTH_CENTER_BOX_FRAC
    bh = fh * AUTH_CENTER_BOX_FRAC
    x1 = (fw - bw) / 2.0
    y1 = (fh - bh) / 2.0
    x2 = x1 + bw
    y2 = y1 + bh
    return (x1 <= cx <= x2) and (y1 <= cy <= y2)

# ---------------- MEDIAPIPE ----------------
import mediapipe as mp
if not hasattr(mp, "solutions"):
    raise RuntimeError("Tu mediapipe no trae 'solutions'. Instala: pip install mediapipe==0.10.13")

mp_face_det = mp.solutions.face_detection
mp_face_mesh = mp.solutions.face_mesh

face_det = mp_face_det.FaceDetection(model_selection=1, min_detection_confidence=0.6)
face_mesh = mp_face_mesh.FaceMesh(
    static_image_mode=False,
    max_num_faces=1,
    refine_landmarks=True,
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5
)

# indices FaceMesh utiles
L_EYE = [33, 160, 158, 133, 153, 144]
R_EYE = [362, 385, 387, 263, 373, 380]
MOUTH = {"L": 61, "R": 291, "U": 13, "D": 14}
NOSE_TIP = 1
CHEEK_L = 234
CHEEK_R = 454

def lm_xy(landmarks, idx, fw, fh):
    p = landmarks[idx]
    return int(p.x * fw), int(p.y * fh)

def dist(a, b):
    return float(np.linalg.norm(np.array(a, dtype=np.float32) - np.array(b, dtype=np.float32)))

def eye_ear(landmarks, eye_ids, fw, fh):
    p1 = lm_xy(landmarks, eye_ids[0], fw, fh)
    p2 = lm_xy(landmarks, eye_ids[1], fw, fh)
    p3 = lm_xy(landmarks, eye_ids[2], fw, fh)
    p4 = lm_xy(landmarks, eye_ids[3], fw, fh)
    p5 = lm_xy(landmarks, eye_ids[4], fw, fh)
    p6 = lm_xy(landmarks, eye_ids[5], fw, fh)

    A = dist(p2, p6)
    B = dist(p3, p5)
    C = dist(p1, p4)
    return (A + B) / (2.0 * C + 1e-6)

def mouth_ratio(landmarks, fw, fh):
    L = lm_xy(landmarks, MOUTH["L"], fw, fh)
    R = lm_xy(landmarks, MOUTH["R"], fw, fh)
    U = lm_xy(landmarks, MOUTH["U"], fw, fh)
    D = lm_xy(landmarks, MOUTH["D"], fw, fh)
    w = dist(L, R)
    h = dist(U, D)
    return w / (h + 1e-6)

def head_turn_score(landmarks, fw, fh):
    nose = lm_xy(landmarks, NOSE_TIP, fw, fh)
    cl = lm_xy(landmarks, CHEEK_L, fw, fh)
    cr = lm_xy(landmarks, CHEEK_R, fw, fh)
    midx = (cl[0] + cr[0]) / 2.0
    facew = abs(cr[0] - cl[0]) + 1e-6
    return (nose[0] - midx) / facew  # negativo = izquierda, positivo = derecha

# ---------------- ANTI SCREEN (mejorado) ----------------
def detect_bright_screen(frame_bgr):
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    fh, fw = gray.shape[:2]

    _, thr = cv2.threshold(gray, BRIGHT_THR, 255, cv2.THRESH_BINARY)
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
    thr = cv2.morphologyEx(thr, cv2.MORPH_CLOSE, k, iterations=2)

    cnts, _ = cv2.findContours(thr, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return None

    min_area = (fw * fh) * SCREEN_MIN_AREA_FRAC
    best = None
    best_area = 0.0

    for c in cnts:
        area = cv2.contourArea(c)
        if area < min_area:
            continue
        x, y, w, h = cv2.boundingRect(c)
        ar = w / float(h + 1e-6)
        if ar < SCREEN_AR_MIN or ar > SCREEN_AR_MAX:
            continue

        area_frac = (w * h) / float(fw * fh + 1e-6)
        if area_frac > 0.60:
            continue  # demasiado grande (falso positivo tipico)

        roi = gray[y:y+h, x:x+w]
        meanv = float(roi.mean())
        bright_frac = float((roi > BRIGHT_THR).mean())

        # si no esta realmente brillante, no es pantalla
        if meanv < 120 and bright_frac < 0.06:
            continue

        if area > best_area:
            best_area = area
            best = (x, y, w, h)
    return best

def face_inside_rect(face, rect):
    if face is None or rect is None:
        return False
    x, y, w, h = face
    rx, ry, rw, rh = rect
    return (rx <= x <= rx+rw) and (ry <= y <= ry+rh) and (rx <= x+w <= rx+rw) and (ry <= y+h <= ry+rh)

# ---------------- LBPH ----------------
def load_labels():
    return load_json(LABELS_FILE, {"name_by_id": {}, "id_by_name": {}})

def save_labels(labels):
    save_json(LABELS_FILE, labels)

def preprocess_face(gray_face):
    gray_face = cv2.equalizeHist(gray_face)
    gray_face = cv2.resize(gray_face, (200, 200))
    return gray_face

def train_lbph():
    labels = load_labels()
    name_by_id = labels["name_by_id"]
    id_by_name = labels["id_by_name"]

    images = []
    y = []

    if not os.path.isdir(DB_DIR):
        return None

    for username in os.listdir(DB_DIR):
        person_dir = os.path.join(DB_DIR, username)
        if not os.path.isdir(person_dir):
            continue
        if username == "users.json":
            continue

        if username not in id_by_name:
            new_id = str(len(id_by_name) + 1)
            id_by_name[username] = new_id
            name_by_id[new_id] = username

        label_id = int(id_by_name[username])

        for fn in os.listdir(person_dir):
            if not fn.lower().endswith(".png"):
                continue
            p = os.path.join(person_dir, fn)
            img = cv2.imread(p, cv2.IMREAD_GRAYSCALE)
            if img is None:
                continue
            img = preprocess_face(img)
            images.append(img)
            y.append(label_id)

    if len(images) < 10:
        return None

    recognizer = cv2.face.LBPHFaceRecognizer_create()
    recognizer.train(images, np.array(y, dtype=np.int32))
    recognizer.save(LBPH_FILE)

    save_labels({"name_by_id": name_by_id, "id_by_name": id_by_name})
    return recognizer

def load_lbph():
    if not os.path.exists(LBPH_FILE):
        return None
    rec = cv2.face.LBPHFaceRecognizer_create()
    rec.read(LBPH_FILE)
    return rec

# ---------------- ACCESSORIES (heuristica) ----------------
def glasses_prob(frame_bgr, landmarks, fw, fh):
    # region ojos -> edge density
    eye_pts = []
    for idx in (L_EYE + R_EYE):
        eye_pts.append(lm_xy(landmarks, idx, fw, fh))
    xs = [p[0] for p in eye_pts]
    ys = [p[1] for p in eye_pts]
    x1, x2 = max(0, min(xs)-15), min(fw-1, max(xs)+15)
    y1, y2 = max(0, min(ys)-15), min(fh-1, max(ys)+15)

    roi = frame_bgr[y1:y2, x1:x2]
    if roi.size == 0:
        return 0.0

    g = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(g, 60, 160)
    ed = float((edges > 0).mean())  # 0..1

    # mapea edge density a prob (ajustable)
    # sin gafas tipico ~0.03-0.08, con gafas sube
    p = (ed - 0.06) / 0.10
    p = max(0.0, min(1.0, p))
    return p

def cap_prob(frame_bgr, face_box):
    if face_box is None:
        return 0.0
    x, y, w, h = face_box
    fh, fw = frame_bgr.shape[:2]

    y_top = max(0, int(y - 0.45 * h))
    y_bot = max(0, int(y + 0.05 * h))
    x1 = max(0, int(x))
    x2 = min(fw-1, int(x + w))

    if y_bot <= y_top or x2 <= x1:
        return 0.0

    roi_hat = frame_bgr[y_top:y_bot, x1:x2]
    roi_face = frame_bgr[y:y+h, x:x+w]
    if roi_hat.size == 0 or roi_face.size == 0:
        return 0.0

    g_hat = cv2.cvtColor(roi_hat, cv2.COLOR_BGR2GRAY)
    g_face = cv2.cvtColor(roi_face, cv2.COLOR_BGR2GRAY)

    mean_hat = float(g_hat.mean())
    mean_face = float(g_face.mean())

    # si arriba es mucho mas oscuro que el rostro, suele ser gorra
    diff = (mean_face - mean_hat) / 255.0
    p = (diff - 0.10) / 0.20
    p = max(0.0, min(1.0, p))
    return p

# ---------------- SESSION (SignUp/Login) ----------------
def run_camera_session(mode, username_target=None):
    """
    mode: "signup" o "login"
    """
    cv2.setUseOptimized(True)

    cam_idx = DEFAULT_CAM_INDEX
    cap = open_cam(cam_idx)
    if cap is None:
        cam_idx = 0
        cap = open_cam(cam_idx)
    if cap is None:
        messagebox.showerror("Camara", "No se pudo abrir camara. Prueba Camo o webcam.")
        return {"ok": False, "reason": "no_camera"}

    recognizer = load_lbph()

    # estado
    samples_got = 0
    closed_frames = 0
    blink_done = False
    liveness_done = False

    # reto rapido (uno solo)
    challenge = random.choice(["blink", "turn"])
    turn_dir = random.choice(["left", "right"])

    last_face = None
    last_landmarks = None
    last_msg = ""
    ok_name = None
    ok_dist = None

    while True:
        ok, frame = cap.read()
        if not ok or frame is None:
            break

        fh, fw = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # caja central
        bw = int(fw * AUTH_CENTER_BOX_FRAC)
        bh = int(fh * AUTH_CENTER_BOX_FRAC)
        cx1 = (fw - bw) // 2
        cy1 = (fh - bh) // 2
        cx2 = cx1 + bw
        cy2 = cy1 + bh
        cv2.rectangle(frame, (cx1, cy1), (cx2, cy2), (255, 255, 255), 1)

        # anti pantalla
        screen = detect_bright_screen(frame)
        if screen is not None:
            sx, sy, sw, sh = screen
            cv2.rectangle(frame, (sx, sy), (sx+sw, sy+sh), (0, 0, 255), 2)
            cv2.putText(frame, "PANTALLA", (sx, max(0, sy-10)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

        # face detection (mediapipe face detection)
        rgb_small = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        det_res = face_det.process(rgb_small)

        face_box = None
        if det_res.detections:
            det = det_res.detections[0]
            bb = det.location_data.relative_bounding_box
            x = int(bb.xmin * fw)
            y = int(bb.ymin * fh)
            w = int(bb.width * fw)
            h = int(bb.height * fh)
            x = max(0, x); y = max(0, y)
            w = max(1, min(w, fw - x)); h = max(1, min(h, fh - y))
            face_box = (x, y, w, h)

        accepted_face = None
        is_screen_attack = False

        if face_box is not None:
            x, y, w, h = face_box
            area_frac = (w * h) / float(fw * fh + 1e-6)

            if screen is not None and face_inside_rect(face_box, screen):
                # confirma brillo real dentro del rectangulo
                sx, sy, sw, sh = screen
                roi = gray[sy:sy+sh, sx:sx+sw]
                meanv = float(roi.mean())
                bright_frac = float((roi > BRIGHT_THR).mean())
                if meanv >= 120 or bright_frac >= 0.06:
                    is_screen_attack = True

            if area_frac >= AUTH_MIN_FACE_AREA_FRAC and center_box_ok(x, y, w, h, fw, fh) and (not is_screen_attack):
                accepted_face = face_box

        # face mesh (para liveness/accesorios)
        mesh_res = face_mesh.process(rgb_small)
        if mesh_res.multi_face_landmarks:
            last_landmarks = mesh_res.multi_face_landmarks[0].landmark
        else:
            last_landmarks = None

        # dibujar rostro
        if face_box is not None:
            x, y, w, h = face_box
            col = (0, 255, 0) if accepted_face is not None else (0, 255, 255)
            cv2.rectangle(frame, (x, y), (x+w, y+h), col, 2)

        # accesorios
        gprob = 0.0
        cprob = 0.0
        if accepted_face is not None and last_landmarks is not None:
            gprob = glasses_prob(frame, last_landmarks, fw, fh)
            cprob = cap_prob(frame, accepted_face)

        accessories_block = (gprob >= 0.65) or (cprob >= 0.65)

        # UI textos
        cv2.putText(frame, f"Modo: {mode}", (20, 35),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
        cv2.putText(frame, f"Cam: {cam_idx}", (20, 70),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)

        if last_landmarks is not None:
            cv2.putText(frame, f"Gafas: {int(gprob*100)}%", (20, 105),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.85, (255, 0, 255), 2)
            cv2.putText(frame, f"Gorra: {int(cprob*100)}%", (20, 140),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.85, (0, 255, 255), 2)

        # logica principal
        if accepted_face is None:
            last_msg = "Coloca tu rostro al centro"
            if is_screen_attack:
                last_msg = "Bloqueado: parece foto/pantalla"
        else:
            if accessories_block:
                if gprob >= 0.65:
                    last_msg = "Para verificar, quita las gafas por favor"
                elif cprob >= 0.65:
                    last_msg = "Para verificar, quita la gorra por favor"
            else:
                # liveness
                if not liveness_done:
                    if last_landmarks is None:
                        last_msg = "Alinea tu rostro"
                    else:
                        if challenge == "blink":
                            ear_l = eye_ear(last_landmarks, L_EYE, fw, fh)
                            ear_r = eye_ear(last_landmarks, R_EYE, fw, fh)
                            ear = (ear_l + ear_r) / 2.0

                            if ear < EAR_THR:
                                closed_frames += 1
                            else:
                                if closed_frames >= EAR_CONSEC_FRAMES:
                                    blink_done = True
                                closed_frames = 0

                            if blink_done:
                                liveness_done = True
                                play_wav(AUDIO_OK)
                                last_msg = "Liveness OK"
                            else:
                                last_msg = "Liveness: parpadea 1 vez"
                        else:
                            score = head_turn_score(last_landmarks, fw, fh)
                            if turn_dir == "left":
                                if score < -TURN_THR:
                                    liveness_done = True
                                    play_wav(AUDIO_OK)
                                    last_msg = "Liveness OK"
                                else:
                                    last_msg = "Liveness: gira a la izquierda"
                            else:
                                if score > TURN_THR:
                                    liveness_done = True
                                    play_wav(AUDIO_OK)
                                    last_msg = "Liveness OK"
                                else:
                                    last_msg = "Liveness: gira a la derecha"
                else:
                    # despues de liveness
                    x, y, w, h = accepted_face
                    face_gray = gray[y:y+h, x:x+w]
                    face_gray = preprocess_face(face_gray)

                    if mode == "signup":
                        person_dir = os.path.join(DB_DIR, username_target)
                        os.makedirs(person_dir, exist_ok=True)
                        out_path = os.path.join(person_dir, f"{int(time.time()*1000)}.png")
                        cv2.imwrite(out_path, face_gray)
                        samples_got += 1
                        last_msg = f"Registrando {username_target}: {samples_got}/{SAMPLES_NEED}"
                        time.sleep(0.02)

                        if samples_got >= SAMPLES_NEED:
                            # entrenar
                            rec = train_lbph()
                            if rec is None:
                                play_wav(AUDIO_NO)
                                cap.release()
                                cv2.destroyAllWindows()
                                return {"ok": False, "reason": "no_train_data"}
                            play_wav(AUDIO_OK)
                            cap.release()
                            cv2.destroyAllWindows()
                            return {"ok": True, "reason": "signup_ok"}

                    elif mode == "login":
                        if recognizer is None:
                            last_msg = "No hay modelo. Haz SignUp primero."
                        else:
                            label_id, distv = recognizer.predict(face_gray)
                            labels = load_labels()
                            name = labels["name_by_id"].get(str(label_id), "desconocido")

                            if distv <= LBPH_THRESHOLD:
                                ok_name = name
                                ok_dist = float(distv)
                                last_msg = f"Acceso OK: {name} ({distv:.1f})"
                                play_wav(AUDIO_OK)
                                cap.release()
                                cv2.destroyAllWindows()
                                return {"ok": True, "reason": "login_ok", "user": ok_name, "dist": ok_dist}
                            else:
                                last_msg = f"Sin match ({distv:.1f})"

        # mostrar mensaje
        if last_msg:
            col = (0, 255, 0) if ("OK" in last_msg) else (0, 0, 255)
            cv2.putText(frame, last_msg, (20, fh - 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, col, 2)

        cv2.imshow("Acceso Biometrico", frame)
        k = cv2.waitKey(1) & 0xFF

        if k == 27:  # ESC
            break
        elif k in (ord("c"), ord("C")):
            cap.release()
            cam_idx = (cam_idx + 1) % MAX_CAM_INDEX_SCAN
            cap = open_cam(cam_idx)
            if cap is None:
                cam_idx = 0
                cap = open_cam(cam_idx)
            if cap is None:
                break

    cap.release()
    cv2.destroyAllWindows()
    return {"ok": False, "reason": "cancel"}

# ---------------- GUI ----------------
def load_users():
    return load_json(USERS_FILE, {"users": {}})

def save_users(data):
    save_json(USERS_FILE, data)

def ensure_user(username, name, password):
    data = load_users()
    users = data["users"]
    if username in users:
        return False, "Ese usuario ya existe"
    users[username] = {
        "name": name,
        "pass_hash": sha256(password) if password else "",
        "created": now_str()
    }
    save_users(data)
    return True, "Usuario creado"

def check_password(username, password):
    data = load_users()
    u = data["users"].get(username)
    if not u:
        return False
    if not u.get("pass_hash"):
        return True  # sin password guardada
    return sha256(password) == u["pass_hash"]

def user_exists(username):
    data = load_users()
    return username in data["users"]

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("920x420")
        self.resizable(False, False)

        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        self.status = tk.StringVar(value="Listo. SignUp o LogIn con biometrico.")

        main = ttk.Frame(self, padding=14)
        main.pack(fill="both", expand=True)

        title = ttk.Label(main, text="Sistema SignUp & LogIn (Biometrico)", font=("Segoe UI", 18, "bold"))
        title.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

        # LEFT: SignUp
        left = ttk.LabelFrame(main, text="Registrarse (SignUp)", padding=12)
        left.grid(row=1, column=0, sticky="nsew", padx=(0, 10))

        ttk.Label(left, text="Nombre").grid(row=0, column=0, sticky="w")
        self.s_name = ttk.Entry(left, width=35)
        self.s_name.grid(row=1, column=0, pady=(0, 10), sticky="w")

        ttk.Label(left, text="Usuario").grid(row=2, column=0, sticky="w")
        self.s_user = ttk.Entry(left, width=35)
        self.s_user.grid(row=3, column=0, pady=(0, 10), sticky="w")

        ttk.Label(left, text="Contrasena (opcional)").grid(row=4, column=0, sticky="w")
        self.s_pass = ttk.Entry(left, width=35, show="*")
        self.s_pass.grid(row=5, column=0, pady=(0, 12), sticky="w")

        self.btn_signup = ttk.Button(left, text="Sign Up Biometrico", command=self.on_signup)
        self.btn_signup.grid(row=6, column=0, sticky="w")

        ttk.Label(left, text="Tip: En la camara usa C para cambiar camara, ESC para salir.",
                  foreground="#444").grid(row=7, column=0, sticky="w", pady=(10, 0))

        # RIGHT: Login
        right = ttk.LabelFrame(main, text="Iniciar Sesion (LogIn)", padding=12)
        right.grid(row=1, column=1, sticky="nsew")

        ttk.Label(right, text="Usuario").grid(row=0, column=0, sticky="w")
        self.l_user = ttk.Entry(right, width=35)
        self.l_user.grid(row=1, column=0, pady=(0, 10), sticky="w")

        ttk.Label(right, text="Contrasena (opcional)").grid(row=2, column=0, sticky="w")
        self.l_pass = ttk.Entry(right, width=35, show="*")
        self.l_pass.grid(row=3, column=0, pady=(0, 12), sticky="w")

        self.btn_login = ttk.Button(right, text="Log In Biometrico", command=self.on_login)
        self.btn_login.grid(row=4, column=0, sticky="w")

        # STATUS
        status_bar = ttk.Label(main, textvariable=self.status, font=("Segoe UI", 11))
        status_bar.grid(row=2, column=0, columnspan=2, sticky="w", pady=(14, 0))

        ensure_dirs()

    def lock_ui(self, locked=True):
        st = "disabled" if locked else "normal"
        self.btn_signup.config(state=st)
        self.btn_login.config(state=st)

    def on_signup(self):
        name = self.s_name.get().strip()
        user = self.s_user.get().strip()
        password = self.s_pass.get().strip()

        if not user:
            messagebox.showwarning("Falta usuario", "Escribe un usuario (matricula).")
            return

        ok, msg = ensure_user(user, name if name else user, password)
        if not ok:
            messagebox.showerror("SignUp", msg)
            return

        self.status.set("Abriendo camara para SignUp... (C cambia camara, ESC sale)")
        self.lock_ui(True)
        self.update()

        res = run_camera_session("signup", username_target=user)

        self.lock_ui(False)
        if res.get("ok"):
            self.status.set("SignUp OK. Ya puedes hacer LogIn.")
            messagebox.showinfo("SignUp", "Registro biometrico listo.")
        else:
            self.status.set(f"SignUp cancelado/fallo: {res.get('reason')}")
            messagebox.showwarning("SignUp", f"No se completo: {res.get('reason')}")

    def on_login(self):
        user = self.l_user.get().strip()
        password = self.l_pass.get().strip()

        if not user:
            messagebox.showwarning("Falta usuario", "Escribe tu usuario.")
            return
        if not user_exists(user):
            messagebox.showerror("LogIn", "Ese usuario no existe. Haz SignUp primero.")
            return

        self.status.set("Abriendo camara para LogIn... (C cambia camara, ESC sale)")
        self.lock_ui(True)
        self.update()

        res = run_camera_session("login")

        self.lock_ui(False)
        if res.get("ok"):
            pred_user = res.get("user", "")
            if pred_user != user:
                play_wav(AUDIO_NO)
                self.status.set("LogIn: biometrico no coincide con el usuario escrito.")
                messagebox.showerror("LogIn", f"Biometrico detecto: {pred_user}. No coincide con: {user}")
                return

            # si escribio contrasena, validala
            if password:
                if not check_password(user, password):
                    play_wav(AUDIO_NO)
                    self.status.set("LogIn: contrasena incorrecta.")
                    messagebox.showerror("LogIn", "Contrasena incorrecta.")
                    return

            self.status.set(f"Acceso OK: {user}  (dist {res.get('dist', 0):.1f})")
            messagebox.showinfo("LogIn", f"Acceso OK: {user}")
        else:
            self.status.set(f"LogIn cancelado/fallo: {res.get('reason')}")
            messagebox.showwarning("LogIn", f"No se completo: {res.get('reason')}")

if __name__ == "__main__":
    ensure_dirs()
    app = App()
    app.mainloop()
