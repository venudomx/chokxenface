import os
import cv2
import time
import json
import math
import numpy as np
import random
from datetime import datetime
import subprocess

# ============================
# Paths (proyecto)
# ============================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))

DATASET_DIR = os.path.join(PROJECT_DIR, "dataset")
LBPH_FILE = os.path.join(PROJECT_DIR, "lbph_model.yml")
LABELS_FILE = os.path.join(PROJECT_DIR, "labels.json")
LOG_FILE = os.path.join(PROJECT_DIR, "logs.csv")

# ============================
# Config camara / rendimiento
# ============================
CAM_INDEX = 0
MAX_CAM_SCAN = 6

CAP_W, CAP_H = 960, 540
PROC_W, PROC_H = 640, 360

INFER_EVERY_N = 2
RECOG_EVERY_N = 3
ACC_EVERY_N = 3

FACE_SIZE = (200, 200)

# ============================
# Liveness
# ============================
BLINK_EAR_THRESH = 0.22  # Subido para detectar parpadeos más ligeros/rápidos
BLINK_COOLDOWN_SEC = 0.20 # Enfriamiento más rápido
LIVENESS_WINDOW_SEC = 6.0
BLINKS_REQUIRED = 1      # Agilizar entrada: 1 solo parpadeo basta
LIVENESS_HOLD_SEC = 3.0  # Tiempo que se mantiene vivo tras parpadear

# ============================
# Avisos (NO bloqueo)
# ============================
GLASSES_WARN_ON = 85
GLASSES_WARN_OFF = 65
HAT_WARN_ON = 85
HAT_WARN_OFF = 65

# ============================
# LBPH (reconocimiento) — umbrales balanceados
# ============================
# LBPH distancia: MENOR = mas parecido a la cara registrada
# < 50 = match excelente  |  50-65 = match aceptable  |  > 65 = rechazar
LBPH_STRICT = 58.0   # umbral principal: por debajo = acceso OK
LBPH_OK     = 65.0   # umbral relajado: muestra nombre sin dar acceso
LBPH_FLOOR  = 68.0   # rechazo absoluto: distancia mayor siempre = DESCONOCIDO
LBPH_MIN_SAMPLES = 3  # frames consecutivos requeridos para confirmar
RECOG_HOLD_SEC   = 1.6
UNKNOWN_AFTER_SEC = 0.9
UNKNOWN_STRIKES   = 3

# ============================
# Mesh / puntos
# ============================
MESH_MODE_DEFAULT = 1   # 0 off, 1 puntos ligeros, 2 puntos mas densos
SHOW_POINTS_DEFAULT = True

# ============================
# UI (tipos chiquitos)
# ============================
FONT_TITLE = 0.62
FONT_MAIN = 0.54
FONT_SMALL = 0.48

# ============================
# Admin menu oculto
# ============================
ADMIN_SECRET = "utslpadmin"  # teclea esto rapido para alternar admin ON/OFF
ADMIN_TYPING_TIMEOUT = 1.8   # segundos max entre teclas para que cuente

# ============================
# Utilidades
# ============================
def clamp(v, a, b):
    return max(a, min(b, v))

def ema(prev, val, k=0.25):
    return (1.0 - k) * prev + k * val

def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def speak_async(text_to_speak):
    try:
        cmd = f'powershell -Command "Add-Type -AssemblyName System.Speech; (New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak(\'{text_to_speak}\')"'
        subprocess.Popen(cmd, shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
    except:
        pass

def ensure_dirs():
    os.makedirs(DATASET_DIR, exist_ok=True)

import requests

API_BASE = "https://chokxenface.onrender.com/api"

def sync_cloud_models():
    print("Sincronizando biometricos con la nube (Render)...")
    try:
        # 1. Descargar labels
        r_labels = requests.get(f"{API_BASE}/model/labels", timeout=10)
        if r_labels.status_code == 200:
            with open(LABELS_FILE, "wb") as f:
                f.write(r_labels.content)
            print("labels.json actualizado desde la nube.")
        
        # 2. Intentar descargar modelo
        r_model = requests.get(f"{API_BASE}/model/lbph", timeout=15)
        
        if r_model.status_code == 404:
            # Modelo no existe en servidor — forzar reentrenamiento remoto
            print("Modelo no encontrado en la nube. Forzando entrenamiento remoto...")
            try:
                r_train = requests.post(f"{API_BASE}/train", timeout=60)
                if r_train.status_code == 200:
                    print("Entrenamiento remoto exitoso. Descargando modelo...")
                    r_model = requests.get(f"{API_BASE}/model/lbph", timeout=15)
                else:
                    print(f"Error entrenando remotamente: {r_train.status_code} {r_train.text}")
            except Exception as te:
                print(f"Error al entrenar remotamente: {te}")
        
        if r_model.status_code == 200:
            with open(LBPH_FILE, "wb") as f:
                f.write(r_model.content)
            print("lbph_model.yml actualizado desde la nube.")
        else:
            print(f"No se pudo obtener el modelo: {r_model.status_code}")
            if os.path.exists(LBPH_FILE):
                os.remove(LBPH_FILE)
    except Exception as e:
        print("Aviso: No se pudo sincronizar con la nube (verifique su internet).", e)

def write_log(name, event_type, extras=""):
    header_needed = not os.path.exists(LOG_FILE)
    line = f"{now_str()},{name},{event_type},{extras}\n"
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        if header_needed:
            f.write("time,name,event,extras\n")
        f.write(line)

def load_labels():
    if os.path.exists(LABELS_FILE):
        with open(LABELS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"next_id": 0, "students": {}}

def save_labels(labels):
    with open(LABELS_FILE, "w", encoding="utf-8") as f:
        json.dump(labels, f, indent=2, ensure_ascii=False)

def get_or_create_label_id(labels, name):
    for k, v in labels.get("students", {}).items():
        if v.get("nombre", "").strip().lower() == name.strip().lower():
            return int(k)
    new_id = int(labels.get("next_id", 0))
    labels.setdefault("students", {})[str(new_id)] = {"nombre": name, "matricula": "", "carrera": "", "email": ""}
    labels["next_id"] = new_id + 1
    save_labels(labels)
    return new_id

# ============================
# Camara robusta (Windows)
# ============================
def open_cam(idx, w=CAP_W, h=CAP_H):
    for api in (cv2.CAP_DSHOW, cv2.CAP_MSMF):
        cap = cv2.VideoCapture(idx, api)
        if not cap.isOpened():
            cap.release()
            continue

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)

        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        time.sleep(0.10)
        ok, frame = cap.read()
        if ok and frame is not None and frame.mean() > 2:
            return cap

        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"YUY2"))
        time.sleep(0.10)
        ok, frame = cap.read()
        if ok and frame is not None and frame.mean() > 2:
            return cap

        cap.release()
    return None

# ============================
# MediaPipe FaceMesh
# ============================
import mediapipe as mp
mp_face_mesh = mp.solutions.face_mesh

L_EYE = [33, 160, 158, 133, 153, 144]
R_EYE = [362, 385, 387, 263, 373, 380]

def dist(p1, p2):
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])

def eye_aspect_ratio(pts6):
    A = dist(pts6[1], pts6[5])
    B = dist(pts6[2], pts6[4])
    C = dist(pts6[0], pts6[3])
    if C < 1e-6:
        return 0.0
    return (A + B) / (2.0 * C)

def landmarks_to_px(lms, w, h):
    pts = []
    for lm in lms:
        pts.append((int(lm.x * w), int(lm.y * h)))
    return pts

def rect_from_points(pts, w, h, pad=0.15):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    x1, x2 = min(xs), max(xs)
    y1, y2 = min(ys), max(ys)
    fw = x2 - x1
    fh = y2 - y1
    x1 = int(x1 - fw * pad)
    y1 = int(y1 - fh * pad)
    x2 = int(x2 + fw * pad)
    y2 = int(y2 + fh * pad)
    x1 = clamp(x1, 0, w - 1)
    y1 = clamp(y1, 0, h - 1)
    x2 = clamp(x2, 0, w - 1)
    y2 = clamp(y2, 0, h - 1)
    return x1, y1, x2, y2

def face_rect_from_landmarks(pts, w, h, pad=0.10):
    return rect_from_points(pts, w, h, pad=pad)

# ============================
# Detectores ojos (2 cascades)
# ============================
EYE_CASCADE = cv2.CascadeClassifier(
    os.path.join(cv2.data.haarcascades, "haarcascade_eye.xml")
)
EYEGLASSES_CASCADE = cv2.CascadeClassifier(
    os.path.join(cv2.data.haarcascades, "haarcascade_eye_tree_eyeglasses.xml")
)

def glasses_raw_from_eyes(gray_small, pts):
    try:
        le = [pts[i] for i in L_EYE]
        re = [pts[i] for i in R_EYE]
    except:
        return 0.0

    x1a, y1a, x2a, y2a = rect_from_points(le, PROC_W, PROC_H, pad=0.60)
    x1b, y1b, x2b, y2b = rect_from_points(re, PROC_W, PROC_H, pad=0.60)

    x1 = min(x1a, x1b)
    y1 = min(y1a, y1b)
    x2 = max(x2a, x2b)
    y2 = max(y2a, y2b)

    roi = gray_small[y1:y2, x1:x2]
    if roi.size == 0:
        return 0.0

    roi = cv2.equalizeHist(roi)

    eyes_norm = EYE_CASCADE.detectMultiScale(
        roi, scaleFactor=1.08, minNeighbors=6, minSize=(18, 18)
    )
    eyes_gl = EYEGLASSES_CASCADE.detectMultiScale(
        roi, scaleFactor=1.08, minNeighbors=6, minSize=(18, 18)
    )

    n_norm = len(eyes_norm)
    n_gl = len(eyes_gl)

    edges = cv2.Canny(roi, 80, 180)
    edge_density = float(np.mean(edges > 0))
    edge_score = clamp((edge_density - 0.03) / 0.10, 0.0, 1.0)

    if n_gl >= 2 and n_norm < 2:
        base = 1.0
    elif n_gl >= 2 and n_norm >= 2:
        base = 0.70
    elif n_gl == 1 and n_norm < 2:
        base = 0.65
    elif n_gl == 0 and n_norm >= 2:
        base = 0.15
    else:
        base = 0.35

    score = 0.75 * base + 0.25 * edge_score
    return clamp(score, 0.0, 1.0)

# ============================
# Gorra (heuristica)
# ============================
def hat_raw(frame_bgr_small, face_box):
    x1, y1, x2, y2 = face_box
    h = y2 - y1
    w = x2 - x1
    if h <= 0 or w <= 0:
        return 0.0

    top_y1 = int(y1 - 0.40 * h)
    top_y2 = int(y1 + 0.05 * h)
    top_y1 = clamp(top_y1, 0, frame_bgr_small.shape[0] - 1)
    top_y2 = clamp(top_y2, 0, frame_bgr_small.shape[0] - 1)

    forehead_y1 = int(y1 + 0.08 * h)
    forehead_y2 = int(y1 + 0.30 * h)
    forehead_y1 = clamp(forehead_y1, 0, frame_bgr_small.shape[0] - 1)
    forehead_y2 = clamp(forehead_y2, 0, frame_bgr_small.shape[0] - 1)

    top_roi = frame_bgr_small[top_y1:top_y2, x1:x2]
    fore_roi = frame_bgr_small[forehead_y1:forehead_y2, x1:x2]
    if top_roi.size == 0 or fore_roi.size == 0:
        return 0.0

    top_gray = cv2.cvtColor(top_roi, cv2.COLOR_BGR2GRAY)
    fore_gray = cv2.cvtColor(fore_roi, cv2.COLOR_BGR2GRAY)

    top_mean = float(np.mean(top_gray))
    fore_mean = float(np.mean(fore_gray))

    edges = cv2.Canny(top_gray, 60, 140)
    edge_density = float(np.mean(edges > 0))

    dark_score = clamp((fore_mean - top_mean) / 40.0, 0.0, 1.0)
    edge_score = clamp((edge_density - 0.02) / 0.10, 0.0, 1.0)
    score = 0.65 * dark_score + 0.35 * edge_score
    return clamp(score, 0.0, 1.0)

# ============================
# LBPH
# ============================
def load_lbph_if_exists():
    if not os.path.exists(LBPH_FILE):
        return None
    if not hasattr(cv2, "face"):
        print("Falta cv2.face. Instala: pip install opencv-contrib-python")
        return None
    rec = cv2.face.LBPHFaceRecognizer_create()
    rec.read(LBPH_FILE)
    return rec

def predict_lbph(recognizer, face_gray):
    if recognizer is None:
        return None, None
    try:
        img = cv2.resize(face_gray, FACE_SIZE)
        label, conf = recognizer.predict(img)
        return int(label), float(conf)
    except:
        return None, None

def train_lbph():
    os.makedirs(DATASET_DIR, exist_ok=True)
    if not hasattr(cv2, "face"):
        print("Falta cv2.face. Instala: pip install opencv-contrib-python")
        return None

    images = []
    y = []

    for folder in os.listdir(DATASET_DIR):
        folder_path = os.path.join(DATASET_DIR, folder)
        if not os.path.isdir(folder_path):
            continue
        try:
            lid = int(folder)
        except:
            continue

        for fn in os.listdir(folder_path):
            if not fn.lower().endswith(".png"):
                continue
            p = os.path.join(folder_path, fn)
            img = cv2.imread(p, cv2.IMREAD_GRAYSCALE)
            if img is None:
                continue
            img = cv2.resize(img, FACE_SIZE)
            images.append(img)
            y.append(lid)

    if len(images) < 2:
        print("No hay suficientes imagenes para entrenar. Minimo 2.")
        return None

    rec = cv2.face.LBPHFaceRecognizer_create()
    rec.train(images, np.array(y))
    rec.save(LBPH_FILE)
    print(f"LBPH entrenado. Total imgs: {len(images)} | Guardado: {LBPH_FILE}")
    return rec

# ============================
# UI helpers
# ============================
def panel(frame, x, y, w, h, alpha=0.65, border=(200, 200, 200), bg=(25, 25, 25)):
    overlay = frame.copy()
    cv2.rectangle(overlay, (x, y), (x + w, y + h), bg, -1)
    cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)
    if border:
        cv2.rectangle(frame, (x, y), (x + w, y + h), border, 1)

def text(frame, s, x, y, color=(255, 255, 255), scale=0.52, thick=1):
    cv2.putText(frame, s, (x+1, y+1), cv2.FONT_HERSHEY_SIMPLEX, scale, (15, 15, 15), thick, cv2.LINE_AA)
    cv2.putText(frame, s, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, thick, cv2.LINE_AA)

def draw_box(frame, box, color=(0, 255, 120), thick=2):
    x1, y1, x2, y2 = box
    l = int(min(x2-x1, y2-y1) * 0.2)
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 1)
    cv2.line(frame, (x1, y1), (x1+l, y1), color, thick)
    cv2.line(frame, (x1, y1), (x1, y1+l), color, thick)
    cv2.line(frame, (x2, y1), (x2-l, y1), color, thick)
    cv2.line(frame, (x2, y1), (x2, y1+l), color, thick)
    cv2.line(frame, (x1, y2), (x1+l, y2), color, thick)
    cv2.line(frame, (x1, y2), (x1, y2-l), color, thick)
    cv2.line(frame, (x2, y2), (x2-l, y2), color, thick)
    cv2.line(frame, (x2, y2), (x2, y2-l), color, thick)

def play_wav_if_exists(path):
    try:
        if os.path.exists(path):
            import winsound
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
            return True
    except:
        pass
    return False

# ============================
# Main
# ============================
def main():
    sync_cloud_models()
    os.makedirs(DATASET_DIR, exist_ok=True)
    labels = load_labels()
    recognizer = load_lbph_if_exists()

    cam_idx = CAM_INDEX
    cap = open_cam(cam_idx)
    if cap is None:
        print("No pude abrir camara. Presiona C para cambiar index.")
        return

    face_mesh = mp_face_mesh.FaceMesh(
        static_image_mode=False,
        max_num_faces=1,
        refine_landmarks=False,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    )

    mode = "gate"
    event_type = "entrada"

    mesh_mode = MESH_MODE_DEFAULT
    show_points = SHOW_POINTS_DEFAULT

    frame_i = 0
    last_pts = None
    last_face_box = None
    last_face_gray = None

    glasses_score = 0.0
    hat_score = 0.0
    glasses_warn = False
    hat_warn = False

    # liveness estable
    blink_times = []
    last_blink_tick = 0.0
    last_lid_closed = False
    liveness_ok_until = 0.0

    # reconocimiento estable (sin parpadeo)
    last_name = "DESCONOCIDO"
    last_conf = None
    last_recog_ts = 0.0
    unknown_streak = 0
    vote_buffer = []   # buffer multi-frame para votacion anti-falso-positivo

    # saludo
    last_greet_ts = 0.0
    GREET_COOLDOWN = 4.0
    last_warn_ts = 0.0

    # registro
    reg_buffer = ""
    reg_name = ""
    reg_id = None
    samples_got = 0
    SAMPLES_TARGET = 25
    REG_SAMPLE_INTERVAL = 0.18
    last_sample_ts = 0.0

    # admin oculto
    admin_mode = False
    admin_buffer = ""
    admin_last_key_ts = 0.0
    toast_msg = ""
    toast_until = 0.0

    # fps
    fps = 0.0
    t0 = time.time()
    frames_counter = 0

    WIN = "chokxen_face_gate"
    cv2.namedWindow(WIN, cv2.WINDOW_AUTOSIZE)

    while True:
        ok, frame = cap.read()
        if not ok or frame is None:
            continue

        frame = cv2.flip(frame, 1)
        frame = cv2.resize(frame, (CAP_W, CAP_H))

        frames_counter += 1
        dt = time.time() - t0
        if dt >= 0.8:
            fps = frames_counter / dt
            frames_counter = 0
            t0 = time.time()

        small = cv2.resize(frame, (PROC_W, PROC_H))
        rgb_small = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)

        faces = 0

        # usamos display_liveness estable
        nowt = time.time()
        liveness_ok_display = (nowt <= liveness_ok_until)

        # inferencia FaceMesh
        if frame_i % INFER_EVERY_N == 0:
            result = face_mesh.process(rgb_small)
            if result.multi_face_landmarks:
                faces = 1
                lms = result.multi_face_landmarks[0].landmark
                pts = landmarks_to_px(lms, PROC_W, PROC_H)
                face_box = face_rect_from_landmarks(pts, PROC_W, PROC_H, pad=0.10)

                x1, y1, x2, y2 = face_box
                roi = small[y1:y2, x1:x2]
                face_gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY) if roi.size > 0 else None

                last_pts = pts
                last_face_box = face_box
                last_face_gray = face_gray

                # liveness (blink)
                try:
                    le = [pts[i] for i in L_EYE]
                    re = [pts[i] for i in R_EYE]
                    ear = (eye_aspect_ratio(le) + eye_aspect_ratio(re)) / 2.0

                    closed = ear < BLINK_EAR_THRESH

                    if closed and (not last_lid_closed) and (nowt - last_blink_tick) > BLINK_COOLDOWN_SEC:
                        last_lid_closed = True

                    if (not closed) and last_lid_closed:
                        last_lid_closed = False
                        last_blink_tick = nowt
                        blink_times.append(nowt)

                    blink_times = [t for t in blink_times if (nowt - t) <= LIVENESS_WINDOW_SEC]
                    if len(blink_times) >= BLINKS_REQUIRED:
                        liveness_ok_until = nowt + LIVENESS_HOLD_SEC
                        liveness_ok_display = True
                except:
                    pass

                # accesorios
                if frame_i % ACC_EVERY_N == 0:
                    gray_small = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
                    g_raw = glasses_raw_from_eyes(gray_small, pts)
                    glasses_score = ema(glasses_score, g_raw, k=0.22)

                    h_raw = hat_raw(small, face_box)
                    hat_score = ema(hat_score, h_raw, k=0.18)

        if last_face_box is not None:
            faces = 1

        glasses_pct = int(clamp(glasses_score, 0.0, 1.0) * 100)
        hat_pct = int(clamp(hat_score, 0.0, 1.0) * 100)

        # histeresis avisos
        if (not glasses_warn) and glasses_pct >= GLASSES_WARN_ON:
            glasses_warn = True
        if glasses_warn and glasses_pct <= GLASSES_WARN_OFF:
            glasses_warn = False

        if (not hat_warn) and hat_pct >= HAT_WARN_ON:
            hat_warn = True
        if hat_warn and hat_pct <= HAT_WARN_OFF:
            hat_warn = False

        # reconocimiento con votacion multi-frame (anti false-positive)
        if recognizer is not None and last_face_gray is not None and frame_i % RECOG_EVERY_N == 0:
            lid, conf = predict_lbph(recognizer, last_face_gray)

            # LBPH_FLOOR: rechazo absoluto — si conf es mayor que el piso, ignorar siempre
            if lid is not None and conf is not None and conf <= LBPH_FLOOR:
                # Acumulamos votos en el buffer
                vote_buffer.append((lid, conf))
                if len(vote_buffer) > LBPH_MIN_SAMPLES:
                    vote_buffer.pop(0)

                # Solo confirmar si todos los votos coinciden CON EL MISMO ID
                if len(vote_buffer) >= LBPH_MIN_SAMPLES:
                    ids_in_buf  = [v[0] for v in vote_buffer]
                    confs_in_buf = [v[1] for v in vote_buffer]
                    # Todos los frames deben coincidir en el mismo ID
                    if len(set(ids_in_buf)) == 1 and max(confs_in_buf) <= LBPH_FLOOR:
                        info = labels.get("students", {}).get(str(lid), {})
                        if not info:
                            # ID fantasma: existe en el modelo pero no en labels
                            vote_buffer.clear()
                            unknown_streak += 1
                        else:
                            nm = info.get("nombre", f"ID_{lid}")
                            last_name = nm
                            last_conf = float(np.mean(confs_in_buf))
                            last_recog_ts = nowt
                            unknown_streak = 0
                    else:
                        # IDs mezclados = persona no confiable
                        vote_buffer.clear()
                        unknown_streak += 1
                else:
                    unknown_streak += 1
            else:
                # Conf fuera del piso: limpiar buffer y sumar fallo
                vote_buffer.clear()
                unknown_streak += 1

        # decide display name sin parpadeo
        if faces == 0:
            if (nowt - last_recog_ts) > RECOG_HOLD_SEC:
                last_name = "DESCONOCIDO"
                last_conf = None
                unknown_streak = 0
        else:
            if unknown_streak >= UNKNOWN_STRIKES and (nowt - last_recog_ts) > UNKNOWN_AFTER_SEC:
                last_name = "DESCONOCIDO"
                last_conf = None
                unknown_streak = 0

        # ============================
        # DIBUJO
        # ============================
        import requests
        API_URL = "https://chokxenface.onrender.com/api/events"
        
        # mesh puntos (ligero)
        if last_pts is not None and mesh_mode != 0 and show_points:
            step = 8 if mesh_mode == 1 else 5
            for i in range(0, len(last_pts), step):
                cv2.circle(small, last_pts[i], 1, (200, 255, 255), -1)

        # caja rostro + etiqueta nombre
        if last_face_box is not None:
            draw_box(small, last_face_box, (0, 255, 0), 2)
            x1, y1, x2, y2 = last_face_box

            tag_h = 24
            tag_w = max(180, min(320, (x2 - x1) + 40))
            tag_x = clamp(x1, 8, PROC_W - tag_w - 8)
            tag_y = clamp(y1 - (tag_h + 8), 8, PROC_H - tag_h - 8)

            panel(small, tag_x, tag_y, tag_w, tag_h, alpha=0.60, border=(0, 255, 0))
            show_name = last_name
            if show_name == "DESCONOCIDO":
                text(small, "DESCONOCIDO", tag_x + 10, tag_y + 17, (255, 255, 255), FONT_SMALL, 2)
            else:
                first = show_name.split(" ")[0].strip()
                text(small, f"{first}", tag_x + 10, tag_y + 17, (255, 255, 255), FONT_SMALL, 2)

        # HUD MINI EN TOP-LEFT
        # HUD MINI EN TOP-LEFT
        panel(small, 10, 10, 200, 95, alpha=0.55)
        text(small, f"Cam: {cam_idx} | M: {mode}", 18, 28, (255, 255, 255), 0.50, 1)
        text(small, f"Liveness: {'OK' if liveness_ok_display else 'OFF'}", 18, 48, (0, 255, 0) if liveness_ok_display else (0, 0, 255), 0.50, 1)
        text(small, f"Ev: {event_type} | G: {glasses_pct}%", 18, 68, (255, 255, 0), 0.50, 1)
        
        if last_conf is not None:
             text(small, f"Conf: {last_conf:.1f}", 18, 88, (200, 200, 200), 0.50, 1)

        # Liveness & Accesorios Módulo Estricto
        # Gorra: siempre bloquea
        # Lentes: solo bloquea si los detecta; si no trae, pasa automáticamente
        if hat_warn or glasses_warn:
            liveness_ok_display = False
            liveness_ok_until = 0.0

        warnings = []
        voice_warning = ""
        
        if glasses_warn:
            warnings.append("QUITATE LOS LENTES")
            voice_warning = "Quítate los lentes."
        elif hat_warn:
            warnings.append("QUITATE LA GORRA")
            voice_warning = "Quítate la gorra."
        elif not liveness_ok_display:
            warnings.append(f"Parpadea {BLINKS_REQUIRED} veces")
            voice_warning = "Parpadea a la cámara."

        if voice_warning and faces > 0 and (nowt - last_warn_ts) > 6.0:
            last_warn_ts = nowt
            speak_async(voice_warning)

        if warnings:
            panel(small, 10, PROC_H - 70, 480, 40, alpha=0.60, border=(0,0,255))
            text(small, warnings[0], 20, PROC_H - 45, (0, 0, 255), FONT_MAIN, 2)

        # saludo automatizado (solo si conf estricta y liveness ok)
        if mode == "gate" and faces > 0 and liveness_ok_display:
            if last_name != "DESCONOCIDO" and last_conf is not None and last_conf <= LBPH_STRICT:
                if (nowt - last_greet_ts) >= GREET_COOLDOWN:
                    last_greet_ts = nowt
                    last_warn_ts = nowt  # Evitar avisos empalmados
                    write_log(last_name, event_type, extras=f"cam={cam_idx}")
                    
                    try:
                        # Find the ID of the student
                        match_id = None
                        labels_data = load_labels().get("students", {})
                        for k, v in labels_data.items():
                            if v.get("nombre") == last_name:
                                match_id = int(k)
                                break
                        if match_id is not None:
                            requests.post(f"{API_URL}?student_id={match_id}&event_type={event_type}&camera={cam_idx}&source=laptop", timeout=1.0)
                    except:
                        pass
                    first = last_name.split(" ")[0].strip()
                    
                    # Obtener género del alumno
                    match_info = {}
                    for k, v in labels_data.items():
                        if v.get("nombre") == last_name:
                            match_info = v
                            break
                    genero = match_info.get("genero", "O")
                    
                    if event_type == "entrada":
                        if genero == "F":
                            frases = [
                                f"Bienvenida {first}.",
                                f"Hola {first}, te ves hermosa hoy.",
                                f"Qué guapa vienes hoy {first}.",
                                f"Hola {first}, la uni brilla más desde que llegaste.",
                                f"Esa sonrisa ilumina el campus {first}.",
                                f"¡Cuidado! {first} acaba de llegar y viene con todo.",
                                f"Hola {first}, qué bonita te ves hoy.",
                                f"Adelante {first}, a conquistar el semestre.",
                                f"¡Qué elegancia, {first}! Directo al cuadro de honor.",
                                f"Pásale {first}, puro diez el día de hoy.",
                                f"Con esa actitud, {first}, vas a sacar puro cien.",
                                f"Bienvenida {first}, futura orgullo de la universidad.",
                                f"Hola {first}, qué bonito outfit traes hoy.",
                                f"Puro VIP hoy, ¿verdad {first}?",
                                f"Adelante {first}, no olvides tomar agüita.",
                                f"Hola {first}, hoy te veo con cara de que vas a triunfar.",
                                f"¡Wow {first}! Estás rompiendo corazones hoy.",
                                f"Hola {first}, espero que hayas desayunado bien.",
                                f"¡Fiu fiu! Qué belleza acaba de entrar, hola {first}.",
                                f"Pase usted {first}, qué elegancia la de Francia."
                            ]
                        elif genero == "M":
                            frases = [
                                f"Bienvenido {first}.",
                                f"Hola {first}, te ves increíble hoy.",
                                f"Qué guapo vienes hoy {first}.",
                                f"¿A dónde vas tan temprano {first}?",
                                f"Hola {first}, no huyas de la uni tan temprano.",
                                f"Qué milagro que llegas {first}.",
                                f"Pase usted {first}, qué elegancia la de Francia.",
                                f"¡Wow {first}! Estás rompiendo corazones hoy.",
                                f"Hola {first}, la uni brilla más desde que llegaste.",
                                f"¡Cuidado! {first} acaba de llegar y viene con todo.",
                                f"Hola {first}, qué buen outfit traes hoy.",
                                f"Adelante {first}, a conquistar el semestre.",
                                f"¡Qué porte, {first}! Directo al cuadro de honor.",
                                f"Hola {first}. Recuerda entregar tus tareas hoy.",
                                f"Pásale {first}, puro diez el día de hoy.",
                                f"Con esa actitud, {first}, vas a sacar puro cien.",
                                f"Bienvenido {first}, futuro orgullo de la universidad.",
                                f"¡Epa {first}! ¿A quién te vas a ligar hoy?",
                                f"Qué bien hueles {first}, pase usted.",
                                f"Hola {first}, espero que hayas desayunado bien.",
                                f"Puro VIP hoy, ¿verdad {first}?",
                                f"Adelante {first}, no olvides tomar agüita.",
                                f"Hola {first}, hoy te veo con cara de que vas a triunfar."
                            ]
                        else:
                            frases = [
                                f"Bienvenido {first}.",
                                f"Hola {first}, te ves increíble hoy.",
                                f"Hola {first}, la uni brilla más desde que llegaste.",
                                f"Adelante {first}, a conquistar el semestre.",
                                f"Pásale {first}, puro diez el día de hoy.",
                                f"Hola {first}, espero que hayas desayunado bien.",
                                f"Puro VIP hoy, ¿verdad {first}?",
                                f"Hola {first}, hoy te veo con cara de que vas a triunfar."
                            ]
                    else:
                        frases = [
                            f"Hasta luego {first}.",
                            f"¿Ya te vas tan temprano {first}?",
                            f"Adiós {first}, que te vaya excelente.",
                            f"Nos vemos {first}, descansa.",
                            f"Cuidado en el camino {first}.",
                            f"Que la fuerza te acompañe {first}.",
                            f"Adiós {first}, ve con cuidado a tu casa.",
                            f"Bye bye {first}.",
                            f"Nos vemos mañana {first}, no faltes.",
                            f"Buen viaje {first}.",
                            f"Al fin libre, ¿eh {first}? Cuídate mucho.",
                            f"Hasta la vista, baby. Adiós {first}.",
                            f"Descansa, {first}, te lo ganaste.",
                            f"No te olvides de hacer la tarea {first}, chao.",
                            f"Se acabó la tortura por hoy {first}, nos vemos.",
                            f"Feliz regreso a casa, {first}.",
                            f"Que descanses, {first}, pórtate bien."
                        ]

                    msg = random.choice(frases)
                    speak_async(msg)

                    panel(small, PROC_W - 220, 10, 210, 52, alpha=0.55, border=(0, 255, 0))
                    text(small, "ACCESO OK", PROC_W - 210, 32, (0, 255, 0), FONT_TITLE, 2)
                    text(small, f"{first}", PROC_W - 210, 54, (255, 255, 255), FONT_MAIN, 2)

                    liveness_ok_until = 0.0
            
            elif last_name == "DESCONOCIDO" and unknown_streak >= UNKNOWN_STRIKES:
                if (nowt - last_greet_ts) >= GREET_COOLDOWN:
                    last_greet_ts = nowt
                    last_warn_ts = nowt
                    
                    frases_desc = [
                        "Rostro desconocido.",
                        "¿Te has registrado?",
                        "Por favor, regístrate en el sistema.",
                        "Acceso denegado, rostro no reconocido."
                    ]
                    speak_async(random.choice(frases_desc))
                    
                    panel(small, PROC_W - 250, 10, 240, 52, alpha=0.55, border=(0, 0, 255))
                    text(small, "ACCESO DENEGADO", PROC_W - 240, 32, (0, 0, 255), FONT_TITLE, 2)
                    text(small, "No reconocido", PROC_W - 240, 54, (255, 255, 255), FONT_MAIN, 2)
                    
                    liveness_ok_until = 0.0

        # modo input
        if mode == "input":
            panel(small, 10, PROC_H - 132, 620, 52, alpha=0.62)
            text(small, "Escribe nombre/matricula y ENTER:", 20, PROC_H - 102, (255, 255, 255), FONT_MAIN, 2)
            text(small, reg_buffer + "_", 20, PROC_H - 80, (0, 255, 0), FONT_TITLE, 2)

        # modo register
        if mode == "register":
            panel(small, 10, PROC_H - 132, 620, 52, alpha=0.62)
            text(small, f"Registrando: {reg_name}", 20, PROC_H - 102, (255, 255, 255), FONT_MAIN, 2)
            text(small, f"Muestras: {samples_got}/{SAMPLES_TARGET}", 20, PROC_H - 80, (0, 255, 0), FONT_TITLE, 2)

            if last_face_gray is not None and liveness_ok_display:
                if (nowt - last_sample_ts) >= REG_SAMPLE_INTERVAL:
                    out_dir = os.path.join(DATASET_DIR, str(reg_id))
                    os.makedirs(out_dir, exist_ok=True)
                    img = cv2.resize(last_face_gray, FACE_SIZE)
                    out_path = os.path.join(out_dir, f"{int(nowt*1000)}_{samples_got}.png")
                    cv2.imwrite(out_path, img)
                    samples_got += 1
                    last_sample_ts = nowt

                    if samples_got >= SAMPLES_TARGET:
                        print("Listo. Entrenando modelo...")
                        recognizer = train_lbph()
                        labels = load_labels()
                        mode = "gate"
                        reg_name = ""
                        reg_id = None
                        samples_got = 0

        # barra controles visible (sin admin)
        panel(small, 10, PROC_H - 32, 620, 24, alpha=0.35)
        text(small, "ESC salir | C cam | E evento | R registrar | T entrenar | M mesh | P puntos",
             18, PROC_H - 14, (255, 255, 255), FONT_SMALL, 2)

        # admin panel SOLO si admin_mode (oculto)
        if admin_mode:
            panel(small, PROC_W - 210, PROC_H - 120, 200, 110, alpha=0.60, border=(255, 255, 0))
            text(small, "ADMIN MODE", PROC_W - 196, PROC_H - 94, (255, 255, 0), FONT_TITLE, 2)
            text(small, f"raw_g: {glasses_score:.2f}", PROC_W - 196, PROC_H - 70, (255, 255, 255), FONT_SMALL, 2)
            text(small, f"raw_h: {hat_score:.2f}", PROC_W - 196, PROC_H - 50, (255, 255, 255), FONT_SMALL, 2)
            text(small, f"u_streak: {unknown_streak}", PROC_W - 196, PROC_H - 30, (255, 255, 255), FONT_SMALL, 2)

        # toast (mensajito corto)
        if nowt <= toast_until and toast_msg:
            panel(small, PROC_W - 210, 70, 200, 36, alpha=0.55, border=(255, 255, 255))
            text(small, toast_msg, PROC_W - 198, 94, (255, 255, 255), FONT_MAIN, 2)

        # reloj en tiempo real
        # reloj en tiempo real
        now_dt = datetime.now()
        fecha_str = now_dt.strftime("%d/%m/%Y")
        hora_str = now_dt.strftime("%H:%M:%S")

        panel(small, 10, 115, 140, 45, alpha=0.60, border=(255,255,255))
        text(small, hora_str, 20, 135, (255, 255, 255), FONT_TITLE, 2)
        text(small, fecha_str, 20, 153, (200, 200, 200), FONT_MAIN, 2)

        # mostrar
        display = cv2.resize(small, (CAP_W, CAP_H), interpolation=cv2.INTER_LINEAR)
        cv2.imshow(WIN, display)

        k = cv2.waitKey(1) & 0xFF

        # ============
        # Admin secreto (NO visible)
        # ============
        if k != 255 and k != 0:
            # letras unicamente
            if 32 <= k <= 126:
                ch = chr(k).lower()
                if (nowt - admin_last_key_ts) > ADMIN_TYPING_TIMEOUT:
                    admin_buffer = ""
                admin_buffer += ch
                admin_last_key_ts = nowt

                if admin_buffer.endswith(ADMIN_SECRET):
                    admin_mode = not admin_mode
                    admin_buffer = ""
                    toast_msg = "ADMIN ON" if admin_mode else "ADMIN OFF"
                    toast_until = nowt + 1.2

        # ============
        # Teclas normales
        # ============
        if k == 27:
            break

        if k in (ord("c"), ord("C")):
            cap.release()
            cam_idx = (cam_idx + 1) % MAX_CAM_SCAN
            cap = open_cam(cam_idx)
            if cap is None:
                cap = open_cam(CAM_INDEX)
                cam_idx = CAM_INDEX

        if k in (ord("e"), ord("E")):
            event_type = "salida" if event_type == "entrada" else "entrada"

        if k in (ord("m"), ord("M")):
            mesh_mode = (mesh_mode + 1) % 3

        if k in (ord("p"), ord("P")):
            show_points = not show_points

        if k in (ord("t"), ord("T")):
            # Primero sincronizar modelo y labels desde el servidor
            sync_cloud_models()
            # Recargar el modelo LBPH actualizado
            recognizer = load_lbph_if_exists()
            labels = load_labels()
            vote_buffer.clear()
            last_name = "DESCONOCIDO"
            last_conf = None
            unknown_streak = 0
            toast_msg = "SYNC OK" if recognizer else "SIN MODELO"
            toast_until = nowt + 2.0

        if k in (ord("r"), ord("R")) and mode == "gate":
            reg_buffer = ""
            mode = "input"

        # input escribir nombre
        if mode == "input":
            if k in (13, 10):
                name = reg_buffer.strip()
                if len(name) >= 1:
                    reg_name = name
                    reg_id = get_or_create_label_id(labels, reg_name)
                    samples_got = 0
                    last_sample_ts = 0.0
                    mode = "register"
                else:
                    mode = "gate"

            elif k in (8, 127):
                reg_buffer = reg_buffer[:-1]

            elif k == 27:
                mode = "gate"

            else:
                if 32 <= k <= 126 and len(reg_buffer) < 30:
                    reg_buffer += chr(k)

        frame_i += 1

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
