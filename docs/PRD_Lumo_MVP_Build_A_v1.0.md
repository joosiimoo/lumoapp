# PRD — Lumo MVP Build A v1.0

**Estado:** Aprobado para implementación  
**Producto:** Lumo  
**Build:** MVP Build A — Daily Sales Operator  
**Mercado inicial:** pequeños comercios independientes en México  
**Piloto de referencia:** Carrota  
**Idioma y moneda iniciales:** español y MXN  
**Fuente maestra:** PRD Lumo v0.11  
**Fecha:** 19 de septiembre de 2026

## 1. Propósito y decisión de alcance

Build A validará si un pequeño comercio delega en Lumo la organización de sus ventas y el cierre de su jornada. La conversación es el control principal, pero Lumo mantiene estado, detecta pendientes, ejecuta operaciones seguras mediante herramientas determinísticas y prepara resultados verificables.

El piloto de Carrota requiere reemplazar dos prácticas diarias: la hoja impresa donde se anotan productos, pesos, cantidades y precios, y la consolidación manual posterior en Excel. Por eso Build A incluye un catálogo básico opcional, venta detallada y consolidados automáticos, sin incorporar inventario ni convertirse en un POS tradicional.

Los outcomes del build son:

- `daily_sales_operations_ready`: las ventas conocidas de la jornada están registradas, calculadas, clasificadas por pago y disponibles para consulta o exportación.
- `daily_close_ready`: la jornada cumple sus gates, muestra el efectivo esperado, incorpora el conteo real y está lista para confirmación.

## 2. Tesis que se validará

La hipótesis principal es que el comercio obtiene valor cuando Lumo absorbe el trabajo de registrar, calcular, consolidar, encontrar pendientes y preparar el cierre, y no únicamente cuando ofrece captura conversacional.

Build A debe demostrar Minimum Operator Behavior:

- mantener el estado de la jornada entre interacciones;
- detectar datos faltantes o ambiguos;
- conservar trabajo pendiente;
- priorizar la siguiente acción necesaria;
- preparar los dos outcomes sin que el usuario construya reportes;
- confirmar qué terminó y explicar qué no pudo verificarse;
- crear memoria factual de cada operación confirmada.

## 3. Usuarios

### 3.1 Dueño operador

Configura el comercio, registra o supervisa ventas, resuelve pendientes, revisa resultados, cuenta efectivo y confirma el cierre.

### 3.2 Colaborador

Registra ventas y completa datos permitidos. No cambia configuración sensible ni confirma el cierre salvo permiso explícito.

### 3.3 Dueño remoto

Consulta el estado de la jornada, consolidados y exportaciones. En Build A utiliza las mismas superficies y permisos básicos; no se construye una experiencia remota especializada.

## 4. Problemas del piloto

Carrota registra productos vendidos en papel, con cantidades por pieza o peso, y después consolida manualmente los datos. Este flujo produce trabajo repetido, dificulta identificar datos faltantes y separa la captura del cierre.

Build A debe resolver:

1. Captura rápida de ventas estructuradas y ventas por monto.
2. Cálculo confiable de cantidades, unidades, precios y totales.
3. Registro explícito de ajustes de precio.
4. Seguimiento de ventas con información pendiente.
5. Consolidación automática por día, semana y mes.
6. Preparación del cierre y comparación del efectivo.
7. Exportación operativa a CSV y XLSX.

## 5. Promesa del producto

Lumo registra las ventas conocidas durante el día, calcula productos y precios en el backend, mantiene organizada la jornada y prepara el cierre y los resultados del comercio.

La promesa se limita a las operaciones registradas o recibidas por fuentes declaradas. Lumo no afirma conocer ventas que nunca ingresaron al sistema.

## 6. Principios del build

1. **Outcome first.** Cada capacidad debe contribuir a uno de los dos outcomes.
2. **Conversation as control plane.** El usuario expresa intención y resuelve excepciones mediante lenguaje natural y acciones estructuradas.
3. **El LLM no muta estado.** Solo herramientas registradas y el dominio pueden modificar datos.
4. **Cálculo determinístico.** Cantidades, conversiones, precios, subtotales, totales, agregados y diferencias se calculan en el backend.
5. **Catálogo cerrado.** El agente solo selecciona tools, acciones y widgets registrados.
6. **Evidence before completion.** Ningún outcome se completa sin commit, gates y evidencia.
7. **Ambigüedad mínima.** Lumo conserva lo inequívoco y pregunta solo por el dato dudoso.
8. **Precio vigente al commit.** El backend vuelve a consultar y validar el precio antes de confirmar la venta.
9. **Idempotencia obligatoria.** Toda mutación tolera reintentos sin duplicar efectos.
10. **Aislamiento por comercio.** Ningún dato o contexto cruza límites de tenant.
11. **Auditoría completa.** Cada mutación registra actor, intención, política, efecto y resultado.
12. **Catálogo opcional.** Un comercio puede operar con venta por monto o concepto libre cuando no usa productos estructurados.

## 7. Alcance funcional

### 7.1 Onboarding mínimo

- Crear un comercio con nombre, moneda, zona horaria y locale.
- Crear un usuario propietario.
- Configurar medios de pago simples: efectivo, tarjeta, transferencia y otro.
- Activar o no el catálogo sin impedir el inicio.
- Registrar el inicio de la fuente `manual_capture`.

### 7.2 Catálogo básico

- Crear, consultar, editar y desactivar productos.
- Campos: nombre, alias, SKU opcional, categoría opcional, unidad de venta, precio vigente y estado.
- Unidades iniciales: pieza, kilogramo, gramo, litro, mililitro, paquete y servicio.
- Definir conversiones válidas entre unidad capturada y unidad de precio.
- Buscar por nombre o alias con coincidencia normalizada.
- Importar el catálogo inicial de Carrota mediante una carga controlada si está disponible.
- No administrar costo, stock, punto de reposición, proveedores ni compras.

### 7.3 Venta conversacional detallada

El usuario puede expresar una venta completa o agregar elementos en varias interacciones.

Ejemplo:

> “900 gramos de zanahoria, 300 gramos de tomate y cuatro galletas A. Pagó con tarjeta.”

Lumo debe:

1. identificar intención y entidades;
2. resolver productos y unidades;
3. aclarar únicamente la ambigüedad necesaria;
4. consultar precios vigentes;
5. preparar una propuesta estructurada;
6. evaluar políticas y permisos;
7. ejecutar mediante una tool del dominio;
8. volver a validar precios durante el commit;
9. guardar venta, líneas, pago, auditoría y eventos en una transacción;
10. responder con texto y UI generativa controlada.

### 7.4 Venta sin catálogo

Build A permite:

- monto y medio de pago: “385 tarjeta”;
- solo monto: “250”, dejando el medio pendiente;
- concepto libre con monto, cuando la política lo permita.

La venta sin catálogo y la venta detallada terminan en la misma entidad `Sale`.

### 7.5 Precios y ajustes

- El precio base proviene del catálogo vigente.
- Un ajuste de precio requiere precio final y motivo.
- El motivo se conserva por línea y en auditoría.
- Lumo muestra precio base, precio final y diferencia.
- Si el precio cambia entre la interpretación y el commit, el servidor usa el precio vigente y devuelve el resultado actualizado.
- El LLM nunca es fuente de verdad de un total.

### 7.6 Pagos simples

- Una venta tiene un único medio de pago en Build A.
- El medio puede quedar pendiente durante la jornada.
- Un pago pendiente crea un `WorkItem` y bloquea `daily_close_ready`.
- Tarjeta y transferencia incrementan ventas, pero no efectivo físico esperado.
- Pagos mixtos pertenecen a Build B.

### 7.7 Jornada operacional

- La primera venta abre la jornada implícitamente.
- El sistema mantiene número de ventas, importe, distribución por pago, efectivo esperado, artículos o conceptos registrados y pendientes.
- El usuario puede consultar la jornada mediante conversación o la vista Hoy.
- Los pendientes sobreviven al cierre de sesión y al cambio de dispositivo cuando existe conexión.

### 7.8 Work Items y Next Best Action

- Cada dato requerido pendiente crea o actualiza un `WorkItem`.
- El sistema asigna prioridad, responsable e impacto sobre el outcome.
- `NextBestAction` prioriza seguridad, gates bloqueantes y excepciones antes de recomendaciones.
- La experiencia explica qué falta, por qué importa y qué acción puede resolverlo.

### 7.9 Preparación y confirmación del cierre

- Lumo prepara el cierre cuando las operaciones conocidas están procesadas.
- Calcula efectivo esperado a partir de ventas pagadas en efectivo.
- Solicita y registra el conteo real de caja.
- Calcula la diferencia y la presenta de forma explícita.
- Build A no corrige ni oculta una diferencia. El usuario puede dejar el outcome bloqueado o confirmar únicamente si la política piloto lo permite y queda evidencia.
- El cierre solo se declara exitoso después de confirmar la transacción.

### 7.10 Consolidados

La vista Hoy y la conversación ofrecen:

- total de ventas y transacciones;
- distribución por medio de pago;
- ticket promedio;
- cantidades e importes por producto, unidad o concepto;
- ajustes de precio y sus motivos;
- pendientes y estado del cierre.

Los mismos indicadores se agregan para semana y mes. Estos son consolidados operativos, no un módulo de BI ni forecasting.

### 7.11 Exportación CSV y XLSX

La exportación es obligatoria y puede solicitarse para día, semana, mes o rango de fechas permitido.

Debe incluir, como mínimo:

- identificadores de comercio, jornada y venta;
- fecha y hora con zona;
- estado de venta;
- producto o concepto;
- cantidad, unidad y cantidad normalizada;
- precio base, precio final, ajuste y motivo;
- subtotal y total declarado;
- medio y estado de pago;
- actor y fuente.

CSV usa UTF-8 y encabezados estables. XLSX incluye hojas `Ventas`, `Detalle`, `Resumen` y `Metadatos`. Los importes se exportan como números y las fechas como valores de fecha cuando el formato lo permite.

### 7.12 Event Memory

Se guardan como hechos confirmados:

- ventas y líneas;
- pagos;
- cambios de precio aplicados;
- work items y resoluciones;
- conteos de efectivo;
- cierre y outcomes;
- exportaciones generadas.

Build A no genera memoria inferida ni aprende reglas autónomas.

### 7.13 Audit and Evidence

Cada mutación conserva:

- comercio y actor;
- solicitud original;
- decisión estructurada del agente cuando aplique;
- tool y versión;
- políticas evaluadas;
- datos anteriores y posteriores relevantes;
- idempotency key y correlation ID;
- resultado del commit;
- timestamp y evidencia asociada.

## 8. Estados principales

### 8.1 Sale

`draft → pending_information → confirmed → voided`

En Build A la cancelación no está expuesta al usuario; `voided` queda reservado para corrección administrativa controlada y pruebas.

### 8.2 Payment

`pending → recorded`

### 8.3 OperationalDay

`not_started → open → in_progress → waiting_for_information → ready_to_close → closed`

El estado `failed` puede alcanzarse desde cualquier estado activo. `closed_with_exceptions` y `reopened` quedan fuera de Build A.

### 8.4 OutcomeRun

`created → running → blocked → ready → completed`

Estados terminales alternos: `failed` y `cancelled`.

## 9. Gates de outcome

### 9.1 daily_sales_operations_ready

- todas las ventas conocidas están confirmadas o marcadas con error visible;
- los cálculos se completaron en backend;
- las líneas resueltas contra catálogo usaron precio vigente al commit;
- cada venta está asociada a una jornada;
- no existe una mutación en estado incierto;
- la cobertura de fuentes está declarada.

### 9.2 daily_close_ready

- `daily_sales_operations_ready` está listo;
- cada venta tiene pago registrado;
- no existe excepción crítica abierta;
- el efectivo esperado se calculó correctamente;
- existe CashCount válido;
- la diferencia de caja está visible;
- existe evidencia y auditoría suficiente;
- las limitaciones de Source Coverage se comunicaron.

## 10. Experiencia mínima

### 10.1 Inicio y Business Stream

Muestra estado de la jornada, actividad de Lumo, pendientes, Next Best Action, respuestas conversacionales y tarjetas generativas.

### 10.2 Hoy

Muestra ventas, pagos, productos o conceptos, efectivo, pendientes, cobertura y estado del cierre. Incluye selector diario, semanal y mensual.

### 10.3 Catálogo

Permite búsqueda, alta y edición básica. No muestra stock ni compras.

### 10.4 Configuración

Permite negocio, moneda, zona horaria, medios de pago y usuarios básicos.

### 10.5 Generative UI controlada

El backend devuelve componentes declarativos de un registro cerrado, por ejemplo:

- `sale_draft_card`;
- `sale_confirmed_card`;
- `clarification_card`;
- `pending_payment_card`;
- `daily_summary_card`;
- `closing_ready_card`;
- `cash_difference_card`;
- `export_ready_card`.

Cada acción usa un `actionId` registrado y un `optionId` opaco; Flutter no envía etiquetas como instrucciones.

## 11. Escenarios prioritarios

1. Venta detallada por peso con precio de catálogo.
2. Venta detallada con ajuste de precio y motivo.
3. Venta por monto y medio de pago.
4. Venta sin medio de pago que genera pendiente.
5. Ambigüedad de producto que requiere una aclaración específica.
6. Cambio de precio antes del commit y revalidación correcta.
7. Reintento de red sin venta duplicada.
8. Usuario sale y vuelve; los pendientes permanecen.
9. Jornada limpia; Lumo prepara cierre y caja coincide.
10. Diferencia de efectivo; Lumo la muestra sin ajustarla.
11. Consolidado semanal y mensual correcto.
12. Exportación CSV y XLSX consistente con la consulta.
13. Intento de acción de otro comercio rechazado.
14. Falla antes del commit; Lumo no declara éxito.

## 12. Fuera de alcance

- inventario, stock, mermas y conteos;
- compras, proveedores y reposición;
- forecasting, predicción y recomendaciones de compra;
- facturación fiscal y contabilidad;
- conciliación bancaria o de adquirentes;
- ecommerce, CRM y marketplace;
- multi-sucursal;
- pagos mixtos;
- cancelaciones y correcciones generales expuestas al usuario;
- reapertura y ClosingSnapshot versionado;
- datos tardíos y resolución avanzada de conflictos;
- operación offline avanzada;
- revisión humana interna y cola de casos;
- memoria inferida, AutomationCandidates y autonomía aprendida;
- voz, cámara y documentos como canales productivos;
- integraciones universales con terminales o bancos;
- Build B y outcomes posteriores.

## 13. Métricas del piloto

### 13.1 Outcome

- porcentaje de jornadas con ambos outcomes listos;
- porcentaje de cierres confirmados sin false completion;
- tiempo entre última venta y cierre listo;
- errores de cálculo o exportación.

### 13.2 Delegación y trabajo absorbido

- pasos manuales antes y con Lumo;
- minutos dedicados a consolidación y cierre;
- porcentaje de pendientes detectados por Lumo;
- porcentaje de jornadas donde Lumo inició la preparación del cierre.

### 13.3 Confianza

- ventas corregidas por error del sistema;
- intentos duplicados evitados;
- discrepancias de precio detectadas;
- comprensión del mensaje de Source Coverage.

### 13.4 Uso y economía

- jornadas activas por comercio;
- costo de modelo e infraestructura por OutcomeRun;
- tasa de fallback o aclaración;
- intención de continuar y pagar.

## 14. Criterios de salida

Build A se considera implementado cuando los 14 escenarios prioritarios pasan pruebas automatizadas y E2E, las exportaciones son consistentes, no existe false completion conocida, las mutaciones son idempotentes y el piloto puede operar durante varias jornadas con auditoría completa.

Build A se considera validado cuando comercios reales delegan el workflow, reducen trabajo manual, entienden los límites de cobertura y muestran una señal de uso sostenido e intención de pago. Solo entonces se evalúa Build B.

## 15. Dependencias y decisiones pendientes

- Catálogo inicial de Carrota y unidades reales.
- Política piloto para confirmar una diferencia de efectivo.
- Ventana de operación que define día, semana y mes.
- Retención de auditoría y exportaciones.
- Proveedor y modelo LLM inicial, sin acoplar el dominio a uno específico.

Estas decisiones son configuración o implementación; no amplían el alcance funcional.
