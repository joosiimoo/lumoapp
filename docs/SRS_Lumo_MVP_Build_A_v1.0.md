# SRS — Lumo MVP Build A v1.0

**Estado:** Especificación de software lista para diseño e implementación  
**Producto:** Lumo  
**Referencia funcional:** PRD — Lumo MVP Build A v1.0  
**Fecha:** 19 de septiembre de 2026

## 1. Propósito

Este documento define requisitos verificables para Build A. Los términos DEBE, NO DEBE, DEBERÍA y PUEDE expresan obligación, prohibición, recomendación y opción. Todo requisito funcional incluye trazabilidad al PRD y un criterio verificable.

## 2. Alcance del sistema

El sistema comprende una aplicación Flutter, una API FastAPI y un backend modular sobre PostgreSQL. Permite configurar un comercio, operar un catálogo básico opcional, registrar ventas por lenguaje natural o acciones estructuradas, mantener la jornada, resolver pagos pendientes, preparar el cierre, consultar consolidados y exportar CSV/XLSX.

Quedan excluidos inventario, compras, reposición, forecasting, facturación, conciliación bancaria, ecommerce, CRM, multi-sucursal y capacidades de Build B.

## 3. Actores y límites de confianza

| Actor o componente | Confianza | Responsabilidad |
|---|---|---|
| Usuario autenticado | Parcial | Expresar intención, revisar, contar efectivo y confirmar |
| Flutter | No confiable | Capturar entrada y renderizar contratos permitidos |
| LLM | Probabilístico | Proponer intención, entidades y respuesta estructurada |
| Orchestrator | Controlado | Mantener contexto y seleccionar tools registradas |
| Policy and Risk Engine | Confiable | Autorizar, bloquear o pedir confirmación |
| Domain Tools | Confiable | Validar, calcular y solicitar persistencia |
| PostgreSQL | Fuente de verdad | Confirmar estado transaccional, evidencia e idempotencia |

## 4. Requisitos funcionales

### 4.1 Identidad, comercio y configuración

- **RF-A-001 Crear comercio.** El sistema DEBE crear un comercio con nombre, moneda, locale y zona horaria. Trazabilidad: PRD 7.1.
- **RF-A-002 Aislar tenant.** Toda lectura y escritura DEBE incluir `business_id` derivado de la sesión autenticada; el cliente NO DEBE seleccionar otro tenant. Trazabilidad: PRD 6.
- **RF-A-003 Crear propietario.** El onboarding DEBE asociar al primer usuario con permisos de propietario. Trazabilidad: PRD 7.1.
- **RF-A-004 Configurar pagos.** El propietario DEBE habilitar efectivo, tarjeta, transferencia u otro método simple. Trazabilidad: PRD 7.1.
- **RF-A-005 Configurar fuente.** El sistema DEBE registrar `manual_capture` como fuente inicial y su periodo de cobertura. Trazabilidad: PRD 7.1 y 9.

### 4.2 Catálogo básico

- **RF-A-010 Crear producto.** Un actor autorizado DEBE crear producto con nombre, unidad de precio, precio y estado. Trazabilidad: PRD 7.2.
- **RF-A-011 Editar producto.** El sistema DEBE permitir cambiar nombre, alias, categoría, unidad, precio y estado, conservando auditoría. Trazabilidad: PRD 7.2.
- **RF-A-012 Desactivar producto.** Un producto desactivado NO DEBE resolverse en nuevas ventas, pero DEBE permanecer en históricos. Trazabilidad: PRD 7.2.
- **RF-A-013 Buscar producto.** La búsqueda DEBE normalizar mayúsculas, acentos y espacios y usar nombre y alias. Trazabilidad: PRD 7.2.
- **RF-A-014 Resolver ambigüedad.** Si más de un producto cumple el umbral de coincidencia, el sistema DEBE pedir una selección y NO DEBE elegir silenciosamente. Trazabilidad: PRD 6 y 7.3.
- **RF-A-015 Validar unidades.** Solo se DEBEN aceptar unidades compatibles y conversiones configuradas. Trazabilidad: PRD 7.2.
- **RF-A-016 Versionar precio.** Cada cambio DEBE conservar vigencia, actor y valor anterior. Trazabilidad: PRD 7.5.

### 4.3 Interpretación agentic

- **RF-A-020 Interpretar intención.** El sistema DEBE mapear el mensaje a una intención registrada o responder sin mutación. Trazabilidad: PRD 6 y 7.3.
- **RF-A-021 Estructurar entidades.** El intérprete PUEDE proponer producto, cantidad, unidad, precio solicitado, pago y fecha, con confianza por campo. Trazabilidad: PRD 7.3.
- **RF-A-022 No inventar esenciales.** Producto, cantidad, unidad, total o acción requeridos NO DEBEN completarse sin evidencia o política explícita. Trazabilidad: PRD 6.
- **RF-A-023 Aclarar parcialmente.** El sistema DEBE conservar campos inequívocos y preguntar solo por los ambiguos. Trazabilidad: PRD 6.
- **RF-A-024 Bloquear baja confianza.** Una mutación con confianza inferior al umbral configurado DEBE pedir aclaración. Trazabilidad: PRD 6.
- **RF-A-025 Catálogo de tools.** El Orchestrator NO DEBE ejecutar una tool que no esté registrada y versionada. Trazabilidad: PRD 6.

### 4.4 Venta y líneas

- **RF-A-030 Iniciar borrador.** El sistema DEBE crear un borrador lógico de venta sin persistir efectos financieros hasta ejecutar la tool autorizada. Trazabilidad: PRD 7.3.
- **RF-A-031 Venta por monto.** El sistema DEBE registrar una venta con total declarado y sin líneas. Trazabilidad: PRD 7.4.
- **RF-A-032 Venta detallada.** El sistema DEBE registrar una o más líneas con producto o concepto, cantidad, unidad, precio y subtotal. Trazabilidad: PRD 7.3.
- **RF-A-033 Concepto libre.** El sistema PUEDE aceptar una línea sin producto con descripción e importe, según política. Trazabilidad: PRD 7.4.
- **RF-A-034 Cantidad positiva.** Toda cantidad DEBE ser mayor que cero. Trazabilidad: PRD 6.
- **RF-A-035 Conversión determinística.** La cantidad normalizada DEBE calcularse con una conversión configurada en backend. Trazabilidad: PRD 6 y 7.2.
- **RF-A-036 Cálculo determinístico.** Subtotales, descuentos o ajustes, total identificado y total final DEBEN calcularse en backend con decimal exacto. Trazabilidad: PRD 6 y 7.5.
- **RF-A-037 Revalidar precio.** Inmediatamente antes del commit, el sistema DEBE leer el precio vigente y recalcular. Trazabilidad: PRD 6 y 7.5.
- **RF-A-038 Informar cambio de precio.** Si la revalidación cambia el resultado propuesto, la respuesta DEBE mostrar el precio aplicado y el total confirmado. Trazabilidad: PRD 7.5.
- **RF-A-039 Ajustar precio.** Un precio final distinto del vigente DEBE incluir motivo no vacío y permiso válido. Trazabilidad: PRD 7.5.
- **RF-A-040 Confirmar venta.** Venta, líneas, pago opcional, eventos y auditoría DEBEN confirmarse en una sola transacción. Trazabilidad: PRD 7.3 y 7.13.
- **RF-A-041 Éxito posterior al commit.** El sistema NO DEBE devolver éxito ni `sale_confirmed_card` antes de recibir confirmación de commit. Trazabilidad: PRD 6.
- **RF-A-042 Asociar jornada.** Toda venta confirmada DEBE asociarse a la jornada de su fecha operativa. Trazabilidad: PRD 7.7.

### 4.5 Pago

- **RF-A-050 Registrar pago simple.** Build A DEBE aceptar cero o un pago por venta. Trazabilidad: PRD 7.6.
- **RF-A-051 Pago pendiente.** Si falta el medio, la venta PUEDE confirmarse con pago pendiente y DEBE crear un WorkItem. Trazabilidad: PRD 7.6.
- **RF-A-052 Efectivo esperado.** Solo pagos que representen efectivo físico DEBEN sumar al efectivo esperado. Trazabilidad: PRD 7.6 y 7.9.
- **RF-A-053 Resolver pago pendiente.** Un actor autorizado DEBE poder asignar un medio y cerrar el WorkItem de forma atómica. Trazabilidad: PRD 7.6 y 7.8.
- **RF-A-054 Rechazar pago mixto.** Dos o más componentes de pago DEBEN devolver `CAPABILITY_NOT_AVAILABLE`. Trazabilidad: PRD 12.

### 4.6 Jornada, workflow y outcomes

- **RF-A-060 Abrir jornada.** La primera venta DEBE crear o abrir la jornada correspondiente si no existe. Trazabilidad: PRD 7.7.
- **RF-A-061 Mantener estado.** El Workflow Engine DEBE aplicar únicamente transiciones válidas de `OperationalDay`. Trazabilidad: PRD 8.3.
- **RF-A-062 Ejecutar outcomes.** Cada jornada DEBE tener un `OutcomeRun` para cada outcome de Build A. Trazabilidad: PRD 1 y 9.
- **RF-A-063 Evaluar sales ready.** El sistema DEBE evaluar los gates de `daily_sales_operations_ready` después de cada mutación relevante. Trazabilidad: PRD 9.1.
- **RF-A-064 Evaluar close ready.** El sistema DEBE evaluar los gates de `daily_close_ready` después de pagos, WorkItems y CashCount. Trazabilidad: PRD 9.2.
- **RF-A-065 Mantener bloqueo.** Un gate fallido DEBE impedir el estado `ready` y producir un reason code y Next Best Action. Trazabilidad: PRD 7.8 y 9.
- **RF-A-066 Source Coverage.** El resultado DEBE distinguir operaciones registradas de cobertura real de fuentes. Trazabilidad: PRD 5 y 9.
- **RF-A-067 No false completion.** Un score, texto del modelo o respuesta del cliente NO DEBE sobreescribir un gate. Trazabilidad: PRD 6 y 9.

### 4.7 Work Items y Next Best Action

- **RF-A-070 Crear WorkItem.** Todo faltante que requiera acción DEBE crear un WorkItem único por tipo y entidad. Trazabilidad: PRD 7.8.
- **RF-A-071 Persistir WorkItem.** El pendiente DEBE sobrevivir sesiones y conservar responsable, prioridad, estado e impacto. Trazabilidad: PRD 7.8.
- **RF-A-072 Resolver WorkItem.** La resolución DEBE registrar actor, acción, evidencia y fecha. Trazabilidad: PRD 7.8.
- **RF-A-073 Calcular Next Best Action.** El sistema DEBE elegir primero seguridad, luego gates, excepciones y acciones necesarias; recomendaciones no operativas quedan fuera. Trazabilidad: PRD 7.8.
- **RF-A-074 Explicar acción.** La salida DEBE decir qué falta, por qué importa y quién actúa. Trazabilidad: PRD 10.1.

### 4.8 Cierre y CashCount

- **RF-A-080 Preparar cierre.** Cuando los gates previos lo permitan, Lumo DEBE solicitar el conteo real sin que el usuario construya el resumen. Trazabilidad: PRD 7.9.
- **RF-A-081 Registrar CashCount.** El sistema DEBE guardar importe, moneda, actor y timestamp. Trazabilidad: PRD 7.9.
- **RF-A-082 Calcular diferencia.** `cash_difference = counted_cash - expected_cash` DEBE calcularse en backend. Trazabilidad: PRD 7.9.
- **RF-A-083 Mostrar diferencia.** Una diferencia distinta de cero DEBE mostrarse explícitamente y NO DEBE ajustarse en silencio. Trazabilidad: PRD 7.9.
- **RF-A-084 Confirmar cierre.** Solo un actor autorizado y con gates satisfechos DEBE confirmar. Trazabilidad: PRD 7.9.
- **RF-A-085 Commit del cierre.** El estado `closed`, auditoría, outcome y memoria DEBEN confirmarse atómicamente. Trazabilidad: PRD 6, 7.9 y 7.12.

### 4.9 Consultas y consolidados

- **RF-A-090 Resumen diario.** El sistema DEBE calcular ventas, transacciones, ticket promedio, pagos, cantidades por producto o concepto, ajustes y pendientes. Trazabilidad: PRD 7.10.
- **RF-A-091 Resumen semanal.** El sistema DEBE agregar por semana local del comercio. Trazabilidad: PRD 7.10.
- **RF-A-092 Resumen mensual.** El sistema DEBE agregar por mes local del comercio. Trazabilidad: PRD 7.10.
- **RF-A-093 Consistencia.** Los totales de resumen DEBEN derivarse de ventas confirmadas y coincidir con exportaciones para el mismo filtro. Trazabilidad: PRD 7.10 y 7.11.

### 4.10 Exportaciones

- **RF-A-100 Solicitar exportación.** Un actor autorizado DEBE solicitar CSV o XLSX para un rango permitido. Trazabilidad: PRD 7.11.
- **RF-A-101 Exportar CSV.** El archivo DEBE usar UTF-8, encabezados estables y una fila por línea o venta sin detalle. Trazabilidad: PRD 7.11.
- **RF-A-102 Exportar XLSX.** El archivo DEBE contener `Ventas`, `Detalle`, `Resumen` y `Metadatos`. Trazabilidad: PRD 7.11.
- **RF-A-103 Tipos nativos.** XLSX DEBE usar valores numéricos y fechas nativas; CSV DEBE usar representación ISO 8601 y punto decimal. Trazabilidad: PRD 7.11.
- **RF-A-104 Evidencia de exportación.** El sistema DEBE registrar solicitante, filtros, formato, conteos, checksum y estado. Trazabilidad: PRD 7.12 y 7.13.
- **RF-A-105 Protección.** Una exportación DEBE contener solo datos del comercio autenticado y usar acceso temporal autenticado. Trazabilidad: PRD 6.

### 4.11 Generative UI

- **RF-A-110 Contrato cerrado.** El backend DEBE emitir únicamente componentes y versiones registrados. Trazabilidad: PRD 10.5.
- **RF-A-111 Validación Flutter.** La app DEBE rechazar componentes, campos o acciones desconocidos y mostrar el texto de fallback. Trazabilidad: PRD 10.5.
- **RF-A-112 Acciones opacas.** Las acciones DEBEN enviar `actionId`, `optionId`, `contextToken` e idempotency key; el servidor NO DEBE confiar en la etiqueta visible. Trazabilidad: PRD 10.5.
- **RF-A-113 Reautorizar acción.** Toda acción de UI DEBE reevaluar autenticación, tenant, permiso, política y vigencia. Trazabilidad: PRD 6.

### 4.12 Memoria, auditoría e idempotencia

- **RF-A-120 Crear Event Memory.** Cada hecho confirmado relevante DEBE producir un MemoryItem factual vinculado al evento fuente. Trazabilidad: PRD 7.12.
- **RF-A-121 Distinguir procedencia.** Memoria y respuesta DEBEN marcar hecho, cálculo, decisión del usuario o interpretación del modelo. Trazabilidad: PRD 6 y 7.12.
- **RF-A-122 Auditar mutación.** Cada mutación DEBE guardar los campos definidos en PRD 7.13. Trazabilidad: PRD 7.13.
- **RF-A-123 Idempotencia.** Toda mutación DEBE requerir `Idempotency-Key` única por comercio y operación lógica. Trazabilidad: PRD 6.
- **RF-A-124 Repetir respuesta.** Una solicitud repetida con misma clave y mismo hash DEBE devolver el resultado original sin nuevos efectos. Trazabilidad: PRD 6.
- **RF-A-125 Detectar conflicto.** La misma clave con payload distinto DEBE devolver `IDEMPOTENCY_CONFLICT`. Trazabilidad: PRD 6.

## 5. Requisitos no funcionales

- **RNF-A-001 Disponibilidad.** Objetivo inicial mensual de API: 99.5 %, excluyendo mantenimiento anunciado.
- **RNF-A-002 Latencia API.** p95 menor a 500 ms para consultas y mutaciones determinísticas sin llamada LLM.
- **RNF-A-003 Latencia agentic.** p95 menor a 8 s para mensajes que requieren LLM, sin contar espera de aclaración del usuario.
- **RNF-A-004 Degradación.** Si el proveedor LLM falla, las APIs estructuradas, consultas, cierre y exportación DEBEN seguir disponibles.
- **RNF-A-005 Exactitud monetaria.** Importes DEBEN usar `numeric`, nunca float binario; redondeo por moneda en un único servicio.
- **RNF-A-006 Integridad.** Venta, pago, auditoría, eventos e idempotencia DEBEN compartir límite transaccional cuando pertenezcan a la misma operación.
- **RNF-A-007 Recuperación.** Un fallo posterior al envío DEBE poder consultarse por idempotency key o correlation ID.
- **RNF-A-008 Seguridad en tránsito.** Todo tráfico externo DEBE usar TLS 1.2 o superior.
- **RNF-A-009 Seguridad en reposo.** Credenciales y secretos DEBEN usar un gestor de secretos; respaldos y almacenamiento administrado DEBEN cifrarse.
- **RNF-A-010 Autorización.** El backend DEBE aplicar permisos atómicos y filtros por tenant en toda ruta.
- **RNF-A-011 Privacidad.** Logs NO DEBEN incluir tokens, contraseñas ni mensajes completos salvo almacenamiento de auditoría con acceso restringido.
- **RNF-A-012 Observabilidad.** Cada request DEBE propagar correlation ID y registrar latencia, resultado, tenant pseudonimizado y componente.
- **RNF-A-013 Trazas agentic.** Se DEBEN registrar modelo, versión de prompt, tools ofrecidas, tool elegida, tokens, latencia y fallback sin exponer secretos.
- **RNF-A-014 Métricas.** Se DEBEN medir outcomes, gates, aclaraciones, errores, reintentos, duplicados evitados, costos y exportaciones.
- **RNF-A-015 Accesibilidad.** Flutter DEBE soportar etiquetas semánticas, contraste WCAG AA, escalado de texto y navegación por lector.
- **RNF-A-016 Compatibilidad.** Build A DEBE soportar las dos versiones mayores vigentes de Android e iOS definidas al iniciar desarrollo.
- **RNF-A-017 Mantenibilidad.** Las dependencias entre módulos DEBEN seguir los límites publicados en Architecture; dominio no depende de FastAPI, Flutter ni proveedor LLM.
- **RNF-A-018 Pruebas.** Cálculos, gates, políticas e idempotencia DEBEN tener pruebas unitarias; flujos prioritarios, pruebas de integración y E2E.
- **RNF-A-019 Respaldo.** PostgreSQL DEBE tener respaldo automatizado y restauración probada antes del piloto.
- **RNF-A-020 Retención.** Datos y auditoría DEBEN usar periodos configurables definidos antes del piloto.
- **RNF-A-021 Internacionalización.** Texto de UI DEBE estar externalizado; dominio usa moneda y zona del comercio.
- **RNF-A-022 Escalabilidad inicial.** El sistema DEBE soportar al menos 100 comercios piloto sin cambios de arquitectura; la prueba de carga fijará límites reales.

## 6. Reglas de negocio

| ID | Regla |
|---|---|
| RB-A-001 | El LLM interpreta; no escribe en PostgreSQL ni invoca repositorios. |
| RB-A-002 | Solo tools registradas pueden solicitar mutaciones. |
| RB-A-003 | Toda mutación requiere autenticación, tenant, permiso, política, validación e idempotencia. |
| RB-A-004 | Cantidad y precio deben ser positivos; cantidad normalizada usa una conversión configurada. |
| RB-A-005 | El precio vigente se consulta durante el commit. |
| RB-A-006 | Un override de precio requiere motivo y queda visible. |
| RB-A-007 | El total confirmado se calcula en backend. |
| RB-A-008 | Una venta sin pago puede existir, pero bloquea el cierre. |
| RB-A-009 | Tarjeta y transferencia no aumentan efectivo esperado. |
| RB-A-010 | La diferencia de efectivo no se corrige automáticamente. |
| RB-A-011 | Un outcome no avanza si falla un gate obligatorio. |
| RB-A-012 | Éxito significa commit confirmado, no intención aceptada. |
| RB-A-013 | Todo acceso está limitado al comercio autenticado. |
| RB-A-014 | Source Coverage limita las afirmaciones de completitud. |
| RB-A-015 | Las agregaciones y exportaciones usan ventas confirmadas y excluyen borradores fallidos. |

## 7. Estados y transiciones

### 7.1 Sale

| Origen | Evento | Destino | Condición |
|---|---|---|---|
| inexistente | `sale.draft_started` | draft | intención válida |
| draft | `sale.information_required` | pending_information | dato esencial ambiguo |
| pending_information | `sale.information_supplied` | draft | dato válido |
| draft | `sale.committed` | confirmed | política aprobada y commit exitoso |
| cualquier no terminal | `sale.failed` | sin cambio persistido | rollback completo |

### 7.2 OperationalDay

| Origen | Evento | Destino |
|---|---|---|
| not_started | primera venta | open |
| open | venta confirmada | in_progress |
| in_progress | gate pendiente | waiting_for_information |
| waiting_for_information | pendiente resuelto | in_progress |
| in_progress | gates de cierre satisfechos | ready_to_close |
| ready_to_close | cierre confirmado | closed |
| estado activo | fallo no recuperable | failed |

### 7.3 WorkItem

`open → in_progress → resolved` y `open|in_progress → dismissed|failed` con motivo y auditoría.

## 8. Contratos de API y datos

### 8.1 Convenciones

- Base path: `/api/v1`.
- JSON UTF-8 y nombres `snake_case`.
- IDs opacos UUID/ULID.
- Fechas ISO 8601 UTC; presentación en zona del comercio.
- Dinero: string decimal en JSON más código ISO 4217.
- Headers: `Authorization`, `Idempotency-Key`, `X-Correlation-ID`.

### 8.2 Mensaje al agente

`POST /api/v1/lumo/messages`

```json
{
  "conversation_id": "01H...",
  "message": "900 gramos de zanahoria y 300 de tomate, tarjeta",
  "client_context": {"surface": "business_stream"}
}
```

Respuesta:

```json
{
  "message_id": "01H...",
  "status": "completed",
  "text": "Registré la venta después de validar precios.",
  "ui": [{"component": "sale_confirmed_card", "version": 1, "data": {}}],
  "outcome": {"daily_sales_operations_ready": "ready", "daily_close_ready": "blocked"},
  "next_best_action": {"action_id": "closing.submit_cash_count", "reason": "cash_count_missing"},
  "correlation_id": "01H..."
}
```

### 8.3 Acción de UI

`POST /api/v1/lumo/actions`

```json
{
  "action_id": "payment.resolve",
  "option_id": "opt_opaque",
  "context_token": "signed-short-lived-token",
  "payload": {}
}
```

### 8.4 Tool create sale

Contrato interno `sale.commit@1`:

```json
{
  "operational_day_id": "01H...",
  "declared_total": null,
  "lines": [
    {"product_id": "01H...", "quantity": "900", "unit": "g", "price_override": null, "override_reason": null}
  ],
  "payment_method": "card",
  "source": "manual_capture"
}
```

El tool ignora totales calculados por el modelo, resuelve conversión, consulta precios y devuelve valores confirmados.

### 8.5 Error envelope

```json
{
  "error": {
    "code": "AMBIGUOUS_PRODUCT",
    "message": "Necesito saber cuál tomate vendiste.",
    "details": {"field": "product", "options": []},
    "retryable": false,
    "correlation_id": "01H..."
  }
}
```

### 8.6 Entidades mínimas

- `Business`, `User`, `Membership`, `PaymentMethod`.
- `Product`, `ProductAlias`, `ProductPrice`, `UnitConversion`.
- `Sale`, `SaleLine`, `Payment`.
- `OperationalDay`, `CashCount`.
- `OutcomeDefinition`, `OutcomeRun`, `CompletionEvidence`.
- `WorkItem`, `NextBestAction`.
- `BusinessEvent`, `MemoryItem`, `AuditEvent`.
- `IdempotencyRecord`, `SourceCoverageRecord`, `ExportJob`.

Todas las entidades de negocio incluyen `business_id`; datos mutables incluyen `created_at`, `updated_at` y versión optimista cuando aplique.

## 9. Catálogo de errores

| Código | HTTP | Uso | Reintento |
|---|---:|---|---|
| `VALIDATION_ERROR` | 422 | Payload o regla de campo inválida | No |
| `AMBIGUOUS_PRODUCT` | 409 | Más de una resolución válida | Tras aclaración |
| `PRODUCT_NOT_FOUND` | 404 | Producto inexistente o inactivo | No |
| `UNIT_NOT_SUPPORTED` | 422 | Unidad sin conversión | No |
| `PRICE_CHANGED` | 409 | Requiere nueva confirmación por política | Sí, con contexto nuevo |
| `PRICE_OVERRIDE_REASON_REQUIRED` | 422 | Falta motivo | No |
| `PAYMENT_REQUIRED_FOR_CLOSE` | 409 | Gate de cierre | Tras resolver |
| `CASH_COUNT_REQUIRED` | 409 | Gate de cierre | Tras conteo |
| `OUTCOME_GATE_BLOCKED` | 409 | Uno o más gates fallaron | Depende |
| `IDEMPOTENCY_CONFLICT` | 409 | Misma clave, payload distinto | No |
| `FORBIDDEN` | 403 | Sin permiso | No |
| `TENANT_SCOPE_VIOLATION` | 404 | Recurso fuera del comercio | No |
| `CAPABILITY_NOT_AVAILABLE` | 422 | Función de Build B o futura | No |
| `LLM_UNAVAILABLE` | 503 | Proveedor no disponible | Sí |
| `DEPENDENCY_UNAVAILABLE` | 503 | Base o servicio requerido | Sí |
| `INTERNAL_ERROR` | 500 | Falla no clasificada | Sí |

## 10. Idempotencia y concurrencia

1. La clave se evalúa dentro del scope `business_id + operation_type`.
2. El servidor guarda hash normalizado, estado `processing|completed|failed`, response code y response body.
3. Dos solicitudes concurrentes con la misma clave se serializan; una ejecuta y la otra obtiene el resultado persistido.
4. Una transacción fallida no deja venta parcial. El registro idempotente indica falla recuperable.
5. El commit usa bloqueo o control optimista para precio, jornada y outcome.
6. La respuesta de éxito se materializa a partir del estado confirmado.

## 11. Seguridad y privacidad

- Autenticación basada en tokens cortos con refresh seguro.
- Permisos mínimos: `catalog.manage`, `sale.create`, `payment.resolve`, `closing.submit_cash_count`, `closing.confirm`, `export.create`, `audit.view`.
- PostgreSQL aplica Row Level Security o filtros equivalentes probados como segunda barrera.
- Context tokens de UI son firmados, de corta duración, de un solo contexto y no contienen datos sensibles en claro.
- Rate limiting por usuario, comercio, IP y endpoint sensible.
- Validación de esquemas en el borde y antes del dominio.
- Protección contra prompt injection: mensajes, nombres de producto y archivos son datos; nunca instrucciones de sistema.
- Auditoría con acceso restringido y exportaciones con URL temporal.
- Eliminación o retención se define por política antes del piloto.

## 12. Observabilidad

### 12.1 Logs estructurados

Campos mínimos: timestamp, severity, service, environment, correlation_id, request_id, business_ref pseudonimizada, actor_ref, route/tool, outcome, duration_ms y error_code.

### 12.2 Métricas

- throughput y errores por endpoint/tool;
- latencia API, LLM, policy, domain y DB;
- tasa de aclaración y fallback;
- tokens y costo por mensaje y OutcomeRun;
- outcomes por estado y reason code;
- gates bloqueantes;
- idempotency hits y conflictos;
- cambios de precio al commit;
- exportaciones por formato y errores;
- diferencias de caja.

### 12.3 Trazas

Una traza enlaza request, interpretación, política, tool, transacción, eventos, memoria y respuesta. El contenido sensible se redacta según política.

### 12.4 Alertas

Alertas iniciales: tasa de error elevada, latencia p95 fuera de objetivo, fallos de commit, duplicados posibles, exportación inconsistente, cola estancada y respaldo fallido.

## 13. Criterios de aceptación

- **CA-001:** dado un mensaje con gramos y productos inequívocos, la venta confirmada usa conversiones y precios del backend.
- **CA-002:** dado un alias ambiguo, no se persiste la venta y se pide solo seleccionar el producto.
- **CA-003:** dado un precio que cambia antes del commit, el importe persistido usa el precio vigente y la respuesta lo informa.
- **CA-004:** dado un override sin motivo, la operación falla sin efectos.
- **CA-005:** dado el mismo request dos veces con igual idempotency key, existe una sola venta y ambas respuestas refieren al mismo ID.
- **CA-006:** dado un pago pendiente, la venta se conserva, aparece un WorkItem y el cierre no queda listo.
- **CA-007:** al resolver el pago, el WorkItem queda resuelto y los gates se reevaluan.
- **CA-008:** tarjeta o transferencia no cambia el efectivo esperado.
- **CA-009:** una diferencia de caja se muestra y permanece auditada.
- **CA-010:** ningún texto o widget indica éxito si la transacción hace rollback.
- **CA-011:** usuario de comercio A no puede leer ni mutar recursos de comercio B.
- **CA-012:** resumen diario, semanal y mensual coincide con consultas de detalle.
- **CA-013:** CSV y XLSX contienen el mismo universo y totales para el mismo filtro.
- **CA-014:** XLSX abre sin reparación y conserva números y fechas editables.
- **CA-015:** un widget desconocido muestra fallback y no ejecuta acción.
- **CA-016:** una acción expirada o manipulada se rechaza y queda auditada.
- **CA-017:** caída del LLM no impide usar catálogo, vistas, cierre estructurado ni exportación.
- **CA-018:** cada mutación puede reconstruirse desde AuditEvent y BusinessEvent.
- **CA-019:** la interfaz comunica la limitación de Source Coverage.
- **CA-020:** los 14 escenarios prioritarios del PRD pasan E2E.

## 14. Matriz de trazabilidad

| Área PRD | Requisitos SRS | Criterios |
|---|---|---|
| Principios y seguridad | RF-A-002, 020–025, 041, 110–125 | CA-002, 005, 010, 011, 015, 016, 018 |
| Catálogo | RF-A-010–016 | CA-001–004 |
| Ventas y precios | RF-A-030–042 | CA-001–005, 010 |
| Pagos | RF-A-050–054 | CA-006–008 |
| Jornada y outcomes | RF-A-060–067 | CA-006, 007, 009, 019, 020 |
| Work Items | RF-A-070–074 | CA-006, 007 |
| Cierre | RF-A-080–085 | CA-008–010 |
| Consolidados | RF-A-090–093 | CA-012 |
| Exportación | RF-A-100–105 | CA-013, 014 |
| UI generativa | RF-A-110–113 | CA-015, 016 |
| Memoria y auditoría | RF-A-120–125 | CA-005, 010, 018 |

## 15. Definition of Done

Un requisito está terminado cuando tiene implementación, pruebas unitarias e integración proporcionales al riesgo, documentación de contrato, métricas, manejo de errores, autorización y auditoría. Una capability con mutación no está terminada sin prueba de idempotencia, rollback y aislamiento de tenant.
