import sys

with open('server/api.py', 'r', encoding='utf-8') as f:
    text = f.read()

text = text.replace('\r\n', '\n')

# 1. load_labels
text = text.replace(
    '"email": r["email"],\n                "genero": r["genero"] if "genero" in r.keys() else "O"\n            }',
    '"email": r["email"],\n                "genero": r["genero"] if "genero" in r.keys() else "O",\n                "fecha_nacimiento": r["fecha_nacimiento"] if "fecha_nacimiento" in r.keys() else ""\n            }'
)

# 2. upsert_student Definition
text = text.replace(
    'def upsert_student(labels: Dict[str, Any], matricula: str, nombre: str, carrera: str, email: str, genero: str = "O") -> int:',
    'def upsert_student(labels: Dict[str, Any], matricula: str, nombre: str, carrera: str, email: str, genero: str = "O", fecha_nac: str = "") -> int:'
)

# 3. upsert_student Body
text = text.replace(
    '    genero = genero.strip() if genero else "O"',
    '    genero = genero.strip() if genero else "O"\n    fecha_nac = fecha_nac.strip() if fecha_nac else ""'
)

# 4. upsert_student Dict
text = text.replace(
    '        "genero": genero,\n        "updated_at": now_str(),',
    '        "genero": genero,\n        "fecha_nacimiento": fecha_nac,\n        "updated_at": now_str(),'
)

# 5. upsert_student SQL
text = text.replace(
    'INSERT INTO students (id, matricula, nombre, carrera, email, created_at, genero)\n        VALUES (?, ?, ?, ?, ?, ?, ?)',
    'INSERT INTO students (id, matricula, nombre, carrera, email, created_at, genero, fecha_nacimiento)\n        VALUES (?, ?, ?, ?, ?, ?, ?, ?)'
)
text = text.replace(
    '            email=excluded.email,\n            genero=excluded.genero\n        """,\n        (sid, matricula, nombre, carrera, email, now_str(), genero),',
    '            email=excluded.email,\n            genero=excluded.genero,\n            fecha_nacimiento=excluded.fecha_nacimiento\n        """,\n        (sid, matricula, nombre, carrera, email, now_str(), genero, fecha_nac),'
)

# 6. verify_google
text = text.replace(
    '        domain_to_check = ALLOWED_DOMAIN if ALLOWED_DOMAIN else "utslp.edu.mx"\n        allowed_domains = [domain_to_check, "plataforma-utslp.net", "alumnos.utslp.edu.mx", "docentes.utslp.edu.mx"]',
    '        domain_to_check = ALLOWED_DOMAIN if ALLOWED_DOMAIN else "plataforma-utslp.net"\n        allowed_domains = [domain_to_check]'
)
text = text.replace(
    '            raise HTTPException(status_code=403, detail="Acceso denegado: Usa tu correo institucional UTSLP (no se permiten cuentas personales)")',
    '            raise HTTPException(status_code=403, detail="Acceso denegado: Usa cuenta exclusivamenta terminada en @plataforma-utslp.net")'
)

# 7. register API definition
text = text.replace(
    '    matricula: str = Form(...),\n    carrera: str = Form(...),\n    nombre: str = Form(""),\n    genero: str = Form("O"),',
    '    carrera: str = Form(...),\n    genero: str = Form("O"),\n    fecha_nacimiento: str = Form(""),\n    matricula: str = Form(""),\n    nombre: str = Form(""),'
)

# 8. register API body
old_body = '''    if auth.get("name"):
        nombre_final = auth["name"]
    else:
        nombre_final = nombre.strip()

    if not nombre_final:
        raise HTTPException(status_code=400, detail="Falta nombre")

    labels = load_labels()
    sid = upsert_student(labels, matricula, nombre_final, carrera, email, genero)'''

new_body = '''    if auth.get("name"):
        nombre_final = auth["name"]
    else:
        nombre_final = nombre.strip()

    if not nombre_final:
        raise HTTPException(status_code=400, detail="Falta nombre y no se pudo obtener de Google")

    matricula_final = matricula.strip()
    if not matricula_final and email:
        import re
        username = email.split('@')[0]
        digits = re.sub(r'\\D', '', username)
        if digits:
            matricula_final = digits

    if not matricula_final:
        raise HTTPException(status_code=400, detail="Falta matricula y no se pudo deducir del correo")

    labels = load_labels()
    sid = upsert_student(labels, matricula_final, nombre_final, carrera, email, genero, fecha_nacimiento)'''

text = text.replace(old_body, new_body)

with open('server/api.py', 'w', encoding='utf-8') as f:
    f.write(text)

print("PARCHEO API.PY EXITOSO")
