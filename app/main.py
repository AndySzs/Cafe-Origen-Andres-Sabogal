"""
Promesa Cafe Origen: cumplida, o te debemos un cafe  (caso ficticio)
Proyecto final - Andres Sabogal - Variacion D Rentabilidad

1. Emitir: resuelve la regla aplicable (catalogo versionado + tren de lanzamientos
   de los lunes) y emite un comprobante firmado. Si las versiones vigentes se
   contradicen, NO decide: 409 y revision humana.
2. Redimir: el POS verifica la firma y aplica una sola vez (idempotente).
3. Te debemos un cafe: si la promesa falla, un HUMANO (cajero) emite un vale.
   Nivel Promesa (cliente activo) recibe el doble. El costo se carga a quien
   causo la falla (politica, operaciones o aliado).
4. Cobrar o donar el vale (cafe pendiente).
5. Reportar error: el cliente reporta; el sistema confirma contra el libro y
   recomienda; la emision del vale sigue siendo humana.
6. Libro y liga de tiendas: costo de la inconsistencia y ranking.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

DATOS = Path(__file__).resolve().parent.parent / "datos"

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("promesa")

RESP_POLITICA = "Duenos de politica (comercial + operaciones)"
RESP_OPERACIONES = "Operaciones de tiendas propias"


# ================================================================ modelos
class Item(BaseModel):
    sku: str = Field(min_length=1, max_length=40)
    categoria: Literal["bebida_caliente", "te", "bebida_fria", "alimento"]
    precio: int = Field(gt=0, le=1_000_000, description="Precio en COP")


class SolicitudEmision(BaseModel):
    cliente_id: str = Field(min_length=1, max_length=20)
    tienda_id: str = Field(pattern=r"^T\d{2}$")
    canal: Literal["APP", "WEB", "POS"]
    fecha: date
    codigo_promocion: str = Field(min_length=1, max_length=20)
    items: list[Item] = Field(min_length=1, max_length=50)

    model_config = {"json_schema_extra": {"examples": [{
        "cliente_id": "C-100", "tienda_id": "T03", "canal": "APP", "fecha": "2026-03-18",
        "codigo_promocion": "CAFE2",
        "items": [{"sku": "LATTE", "categoria": "bebida_caliente", "precio": 9000},
                  {"sku": "TINTO", "categoria": "bebida_caliente", "precio": 5000}]}]}}


class SolicitudRedencion(BaseModel):
    token: str = Field(min_length=10, max_length=4000)
    tienda_id: str = Field(pattern=r"^T\d{2}$")
    fecha: date
    idempotency_key: str = Field(min_length=8, max_length=80)


class SolicitudDeuda(BaseModel):
    cliente_id: str = Field(min_length=1, max_length=20)
    tienda_id: str = Field(pattern=r"^T\d{2}$")
    cajero_id: str = Field(min_length=3, max_length=20, description="Humano que toma la decision")
    fecha: date
    motivo: Literal["CONFLICTO_POLITICA", "POS_NO_RECONOCE", "SIN_CONEXION", "REPORTE_CLIENTE"]
    referencia_request_id: str | None = Field(default=None, max_length=40)
    idempotency_key: str = Field(min_length=8, max_length=80)

    model_config = {"json_schema_extra": {"examples": [{
        "cliente_id": "C-100", "tienda_id": "T10", "cajero_id": "CAJ-07", "fecha": "2026-03-18",
        "motivo": "POS_NO_RECONOCE", "idempotency_key": "deuda-T10-0001"}]}}


class SolicitudCobro(BaseModel):
    token: str = Field(min_length=10, max_length=4000)
    tienda_id: str = Field(pattern=r"^T\d{2}$")
    fecha: date
    destino: Literal["CLIENTE", "DONAR"] = "CLIENTE"
    idempotency_key: str = Field(min_length=8, max_length=80)


class SolicitudReporte(BaseModel):
    cliente_id: str = Field(min_length=1, max_length=20)
    tienda_id: str = Field(pattern=r"^T\d{2}$")
    fecha: date
    referencia_request_id: str = Field(min_length=4, max_length=40)
    descripcion: str = Field(min_length=5, max_length=500)


# ================================================================ errores
class ErrorNegocio(Exception):
    def __init__(self, status: int, codigo: str, mensaje: str, **extra):
        self.status, self.codigo, self.mensaje, self.extra = status, codigo, mensaje, extra


# ================================================================ firma
def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(texto: str) -> bytes:
    return base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))


def firmar(payload: dict, secreto: bytes) -> str:
    cuerpo = _b64(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
    firma = _b64(hmac.new(secreto, cuerpo.encode(), hashlib.sha256).digest())
    return f"{cuerpo}.{firma}"


def verificar(token: str, secreto: bytes, tipo: str) -> dict:
    try:
        cuerpo, firma = token.split(".")
        esperada = _b64(hmac.new(secreto, cuerpo.encode(), hashlib.sha256).digest())
    except ValueError:
        raise ErrorNegocio(422, "TOKEN_MALFORMADO", "El comprobante no tiene el formato esperado.")
    if not hmac.compare_digest(firma, esperada):
        raise ErrorNegocio(401, "FIRMA_INVALIDA",
                           "La firma no corresponde: el comprobante fue alterado o no lo emitio este servicio.")
    datos = json.loads(_unb64(cuerpo))
    if datos.get("tipo") != tipo:
        raise ErrorNegocio(422, "TIPO_COMPROBANTE_INCORRECTO", f"Se esperaba un comprobante de tipo {tipo}.")
    return datos


# ================================================================ reglas
def lunes_siguiente(d: date) -> date:
    """Tren de lanzamientos: una version entra en vigor el lunes siguiente (o el mismo dia si es lunes)."""
    return d + timedelta(days=(7 - d.weekday()) % 7)


def evaluar_version(v: dict, sol: SolicitudEmision, cliente_activo: bool) -> dict:
    base = {"regla": v["id"], "version": v["version"], "fuente": v["fuente"]}
    if v["requiere_cliente_activo"] and not cliente_activo:
        return {**base, "aplica": False, "descuento": 0,
                "motivo": "Requiere cliente activo del programa y el cliente no lo esta."}
    elegibles = sorted(i.precio for i in sol.items if i.categoria in v["categorias_elegibles"])
    if len(elegibles) < v["minimo_items"]:
        return {**base, "aplica": False, "descuento": 0,
                "motivo": f"Se requieren {v['minimo_items']} bebidas elegibles "
                          f"({', '.join(v['categorias_elegibles'])}); hay {len(elegibles)}."}
    descuento = round(elegibles[0] * v["descuento_pct"] / 100)
    return {**base, "aplica": True, "descuento": descuento,
            "motivo": f"{v['descuento_pct']} % sobre la bebida elegible de menor precio ({elegibles[0]} COP)."}


# ================================================================ app
def create_app(secreto: str | None = None) -> FastAPI:
    app = FastAPI(
        title="Promesa Cafe Origen: cumplida, o te debemos un cafe",
        version="1.0.0",
        description="Prototipo academico con datos ficticios. Andres Sabogal - Variacion D Rentabilidad.",
    )
    reglas = json.loads((DATOS / "reglas.json").read_text(encoding="utf-8"))
    maestros = json.loads((DATOS / "clientes.json").read_text(encoding="utf-8"))
    P = maestros["parametros"]
    tiendas = maestros["tiendas_piloto"]
    clave = (secreto or os.getenv("FIRMA_SECRETO", "secreto-demo-no-usar-en-produccion")).encode()

    # Libro de beneficios: en memoria en el prototipo (en nube: tabla con clave unica y escritura condicional)
    libro: list[dict] = []
    usados: dict[str, str] = {}             # beneficio_id / vale_id -> idempotency_key
    respuestas_idem: dict[str, dict] = {}   # idempotency_key -> respuesta original
    conflictos: dict[str, dict] = {}        # request_id del 409 -> datos
    vales_por_cliente_dia: dict[tuple, int] = defaultdict(int)

    def registrar(evento: str, rid: str, **datos):
        libro.append({"evento": evento, "request_id": rid, "ts": time.time(), **datos})

    def replay(key: str):
        if key in respuestas_idem:
            return JSONResponse(respuestas_idem[key], headers={"Idempotent-Replay": "true"})
        return None

    def tienda_piloto(tid: str) -> str:
        if tid not in tiendas:
            raise ErrorNegocio(403, "TIENDA_FUERA_DE_PILOTO",
                               f"La tienda {tid} no esta en el piloto; se usa el proceso actual.")
        return tiendas[tid]

    def cliente(cid: str) -> dict:
        c = maestros["clientes"].get(cid)
        if c is None:
            raise ErrorNegocio(404, "CLIENTE_DESCONOCIDO", f"No existe el cliente {cid}.")
        return c

    def responsable(motivo: str, tipo_tienda: str, tienda_id: str) -> str:
        if motivo in ("CONFLICTO_POLITICA", "REPORTE_CLIENTE"):
            return RESP_POLITICA
        return f"Aliado de la tienda {tienda_id}" if tipo_tienda == "aliada" else RESP_OPERACIONES

    # ---- middleware: request_id + log estructurado
    @app.middleware("http")
    async def request_id_mw(request: Request, call_next):
        rid = request.headers.get("X-Request-ID") or f"req-{uuid.uuid4().hex[:12]}"
        request.state.rid = rid
        t0 = time.perf_counter()
        resp = await call_next(request)
        resp.headers["X-Request-ID"] = rid
        log.info(json.dumps({"request_id": rid, "metodo": request.method, "ruta": request.url.path,
                             "status": resp.status_code, "ms": round((time.perf_counter() - t0) * 1000, 2)}))
        return resp

    @app.exception_handler(ErrorNegocio)
    async def _err_negocio(request: Request, exc: ErrorNegocio):
        return JSONResponse(status_code=exc.status, content={
            "request_id": request.state.rid,
            "error": {"codigo": exc.codigo, "mensaje": exc.mensaje, **exc.extra}})

    @app.exception_handler(RequestValidationError)
    async def _err_validacion(request: Request, exc: RequestValidationError):
        detalle = [{"campo": ".".join(str(x) for x in e["loc"][1:]), "problema": e["msg"]} for e in exc.errors()]
        return JSONResponse(status_code=422, content={
            "request_id": request.state.rid,
            "error": {"codigo": "ENTRADA_INVALIDA", "mensaje": "La solicitud no cumple el contrato.",
                      "detalle": detalle}})

    @app.get("/health")
    def health():
        return {"estado": "ok"}

    # ------------------------------------------------------------ 1. emitir
    @app.post("/v1/beneficios/emitir", tags=["Promesa"],
              summary="Resuelve la regla aplicable y emite un beneficio firmado")
    def emitir(sol: SolicitudEmision, request: Request):
        rid = request.state.rid
        c = cliente(sol.cliente_id)
        tienda_piloto(sol.tienda_id)
        promo = reglas["promociones"].get(sol.codigo_promocion)
        if promo is None:
            raise ErrorNegocio(404, "PROMOCION_DESCONOCIDA", f"No existe la promocion {sol.codigo_promocion}.")

        vigentes = [v for v in promo["versiones"]
                    if lunes_siguiente(date.fromisoformat(v["publicada"])) <= sol.fecha
                    <= date.fromisoformat(v["vence"])]
        if not vigentes:
            raise ErrorNegocio(422, "PROMOCION_NO_VIGENTE",
                               f"Ninguna version de {sol.codigo_promocion} esta vigente el {sol.fecha} "
                               "(las versiones entran en vigor el lunes siguiente a su publicacion).")
        if promo.get("acta_precedencia"):
            vigentes = [v for v in vigentes if v["id"] == promo["acta_precedencia"]["version_vigente"]]

        version_mostrador = f"{sol.codigo_promocion} " + " + ".join(f"v{v['version']}" for v in vigentes)
        evaluaciones = [evaluar_version(v, sol, c["programa_activo"]) for v in vigentes]

        if len({(e["aplica"], e["descuento"]) for e in evaluaciones}) > 1:
            conflictos[rid] = {"cliente_id": sol.cliente_id, "tienda_id": sol.tienda_id}
            registrar("conflicto", rid, cliente_id=sol.cliente_id, tienda_id=sol.tienda_id,
                      reglas=[e["regla"] for e in evaluaciones])
            raise ErrorNegocio(
                409, "CONFLICTO_POLITICA",
                "Hay versiones vigentes que dan resultados distintos y no existe acta de precedencia. "
                "No se emite beneficio automatico.",
                requiere_revision_humana=True,
                version_mostrador=version_mostrador,
                recomendacion="El cajero puede aplicar la garantia (POST /v1/promesa/deuda, motivo "
                              "CONFLICTO_POLITICA). El caso va a la cola de los duenos de politica (E09).",
                evaluaciones=evaluaciones)

        e = evaluaciones[0]
        base = {"request_id": rid, "aplica": e["aplica"], "descuento_cop": e["descuento"],
                "version_mostrador": version_mostrador,
                "explicacion": {"reglas_evaluadas": evaluaciones,
                                "consistencia": "Una sola version vigente" if len(vigentes) == 1
                                else "Todas las versiones vigentes coinciden"}}
        if not e["aplica"]:
            return base
        beneficio_id = f"BEN-{uuid.uuid4().hex[:10]}"
        payload = {"tipo": "BENEFICIO", "beneficio_id": beneficio_id, "cliente_id": sol.cliente_id,
                   "reglas": [x["regla"] for x in evaluaciones], "descuento_cop": e["descuento"],
                   "emitido": sol.fecha.isoformat(),
                   "valido_hasta": (sol.fecha + timedelta(days=1)).isoformat(), "request_id": rid}
        registrar("emitido", rid, beneficio_id=beneficio_id, descuento_cop=e["descuento"],
                  reglas=payload["reglas"], tienda_id=sol.tienda_id)
        return {**base, "beneficio_id": beneficio_id, "valido_hasta": payload["valido_hasta"],
                "token": firmar(payload, clave)}

    # ------------------------------------------------------------ 2. redimir
    @app.post("/v1/beneficios/redimir", tags=["Promesa"],
              summary="Verifica la firma y redime una sola vez (idempotente)")
    def redimir(sol: SolicitudRedencion, request: Request):
        rid = request.state.rid
        if (r := replay(sol.idempotency_key)) is not None:
            return r
        datos = verificar(sol.token, clave, "BENEFICIO")
        if sol.fecha > date.fromisoformat(datos["valido_hasta"]):
            raise ErrorNegocio(409, "BENEFICIO_VENCIDO", f"El beneficio vencio el {datos['valido_hasta']}.")
        if datos["beneficio_id"] in usados:
            raise ErrorNegocio(409, "YA_REDIMIDO",
                               "Este beneficio ya fue redimido con otra operacion; no se aplica dos veces.",
                               beneficio_id=datos["beneficio_id"])
        usados[datos["beneficio_id"]] = sol.idempotency_key
        registrar("redimido", rid, beneficio_id=datos["beneficio_id"], descuento_cop=datos["descuento_cop"],
                  tienda_id=sol.tienda_id)
        resp = {"request_id": rid, "resultado": "REDIMIDO", "beneficio_id": datos["beneficio_id"],
                "descuento_cop": datos["descuento_cop"],
                "explicacion": {"reglas": datos["reglas"], "verificacion": "Firma valida; primer uso",
                                "emision_request_id": datos["request_id"]}}
        respuestas_idem[sol.idempotency_key] = resp
        return resp

    # ------------------------------------------------------------ 3. te debemos un cafe
    @app.post("/v1/promesa/deuda", tags=["Te debemos un cafe"],
              summary="Un humano (cajero) emite un vale cuando la promesa falla")
    def crear_deuda(sol: SolicitudDeuda, request: Request):
        rid = request.state.rid
        if (r := replay(sol.idempotency_key)) is not None:
            return r
        c = cliente(sol.cliente_id)
        tipo_tienda = tienda_piloto(sol.tienda_id)
        if sol.motivo in ("CONFLICTO_POLITICA", "REPORTE_CLIENTE"):
            if not sol.referencia_request_id or sol.referencia_request_id not in conflictos:
                raise ErrorNegocio(422, "REFERENCIA_NO_CONFIRMADA",
                                   "Para este motivo se requiere el request_id de un conflicto registrado en el libro.")
        clave_tope = (sol.cliente_id, sol.fecha)
        if vales_por_cliente_dia[clave_tope] >= P["tope_vales_por_cliente_dia"]:
            raise ErrorNegocio(409, "TOPE_DIARIO",
                               f"El cliente ya recibio {P['tope_vales_por_cliente_dia']} vale(s) hoy. "
                               "Escalar a supervisor de tienda.")
        cafes = P["multiplicador_nivel_promesa"] if c["programa_activo"] else 1
        resp_costo = responsable(sol.motivo, tipo_tienda, sol.tienda_id)
        costo = cafes * P["costo_cafe_debido_cop"]
        vale_id = f"VALE-{uuid.uuid4().hex[:10]}"
        payload = {"tipo": "VALE", "vale_id": vale_id, "cliente_id": sol.cliente_id, "cafes": cafes,
                   "valido_hasta": (sol.fecha + timedelta(days=P["vigencia_vale_dias"])).isoformat(),
                   "request_id": rid}
        vales_por_cliente_dia[clave_tope] += 1
        registrar("deuda", rid, vale_id=vale_id, cafes=cafes, costo_cop=costo, responsable=resp_costo,
                  motivo=sol.motivo, tienda_id=sol.tienda_id, cajero_id=sol.cajero_id)
        resp = {"request_id": rid, "resultado": "TE_DEBEMOS_UN_CAFE", "vale_id": vale_id, "cafes": cafes,
                "valido_hasta": payload["valido_hasta"], "token": firmar(payload, clave),
                "explicacion": {
                    "decidido_por": sol.cajero_id,
                    "nivel": "Promesa (cliente activo: doble)" if c["programa_activo"] else "Estandar",
                    "costo_estimado_cop": costo, "cargado_a": resp_costo,
                    "regla_de_costo": "Quien causa la falla paga: politica, operaciones o aliado."}}
        respuestas_idem[sol.idempotency_key] = resp
        return resp

    # ------------------------------------------------------------ 4. cobrar o donar
    @app.post("/v1/promesa/cobrar", tags=["Te debemos un cafe"],
              summary="Cobra el vale o lo dona como cafe pendiente")
    def cobrar(sol: SolicitudCobro, request: Request):
        rid = request.state.rid
        if (r := replay(sol.idempotency_key)) is not None:
            return r
        tienda_piloto(sol.tienda_id)
        datos = verificar(sol.token, clave, "VALE")
        if sol.fecha > date.fromisoformat(datos["valido_hasta"]):
            raise ErrorNegocio(409, "VALE_VENCIDO", f"El vale vencio el {datos['valido_hasta']}.")
        if datos["vale_id"] in usados:
            raise ErrorNegocio(409, "VALE_YA_USADO", "Este vale ya fue cobrado o donado.", vale_id=datos["vale_id"])
        usados[datos["vale_id"]] = sol.idempotency_key
        evento = "cobrado" if sol.destino == "CLIENTE" else "donado"
        registrar(evento, rid, vale_id=datos["vale_id"], cafes=datos["cafes"], tienda_id=sol.tienda_id)
        resp = {"request_id": rid, "resultado": "COBRADO" if evento == "cobrado" else "CAFE_PENDIENTE_DONADO",
                "vale_id": datos["vale_id"], "cafes": datos["cafes"],
                "explicacion": {"verificacion": "Firma valida; primer uso", "tienda": sol.tienda_id}}
        respuestas_idem[sol.idempotency_key] = resp
        return resp

    # ------------------------------------------------------------ 5. reportar error
    @app.post("/v1/promesa/reportar", tags=["Te debemos un cafe"],
              summary="El cliente reporta un error; el sistema confirma contra el libro y recomienda")
    def reportar(sol: SolicitudReporte, request: Request):
        rid = request.state.rid
        cliente(sol.cliente_id)
        tienda_piloto(sol.tienda_id)
        conf = conflictos.get(sol.referencia_request_id)
        confirmado = conf is not None and conf["cliente_id"] == sol.cliente_id
        registrar("reporte", rid, cliente_id=sol.cliente_id, confirmado=confirmado,
                  referencia=sol.referencia_request_id)
        if not confirmado:
            return JSONResponse(status_code=202, content={
                "request_id": rid, "resultado": "EN_REVISION",
                "explicacion": "El libro no confirma una diferencia para esa referencia y este cliente. "
                               "No hay recompensa automatica; servicio revisa el caso."})
        return {"request_id": rid, "resultado": "CONFIRMADO",
                "recomendacion": "Emitir vale con motivo REPORTE_CLIENTE (decision humana en tienda o servicio).",
                "explicacion": {"conflicto_confirmado": sol.referencia_request_id,
                                "fuente": "Libro de beneficios"}}

    # ------------------------------------------------------------ 6. libro y liga
    @app.get("/v1/libro", tags=["Medicion"], summary="Costo de la inconsistencia e indicadores del piloto")
    def resumen_libro():
        def ev(n): return [x for x in libro if x["evento"] == n]
        por_resp: dict[str, int] = defaultdict(int)
        for d in ev("deuda"):
            por_resp[d["responsable"]] += d["costo_cop"]
        debidos = sum(d["cafes"] for d in ev("deuda"))
        usados_cafes = sum(d["cafes"] for d in ev("cobrado")) + sum(d["cafes"] for d in ev("donado"))
        return {"beneficios_emitidos": len(ev("emitido")), "beneficios_redimidos": len(ev("redimido")),
                "descuento_redimido_cop": sum(x["descuento_cop"] for x in ev("redimido")),
                "conflictos_a_revision": len(ev("conflicto")),
                "cafes_debidos": debidos, "cafes_cobrados": sum(d["cafes"] for d in ev("cobrado")),
                "cafes_pendientes_donados": sum(d["cafes"] for d in ev("donado")),
                "cafes_sin_usar": debidos - usados_cafes,
                "reportes_cliente": len(ev("reporte")),
                "reportes_confirmados": sum(1 for r in ev("reporte") if r["confirmado"]),
                "costo_inconsistencia_cop": sum(por_resp.values()),
                "costo_por_responsable_cop": dict(por_resp)}

    @app.get("/v1/liga", tags=["Medicion"], summary="Liga de tiendas: menos cafes debidos = mejor posicion")
    def liga():
        tabla = {t: {"tienda": t, "tipo": tipo, "cafes_debidos": 0, "conflictos": 0, "cafes_donados": 0}
                 for t, tipo in tiendas.items()}
        for x in libro:
            t = x.get("tienda_id")
            if t not in tabla:
                continue
            if x["evento"] == "deuda":
                tabla[t]["cafes_debidos"] += x["cafes"]
            elif x["evento"] == "conflicto":
                tabla[t]["conflictos"] += 1
            elif x["evento"] == "donado":
                tabla[t]["cafes_donados"] += x["cafes"]
        ranking = sorted(tabla.values(), key=lambda r: (r["cafes_debidos"] + r["conflictos"], -r["cafes_donados"], r["tienda"]))
        for i, r in enumerate(ranking, 1):
            r["posicion"] = i
        return {"criterio": "Menos cafes debidos y conflictos; desempate por cafes donados", "ranking": ranking}

    return app


app = create_app()
