"""Persistencia en SQLite (biblioteca estándar): órdenes, eventos y webhooks recibidos."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

ESQUEMA = """
CREATE TABLE IF NOT EXISTS ordenes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT UNIQUE,
    cliente TEXT NOT NULL,
    direccion TEXT NOT NULL,
    servicio TEXT NOT NULL,
    prioridad TEXT NOT NULL,
    descripcion TEXT,
    estado TEXT NOT NULL,
    intentos INTEGER NOT NULL DEFAULT 0,
    referencia_externa TEXT,
    tecnico TEXT,
    ultimo_error TEXT,
    creada_en TEXT NOT NULL,
    actualizada_en TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS eventos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    orden_codigo TEXT,
    tipo TEXT NOT NULL,
    detalle TEXT,
    creado_en TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS webhooks_recibidos (
    id_evento TEXT PRIMARY KEY,
    orden_codigo TEXT,
    tipo TEXT,
    recibido_en TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_eventos_orden ON eventos(orden_codigo);
"""


def ahora_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class BaseDatos:
    def __init__(self, ruta: str):
        self.ruta = ruta
        with self.conexion() as con:
            con.execute("PRAGMA journal_mode=WAL")
            con.executescript(ESQUEMA)

    @contextmanager
    def conexion(self) -> Iterator[sqlite3.Connection]:
        con = sqlite3.connect(self.ruta, timeout=10)
        con.row_factory = sqlite3.Row
        try:
            yield con
            con.commit()
        finally:
            con.close()


class Repositorio:
    def __init__(self, bd: BaseDatos):
        self.bd = bd

    def crear_orden(self, datos: dict) -> dict:
        momento = ahora_iso()
        with self.bd.conexion() as con:
            cursor = con.execute(
                "INSERT INTO ordenes (cliente, direccion, servicio, prioridad, descripcion, estado, creada_en, actualizada_en)"
                " VALUES (?, ?, ?, ?, ?, 'PENDIENTE', ?, ?)",
                (datos["cliente"], datos["direccion"], datos["servicio"], datos["prioridad"], datos.get("descripcion"),
                 momento, momento))
            codigo = f"OT-{cursor.lastrowid:04d}"
            con.execute("UPDATE ordenes SET codigo = ? WHERE id = ?", (codigo, cursor.lastrowid))
            con.execute("INSERT INTO eventos (orden_codigo, tipo, detalle, creado_en) VALUES (?, 'ORDEN_CREADA', ?, ?)",
                        (codigo, f"Orden de {datos['servicio']} con prioridad {datos['prioridad']}", momento))
        return self.obtener(codigo)

    def obtener(self, codigo: str) -> dict | None:
        with self.bd.conexion() as con:
            fila = con.execute("SELECT * FROM ordenes WHERE codigo = ?", (codigo,)).fetchone()
        return _sin_id(dict(fila)) if fila else None

    def listar(self, estado: str | None = None, texto: str | None = None, limite: int = 20,
               desplazamiento: int = 0) -> tuple[list[dict], int]:
        condiciones, parametros = [], []
        if estado:
            condiciones.append("estado = ?")
            parametros.append(estado)
        if texto:
            condiciones.append("(lower(cliente) LIKE ? OR lower(codigo) LIKE ?)")
            parametros += [f"%{texto.lower()}%"] * 2
        donde = f"WHERE {' AND '.join(condiciones)}" if condiciones else ""
        with self.bd.conexion() as con:
            total = con.execute(f"SELECT COUNT(*) FROM ordenes {donde}", parametros).fetchone()[0]
            filas = con.execute(f"SELECT * FROM ordenes {donde} ORDER BY id DESC LIMIT ? OFFSET ?",
                                [*parametros, limite, desplazamiento]).fetchall()
        return [_sin_id(dict(f)) for f in filas], total

    def actualizar(self, codigo: str, **campos) -> None:
        campos["actualizada_en"] = ahora_iso()
        asignaciones = ", ".join(f"{campo} = ?" for campo in campos)
        with self.bd.conexion() as con:
            con.execute(f"UPDATE ordenes SET {asignaciones} WHERE codigo = ?", [*campos.values(), codigo])

    def registrar_evento(self, codigo: str | None, tipo: str, detalle: str) -> None:
        with self.bd.conexion() as con:
            con.execute("INSERT INTO eventos (orden_codigo, tipo, detalle, creado_en) VALUES (?, ?, ?, ?)",
                        (codigo, tipo, detalle, ahora_iso()))

    def eventos(self, codigo: str | None = None, tipo: str | None = None, limite: int = 50) -> list[dict]:
        condiciones, parametros = [], []
        if codigo:
            condiciones.append("orden_codigo = ?")
            parametros.append(codigo)
        if tipo:
            condiciones.append("tipo = ?")
            parametros.append(tipo)
        donde = f"WHERE {' AND '.join(condiciones)}" if condiciones else ""
        with self.bd.conexion() as con:
            filas = con.execute(f"SELECT * FROM eventos {donde} ORDER BY id DESC LIMIT ?", [*parametros, limite]).fetchall()
        return [dict(f) for f in filas]

    def webhook_ya_recibido(self, id_evento: str) -> bool:
        with self.bd.conexion() as con:
            return con.execute("SELECT 1 FROM webhooks_recibidos WHERE id_evento = ?", (id_evento,)).fetchone() is not None

    def guardar_webhook(self, id_evento: str, codigo: str, tipo: str) -> None:
        with self.bd.conexion() as con:
            con.execute("INSERT INTO webhooks_recibidos (id_evento, orden_codigo, tipo, recibido_en) VALUES (?, ?, ?, ?)",
                        (id_evento, codigo, tipo, ahora_iso()))

    def resumen(self) -> dict:
        with self.bd.conexion() as con:
            por_estado = {f["estado"]: f["n"] for f in con.execute("SELECT estado, COUNT(*) AS n FROM ordenes GROUP BY estado")}
            promedio = con.execute("SELECT AVG(intentos) FROM ordenes WHERE intentos > 0").fetchone()[0]
            reintentos = con.execute("SELECT COUNT(*) FROM eventos WHERE tipo = 'ENVIO_FALLIDO'").fetchone()[0]
        total = sum(por_estado.values())
        entregadas = sum(por_estado.get(e, 0) for e in ("ENVIADA", "ASIGNADA", "COMPLETADA"))
        con_error = por_estado.get("ERROR_INTEGRACION", 0)
        finalizadas = entregadas + con_error
        return {
            "total": total,
            "por_estado": por_estado,
            "entregadas_al_proveedor": entregadas,
            "con_error": con_error,
            "fallas_transitorias": reintentos,
            "tasa_exito": round(100 * entregadas / finalizadas, 1) if finalizadas else None,
            "promedio_intentos": round(promedio, 2) if promedio else None,
        }


def _sin_id(fila: dict) -> dict:
    fila.pop("id", None)
    return fila
