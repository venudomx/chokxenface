"""
Herramienta rápida para ver la Base de Datos de Chokxen Face.
Ejecuta: py ver_db.py
"""
import sqlite3, json, os

DB = os.path.join(os.path.dirname(__file__), "server", "faceaccess.db")
LABELS = os.path.join(os.path.dirname(__file__), "labels.json")

print("=" * 60)
print("  CHOKXEN FACE - VISOR DE BASE DE DATOS")
print("=" * 60)

# Labels.json
print("\n📋 ALUMNOS REGISTRADOS (labels.json):")
print("-" * 50)
if os.path.exists(LABELS):
    with open(LABELS, "r", encoding="utf-8") as f:
        data = json.load(f)
    for sid, info in data.get("students", {}).items():
        print(f"  ID: {sid} | {info.get('nombre', '?')} | Mat: {info.get('matricula', '?')} | {info.get('carrera', '?')}")
        print(f"         Email: {info.get('email', 'SIN EMAIL')} | Actualizado: {info.get('updated_at', '?')}")
    print(f"\n  Siguiente ID libre: {data.get('next_id', '?')}")
else:
    print("  ⚠ No se encontró labels.json")

# SQLite DB
if os.path.exists(DB):
    con = sqlite3.connect(DB)
    cur = con.cursor()
    
    # Tables
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cur.fetchall()]
    print(f"\n📊 TABLAS EN LA DB: {tables}")
    
    # Events
    print("\n📌 ÚLTIMOS 10 EVENTOS (entradas/salidas):")
    print("-" * 50)
    cur.execute("SELECT ts, student_id, nombre, event_type, source FROM events ORDER BY id DESC LIMIT 10")
    rows = cur.fetchall()
    if rows:
        for r in rows:
            print(f"  [{r[0]}] ID:{r[1]} {r[2]} → {r[3]} (desde: {r[4]})")
    else:
        print("  (Sin eventos registrados)")
    
    # Absences
    print("\n❌ FALTAS REGISTRADAS:")
    print("-" * 50)
    cur.execute("SELECT student_id, date, reason FROM absences ORDER BY id DESC LIMIT 10")
    absences = cur.fetchall()
    if absences:
        for a in absences:
            print(f"  Alumno ID:{a[0]} | Fecha: {a[1]} | Motivo: {a[2]}")
    else:
        print("  (Sin faltas registradas)")
    
    con.close()
else:
    print(f"\n⚠ No se encontró la base de datos en: {DB}")

print("\n" + "=" * 60)
input("Presiona ENTER para cerrar...")
