# Technical Architecture — Lumo MVP Build A v1.0

**Estado:** Arquitectura base para implementación  
**Producto:** Lumo  
**Stack:** Flutter, FastAPI, PostgreSQL y Docker  
**Estilo:** monolito modular AI-native  
**Fecha:** 19 de septiembre de 2026

## 1. Decisión arquitectónica

Build A se implementará como un monolito modular desplegable en contenedores. FastAPI aloja el API and Experience Gateway, el runtime agentic y los módulos de aplicación y dominio. PostgreSQL es la fuente de verdad. Flutter ofrece el Business Stream, vistas operativas y un renderer de UI generativa controlada.

La arquitectura separa el razonamiento probabilístico de la ejecución confiable. El LLM interpreta y propone; Policy and Risk Engine decide si la acción puede continuar; Domain Tools validan y calculan; PostgreSQL confirma; Audit and Evidence prueba qué ocurrió; Event Memory conserva hechos; el sistema solo entonces responde éxito.

## 2. Objetivos y restricciones

### 2.1 Objetivos

- soportar conversación como plano de control;
- mantener responsabilidad sobre workflows y outcomes;
- ejecutar cálculos y mutaciones de manera determinística;
- permitir venta por monto y venta detallada con catálogo;
- aislar datos por comercio;
- evitar duplicados y false completion;
- ofrecer contratos estables a Flutter y futuras integraciones;
- observar precisión, costo y comportamiento agentic;
- evolucionar sin dividir prematuramente en microservicios.

### 2.2 Restricciones de Build A

- una sola región y despliegue lógico;
- operación online con recuperación; no offline avanzado;
- un Orchestrator principal;
- un proveedor LLM detrás de una abstracción;
- no event bus externo, vector database, Redis ni object storage obligatorios;
- exportaciones pequeñas pueden generarse dentro del proceso o por job interno;
- inventario, compras, conciliación, facturación y multi-sucursal no se modelan como módulos activos.

## 3. Vista de contexto

```text
Usuario
  │
  ▼
Flutter Mobile App
  │ HTTPS JSON
  ▼
FastAPI API and Experience Gateway
  ├── Resource APIs
  ├── Agent Message API
  ├── Action API
  └── View APIs
        │
        ▼
AI and Agent Runtime
  ├── Intent and Entity Understanding
  ├── Lumo Orchestrator
  ├── Policy and Risk Engine
  ├── Workflow and Outcome Engine
  └── Response and Generative UI Composer
        │
        ▼
Application and Domain Tools
  ├── Catalog
  ├── Sales and Payments
  ├── Operational Day and Closing
  ├── Reporting and Export
  ├── Event Memory
  └── Audit and Evidence
        │
        ▼
PostgreSQL
```

## 4. Capas y regla de dependencia

```text
Flutter Views
  → Flutter BFF Client
  → HTTP Contracts
  → FastAPI Gateway
  → Application Use Cases and Orchestrator
  → Domain
  → Ports
  → PostgreSQL and external adapters
```

Las dependencias apuntan hacia el dominio. El dominio no importa FastAPI, ORM, SDK del proveedor LLM ni tipos de Flutter. Los adapters implementan puertos definidos por capas interiores.

## 5. Flutter Experience Layer

### 5.1 Responsabilidades

- autenticación y sesión;
- Business Stream y composer;
- vista Hoy con periodos diario, semanal y mensual;
- catálogo básico;
- configuración mínima;
- renderer de componentes generativos permitidos;
- acciones optimistas solo para estado visual, nunca para confirmar negocio;
- caché de lectura y reintento seguro de mutaciones con la misma idempotency key.

### 5.2 Estructura propuesta

```text
lib/
  app/
  core/
    auth/
    networking/
    observability/
    localization/
  features/
    business_stream/
    today/
    catalog/
    closing/
    settings/
  generative_ui/
    contracts/
    registry/
    renderers/
    actions/
```

### 5.3 BFF client

La app usa un cliente único tipado. Ninguna vista construye URLs ni calcula totales. Los view models provienen del Experience Gateway y la app solo aplica formato local de fecha, moneda y accesibilidad.

### 5.4 Generative UI controlada

El backend emite un esquema versionado con `component`, `version`, `data`, `actions` y `fallback_text`. Flutter mantiene un registry local. No se permiten HTML, JavaScript, WebView, URL ejecutable, código descargado ni componente desconocido.

Las acciones contienen identificadores estables y un `context_token` firmado. Al volver al servidor se revalidan tenant, actor, permiso, política, vigencia y estado actual.

## 6. API and Experience Gateway

FastAPI expone cuatro familias:

```text
/api/v1/catalog/*
/api/v1/sales/*
/api/v1/operational-days/*
/api/v1/exports/*
/api/v1/lumo/messages
/api/v1/lumo/actions
/api/v1/views/home
/api/v1/views/today
```

### 6.1 Responsabilidades

- autenticar y resolver `TenantContext`;
- validar payloads con esquemas estrictos;
- exigir idempotencia en mutaciones;
- aplicar rate limits y correlation IDs;
- traducir errores de aplicación al envelope público;
- presentar view models y contratos de UI;
- no contener reglas de negocio.

### 6.2 APIs de recursos y agente

Las resource APIs sirven flujos estructurados, pruebas e integraciones futuras. La Agent API sirve lenguaje natural. Ambas invocan los mismos casos de uso y Domain Tools; no existen dos implementaciones del dominio.

## 7. AI and Agent Runtime

### 7.1 Intent and Entity Understanding

Convierte texto en una `AgentDecision` validada:

```text
intent
entities with confidence and provenance
candidate tool
missing fields
clarification question
response hints
```

El output se valida contra JSON Schema/Pydantic. Texto de usuario, catálogo y memoria se tratan como datos no confiables. Una salida inválida no alcanza el dominio.

### 7.2 Lumo Orchestrator

Build A usa un solo orquestador para preservar una inteligencia coherente. Sus responsabilidades son:

1. cargar contexto mínimo de conversación, jornada y outcomes;
2. solicitar interpretación cuando hace falta;
3. resolver ambigüedad o elegir una tool registrada;
4. pedir autorización al Policy and Risk Engine;
5. invocar el caso de uso;
6. verificar el resultado confirmado;
7. solicitar reevaluación de workflow y Next Best Action;
8. componer texto y UI controlada.

El Orchestrator no accede al ORM ni abre transacciones de negocio directamente.

### 7.3 Model Provider Port

El proveedor LLM se abstrae mediante:

```text
interpret(message, context, allowed_tools) -> AgentDecision
compose(result, ui_contracts) -> AgentResponse
health() -> ProviderStatus
```

Se versionan modelo, prompt, schemas y tool catalog. El fallback puede usar rutas estructuradas o un intérprete local limitado; nunca relaja políticas.

### 7.4 Context assembly

El contexto sigue minimización:

- identidad y tenant;
- estado de jornada y outcome;
- WorkItems relevantes;
- candidatos de catálogo necesarios;
- políticas aplicables;
- últimos turnos necesarios.

No se envía toda la base ni memoria indiscriminadamente.

## 8. Policy and Risk Engine

### 8.1 Orden de evaluación

```text
security
→ integrity
→ tenant and permissions
→ workflow gates
→ business rules
→ catalog and pricing
→ confidence and ambiguity
→ user experience
```

Una regla inferior no invalida una superior.

### 8.2 Políticas core

| ID | Decisión |
|---|---|
| `SEC-001` | LLM no muta estado |
| `SEC-002` | Solo tools/actions/widgets registrados |
| `SEC-003` | Argumentos se revalidan en servidor |
| `INT-001` | Mutaciones idempotentes |
| `INT-002` | Operación y evidencia atómicas |
| `INT-003` | Cálculos determinísticos |
| `INTP-001` | Intención soportada antes de actuar |
| `INTP-002` | Datos esenciales no se inventan |
| `INTP-003` | Se aclara solo la parte ambigua |
| `INTP-004` | Baja confianza bloquea mutación |
| `CAT-001` | Producto activo es fuente de verdad |
| `CAT-002` | Solo unidades compatibles |
| `SALE-001` | Cantidad positiva |
| `SALE-003` | Precio vigente durante commit |
| `PRICE-001` | Override exige permiso y motivo |
| `PAY-001` | Pago puede quedar pendiente, no se infiere efectivo |
| `CASH-001` | Venta y efectivo son conceptos distintos |
| `CASH-002` | Diferencia no se corrige silenciosamente |
| `AUD-001` | Entrada, política y efectos se auditan |
| `ERR-001` | No hay éxito antes del commit |

La decisión acordada para Lumo reemplaza la inferencia automática de efectivo de la POC. Si el medio no se indicó, queda pendiente.

### 8.3 Resultado de política

El engine devuelve `allow`, `deny`, `clarify` o `confirm`, con rule IDs, reason code y requisitos de evidencia. La respuesta se guarda en AuditEvent.

## 9. Workflow and Outcome Engine

### 9.1 Responsabilidades

- mantener estados de `OperationalDay` y `OutcomeRun`;
- evaluar gates determinísticos;
- crear y resolver WorkItems;
- calcular Next Best Action;
- mantener owner, reason code y evidencia;
- emitir eventos después de mutaciones relevantes.

### 9.2 Outcome definitions

Las definiciones se versionan en datos o código declarativo. Cada una incluye trigger, inputs, gates, output, limitaciones y esquema de evidencia. Build A registra:

- `daily_sales_operations_ready@1`;
- `daily_close_ready@1`.

El LLM puede explicar un gate, pero no modificar su resultado.

### 9.3 Evaluación transaccional

Cuando una mutación cambia un gate, el caso de uso actualiza la operación y emite un evento en la misma transacción. El engine procesa la reevaluación de forma síncrona para respuestas que dependen del nuevo estado. Procesos derivados pueden usar un outbox interno.

## 10. Domain Tools

### 10.1 Registro cerrado

```text
catalog.search
catalog.create_product
catalog.update_product
sale.prepare
sale.commit
payment.resolve
operational_day.get
operational_day.summary
closing.prepare
closing.submit_cash_count
closing.confirm
export.create
memory.query_events
```

Cada tool declara versión, input/output schema, permiso, política, idempotencia, side effects y eventos.

### 10.2 Venta

`sale.commit` ejecuta dentro de una transacción:

1. valida tenant, actor y argumentos;
2. resuelve productos y conversiones;
3. lee precios vigentes con control de concurrencia;
4. valida override y motivo;
5. calcula líneas y total con decimal exacto;
6. crea venta, líneas y pago o pendiente;
7. actualiza jornada;
8. escribe AuditEvent, BusinessEvent y outbox;
9. completa IdempotencyRecord;
10. confirma.

Solo después del paso 10 la aplicación puede devolver éxito.

### 10.3 Reportes y exportación

Las consultas agregadas viven en un módulo de reporting con read models SQL. Las exportaciones reutilizan las mismas definiciones de filtro y agregación para evitar discrepancias. XLSX y CSV son adapters de salida, no lógica de dominio.

## 11. Persistencia PostgreSQL

### 11.1 Esquemas o namespaces

```text
identity
catalog
sales
operations
workflow
memory
audit
platform
```

Pueden implementarse como schemas PostgreSQL o convenciones de tablas dentro de una sola base. El límite modular importa más que la separación física inicial.

### 11.2 Tablas principales

```text
businesses
users
memberships
payment_methods

products
product_aliases
product_prices
unit_conversions

sales
sale_lines
payments

operational_days
cash_counts

outcome_definitions
outcome_runs
completion_evidence
work_items
next_best_actions
source_coverage_records

business_events
memory_items
audit_events
idempotency_records
outbox_events
export_jobs
```

### 11.3 Multi-tenancy

Modelo compartido con columna `business_id` en toda entidad de negocio. Controles:

- `TenantContext` derivado del token;
- repositorios que requieren tenant explícito;
- índices compuestos con `business_id`;
- constraints y claves foráneas que evitan referencias cruzadas;
- Row Level Security donde el stack operativo lo permita;
- pruebas automatizadas de aislamiento.

### 11.4 Dinero, unidades y tiempo

- dinero: `numeric(19,4)` y moneda ISO;
- cantidad: `numeric(19,6)`;
- timestamps: `timestamptz` UTC;
- fecha operacional: `date` calculada con zona del comercio;
- IDs: UUIDv7 o ULID;
- eventos y auditoría: append-only lógico.

### 11.5 Idempotencia

`idempotency_records` tiene unique `(business_id, operation_type, key)`, request hash, estado, resource ID y respuesta materializada. La reserva y la mutación se coordinan transaccionalmente. Reintentos con payload distinto fallan.

### 11.6 Outbox

Aunque Build A no usa un broker externo, `outbox_events` evita perder eventos entre el commit y procesos derivados. Un worker del mismo despliegue publica internamente memoria, métricas o jobs. El consumidor también es idempotente.

## 12. Event Memory

Event Memory es factual y se construye desde eventos confirmados. Cada `MemoryItem` incluye tipo semántico, referencia fuente, tiempo efectivo, actor, tenant y nivel de confianza. No convierte inferencias en hechos.

Ejemplos:

- venta confirmada;
- producto y cantidad vendidos;
- override de precio con motivo;
- pago resuelto;
- CashCount registrado;
- outcome completado;
- exportación generada.

Build A puede consultar memoria factual para continuidad, pero no usa embeddings ni vector database. La evolución futura añadirá memoria contextual y de resolución detrás de puertos separados.

## 13. Audit and Evidence

### 13.1 AuditEvent

Registro append-only con actor, fuente, acción, intención original, tool, políticas, before/after permitido, resultado, correlation ID, idempotency key y timestamp.

### 13.2 CompletionEvidence

Vincula un gate u outcome con evidencia estructurada: ventas incluidas, pagos resueltos, cálculo de efectivo, CashCount, cobertura y versión de contrato.

### 13.3 Integridad

La auditoría crítica se escribe en la misma transacción que el efecto. La evidencia de completion se deriva de estado confirmado. No se puede eliminar desde APIs de Build A.

## 14. Seguridad

### 14.1 Controles

- OIDC/OAuth compatible y tokens cortos;
- permisos atómicos evaluados en backend;
- aislamiento por tenant y RLS;
- TLS, secretos fuera de imágenes y rotación;
- validación Pydantic y allowlists;
- protección contra prompt injection y tool injection;
- context tokens firmados para UI generativa;
- rate limiting y límites de tamaño;
- dependencia y container scanning en CI;
- backups cifrados y restauración probada.

### 14.2 Amenazas agentic

| Amenaza | Control |
|---|---|
| Prompt intenta saltar reglas | Prompt aislado, decisión esquemática y policy check independiente |
| Modelo inventa tool | Registry cerrado y validación por ID/versión |
| Modelo calcula importe | Tool descarta totales propuestos y recalcula |
| Acción de widget manipulada | optionId opaco, token firmado y reautorización |
| Contexto de otro comercio | TenantContext servidor, RLS y pruebas de aislamiento |
| Respuesta anuncia éxito prematuro | Response composer usa resultado post-commit |
| Reintento duplica venta | IdempotencyRecord y unique constraints |

## 15. Observabilidad y evaluación

### 15.1 Telemetría técnica

OpenTelemetry para trazas, métricas y logs estructurados. La traza principal conserva:

```text
request
→ auth and tenant
→ interpretation
→ policy
→ tool
→ transaction
→ workflow gates
→ memory and audit
→ response
```

### 15.2 Telemetría de producto

- estado y duración de OutcomeRun;
- WorkItems creados, resueltos y vencidos;
- Next Best Action aceptada o ignorada;
- tasa de aclaración;
- cambios de precio al commit;
- duplicados evitados;
- diferencia de caja;
- consistencia de exportación;
- trabajo manual antes y después.

### 15.3 Telemetría de IA y costo

- proveedor, modelo y versión de prompt;
- tokens, latencia, errores y fallback;
- tool accuracy y schema failures;
- costo de modelo, infraestructura y reintentos por outcome;
- muestreo seguro para evaluación humana.

## 16. Despliegue con Docker

### 16.1 Contenedores

```text
api        FastAPI ASGI
worker     jobs de outbox y exportación
postgres   desarrollo local únicamente
```

En producción se prefiere PostgreSQL administrado. `api` y `worker` usan la misma imagen y distintos comandos. Las migraciones se ejecutan como job único antes del rollout.

### 16.2 Entornos

- local: Docker Compose, datos de prueba y proveedor LLM opcional;
- test: base efímera y mocks determinísticos del modelo;
- staging: configuración semejante a producción y datos sintéticos;
- production/pilot: secretos administrados, backups, alertas y acceso restringido.

### 16.3 Configuración

Configuración por variables tipadas y secret references. El arranque falla si faltan valores críticos. No se incluyen secretos en repositorio ni imagen.

## 17. Estructura del backend

```text
backend/
  app/
    api/
      routes/
      schemas/
      dependencies/
    agent/
      orchestrator/
      interpretation/
      providers/
      generative_ui/
    application/
      commands/
      queries/
      workflows/
    domain/
      catalog/
      sales/
      operations/
      outcomes/
      shared/
    infrastructure/
      persistence/
      llm/
      exports/
      telemetry/
    policies/
    bootstrap/
  migrations/
  tests/
```

Los módulos públicos exponen casos de uso o puertos. No se permiten imports directos de tablas entre dominios; las dependencias pasan por interfaces o servicios de aplicación.

## 18. Estrategia de pruebas

### 18.1 Unitarias

- conversiones y dinero;
- precio vigente y overrides;
- gates y transiciones;
- Policy Engine;
- Next Best Action;
- serializers CSV/XLSX.

### 18.2 Integración

- transacciones y rollback;
- idempotencia concurrente;
- RLS y aislamiento tenant;
- outbox y consumidores;
- APIs y error envelope;
- exportaciones contra queries.

### 18.3 Contract tests

- Pydantic ↔ cliente Dart;
- Tool schemas ↔ Orchestrator;
- Generative UI registry backend ↔ Flutter;
- OutcomeDefinition ↔ Workflow Engine.

### 18.4 E2E

Los 14 escenarios del PRD son la suite mínima. Se agregan fallas del proveedor LLM, pérdida de respuesta después de commit y acceso cruzado entre comercios.

## 19. Decisiones heredadas de NexoPOS

### 19.1 Se conservan

- separación entre interpretación probabilística y dominio determinístico;
- policy check antes de ejecutar;
- catálogo cerrado de tools/actions/widgets;
- validación de argumentos en servidor;
- idempotencia y transacciones atómicas;
- revalidación de precio al commit;
- auditoría de entrada, reglas y efectos;
- aclaración limitada a la parte ambigua;
- UI declarativa restringida;
- vistas sin lógica de negocio;
- APIs de recursos y experiencia sobre el mismo dominio.

### 19.2 Se reemplazan para producción

| POC NexoPOS | Lumo Build A |
|---|---|
| React y Vite | Flutter |
| Express TypeScript | FastAPI Python |
| SQLite WAL | PostgreSQL |
| OpenJSON específico | Contrato generativo versionado para Flutter |
| Reglas de inventario y gastos | Políticas de ventas, catálogo y cierre |
| Efectivo inferido por defecto | Pago pendiente explícito |
| Instancia local | Multi-tenant con aislamiento por comercio |

El seed de 58 productos y reglas sirve como referencia de modelo y pruebas; no se importa como verdad de producción sin revisión de Carrota.

## 20. Target Architecture futura

La arquitectura objetivo extiende los mismos límites sin obligar a Build A a desplegar todos sus componentes.

```text
Canales
  Flutter · voz · cámara · documentos · dispositivos · integraciones
        │
Experience Gateway and Identity
        │
Multi-agent and Outcome Runtime
  Orchestrators · planners · policy/risk · human review · evaluations
        │
Domain Capabilities
  Sales · Inventory · Purchasing · Reconciliation · Finance · Reporting
        │
Memory and Knowledge
  Event · Operational Context · Resolution · Semantic Retrieval
        │
Data and Integration Platform
  PostgreSQL · object storage · cache · vector store · event bus · connectors
        │
Cross-cutting
  Security · privacy · audit · observability · cost · backup · governance
```

### 20.1 Disparadores de evolución

- separar worker o servicio cuando carga o aislamiento lo exija;
- adoptar Redis cuando haya necesidad probada de cache, locks o colas;
- adoptar object storage cuando archivos y exportaciones superen el manejo local;
- adoptar event bus cuando existan múltiples consumidores o integraciones;
- adoptar vector store cuando la recuperación semántica tenga casos medidos;
- separar módulos en servicios cuando equipos, escalamiento o fallos independientes lo justifiquen;
- introducir múltiples agentes solo cuando tareas especializadas mejoren calidad o costo y mantengan una experiencia única.

## 21. Architecture Decision Records requeridos

- ADR-001 Flutter como cliente móvil.
- ADR-002 FastAPI y Python para backend.
- ADR-003 PostgreSQL como fuente de verdad.
- ADR-004 Docker como unidad de despliegue.
- ADR-005 Monolito modular para Build A.
- ADR-006 LLM no puede mutar estado.
- ADR-007 Cálculo determinístico en backend.
- ADR-008 Orchestrator único en Build A.
- ADR-009 Generative UI controlada.
- ADR-010 Multi-tenancy compartido con aislamiento estricto.
- ADR-011 Idempotencia y outbox transaccional.
- ADR-012 Outcome definitions y gates versionados.

## 22. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Lumo se percibe como POS con chat | Outcomes, Next Best Action, memoria y proactividad medibles |
| Hallucination o tool incorrecta | Schemas, registry cerrado, policy engine y cálculo servidor |
| Falsa completitud | Gates determinísticos y evidencia post-commit |
| Datos cruzados entre comercios | TenantContext, RLS, constraints y pruebas negativas |
| Sobrearquitectura | Monolito modular y componentes futuros condicionados |
| Precio inconsistente | Relectura y control de concurrencia al commit |
| Exportaciones no cuadran | Misma capa de queries y pruebas de reconciliación |
| Costo LLM alto | Contexto mínimo, rutas estructuradas, caching seguro y medición por outcome |
| Dependencia de proveedor | Model Provider Port y fixtures determinísticos |
| Pérdida de eventos | Outbox transaccional y consumidores idempotentes |

## 23. Secuencia de implementación

1. Foundation: repositorio, Docker, configuración, health, PostgreSQL, migraciones, auth, tenant, auditoría e idempotencia.
2. Catálogo: productos, alias, unidades, precios y búsquedas.
3. Sales core: ventas por monto, líneas, pagos simples y transacciones.
4. Agent runtime: provider port, decisiones estructuradas, policy engine y tools.
5. Workflow: jornada, outcomes, gates, WorkItems y Next Best Action.
6. Closing: efectivo esperado, CashCount, diferencia y confirmación.
7. Experience: Business Stream, Hoy, catálogo y Generative UI.
8. Reporting: consolidados diario, semanal y mensual.
9. Export: CSV/XLSX, checksum, acceso y auditoría.
10. Hardening: pruebas E2E, seguridad, observabilidad, backups y piloto.

## 24. Criterios de aceptación arquitectónica

- El LLM no tiene acceso a repositorios ni credenciales de base.
- Toda mutación pasa por una Domain Tool y Policy Engine.
- El resultado exitoso siempre proviene de estado confirmado.
- Los cálculos monetarios se reproducen sin el LLM.
- Un reintento concurrente no duplica efectos.
- Las pruebas impiden lectura y escritura cruzada entre comercios.
- Flutter rechaza UI y acciones fuera del registro.
- Resource API y Agent API producen el mismo resultado de dominio.
- Los dos outcomes se evalúan mediante definiciones versionadas.
- CSV, XLSX y resúmenes comparten filtros y totales.
- La caída del LLM no elimina operaciones estructuradas esenciales.
- La telemetría permite seguir intención, política, tool, commit, outcome y costo.
