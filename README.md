# Prototipo: Promesa Café Origen ("cumplida, o te debemos un café")

**Proyecto final · Andrés Sabogal · Variación D (Rentabilidad)**
Caso ficticio. Todos los datos son simulados.

## Qué demuestra
| Capacidad | Endpoint | Evidencia del caso |
|---|---|---|
| Resolver la regla con catálogo versionado y **tren de lanzamientos** (una versión rige desde el lunes siguiente a su publicación) | `POST /v1/beneficios/emitir` | E04, E07, INC-01 |
| **Conflicto a humano**: si POL-01 y POL-02 dan resultados distintos, responde 409 y no decide | `POST /v1/beneficios/emitir` | E07, E09 |
| **Comprobante firmado** verificable en el POS; redención una sola vez (idempotente) | `POST /v1/beneficios/redimir` | INC-01, INC-03 |
| **Te debemos un café**: si la promesa falla, el cajero (un humano) emite un vale. **Nivel Promesa** (cliente activo) recibe el doble. **Quien falla, paga**: el costo se carga a política, operaciones o aliado | `POST /v1/promesa/deuda` | E06, INC-02, E09, E04 |
| **Café pendiente**: el vale se cobra o se dona | `POST /v1/promesa/cobrar` | — |
| **Reporte de error del cliente**: el sistema confirma contra el libro y recomienda; no paga de forma automática | `POST /v1/promesa/reportar` | E05 (no hay tasas de incidentes) |
| **Costo de la inconsistencia** y **liga de tiendas** | `GET /v1/libro`, `GET /v1/liga` | E02 (variación D) |

## Requisitos e instalación
- Python 3.10 o superior.

```bash
cd Andres_Sabogal_D_Prototipo
python -m venv .venv
# Windows:  .venv\Scripts\activate      Linux/Mac:  source .venv/bin/activate
pip install -r requirements.txt
```

## Ejecución
```bash
uvicorn app.main:app --port 8000
```
- Contrato interactivo (OpenAPI/Swagger): http://localhost:8000/docs
- Pruebas: `python -m pytest -v` (18 pruebas)
- Ejemplos (en Windows usar `curl.exe`):

```bash
curl -X POST http://localhost:8000/v1/beneficios/emitir -H "Content-Type: application/json" -d @demo/1_valido.json
curl -X POST http://localhost:8000/v1/beneficios/emitir -H "Content-Type: application/json" -d @demo/2_invalido.json
curl -X POST http://localhost:8000/v1/beneficios/emitir -H "Content-Type: application/json" -d @demo/3_conflicto.json
curl -X POST http://localhost:8000/v1/promesa/deuda    -H "Content-Type: application/json" -d @demo/4_deuda_aliado.json
```
Los resultados obtenidos están en `RESULTADOS.md`.

## Contrato de API (resumen)
- Todas las respuestas incluyen `request_id`, también en el header `X-Request-ID`.
- Los errores siguen el formato `{request_id, error:{codigo, mensaje, ...}}`.
- Las operaciones que cambian estado reciben una `idempotency_key`. Un reintento devuelve la misma respuesta con el header `Idempotent-Replay: true`.

| Código | Cuándo |
|---|---|
| 200 | Éxito, con explicación (regla, versión, fuente, responsable del costo) |
| 202 `EN_REVISION` | Reporte de cliente no confirmado por el libro |
| 401 `FIRMA_INVALIDA` | Comprobante alterado |
| 403 `TIENDA_FUERA_DE_PILOTO` | Tienda fuera del piloto: se usa el proceso actual |
| 404 `CLIENTE_DESCONOCIDO` / `PROMOCION_DESCONOCIDA` | Datos maestros |
| 409 `CONFLICTO_POLITICA` / `YA_REDIMIDO` / `TOPE_DIARIO` / `VALE_YA_USADO` / vencidos | Excepciones del caso |
| 422 `ENTRADA_INVALIDA` / `REFERENCIA_NO_CONFIRMADA` / `TIPO_COMPROBANTE_INCORRECTO` / `PROMOCION_NO_VIGENTE` | Entrada inválida |

## Reglas, fuentes y supuestos
- **Reglas:** `datos/reglas.json`, transcritas de E07 y de la hoja *Reglas*. Cada evaluación devuelve su `fuente`.
- **Acta de precedencia:** cuando comercial y operaciones firmen el acta, se llena `acta_precedencia: {"version_vigente": "POL-02"}` y el conflicto desaparece sin cambiar código.
- **Parámetros** en `datos/clientes.json`. Todos son **supuestos**, no datos del caso:
  - costo de un café debido: 4.000 COP (costo para la empresa, no precio);
  - vigencia del vale: 30 días;
  - tope: 1 vale por cliente al día;
  - nivel Promesa: el doble;
  - piloto: T01 a T08 son propias y T09 a T12 aliadas.
- **Otros supuestos:**
  - el 20 % se aplica a la bebida elegible de menor precio, una vez por transacción;
  - el comprobante de beneficio vale hasta el día siguiente.
- El nivel Promesa usa el programa de fidelización existente (`programa_activo`). **No crea una base de clientes nueva** (E09).

## Pruebas (18, reproducibles)
| Tipo | Pruebas |
|---|---|
| Caso válido | emisión válida; versión única antes de POL-02; tren de lanzamientos; redención idempotente; vale con nivel Promesa cargado al aliado; vale por conflicto cargado a política; cobrar y donar; liga |
| Entrada inválida | precio negativo y tienda mal formada; token alterado; vale usado como beneficio; conflicto sin referencia confirmada |
| Conflicto o excepción | POL-01 frente a POL-02 (no activo); té solo elegible en POL-02; doble redención; tope diario; reporte no confirmado; tienda fuera de piloto |

## Límites (fuera de alcance)
- El libro vive en memoria.
- No hay integración real con POS, CRM ni el programa de fidelización.
- La firma usa HMAC con un secreto compartido. En producción sería asimétrica (Ed25519): el POS solo tendría la llave pública.
- No hay autenticación de cajeros. En producción, el `cajero_id` vendría del inicio de sesión en el POS, no del cuerpo de la solicitud.

## Diseño de despliegue en nube (no implementado, AWS opcional)
- **API:** API Gateway + ECS Fargate (o Lambda).
- **Libro:** DynamoDB con clave única y escritura condicional, que da idempotencia real.
- **Llaves:** KMS para la firma.
- **Observabilidad:** CloudWatch para los logs estructurados con `request_id`, con alarmas sobre la tasa de 409 y sobre el costo diario de la inconsistencia.
- **Tiendas sin conexión:** el POS verifica la firma con la llave pública y encola las operaciones. Al reconectar, las envía con su `idempotency_key`.
