"""Pruebas reproducibles - Andres Sabogal - Variacion D Rentabilidad.
Ejecutar: python -m pytest -v
"""
import pytest
from fastapi.testclient import TestClient

from app.main import create_app

DOS_CAFES = [{"sku": "LATTE", "categoria": "bebida_caliente", "precio": 9000},
             {"sku": "TINTO", "categoria": "bebida_caliente", "precio": 5000}]


@pytest.fixture
def client():
    return TestClient(create_app(secreto="clave-pruebas"))


def emitir(client, **cambios):
    cuerpo = {"cliente_id": "C-100", "tienda_id": "T03", "canal": "APP", "fecha": "2026-03-18",
              "codigo_promocion": "CAFE2", "items": DOS_CAFES}
    cuerpo.update(cambios)
    return client.post("/v1/beneficios/emitir", json=cuerpo)


# 1. CASO VALIDO -----------------------------------------------------------
def test_caso_valido_cliente_activo_dos_cafes(client):
    r = emitir(client)
    assert r.status_code == 200
    b = r.json()
    assert b["aplica"] is True and b["descuento_cop"] == 1000        # 20 % de 5000
    assert b["explicacion"]["consistencia"] == "Todas las versiones vigentes coinciden"
    assert {e["regla"] for e in b["explicacion"]["reglas_evaluadas"]} == {"POL-01", "POL-02"}
    assert b["request_id"] == r.headers["X-Request-ID"]
    assert b["token"].count(".") == 1


def test_caso_valido_antes_de_pol02_solo_una_version(client):
    r = emitir(client, cliente_id="C-200", fecha="2026-03-12")      # dia de INC-01
    assert r.status_code == 200
    assert r.json()["explicacion"]["consistencia"] == "Una sola version vigente"


def test_redencion_valida_e_idempotente(client):
    token = emitir(client).json()["token"]
    cuerpo = {"token": token, "tienda_id": "T03", "fecha": "2026-03-18", "idempotency_key": "pos-T03-0001"}
    r1 = client.post("/v1/beneficios/redimir", json=cuerpo)
    r2 = client.post("/v1/beneficios/redimir", json=cuerpo)          # reintento (INC-03)
    assert r1.status_code == r2.status_code == 200
    assert r2.headers.get("Idempotent-Replay") == "true"
    assert r1.json()["beneficio_id"] == r2.json()["beneficio_id"]
    assert client.get("/v1/libro").json()["beneficios_redimidos"] == 1           # no se duplico


# 2. ENTRADA INVALIDA -------------------------------------------------------
def test_entrada_invalida_precio_negativo_y_tienda_mal_formada(client):
    r = emitir(client, tienda_id="tienda3",
               items=[{"sku": "X", "categoria": "bebida_caliente", "precio": -5}])
    assert r.status_code == 422
    b = r.json()
    assert b["error"]["codigo"] == "ENTRADA_INVALIDA"
    campos = {d["campo"] for d in b["error"]["detalle"]}
    assert "tienda_id" in campos and "items.0.precio" in campos
    assert b["request_id"].startswith("req-")


def test_token_alterado_rechazado(client):
    token = emitir(client).json()["token"]
    alterado = token[:-3] + ("AAA" if not token.endswith("AAA") else "BBB")
    r = client.post("/v1/beneficios/redimir", json={"token": alterado, "tienda_id": "T03",
                                                    "fecha": "2026-03-18", "idempotency_key": "pos-T03-0002"})
    assert r.status_code == 401 and r.json()["error"]["codigo"] == "FIRMA_INVALIDA"


# 3. CONFLICTO / EXCEPCION DEL CASO ----------------------------------------
def test_conflicto_pol01_vs_pol02_cliente_no_activo(client):
    r = emitir(client, cliente_id="C-200")          # POL-01 aplica, POL-02 no (no activo)
    assert r.status_code == 409
    err = r.json()["error"]
    assert err["codigo"] == "CONFLICTO_POLITICA"
    assert err["requiere_revision_humana"] is True
    assert {e["regla"]: e["aplica"] for e in err["evaluaciones"]} == {"POL-01": True, "POL-02": False}
    assert "token" not in r.json()
    assert client.get("/v1/libro").json()["conflictos_a_revision"] == 1


def test_conflicto_te_solo_elegible_en_pol02(client):
    items = [{"sku": "LATTE", "categoria": "bebida_caliente", "precio": 9000},
             {"sku": "TE", "categoria": "te", "precio": 6000}]
    r = emitir(client, items=items)
    assert r.status_code == 409


def test_doble_redencion_con_otra_operacion(client):
    token = emitir(client).json()["token"]
    base = {"token": token, "tienda_id": "T03", "fecha": "2026-03-18"}
    assert client.post("/v1/beneficios/redimir", json={**base, "idempotency_key": "pos-T03-0003"}).status_code == 200
    r = client.post("/v1/beneficios/redimir", json={**base, "tienda_id": "T05", "idempotency_key": "pos-T05-0099"})
    assert r.status_code == 409 and r.json()["error"]["codigo"] == "YA_REDIMIDO"


def test_tienda_fuera_de_piloto(client):
    r = emitir(client, tienda_id="T40")
    assert r.status_code == 403 and r.json()["error"]["codigo"] == "TIENDA_FUERA_DE_PILOTO"


# ---- Tren de lanzamientos -------------------------------------------------
def test_tren_lanzamientos_pol02_no_rige_hasta_el_lunes(client):
    # POL-02 se publica el domingo 15; entra en vigor el lunes 16. El 15 solo rige POL-01: sin conflicto.
    r = emitir(client, cliente_id="C-200", fecha="2026-03-15")
    assert r.status_code == 200
    assert r.json()["version_mostrador"] == "CAFE2 v1"


# ---- Te debemos un cafe ---------------------------------------------------
def deuda(client, **cambios):
    cuerpo = {"cliente_id": "C-100", "tienda_id": "T10", "cajero_id": "CAJ-07", "fecha": "2026-03-18",
              "motivo": "POS_NO_RECONOCE", "idempotency_key": "deuda-T10-0001"}
    cuerpo.update(cambios)
    return client.post("/v1/promesa/deuda", json=cuerpo)


def test_vale_nivel_promesa_doble_y_costo_al_aliado(client):
    r = deuda(client)
    assert r.status_code == 200
    b = r.json()
    assert b["resultado"] == "TE_DEBEMOS_UN_CAFE" and b["cafes"] == 2          # cliente activo: doble
    assert b["explicacion"]["cargado_a"] == "Aliado de la tienda T10"
    assert b["explicacion"]["decidido_por"] == "CAJ-07"
    libro = client.get("/v1/libro").json()
    assert libro["costo_por_responsable_cop"] == {"Aliado de la tienda T10": 8000}


def test_vale_por_conflicto_se_carga_a_duenos_de_politica(client):
    rid = emitir(client, cliente_id="C-200").json()["request_id"]           # 409
    r = deuda(client, cliente_id="C-200", tienda_id="T03", motivo="CONFLICTO_POLITICA",
              referencia_request_id=rid, idempotency_key="deuda-T03-0001")
    assert r.status_code == 200 and r.json()["cafes"] == 1
    assert r.json()["explicacion"]["cargado_a"].startswith("Duenos de politica")


def test_vale_conflicto_sin_referencia_confirmada(client):
    r = deuda(client, motivo="CONFLICTO_POLITICA", referencia_request_id="req-inventado")
    assert r.status_code == 422 and r.json()["error"]["codigo"] == "REFERENCIA_NO_CONFIRMADA"


def test_tope_diario_de_vales(client):
    assert deuda(client).status_code == 200
    r = deuda(client, idempotency_key="deuda-T10-0002")
    assert r.status_code == 409 and r.json()["error"]["codigo"] == "TOPE_DIARIO"


def test_cobrar_y_donar_vale(client):
    token = deuda(client).json()["token"]
    base = {"token": token, "tienda_id": "T01", "fecha": "2026-03-20"}
    r = client.post("/v1/promesa/cobrar", json={**base, "destino": "DONAR", "idempotency_key": "cobro-0001"})
    assert r.status_code == 200 and r.json()["resultado"] == "CAFE_PENDIENTE_DONADO"
    r2 = client.post("/v1/promesa/cobrar", json={**base, "idempotency_key": "cobro-0002"})
    assert r2.status_code == 409 and r2.json()["error"]["codigo"] == "VALE_YA_USADO"
    assert client.get("/v1/libro").json()["cafes_pendientes_donados"] == 2


def test_vale_no_sirve_como_beneficio(client):
    token = deuda(client).json()["token"]
    r = client.post("/v1/beneficios/redimir", json={"token": token, "tienda_id": "T03",
                                                    "fecha": "2026-03-18", "idempotency_key": "pos-T03-0100"})
    assert r.status_code == 422 and r.json()["error"]["codigo"] == "TIPO_COMPROBANTE_INCORRECTO"


# ---- Reportar error (recompensa) y liga ----------------------------------
def test_reporte_confirmado_y_no_confirmado(client):
    rid = emitir(client, cliente_id="C-200").json()["request_id"]
    base = {"cliente_id": "C-200", "tienda_id": "T03", "fecha": "2026-03-18",
            "descripcion": "La app mostraba CAFE2 y la caja no lo aplico"}
    ok = client.post("/v1/promesa/reportar", json={**base, "referencia_request_id": rid})
    assert ok.status_code == 200 and ok.json()["resultado"] == "CONFIRMADO"
    no = client.post("/v1/promesa/reportar", json={**base, "referencia_request_id": "req-falso01"})
    assert no.status_code == 202 and no.json()["resultado"] == "EN_REVISION"


def test_liga_de_tiendas(client):
    deuda(client)                                                            # T10 debe 2 cafes
    ranking = client.get("/v1/liga").json()["ranking"]
    assert ranking[-1]["tienda"] == "T10" and ranking[-1]["cafes_debidos"] == 2
    assert ranking[0]["cafes_debidos"] == 0
