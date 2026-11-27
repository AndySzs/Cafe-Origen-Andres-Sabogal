# Resultados de ejecucion · Andres Sabogal · Variacion D

Servidor local (uvicorn). Datos ficticios.

## 1_valido
```
HTTP/1.1 200 OK
content-type: application/json
x-request-id: req-f78ffddeb9da

{"request_id":"req-f78ffddeb9da","aplica":true,"descuento_cop":1000,"version_mostrador":"CAFE2 v1 + v2","explicacion":{"reglas_evaluadas":[{"regla":"POL-01","version":1,"fuente":["E07","Reglas!A2"],"aplica":true,"descuento":1000,"motivo":"20 % sobre la bebida elegible de menor precio (5000 COP)."},{"regla":"POL-02","version":2,"fuente":["E07","Reglas!A3"],"aplica":true,"descuento":1000,"motivo":"20 % sobre la bebida elegible de menor precio (5000 COP)."}],"consistencia":"Todas las versiones vigentes coinciden"},"beneficio_id":"BEN-1eec82e32a","valido_hasta":"2026-03-19","token":"eyJiZW5lZmljaW9faWQiOiJCRU4tMWVlYzgyZTMyYSIsImNsaWVudGVfaWQiOiJDLTEwMCIsImRlc2N1ZW50b19jb3AiOjEwMDAsImVtaXRpZG8iOiIyMDI2LTAzLTE4IiwicmVnbGFzIjpbIlBPTC0wMSIsIlBPTC0wMiJdLCJyZXF1ZXN0X2lkIjoicmVxLWY3OGZmZGRlYjlkYSIsInRpcG8iOiJCRU5FRklDSU8iLCJ2YWxpZG9faGFzdGEiOiIyMDI2LTAzLTE5In0.zgeJJHtM345TxaJcA12Cm5PMu3yJo8wM8w5bEM2XplM"}

```

## 2_invalido
```
HTTP/1.1 422 Unprocessable Content
content-type: application/json
x-request-id: req-a68759a4bafe

{"request_id":"req-a68759a4bafe","error":{"codigo":"ENTRADA_INVALIDA","mensaje":"La solicitud no cumple el contrato.","detalle":[{"campo":"tienda_id","problema":"String should match pattern '^T\\d{2}$'"},{"campo":"items.0.precio","problema":"Input should be greater than 0"}]}}

```

## 3_conflicto
```
HTTP/1.1 409 Conflict
content-type: application/json
x-request-id: req-7eab711d1e87

{"request_id":"req-7eab711d1e87","error":{"codigo":"CONFLICTO_POLITICA","mensaje":"Hay versiones vigentes que dan resultados distintos y no existe acta de precedencia. No se emite beneficio automatico.","requiere_revision_humana":true,"version_mostrador":"CAFE2 v1 + v2","recomendacion":"El cajero puede aplicar la garantia (POST /v1/promesa/deuda, motivo CONFLICTO_POLITICA). El caso va a la cola de los duenos de politica (E09).","evaluaciones":[{"regla":"POL-01","version":1,"fuente":["E07","Reglas!A2"],"aplica":true,"descuento":1000,"motivo":"20 % sobre la bebida elegible de menor precio (5000 COP)."},{"regla":"POL-02","version":2,"fuente":["E07","Reglas!A3"],"aplica":false,"descuento":0,"motivo":"Requiere cliente activo del programa y el cliente no lo esta."}]}}

```

## 4 Redimir: primera vez, reintento con la misma llave (idempotente) y otra operacion (YA_REDIMIDO)
```
{"request_id":"req-bebdcf9a1820","resultado":"REDIMIDO","beneficio_id":"BEN-7014ec9ea6","descuento_cop":1000,"explicacion":{"reglas":["POL-01","POL-02"],"verificacion":"Firma valida; primer uso","emision_request_id":"req-b4db448fe48e"}}
{"request_id":"req-bebdcf9a1820","resultado":"REDIMIDO","beneficio_id":"BEN-7014ec9ea6","descuento_cop":1000,"explicacion":{"reglas":["POL-01","POL-02"],"verificacion":"Firma valida; primer uso","emision_request_id":"req-b4db448fe48e"}}
{"request_id":"req-e57ca73f41d6","error":{"codigo":"YA_REDIMIDO","mensaje":"Este beneficio ya fue redimido con otra operacion; no se aplica dos veces.","beneficio_id":"BEN-7014ec9ea6"}}
```

## 5 Te debemos un cafe: tienda aliada T10, cliente nivel Promesa (doble, cargado al aliado)
```
{"request_id":"req-82bbc98e3972","resultado":"TE_DEBEMOS_UN_CAFE","vale_id":"VALE-ff376dbd82","cafes":2,"valido_hasta":"2026-04-17","token":"eyJjYWZlcyI6MiwiY2xpZW50ZV9pZCI6IkMtMTAwIiwicmVxdWVzdF9pZCI6InJlcS04MmJiYzk4ZTM5NzIiLCJ0aXBvIjoiVkFMRSIsInZhbGVfaWQiOiJWQUxFLWZmMzc2ZGJkODIiLCJ2YWxpZG9faGFzdGEiOiIyMDI2LTA0LTE3In0.HC9gMVu3FV3w0UV1dQQn292gdiuo2MbdrHjyAmo-5no","explicacion":{"decidido_por":"CAJ-07","nivel":"Promesa (cliente activo: doble)","costo_estimado_cop":8000,"cargado_a":"Aliado de la tienda T10","regla_de_costo":"Quien causa la falla paga: politica, operaciones o aliado."}}
```

## 6 Vale por conflicto de politica (cargado a duenos de politica)
```
{"request_id":"req-733226de12c7","resultado":"TE_DEBEMOS_UN_CAFE","vale_id":"VALE-9c220437a5","cafes":1,"valido_hasta":"2026-04-17","token":"eyJjYWZlcyI6MSwiY2xpZW50ZV9pZCI6IkMtMjAwIiwicmVxdWVzdF9pZCI6InJlcS03MzMyMjZkZTEyYzciLCJ0aXBvIjoiVkFMRSIsInZhbGVfaWQiOiJWQUxFLTljMjIwNDM3YTUiLCJ2YWxpZG9faGFzdGEiOiIyMDI2LTA0LTE3In0.46jqqJ5xW1bh1FdTpG2Bejx8lvAmj5BTTVQ848giyD8","explicacion":{"decidido_por":"CAJ-02","nivel":"Estandar","costo_estimado_cop":4000,"cargado_a":"Duenos de politica (comercial + operaciones)","regla_de_costo":"Quien causa la falla paga: politica, operaciones o aliado."}}
```

## 7 Tope diario (segundo vale del mismo cliente el mismo dia)
```
{"request_id":"req-80e85ca2b7ab","error":{"codigo":"TOPE_DIARIO","mensaje":"El cliente ya recibio 1 vale(s) hoy. Escalar a supervisor de tienda."}}
```

## 8 Cafe pendiente: el cliente dona su vale
```
{"request_id":"req-126b40a347ea","resultado":"CAFE_PENDIENTE_DONADO","vale_id":"VALE-ff376dbd82","cafes":2,"explicacion":{"verificacion":"Firma valida; primer uso","tienda":"T02"}}
```

## 9 Reporte de error del cliente (confirmado y no confirmado)
```
{"request_id":"req-c1d1feb3bee6","resultado":"CONFIRMADO","recomendacion":"Emitir vale con motivo REPORTE_CLIENTE (decision humana en tienda o servicio).","explicacion":{"conflicto_confirmado":"req-a0bceac2bc62","fuente":"Libro de beneficios"}}
{"request_id":"req-377338ba66be","resultado":"EN_REVISION","explicacion":"El libro no confirma una diferencia para esa referencia y este cliente. No hay recompensa automatica; servicio revisa el caso."}
```

## 10 Libro: costo de la inconsistencia
```
{
    "beneficios_emitidos": 2,
    "beneficios_redimidos": 1,
    "descuento_redimido_cop": 1000,
    "conflictos_a_revision": 2,
    "cafes_debidos": 3,
    "cafes_cobrados": 0,
    "cafes_pendientes_donados": 2,
    "cafes_sin_usar": 1,
    "reportes_cliente": 2,
    "reportes_confirmados": 1,
    "costo_inconsistencia_cop": 12000,
    "costo_por_responsable_cop": {
        "Aliado de la tienda T10": 8000,
        "Duenos de politica (comercial + operaciones)": 4000
    }
}
```

## 11 Liga de tiendas (primeras 3 y ultimas 2)
```
{"tienda": "T02", "tipo": "propia", "cafes_debidos": 0, "conflictos": 0, "cafes_donados": 2, "posicion": 1}
{"tienda": "T03", "tipo": "propia", "cafes_debidos": 0, "conflictos": 0, "cafes_donados": 0, "posicion": 2}
{"tienda": "T04", "tipo": "propia", "cafes_debidos": 0, "conflictos": 0, "cafes_donados": 0, "posicion": 3}
{"tienda": "T10", "tipo": "aliada", "cafes_debidos": 2, "conflictos": 0, "cafes_donados": 0, "posicion": 11}
{"tienda": "T01", "tipo": "propia", "cafes_debidos": 1, "conflictos": 2, "cafes_donados": 0, "posicion": 12}
```

## Log estructurado del servidor (observabilidad)
```
{"request_id": "req-f78ffddeb9da", "metodo": "POST", "ruta": "/v1/beneficios/emitir", "status": 200, "ms": 3.42}
{"request_id": "req-a68759a4bafe", "metodo": "POST", "ruta": "/v1/beneficios/emitir", "status": 422, "ms": 0.91}
{"request_id": "req-7eab711d1e87", "metodo": "POST", "ruta": "/v1/beneficios/emitir", "status": 409, "ms": 1.17}
{"request_id": "req-b4db448fe48e", "metodo": "POST", "ruta": "/v1/beneficios/emitir", "status": 200, "ms": 0.89}
{"request_id": "req-bebdcf9a1820", "metodo": "POST", "ruta": "/v1/beneficios/redimir", "status": 200, "ms": 1.98}
{"request_id": "req-375c0de646a6", "metodo": "POST", "ruta": "/v1/beneficios/redimir", "status": 200, "ms": 1.12}
{"request_id": "req-e57ca73f41d6", "metodo": "POST", "ruta": "/v1/beneficios/redimir", "status": 409, "ms": 11.14}
{"request_id": "req-a0bceac2bc62", "metodo": "POST", "ruta": "/v1/beneficios/emitir", "status": 409, "ms": 1.12}
{"request_id": "req-82bbc98e3972", "metodo": "POST", "ruta": "/v1/promesa/deuda", "status": 200, "ms": 1.83}
{"request_id": "req-733226de12c7", "metodo": "POST", "ruta": "/v1/promesa/deuda", "status": 200, "ms": 1.18}
{"request_id": "req-80e85ca2b7ab", "metodo": "POST", "ruta": "/v1/promesa/deuda", "status": 409, "ms": 1.07}
{"request_id": "req-126b40a347ea", "metodo": "POST", "ruta": "/v1/promesa/cobrar", "status": 200, "ms": 1.44}
{"request_id": "req-c1d1feb3bee6", "metodo": "POST", "ruta": "/v1/promesa/reportar", "status": 200, "ms": 1.33}
{"request_id": "req-377338ba66be", "metodo": "POST", "ruta": "/v1/promesa/reportar", "status": 202, "ms": 0.87}
{"request_id": "req-b5b530dd32ba", "metodo": "GET", "ruta": "/v1/libro", "status": 200, "ms": 3.59}
{"request_id": "req-f0c41e546da5", "metodo": "GET", "ruta": "/v1/liga", "status": 200, "ms": 3.62}
```

## Pruebas automatizadas (pytest)
```
collecting ... collected 18 items

tests/test_api.py::test_caso_valido_cliente_activo_dos_cafes PASSED      [  5%]
tests/test_api.py::test_caso_valido_antes_de_pol02_solo_una_version PASSED [ 11%]
tests/test_api.py::test_redencion_valida_e_idempotente PASSED            [ 16%]
tests/test_api.py::test_entrada_invalida_precio_negativo_y_tienda_mal_formada PASSED [ 22%]
tests/test_api.py::test_token_alterado_rechazado PASSED                  [ 27%]
tests/test_api.py::test_conflicto_pol01_vs_pol02_cliente_no_activo PASSED [ 33%]
tests/test_api.py::test_conflicto_te_solo_elegible_en_pol02 PASSED       [ 38%]
tests/test_api.py::test_doble_redencion_con_otra_operacion PASSED        [ 44%]
tests/test_api.py::test_tienda_fuera_de_piloto PASSED                    [ 50%]
tests/test_api.py::test_tren_lanzamientos_pol02_no_rige_hasta_el_lunes PASSED [ 55%]
tests/test_api.py::test_vale_nivel_promesa_doble_y_costo_al_aliado PASSED [ 61%]
tests/test_api.py::test_vale_por_conflicto_se_carga_a_duenos_de_politica PASSED [ 66%]
tests/test_api.py::test_vale_conflicto_sin_referencia_confirmada PASSED  [ 72%]
tests/test_api.py::test_tope_diario_de_vales PASSED                      [ 77%]
tests/test_api.py::test_cobrar_y_donar_vale PASSED                       [ 83%]
tests/test_api.py::test_vale_no_sirve_como_beneficio PASSED              [ 88%]
tests/test_api.py::test_reporte_confirmado_y_no_confirmado PASSED        [ 94%]
tests/test_api.py::test_liga_de_tiendas PASSED                           [100%]

============================== 18 passed in 0.51s ==============================
```
