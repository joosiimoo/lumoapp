# PRD — Lumo: AI-Native Managed Business Operations para pequeños comercios

| Campo | Definición |
|---|---|
| **Nombre del producto** | Lumo |
| **Categoría** | AI-Native Managed Business Operations / Service-as-Software |
| **Versión** | 0.11 |
| **Estado** | Definición maestra del producto, contrato de implementación del MVP y arquitectura de evolución por outcomes |
| **Mercado inicial** | Pequeños comercios independientes en México y Latinoamérica |
| **Canal inicial** | Aplicación móvil |
| **Idioma inicial** | Español |
| **Fecha** | 2 de agosto de 2026 |
| **Documentos base** | PRD v0.7, PRD v0.8, PRD v0.9, PRD v0.10 y backlog maestro de mejoras para v0.11 |

---

# 0. Control de versión

## 0.1 Propósito de la versión 0.11

La versión 0.11 reconstruye y consolida la definición maestra de Lumo después de las iteraciones 0.7, 0.8, 0.9 y 0.10. No reemplaza la tesis establecida en esas versiones; la convierte en un contrato de producto más completo, coherente y ejecutable.

La versión 0.10 resolvió riesgos importantes: separó reglas normativas de hipótesis, distinguió completitud de operaciones conocidas y cobertura de fuentes, introdujo gates formales, versionado del cierre, permisos atómicos, stage gates y una estrategia incremental. Sin embargo, todavía quedaban brechas entre el MVP de Daily Close y la naturaleza completa de Lumo como operador administrativo AI-native.

La versión 0.11 cierra esas brechas mediante:

* una definición explícita de **Minimum Operator Behavior**;
* un framework reusable de **Outcome Contracts**;
* un **Product Outcome Map** que conecta el MVP con el producto completo;
* un modelo de **trabajo absorbido** para medir Service-as-Software;
* memoria factual y contextual desde el primer build;
* una arquitectura incremental del Business Stream;
* `NextBestAction` como mecanismo de priorización;
* un ciclo seguro de aprendizaje de excepciones mediante `AutomationCandidate`;
* outcomes parciales y reason codes de bloqueo o falla;
* un Service Blueprint que delimita responsabilidades visibles e internas;
* una definición más precisa del arquetipo operativo inicial;
* un diseño de piloto centrado en input, ejecución, outcome, delegación, confianza y economía;
* requisitos funcionales adicionales asignados explícitamente a MVP, horizonte inmediato, condicional o futuro.

El objetivo de 0.11 no es aumentar el alcance previo al piloto. Es conservar íntegramente la visión del producto completo mientras reduce la ambigüedad sobre qué debe implementarse primero.

## 0.2 Estado real del proyecto

* La POC conceptual fue completada con 10 comercios de distintos formatos.
* La POC generó evidencia cualitativa favorable sobre simplicidad, interacción conversacional, registro sin catálogo y baja configuración inicial.
* La POC ya no es el objetivo de validación del producto.
* El equipo está terminando la definición del MVP y el siguiente paso es su implementación.
* Después de implementar el MVP se ejecutará un piloto con operación real.
* Todavía no existe evidencia suficiente de uso sostenido, precisión operacional, reducción de trabajo, disposición de pago, costo por outcome, gross margin o disminución progresiva de intervención humana.
* Daily Close es el primer outcome recomendado, pero continúa sujeto a evidencia operacional.

Secuencia oficial:

```text
POC completada
    ↓
Definición final del MVP
    ↓
Implementación del MVP
    ↓
Piloto operativo
    ↓
Validación de outcome, delegación, confianza y economía
    ↓
Expansión progresiva por outcomes
```

La metodología y evidencia de la POC deben conservarse en un informe separado. Este PRD utiliza sus aprendizajes, pero no presenta interés cualitativo como prueba de product-market fit.

## 0.3 Cambios principales respecto de la versión 0.10

Esta versión incorpora o redefine:

1. MVP compuesto por **MVP Build A — Operator Foundation** y **MVP Build B — Reliable Daily Close**.
2. **Product Horizon 1 — Managed Operations** como evolución inmediata posterior al MVP, no como prerequisito para comenzar el piloto.
3. Minimum Operator Behavior como criterio anti-POS y de validez AI-native.
4. Outcome Contract framework y contrato completo de `daily_close_ready`.
5. Estados `partially_completed` y reason codes de outcomes incompletos o fallidos.
6. Product Outcome Map para Daily Close, Weekly Review, Reconciliation, Replenishment, Purchasing, External Review y Financial Operations.
7. Work Absorption Model y `WorkAbsorptionRecord`.
8. Event Memory desde MVP Build A, Operational Context Memory desde MVP Build B y Resolution Intelligence Memory en Product Horizon 1.
9. Business Stream mínimo por build para evitar sobreconstrucción de superficies.
10. Guardrails y métricas explícitas para evitar que Lumo sea percibido como POS.
11. `NextBestAction` y jerarquía de prioridades.
12. `AutomationCandidate` y ciclo de evolución segura de autonomía.
13. Service Blueprint y límites de responsabilidad por workflow.
14. Arquetipo operacional y criterios de inclusión/exclusión del piloto.
15. Métricas de outcome, trabajo absorbido, calidad, service operations, economía y percepción anti-POS.
16. Entidades y eventos adicionales para contracts, outcomes, cobertura, acciones y aprendizaje.
17. Requisitos funcionales nuevos RF-076 a RF-100.
18. Requisitos no funcionales ampliados para reliability de IA, data lineage, operación degradada y cost observability.
19. Escenarios end-to-end adicionales y matriz de trazabilidad ampliada.
20. Contrato de alineación actualizado para evaluar funcionalidades futuras.

## 0.4 Jerarquía de autoridad

Este documento contiene cuatro clases de contenido:

### Normativo

Reglas, estados, requisitos, permisos, gates y criterios que deben cumplirse para considerar construida una capacidad.

### Contrato de MVP

Contenido normativo asignado a `MVP Build A` o `MVP Build B`. Tiene prioridad sobre capacidades de horizontes posteriores.

### Hipótesis de piloto

Supuestos que deben medirse antes de convertirse en reglas definitivas: thresholds, tolerancias, pesos, frecuencias, intención de pago y límites de intervención.

### Estratégico

Visión, posicionamiento, Product Outcome Map, GTM, moat y roadmap. Protege la dirección de largo plazo sin convertirla automáticamente en alcance del MVP.

Cuando exista contradicción:

```text
Seguridad, privacidad y veracidad
    > Outcome Contract y gates formales
    > alcance del build vigente
    > requisitos normativos
    > hipótesis de piloto
    > visión futura
```

## 0.5 Reglas de interpretación

Cuando exista tensión entre amplitud y aprendizaje:

> Ninguna capacidad secundaria debe retrasar la implementación y validación del outcome `daily_close_ready`.

Cuando exista tensión entre velocidad y confiabilidad:

> Lumo puede trabajar con información incompleta, pero nunca debe presentar como completo un resultado que no puede verificar.

Cuando exista tensión entre score y estado:

> El estado del outcome y sus gates tienen prioridad sobre cualquier porcentaje de progreso.

Cuando exista tensión entre facilidad de captura y naturaleza del producto:

> Una experiencia conversacional no es suficiente para declarar que Lumo es AI-native; Lumo debe mantener responsabilidad sobre el workflow.

Cuando exista tensión entre MVP y producto completo:

> Daily Close es el primer outcome que Lumo opera, no la definición completa de Lumo.

## 0.6 Definición de “completo” para este PRD

El PRD 0.11 se considera completo cuando:

* define qué vende Lumo;
* delimita el MVP implementable;
* conserva la evolución del producto completo;
* especifica los contratos operativos del primer outcome;
* define experiencia, reglas, datos, arquitectura y métricas;
* modela trabajo humano, automatización, fallos y cobertura;
* contiene criterios y escenarios verificables;
* separa decisiones estables de hipótesis aún abiertas.

# Parte I — Estrategia del producto

# 1. Resumen ejecutivo

Lumo es un operador administrativo AI-native para pequeños comercios. Captura y organiza la operación diaria, mantiene una memoria continua del negocio, detecta excepciones y cambios relevantes, prepara el cierre y propone las decisiones y acciones que requieren atención.

El producto comienza con un workflow pequeño, frecuente y medible: el cierre diario.

Durante una jornada, un comercio genera información en ventas, cobros, terminales, cuadernos, mensajes, fotografías, documentos y la memoria de las personas. El software tradicional permite registrar parte de esa información, pero continúa dejando al dueño la responsabilidad de mantenerla completa, detectar errores, sumar resultados y decidir qué debe revisar.

Lumo cambia la unidad de valor:

```text
SaaS tradicional
Herramienta → Usuario opera → Usuario verifica → Resultado

Lumo
Señales del negocio → Lumo organiza y verifica → Usuario resuelve excepciones → Resultado terminado
```

El resultado inicial del MVP es:

> Cada día, Lumo organiza las ventas y pagos registrados, identifica toda inconsistencia conocida, calcula el efectivo esperado y entrega una jornada lista para revisar y cerrar, con evidencia y responsabilidad visible para cada pendiente.

El cierre es el punto de entrada, no el límite de la compañía. El workflow genera la memoria y la infraestructura necesarias para asumir progresivamente más trabajo del back office:

```text
Daily Close
    ↓
Weekly Business Review
    ↓
Payment Reconciliation
    ↓
Inventory & Replenishment
    ↓
Purchasing & Supplier Operations
    ↓
Financial Operations & Embedded Finance
```

La experiencia continúa siendo conversacional, pero la conversación no es el producto final. Es el control plane desde el cual el comerciante informa lo ocurrido, revisa resultados, resuelve excepciones y toma decisiones.

La promesa comercial inicial es:

> **Tu negocio se mantiene organizado. Tú intervienes cuando realmente importa.**

# 2. Tesis de producto y compañía

## 2.1 De software de administración a operación gestionada

Los pequeños comercios no necesitan solamente mejores pantallas. Necesitan que parte del trabajo administrativo esté hecho.

Un SaaS tradicional vende acceso a una herramienta. El cliente debe configurar, capturar, corregir, interpretar y perseguir pendientes. Incluso cuando la interfaz es simple, la responsabilidad del resultado continúa en el usuario.

Lumo vende una operación gestionada por software:

* mantiene el estado del workflow;
* detecta información faltante;
* ejecuta validaciones;
* prepara resoluciones;
* aísla excepciones;
* solicita intervención específica;
* verifica criterios de completitud;
* conserva evidencia y auditoría.

## 2.2 De asistente a operador

Un asistente responde cuando se le solicita. Un copiloto prepara o recomienda. Un operador conoce el resultado esperado y mantiene el proceso hasta completarlo o declarar explícitamente por qué no puede completarlo.

La evolución prevista es:

| Nivel | Nombre | Responsabilidad de Lumo |
|---|---|---|
| 0 | Observador | Registra y explica hechos. |
| 1 | Asistente | Prepara acciones solicitadas. |
| 2 | Copiloto | Sugiere acciones de forma proactiva. |
| 3 | Operador supervisado | Ejecuta y solicita confirmación cuando corresponde. |
| 4 | Operador por excepción | Ejecuta dentro de políticas y escala excepciones. |
| 5 | Autónomo bajo políticas | Coordina workflows completos con auditoría. |

El MVP debe operar principalmente en niveles 1 a 3. El nivel 4 se permite únicamente para tareas reversibles, de bajo riesgo y con evidencia suficiente.

## 2.3 De módulos a workflows

Las capacidades no se justifican por existir como módulos. Deben completar un resultado.

Ventas, pagos, inventario, memoria y recomendaciones no son áreas paralelas del MVP. Son capacidades que participan en uno o más workflows.

La pregunta de producto es:

> ¿Qué resultado completo puede delegar hoy el comercio a Lumo?

La respuesta inicial es:

> La organización y cierre de la jornada.

## 2.4 De engagement a trabajo completado

Lumo no optimiza tiempo en pantalla ni cantidad de conversaciones. Optimiza:

* jornadas listas para cerrar;
* cierres correctos;
* pagos organizados;
* excepciones detectadas;
* pendientes resueltos;
* decisiones preparadas;
* minutos administrativos eliminados;
* porcentaje del workflow completado sin intervención humana.

## 2.5 Platform inside, service outside

El cliente puede experimentar un servicio terminado. La empresa debe operar sobre una plataforma común:

* modelo de datos estructurado;
* workflow engine;
* reglas reutilizables;
* agentes especializados;
* políticas de autonomía;
* memoria auditable;
* review queue;
* observabilidad de costo y calidad.

La personalización no debe convertirse en procesos manuales distintos para cada comercio. Las diferencias deben modelarse como configuración, políticas, playbooks verticales o integraciones.

## 2.6 Tesis operativa AI-native

Lumo es AI-native cuando la inteligencia no se limita a interpretar una frase. Debe participar en el ciclo completo:

```text
Percibir señales
→ mantener estado
→ planificar tareas
→ invocar herramientas
→ verificar evidencia
→ manejar excepciones
→ solicitar decisiones
→ completar outcome
→ aprender de la resolución
```

Los modelos pueden interpretar, clasificar, explicar y proponer. Los cálculos, permisos, persistencia, movimientos críticos y gates deben ejecutarse mediante componentes determinísticos.

## 2.7 De software de registro a sistema de responsabilidad

Un sistema de registro almacena lo que el usuario ingresa. Un sistema de responsabilidad conoce el resultado esperado, conserva lo pendiente y declara explícitamente cuándo el trabajo está completo, parcial, bloqueado o fallido.

Lumo debe ser evaluado como sistema de responsabilidad.

## 2.8 Unidad de expansión

Lumo no se expande agregando módulos. Se expande asumiendo un nuevo Outcome Contract sobre la misma plataforma de señales, memoria, políticas, evidencia y operación.

# 3. Problema y oportunidad

## 3.1 Problema principal

La información diaria de un pequeño comercio está fragmentada y depende de la memoria humana. Incluso cuando existe un POS, suele utilizarse parcialmente o no representa toda la operación.

El dueño combina:

* cuadernos;
* calculadora;
* terminal bancaria;
* efectivo;
* transferencias;
* WhatsApp;
* fotografías;
* hojas de cálculo;
* listas de precios;
* reportes que rara vez revisa.

El software registra datos, pero deja al comercio el trabajo invisible:

* verificar si faltan pagos;
* completar autorizaciones;
* detectar duplicados;
* recordar pendientes;
* sumar efectivo;
* explicar diferencias;
* reconstruir lo ocurrido;
* decidir qué comprar;
* preparar información para terceros.

## 3.2 Por qué las alternativas actuales no resuelven el problema

### POS tradicional

Requiere catálogo, capacitación y disciplina de captura. El comercio se adapta al sistema.

### Aplicaciones simples

Reducen fricción, pero el usuario continúa siendo responsable de mantener calidad y obtener conclusiones.

### POS con IA

Agrega una capa de chat o sugerencias, pero conserva módulos y responsabilidad operativa en el usuario.

### Chatbots genéricos

Responden preguntas, pero no mantienen estado ni responsabilidad de un workflow completo.

### ERP para pequeñas empresas

Ofrece amplitud antes de demostrar valor y suele introducir más administración.

## 3.3 Problema económico

El comerciante paga por software y sigue pagando el costo humano de operarlo. Lumo busca capturar parte del valor económico del trabajo eliminado, no solamente del acceso a una interfaz.

## 3.4 Por qué ahora

Los modelos actuales pueden:

* interpretar lenguaje natural;
* extraer datos de imágenes y documentos;
* invocar herramientas determinísticas;
* mantener contexto;
* clasificar excepciones;
* redactar explicaciones;
* operar dentro de políticas.

La oportunidad no está en reemplazar controles críticos con texto generado, sino en combinar modelos, reglas, herramientas, memoria y revisión humana para transformar trabajo repetitivo en software verificable.

# 4. Segmento inicial y wedge

## 4.1 Mercado amplio

La visión aplica a pequeños comercios independientes de múltiples verticales en México y Latinoamérica.

## 4.2 Arquetipo operativo inicial

El MVP y el piloto priorizarán:

> **Comercio independiente de una sola ubicación, operado por el dueño y un equipo pequeño, con 20 a 150 operaciones diarias, efectivo y al menos un medio digital, catálogo inexistente o parcial, cierre manual y sin dependencia inicial de integración fiscal.**

La selección se realiza por homogeneidad operacional, no únicamente por giro comercial.

## 4.3 Criterios de inclusión

* dueño involucrado en la operación o el cierre;
* una sola sucursal;
* uno a cinco colaboradores;
* operación diaria frecuente;
* efectivo y al menos un medio digital;
* proceso de cierre repetitivo;
* información fragmentada o reconstruida manualmente;
* capacidad de registrar las señales mínimas del piloto;
* disponibilidad para acompañamiento e instrumentación;
* baja complejidad regulatoria en el workflow inicial;
* percepción de falta de control, tiempo perdido o diferencias frecuentes.

## 4.4 Criterios de exclusión inicial

* múltiples sucursales como requisito central;
* facturación fiscal como condición para operar;
* integración ERP obligatoria antes de generar valor;
* operación exclusivamente ecommerce;
* conciliación bancaria universal como dolor principal;
* devoluciones o crédito complejo como flujo dominante;
* catálogo que requiere escáner especializado como única captura viable;
* ausencia total de disciplina para informar señales mínimas;
* operación donde el cierre no tenga frecuencia ni valor observable.

## 4.5 Segmentos candidatos

* tiendas de barrio modernas;
* verdulerías y tiendas de alimentos frescos;
* panaderías y cafeterías independientes;
* relojerías y comercios de servicios rápidos;
* tiendas de productos artesanales u orgánicos;
* comercios nacidos en redes sociales con punto físico.

Estos segmentos son candidatos. El piloto debe elegir un subconjunto con workflow comparable.

## 4.6 Wedge funcional

El wedge es:

> **Daily Close Operations for Small Merchants.**

No es “POS conversacional”. El cierre permite entrar por un resultado visible, frecuente y verificable, mientras Lumo construye captura, memoria, excepciones, confianza y una relación de delegación.

## 4.7 Supuestos por validar en el piloto

* El cierre actual consume tiempo, genera incertidumbre o produce errores relevantes.
* El comercio puede suministrar señales suficientes para preparar el outcome.
* El dueño prefiere revisar excepciones en lugar de revisar toda la operación.
* El valor del cierre preparado sostiene uso habitual.
* El comercio acepta que Lumo mantenga pendientes y solicite decisiones.
* Existe intención de pago por control y trabajo eliminado.
* El costo de entregar el outcome puede reducirse mediante producto y aprendizaje.

## 4.8 Stage gate del wedge

Daily Close es el wedge recomendado, no una verdad irreversible. La inversión posterior a Operator Foundation depende de comprobar:

1. **Dolor:** el proceso actual consume tiempo, genera incertidumbre o errores.
2. **Frecuencia:** el resultado es necesario con recurrencia suficiente.
3. **Delegación:** el comercio acepta que Lumo mantenga el workflow.
4. **Confianza:** el usuario comprende evidencia, cobertura y limitaciones.
5. **Valor económico:** existe señal de pago, continuidad o ahorro significativo.
6. **Viabilidad:** las excepciones frecuentes pueden modelarse y automatizarse.

### Gate de continuidad

Antes de ampliar hacia Reliable Daily Close se requiere, como señal inicial:

* operación real durante al menos cinco jornadas en tres o más comercios;
* reducción observable del esfuerzo de cierre;
* comprensión clara del resultado entregado;
* aceptación del modelo de excepciones;
* evidencia de Minimum Operator Behavior;
* señal de intención de pago o continuidad;
* medición inicial del costo por outcome.

Los números son hipótesis de piloto, no thresholds comerciales definitivos.

# 5. Propuesta de valor y posicionamiento

## 5.1 Definición corta

> **Lumo es un operador administrativo AI-native para pequeños comercios que mantiene organizada la operación diaria, prepara el cierre y convierte los datos del negocio en decisiones y acciones.**

## 5.2 One-liner para inversionistas

> **Lumo is the AI-native back-office operator for small merchants: it captures daily operations, resolves exceptions and delivers a ready-to-review close.**

## 5.3 Qué compra el cliente

El cliente compra:

* una jornada organizada;
* un cierre listo para revisar;
* excepciones visibles;
* información confiable;
* menos trabajo administrativo;
* memoria operativa acumulativa;
* acciones preparadas cuando existe suficiente evidencia.

No compra principalmente:

* un chat;
* un POS;
* un dashboard;
* un inventario;
* un agente genérico;
* una licencia por usuario.

## 5.4 Promesa principal

> **Lumo mantiene organizada la operación diaria de tu negocio, prepara el cierre y te muestra solo lo que necesita tu atención.**

## 5.5 Promesa ampliada

Durante la jornada, Lumo:

* registra y organiza la información disponible;
* recuerda pendientes;
* detecta inconsistencias;
* correlaciona ventas, pagos y eventos;
* informa cambios relevantes;
* prepara acciones para el día siguiente;
* conserva evidencia de lo ocurrido.

## 5.6 Resultado emocional

El comerciante debe sentir:

* “el negocio está bajo control”;
* “no tengo que ir a buscar la información”;
* “sé exactamente qué falta”;
* “Lumo recuerda lo que yo olvidaría”;
* “solo reviso lo importante”.

## 5.7 Posicionamiento negativo

Lumo no se presentará como:

* POS;
* ERP para microempresas;
* dashboard con IA;
* chatbot comercial;
* herramienta de productividad;
* firma contable;
* BPO humano disfrazado de software.

# 6. Visión y Product Outcome Map

## 6.1 Visión completa

Lumo será la capa operativa entre el comercio y las señales de su negocio.

```text
Ventas · pagos · compras · inventario · proveedores · documentos
                              ↓
                           Lumo
                              ↓
          Outcomes · excepciones · decisiones · acciones · memoria
```

La visión no es reemplazar cada módulo de un ERP. Es asumir progresivamente workflows completos y entregar resultados listos para decidir.

## 6.2 Product Outcome Map

| Workflow | Outcome que compra el comercio | Trabajo asumido por Lumo | Intervención humana principal |
|---|---|---|---|
| Daily Close | Jornada organizada y lista para revisar | Capturar, ordenar, validar, detectar faltantes, calcular y preparar | Informar efectivo, resolver o aceptar excepciones y confirmar |
| Weekly Business Review | Decisiones semanales preparadas | Consolidar jornadas, detectar cambios, correlacionar y priorizar | Elegir acciones y contextualizar eventos atípicos |
| Payment Reconciliation | Diferencias de cobro identificadas y explicadas | Conectar fuentes, asociar ventas y pagos, detectar duplicados o faltantes | Resolver anomalías o autorizar regularización |
| Inventory & Replenishment | Reposición recomendada | Registrar señales, estimar disponibilidad y proyectar necesidad | Aprobar cantidades y excepciones |
| Purchasing & Supplier Operations | Compra preparada y seguida | Organizar proveedores, documentos, comparaciones y pendientes | Aprobar compromisos y condiciones |
| External Review Package | Información lista para contador o administrador | Consolidar periodos, evidencia, cierres, diferencias y notas | Seleccionar destinatario y compartir |
| Financial Operations | Operación financiera organizada | Correlacionar caja, pagos, compras y compromisos | Autorizar acciones de riesgo o reguladas |

## 6.3 Evolución por outcomes

```text
daily_close_ready
    ↓
weekly_review_ready
    ↓
payment_reconciliation_ready
    ↓
replenishment_plan_ready
    ↓
purchase_plan_ready
    ↓
external_review_package_ready
    ↓
financial_operations_ready
```

La secuencia no es rígida. El siguiente outcome debe seleccionarse por demanda, reutilización de plataforma, valor económico y capacidad de entregar evidencia.

## 6.4 Reutilización de plataforma

Cada outcome debe reutilizar, cuando aplique:

* identidad y permisos del negocio;
* eventos y fuentes;
* Operational Memory;
* workflow engine;
* Policy & Risk Engine;
* Completion Evidence;
* Exception System;
* Review Operations;
* Source Coverage;
* audit trail;
* observabilidad de costo y calidad.

## 6.5 Regla de expansión

Un outcome nuevo entra al roadmap cuando:

1. resuelve un trabajo recurrente y delegable;
2. tiene una promesa verificable;
3. utiliza señales disponibles o integrables;
4. puede aislar excepciones;
5. genera valor y willingness to pay;
6. comparte infraestructura con outcomes existentes;
7. tiene una ruta de reducción de intervención humana.

## 6.6 North Star vision

> **El comercio deja de administrar software y comienza a supervisar resultados.**

## 6.7 Límite del wedge

Daily Close es el primer outcome que Lumo opera. No es el producto completo, ni debe impedir que el modelo de datos, memoria y arquitectura soporte outcomes posteriores.

---

# Parte II — Definición del producto

# 7. Usuarios y Jobs to Be Done

## 7.1 Persona principal: dueño-operador

Administra el negocio y atiende clientes. Tiene poco tiempo para tareas administrativas. Conoce precios y operación de memoria. Necesita registrar sin detener la atención, saber cuánto vendió, detectar diferencias y cerrar rápidamente.

## 7.2 Persona secundaria: colaborador

Atiende clientes, registra ventas y puede desconocer algunos precios. Necesita una captura rápida, ayuda puntual y permisos limitados.

## 7.3 Persona secundaria: dueño remoto

No permanece todo el día en el comercio. Necesita una síntesis confiable, excepciones visibles y capacidad de revisar cambios relevantes.

## 7.4 Persona operacional: operador interno del piloto

Revisa excepciones que Lumo no puede resolver. Debe trabajar dentro de la plataforma, con acceso mínimo, auditoría y medición de tiempo. No debe convertirse en una dependencia invisible.

## 7.5 Job principal

> Cuando termina mi jornada, quiero que las ventas y pagos estén organizados, las diferencias identificadas y el cierre listo para revisar, para terminar el día sin reconstruir manualmente lo ocurrido.

## 7.6 Jobs secundarios

### Registrar sin interrumpir

> Cuando atiendo a un cliente, quiero informar lo vendido en segundos.

### Encontrar excepciones

> Cuando algo falta o no coincide, quiero que Lumo lo detecte y me pida solo la información necesaria.

### Entender el negocio

> Cuando necesito saber cómo va el día, quiero recibir una explicación y acciones relevantes sin construir reportes.

### Recordar decisiones

> Cuando cambia un precio, proveedor o patrón, quiero que Lumo lo recuerde y lo relacione con lo que ocurra después.

### Preparar el siguiente paso

> Cuando el negocio necesita comprar, reponer o corregir algo, quiero recibir una propuesta lista para decidir.

# 8. Principios y guardrails

## 8.1 Outcome First

Toda capacidad debe contribuir a un resultado operativo verificable.

## 8.2 Workflow Complete

Es preferible completar un workflow pequeño de punta a punta que ofrecer muchas funciones parciales.

## 8.3 Exceptions, Not Administration

La operación normal debe requerir mínima atención. La intervención humana se concentra en excepciones y decisiones.

## 8.4 Conversation as Control Plane

La conversación es el mecanismo principal para expresar intención, revisar resultados y resolver excepciones. No sustituye la ejecución determinística.

## 8.5 System of Action and Responsibility

Lumo registra, inicia, verifica, persigue, explica y mantiene responsabilidad hasta completar, bloquear o fallar explícitamente.

## 8.6 Evidence Before Completion

Un outcome no puede marcarse como completo sin evidencia y reglas verificables.

## 8.7 Human-in-the-Loop by Design

La revisión humana es explícita, consentida, auditada y medible.

## 8.8 Autonomy per Task

Cada tarea define autonomía, riesgo, evidencia, permisos y reversibilidad.

## 8.9 No Catalog Required

El comercio puede comenzar con monto y medio de pago. El catálogo no bloquea activación ni cierre.

## 8.10 Progressive Structuring

La estructura aparece cuando genera valor. Una observación no se convierte automáticamente en dato oficial.

## 8.11 Declared Total Is Authoritative

El total declarado es la referencia operativa principal. Las diferencias con el detalle se muestran y clasifican.

## 8.12 Trust Before Autonomy

La autonomía aumenta después de demostrar precisión, evidencia, corrección y control.

## 8.13 Never Hide Manual Work

Las acciones de usuario, regla, modelo y operador interno deben distinguirse.

## 8.14 Control the Promise

Lumo solo promete resultados sobre fuentes que controla o cuya cobertura puede explicar.

## 8.15 Improve the Gross Margin Loop

Cada intervención humana repetida debe convertirse en backlog de producto, regla, integración o aprendizaje.

## 8.16 Never Block the Customer

La atención al cliente tiene prioridad. Los datos no críticos pueden completarse después como pendientes visibles.

## 8.17 Transparent Uncertainty

Hechos, cálculos, observaciones, inferencias, recomendaciones y decisiones deben distinguirse.

## 8.18 Minimum Operator Behavior

Lumo no puede considerarse operador si únicamente registra y reporta. Desde el MVP debe:

* mantener el estado del workflow;
* detectar datos faltantes;
* conservar pendientes;
* iniciar recordatorios contextuales;
* determinar qué impide avanzar;
* preparar el outcome;
* solicitar decisiones específicas;
* confirmar qué quedó terminado;
* explicar limitaciones y cobertura.

## 8.19 Absorb Work, Not Only Clicks

La mejora principal debe expresarse como trabajo eliminado o asumido, no solo como menor número de campos.

## 8.20 Memory from Day One

Cada jornada debe aumentar la memoria factual del negocio desde el primer build. La inteligencia longitudinal puede madurar después.

## 8.21 One Intelligence, Multiple Systems

El usuario percibe una inteligencia coherente. Internamente pueden existir agentes, reglas, operadores y herramientas.

## 8.22 Anti-POS Guardrail

Una captura conversacional no convierte por sí sola a Lumo en una categoría nueva. La diferenciación debe observarse en responsabilidad del workflow, proactividad, memoria, excepciones y outcome.

## 8.23 UX guardrails

No se permite como experiencia principal:

* dashboard tradicional;
* grilla de POS;
* catálogo obligatorio;
* formularios extensos;
* navegación por módulos;
* tablas para encontrar errores;
* chatbot sin estado operativo;
* alertas sin acción;
* teclado de caja como pantalla dominante;
* lenguaje de ERP o procesamiento técnico;
* cierre construido manualmente por el usuario;
* insights sin evidencia o siguiente acción.

## 8.24 Regla de entrada de capacidades

Toda capacidad nueva debe demostrar al menos uno de estos efectos:

* mejora un outcome;
* completa un paso del workflow;
* reduce una excepción;
* absorbe trabajo;
* aumenta cobertura;
* aumenta confiabilidad;
* reduce costo por outcome;
* fortalece memoria, datos o moat.

# 9. Modelo operativo del servicio

## 9.1 Daily Operations Loop

```text
Abrir jornada
    ↓
Capturar señales
    ↓
Normalizar ventas y pagos
    ↓
Actualizar estado y cobertura
    ↓
Detectar excepciones
    ↓
Priorizar Next Best Action
    ↓
Resolver automáticamente lo permitido
    ↓
Solicitar información o revisión
    ↓
Preparar ClosingSnapshot
    ↓
Confirmar outcome
    ↓
Actualizar memoria y aprendizaje
```

## 9.2 Operational Outcome

Un outcome representa el resultado que Lumo promete, independientemente de las tareas internas necesarias.

Estados:

```text
not_started
in_progress
waiting_for_data
waiting_for_user
waiting_for_review
ready
completed
completed_with_exceptions
partially_completed
failed
cancelled
```

`partially_completed` significa que Lumo entrega un artefacto útil, pero uno o más criterios no bloqueantes del contrato no se cumplieron. No equivale a `completed_with_exceptions`, que requiere una política explícita de aceptación.

## 9.3 Outcome Contract framework

Todo outcome debe declarar:

```text
outcome_type
customer_promise
business_value
eligible_segment
trigger
service_window
minimum_inputs
required_sources
optional_sources
source_coverage_requirement
workflow_steps
completion_gates
success_criteria
tolerances
required_evidence
possible_exceptions
allowed_partial_results
failure_conditions
responsible_party
human_confirmation
reversibility
output_artifact
audit_requirements
service_limitations
cost_measurement
pricing_unit
version
```

El contrato debe versionarse. Un cambio en gates, promesa, tolerancia o evidencia no debe alterar silenciosamente outcomes históricos.

## 9.4 Outcome Contract: `daily_close_ready`

### Promesa al cliente

> Lumo organiza todas las operaciones conocidas de la jornada, verifica su estado de pago, calcula el efectivo esperado, muestra las inconsistencias conocidas y entrega un cierre listo para revisar.

### Valor

* reduce reconstrucción manual;
* concentra atención en excepciones;
* genera una evidencia diaria consistente;
* crea memoria operacional;
* permite terminar la jornada con mayor control.

### Trigger

* apertura explícita;
* primera venta de la fecha operativa;
* importación de una señal válida;
* creación programada de jornada según política.

### Inputs mínimos

* negocio y fecha operativa;
* al menos una operación o declaración explícita de jornada sin ventas;
* medios de pago configurados;
* actor identificado;
* datos necesarios para calcular efectivo esperado.

### Fuentes

Requerida en MVP:

* `manual_capture` o `lumo_device_sync`.

Opcionales:

* `voucher_capture`;
* `terminal_integration`;
* `bank_or_acquirer_feed`;
* `ecommerce_feed`;
* otras fuentes declaradas.

### Gates

* no existe excepción crítica abierta;
* toda venta conocida tiene estado de pago permitido;
* no existe diferencia de pagos bloqueante sin resolución o aceptación válida;
* no existen operaciones críticas pendientes de sincronización;
* el cálculo de efectivo esperado terminó correctamente;
* se dispone de evidencia obligatoria;
* las limitaciones de Source Coverage fueron comunicadas.

### Output artifact

`ClosingSnapshot` versionado e inmutable, vinculado a `CashCount`, excepciones, fuentes, evidencia y actor de confirmación.

### Responsabilidad

* Lumo mantiene responsabilidad hasta estado `ready`, `partially_completed`, `failed` o bloqueo explícito.
* El dueño o actor autorizado confirma el cierre.
* Un operador interno puede revisar, pero no confirmar por el comercio salvo política futura explícita.

### Limitaciones

Lumo no garantiza ventas que nunca ingresaron a una fuente cubierta. Tampoco realiza conciliación bancaria, contabilidad oficial, movimiento de dinero ni cumplimiento fiscal en el MVP.

### Medición de costo

Cada ejecución debe registrar costo de modelo, infraestructura, reintentos, segundos de intervención interna y costo total estimado.

## 9.5 Criterios del resultado comprometido

Una jornada puede estar lista para cerrar cuando:

* las ventas conocidas están procesadas;
* cada venta tiene estado de pago válido o excepción explícita;
* la suma de pagos coincide o existe tratamiento autorizado;
* sincronizaciones críticas están resueltas;
* efectivo esperado está calculado;
* excepciones críticas están resueltas;
* excepciones no críticas están resueltas o aceptadas;
* existe evidencia y auditoría suficiente;
* Source Coverage y sus limitaciones están disponibles.

## 9.6 Service commitment inicial

Durante el MVP, Lumo compromete:

* mantener el estado de la jornada;
* iniciar el workflow con la primera señal;
* perseguir pendientes relevantes;
* preparar el cierre con la información disponible;
* mostrar toda inconsistencia conocida;
* no declarar completitud falsa;
* conservar trazabilidad y memoria factual;
* recuperar operaciones fallidas cuando sea posible;
* explicar cuando el outcome es parcial, bloqueado o fallido.

No compromete todavía:

* conciliación bancaria completa;
* exactitud sobre ventas fuera de fuentes conocidas;
* contabilidad oficial;
* depósitos o movimientos de dinero;
* cumplimiento fiscal;
* decisiones financieras irreversibles.

## 9.7 Cobertura del resultado

Lumo distingue:

### Recorded Operations Completeness

Estado de todas las operaciones registradas o recibidas por Lumo.

### Source Coverage

Qué fuentes relevantes del comercio están conectadas, declaradas o capturadas, con periodo, salud y limitaciones.

### Outcome Completion

Cumplimiento del Outcome Contract y sus gates.

### Progress Score

Indicador experimental y explicativo. Nunca sustituye los tres conceptos anteriores.

Mensaje obligatorio cuando la cobertura no es total:

> “Todas las operaciones registradas en Lumo están organizadas. Lumo no puede verificar operaciones realizadas fuera de las fuentes conectadas.”

## 9.8 Taxonomía de outcome incompleto o fallido

Reason codes mínimos:

```text
incomplete_missing_input
incomplete_source_gap
blocked_by_business
blocked_by_review
blocked_by_external_source
blocked_by_policy
failed_technical
failed_validation
failed_evidence
failed_recovery
cancelled_by_business
```

La experiencia debe mostrar:

* qué se completó;
* qué no se completó;
* el reason code traducido a lenguaje natural;
* responsable actual;
* siguiente acción;
* si habrá reintento;
* si existe resultado parcial.

## 9.9 Service Blueprint

### Capa visible para el comercio

* captura de señales;
* estado narrativo;
* pendientes;
* excepciones;
* Next Best Action;
* outcome preparado;
* evidencia y limitaciones;
* confirmación.

### Operación automatizada

* orquestación;
* agentes;
* workflow engine;
* reglas;
* herramientas determinísticas;
* validaciones;
* memoria;
* cobertura y lineage.

### Operación humana

* revisión de casos;
* recuperación;
* soporte;
* doble control;
* escalamiento;
* clasificación para aprendizaje.

### Infraestructura

* fuentes;
* eventos;
* permisos;
* auditoría;
* observabilidad;
* costos;
* evaluación de modelos.

## 9.10 Inicio y fin de responsabilidad

La responsabilidad de Lumo inicia cuando un Outcome Contract recibe un trigger válido y los inputs mínimos disponibles. Termina cuando:

* el outcome se completa;
* se completa con excepciones aceptadas;
* se entrega parcialmente con limitaciones explícitas;
* se cancela;
* se declara fallido con reason code y responsable;
* queda bloqueado por una dependencia fuera del control de Lumo.

Lumo no debe dejar workflows “olvidados” sin estado ni responsable.

## 9.11 Operación asistida

Durante el piloto, un operador interno puede intervenir cuando:

* una inconsistencia no tiene resolución automatizada;
* una falla requiere recuperación;
* se necesita verificar calidad;
* una fuente o documento no puede interpretarse;
* existe un caso de aprendizaje aprobado.

Toda intervención requiere:

* consentimiento;
* acceso mínimo;
* ReviewTask;
* motivo y evidencia;
* actor identificado;
* tiempo y costo medidos;
* decisión registrada;
* aprendizaje reutilizable;
* distinción visible interna entre humano, regla y modelo.

## 9.12 Modelo de trabajo absorbido

Modos:

```text
manual_by_business
assisted_by_lumo
prepared_by_lumo
executed_with_confirmation
executed_and_reversible
executed_under_policy
reviewed_by_lumo_operator
fully_automated
```

Cada tarea relevante debe registrar su modo. La evolución hacia un modo superior requiere evidencia de calidad, seguridad y menor costo.

# 10. Estados y transiciones

## 10.1 Estados de OperationalDay

```text
not_started
open
in_progress
waiting_for_information
ready_to_close
closed
closed_with_exceptions
reopened
failed
```

### Transiciones principales

* `not_started → open`: primera operación o apertura explícita.
* `open → in_progress`: existe actividad registrada.
* `in_progress → waiting_for_information`: existe información necesaria pendiente.
* `in_progress → ready_to_close`: se cumplen criterios de preparación.
* `ready_to_close → closed`: usuario confirma sin excepciones abiertas.
* `ready_to_close → closed_with_exceptions`: usuario autorizado acepta excepciones no críticas.
* `closed|closed_with_exceptions → reopened`: usuario autorizado reabre con motivo.
* cualquier estado activo → `failed`: el workflow no puede continuar y requiere recuperación.

## 10.2 WorkItem

Representa trabajo pendiente.

Estados:

```text
open
assigned
in_progress
waiting
resolved
dismissed
expired
failed
```

Cada work item debe tener:

* tipo;
* origen;
* prioridad;
* responsable;
* fecha de creación;
* fecha límite cuando aplique;
* resolución;
* efecto sobre el outcome.

## 10.3 OperationalException

Representa una condición que requiere decisión, información o recuperación.

Estados:

```text
open
acknowledged
in_review
resolved
accepted
ignored
expired
reopened
```

`accepted` significa que el usuario reconoce la excepción y permite continuar. No significa que la inconsistencia desapareció.

## 10.4 ReviewTask

Representa la revisión humana interna o especializada.

Estados:

```text
queued
assigned
in_review
waiting_for_business
completed
cancelled
failed
```

# 11. Modelo de autonomía y políticas

## 11.1 Modos por tarea

* `suggest_only`
* `prepare_and_confirm`
* `execute_and_undo`
* `execute_under_policy`
* `prohibited`

## 11.2 Evaluación de política

Antes de ejecutar, Lumo debe evaluar:

* tipo de tarea;
* riesgo;
* monto;
* actor;
* evidencia;
* reversibilidad;
* confianza;
* estado de la jornada;
* política del comercio.

## 11.3 Acciones restringidas en el MVP

Siempre requieren autorización o están prohibidas:

* cambiar montos históricos relevantes;
* cerrar diferencias de efectivo sin motivo;
* eliminar evidencia;
* mover dinero;
* generar obligaciones fiscales;
* comprometer compras;
* reabrir una jornada sin rol autorizado;
* aceptar excepciones críticas automáticamente.

## 11.4 Ciclo de aprendizaje y Automation Candidate

Una resolución repetida no se convierte automáticamente en autonomía. El ciclo requerido es:

```text
Excepción detectada
→ revisión y resolución
→ memoria de resolución
→ patrón repetido
→ AutomationCandidate
→ simulación
→ evaluación
→ aprobación
→ ejecución supervisada
→ ejecución reversible
→ ejecución bajo política
```

Cada candidato debe incluir muestra, confianza, riesgo, evidencia requerida, resultados de simulación, aprobador y modo de autonomía.

## 11.5 Acciones candidatas a ejecución automática

Solo cuando sean reversibles y de bajo riesgo:

* clasificar recordatorios;
* actualizar estados internos;
* agrupar pendientes;
* deduplicar alertas;
* cerrar work items derivados de evidencia determinística;
* asignar una excepción según reglas.

---

# Parte III — Experiencia de producto

# 12. Arquitectura de experiencia

## 12.1 Lumo como interfaz operativa

Lumo es la identidad y el control plane de la operación. No es un chatbot flotante.

Debe:

* conocer el estado del negocio;
* iniciar conversaciones cuando importa;
* mostrar resultados estructurados;
* mantener continuidad;
* permitir corrección y deshacer;
* distinguir hechos, cálculos e inferencias;
* explicar por qué algo requiere atención.

## 12.2 Business Stream

El Business Stream combina:

* estado narrativo;
* composer persistente;
* acciones recientes;
* resultados preparados;
* excepciones;
* recomendaciones;
* memoria relevante;
* accesos contextuales.

Debe responder:

1. ¿Qué está ocurriendo ahora?
2. ¿Qué necesita atención?
3. ¿Qué puede hacer o decir el usuario a continuación?

## 12.3 Navegación principal

```text
Inicio
Hoy
Memoria
Negocio
```

### Inicio

Estado narrativo y prioridades actuales.

### Hoy

Progreso de la jornada, ventas, pagos, excepciones y cierre.

### Memoria

Hechos, decisiones, observaciones, inferencias y evidencia.

### Negocio

Configuración estructurada secundaria: medios de pago, referencias, usuarios, políticas y preferencias.

## 12.4 Composer persistente

Disponible en Inicio, Hoy y Memoria con:

* texto;
* voz;
* cámara;
* sugerencias contextuales;
* estado de interpretación;
* posibilidad de cancelar.

Placeholder recomendado:

> “Dile algo a tu negocio…”

## 12.5 Tarjetas generativas

Las intenciones y resultados se representan mediante tarjetas específicas:

* venta preparada;
* venta registrada;
* corrección propuesta;
* excepción;
* cierre preparado;
* diferencia de caja;
* memoria detectada;
* recomendación;
* operación fallida.

Una respuesta de texto no debe sustituir una tarjeta cuando existe una acción estructurada.

## 12.6 Superficies por horizonte

### MVP Build A — Operator Foundation

* **Inicio / Business Stream:** estado, siguiente acción, pendientes, composer y tarjetas de venta/cierre.
* **Hoy:** jornada, ventas, pagos, efectivo, cobertura, excepciones y estado del outcome.
* **Configuración mínima:** negocio, moneda, medios de pago y usuarios básicos.
* **Memoria embebida:** timeline factual y continuidad contextual, sin requerir todavía una superficie completa.

### MVP Build B — Reliable Daily Close

Agrega:

* timeline navegable;
* historial de cierres;
* evidencia;
* correcciones y reapertura;
* excepciones agrupadas;
* estado de sincronización;
* memoria contextual.

### Product Horizon 1 — Managed Operations

Agrega plenamente:

* Memoria;
* review operations;
* preferencias;
* políticas;
* automatizaciones candidatas;
* proactividad longitudinal.

## 12.7 Regla anti-sobreconstrucción

La arquitectura objetivo continúa siendo Inicio, Hoy, Memoria y Negocio. No es obligatorio implementar cuatro superficies completas antes de validar el MVP.

## 12.8 Criterios de percepción anti-POS

En pruebas, la experiencia debe llevar al usuario a expresar conceptos como:

* “Lumo organiza el día”;
* “Lumo me dice qué falta”;
* “Lumo prepara el cierre”;
* “solo reviso lo importante”;
* “recuerda lo que ocurrió”.

Si predomina “es una caja”, “es un POS por chat” o “solo registra ventas”, debe revisarse Minimum Operator Behavior y la narrativa.

# 13. Captura progresiva de ventas

## 13.1 Nivel 1 — Solo monto

> “385.”

Datos mínimos:

* monto declarado;
* fecha y hora;
* negocio;
* actor o dispositivo;
* estado.

El medio de pago queda pendiente si la política lo permite.

## 13.2 Nivel 2 — Monto y pago

> “385 tarjeta.”

Es la captura recomendada para el MVP.

## 13.3 Nivel 3 — Categoría

> “240 efectivo, verduras.”

Permite análisis general sin catálogo.

## 13.4 Nivel 4 — Conceptos libres

> “Cambio de pila y ajuste, 350 efectivo.”

Los conceptos se conservan sin afirmar que son productos formales.

## 13.5 Nivel 5 — Venta híbrida

Combina productos conocidos, conceptos y monto no detallado.

```text
2 × Coca-Cola 600 ml      $44
1 × Papas                 $36
Otros productos           $85
Total                    $165
```

## 13.6 Nivel 6 — Venta estructurada

Productos, cantidades, precios e inventario, cuando el negocio lo utiliza.

## 13.7 Enriquecimiento posterior

Una venta puede recibir después:

* medio de pago;
* autorización;
* categoría;
* conceptos;
* productos;
* cliente;
* nota;
* evidencia.

El enriquecimiento no debe cambiar el total declarado sin una corrección explícita.

# 14. Experiencia de excepciones

## 14.1 Principio

El usuario no debe revisar todas las operaciones para descubrir errores. Lumo debe presentar solo lo que requiere atención.

## 14.2 Tarjeta de excepción

Debe mostrar:

* qué ocurrió;
* por qué importa;
* impacto;
* evidencia;
* resolución recomendada;
* acciones permitidas;
* responsable actual;
* urgencia;
* efecto sobre el cierre.

Ejemplo:

```text
Falta el medio de pago

Venta de $620 · 4:20 PM
No asumiré el método a partir de ventas cercanas.
Esta excepción bloquea el cierre.

[Efectivo] [Tarjeta] [Transferencia] [Dejar pendiente]
```

## 14.3 Agrupación

Lumo puede agrupar excepciones similares, pero debe permitir resolver cada operación de forma individual.

## 14.4 Seguimiento

Los pendientes permanecen activos hasta:

* resolución;
* aceptación explícita;
* descarte autorizado;
* expiración definida;
* fallo y escalamiento.

# 15. Experiencia del cierre

## 15.1 Preparación proactiva

El cierre debe prepararse sin que el usuario construya un reporte.

## 15.2 Estado previo

```text
Tu operación está 94 % completa.

Registré 38 ventas por $8,250.
36 pagos están completos.
Quedan dos excepciones antes del cierre.

[Resolver excepciones] [Ver jornada]
```

## 15.3 Cierre listo

```text
Tu jornada está lista para revisar.

Ventas: $8,250
Operaciones: 47
Efectivo esperado: $3,150
Tarjeta: $4,400
Transferencia: $700
Pendientes: 0

¿Cuánto efectivo contaste?
```

## 15.4 Diferencia de efectivo

Si el usuario declara $3,100:

```text
Encontré una diferencia de $50.

Esperado: $3,150
Contado: $3,100
Diferencia: -$50

[Agregar motivo] [Corregir conteo] [Cerrar con diferencia]
```

## 15.5 Cierre con excepciones

Solo se permite cuando:

* no existen excepciones críticas abiertas;
* el actor tiene permiso;
* cada excepción aceptada tiene motivo;
* el resultado se marca `closed_with_exceptions`;
* la excepción permanece visible en auditoría y reportes.

## 15.6 Reapertura

La reapertura requiere:

* rol autorizado;
* motivo obligatorio;
* conservación del cierre original;
* nueva versión del resultado;
* recalcular métricas y resúmenes afectados;
* auditoría del antes y después;
* notificación al dueño cuando la realiza otro actor.

# 16. Memoria operacional desde el primer día

## 16.1 Propósito

La memoria permite que Lumo mantenga continuidad, evite preguntas repetidas, relacione decisiones y convierta la operación diaria en una representación acumulativa del negocio.

La memoria no es el historial del chat. Debe vincular declaraciones con eventos, fuentes, actores, evidencia, vigencia y confianza.

## 16.2 Capas incrementales

### MVP Build A — Event Memory

Debe conservar:

* ventas y pagos;
* correcciones y cancelaciones;
* excepciones;
* responsables;
* CashCount;
* ClosingSnapshot;
* motivos;
* evidencia;
* acciones anteriores;
* pendientes que cruzan jornadas;
* estado y reason codes de outcomes.

### MVP Build B — Operational Context Memory

Agrega:

* preferencias confirmadas;
* políticas utilizadas;
* métodos frecuentes;
* comportamiento de cierre;
* excepciones recurrentes;
* referencias y conceptos repetidos;
* historial de decisiones;
* relaciones entre jornadas.

### Product Horizon 1 — Resolution and Intelligence Memory

Agrega:

* patrones;
* correlaciones;
* memoria de resolución;
* candidatos de política;
* AutomationCandidates;
* cambios de comportamiento;
* relaciones entre venta, precio, inventario y compra.

## 16.3 Tipos semánticos

* hecho;
* evento;
* observación;
* cálculo;
* inferencia;
* decisión;
* resolución;
* preferencia;
* política.

Cada elemento debe mantener su tipo. Una inferencia no se promociona a hecho sin confirmación o evidencia determinística.

## 16.4 Propiedades obligatorias

Toda memoria relevante debe indicar:

* declaración;
* tipo;
* fuente;
* evidencia;
* confianza;
* vigencia;
* actor que confirmó;
* estado;
* entidades relacionadas;
* posibilidad de corregir, invalidar u olvidar;
* versión de regla o modelo cuando aplique.

## 16.5 Memoria de resolución

Debe capturar:

* excepción original;
* contexto;
* evidencia consultada;
* decisión;
* actor;
* resultado;
* recurrencia;
* aptitud para convertirse en regla;
* riesgos de reutilización.

## 16.6 Correlación

Lumo puede relacionar:

```text
Cambio de precio
    ↓
Cambio en volumen vendido
    ↓
Cambio en ticket promedio
    ↓
Necesidad de reposición
    ↓
Decisión del dueño
```

No debe presentar causalidad cuando solo existe correlación.

## 16.7 Privacidad y control

El comercio debe poder consultar qué recuerda Lumo, ver evidencia, corregir, invalidar u olvidar información cuando sea legal y operacionalmente posible. Los artefactos de auditoría obligatoria no se eliminan silenciosamente; se revocan o corrigen con trazabilidad.

# 17. Proactividad, Next Best Action, alertas e insights

## 17.1 Tipos de salida proactiva

| Tipo | Propósito |
|---|---|
| Excepción | Algo compromete un workflow. |
| Alerta | Algo requiere atención próxima. |
| Insight | Existe un cambio o patrón relevante. |
| Recomendación | Existe una acción sugerida. |
| WorkItem | Existe trabajo con responsable. |
| Outcome | Existe un resultado comprometido. |
| NextBestAction | Existe una acción prioritaria para avanzar el outcome. |

## 17.2 Next Best Action

Cada Next Best Action debe incluir:

* outcome asociado;
* acción;
* razón;
* resultado esperado;
* prioridad y urgencia;
* evidencia;
* actor y permiso requeridos;
* riesgo;
* reversibilidad;
* expiración;
* estado.

## 17.3 Jerarquía de prioridad

```text
Seguridad y privacidad
→ gates bloqueantes
→ excepciones críticas
→ acciones necesarias para outcome
→ decisiones de alto impacto
→ recomendaciones
→ insights informativos
```

Lumo no debe mostrar una recomendación comercial si existe una excepción crítica que impide completar el outcome actual.

## 17.4 Reglas de proactividad

Toda salida debe tener:

* evidencia;
* confianza mínima;
* relevancia;
* acción posible;
* frecuencia controlada;
* deduplicación;
* expiración;
* opción de ignorar o silenciar;
* vinculación con un outcome o memoria.

## 17.5 Proactividad del MVP

Obligatoria:

* pago faltante;
* diferencia de pagos;
* posible duplicado cuando entre al build;
* diferencia de efectivo;
* jornada lista para cerrar;
* falla o sincronización pendiente;
* solicitud contextual de CashCount;
* aviso de limitación de cobertura;
* siguiente acción para completar el cierre.

Condicionada:

* autorización pendiente;
* cambio relevante de ventas;
* patrón horario;
* concepto recurrente;
* reposición sugerida;
* compra habitual próxima.

## 17.6 Límite de proactividad

Lumo debe optimizar relevancia, no volumen de mensajes. Una señal sin acción, evidencia o impacto suficiente debe permanecer disponible bajo consulta y no interrumpir al usuario.

# Parte IV — Especificación del MVP

# 18. Estrategia incremental del MVP y horizontes

La implementación comienza por el MVP, pero el modelo de datos y la arquitectura deben preservar el producto completo.

## 18.1 MVP Build A — Operator Foundation

**Objetivo:** demostrar que Daily Close importa y que Lumo mantiene responsabilidad sobre la jornada, no solamente captura transacciones.

Incluye:

* creación de negocio y configuración mínima;
* venta por monto y medio de pago;
* medio de pago pendiente;
* jornada por fecha;
* ventas totales y distribución de pagos;
* detección de pago faltante;
* estado persistente del workflow;
* WorkItems básicos;
* Next Best Action para avanzar el cierre;
* recordatorio contextual de pendientes;
* efectivo esperado;
* CashCount;
* diferencia de caja;
* cierre preparado proactivamente;
* confirmación asistida;
* Event Memory;
* audit trail básico;
* idempotencia y reintento seguro;
* Recorded Operations Completeness;
* Source Coverage y limitaciones;
* Outcome Contract `daily_close_ready`;
* reason codes de bloqueo o falla;
* instrumentación de costo y trabajo absorbido;
* registro del stage gate.

No requiere todavía:

* motor general de políticas;
* offline avanzado;
* catálogo;
* memoria inferida;
* review queue completa;
* automatización de excepciones complejas;
* múltiples fuentes externas.

### Criterio de salida

El comercio entiende el outcome, Lumo demuestra Minimum Operator Behavior, el esfuerzo de cierre disminuye y existe señal de delegación y continuidad.

## 18.2 MVP Build B — Reliable Daily Close

**Objetivo:** convertir el cierre en un workflow confiable, repetible y apto para piloto ampliado.

Incluye además:

* pagos mixtos;
* correcciones y cancelaciones;
* venta híbrida y enriquecimiento posterior cuando agreguen valor;
* taxonomía core de excepciones;
* gates formales completos;
* cierre con excepciones permitidas;
* ClosingSnapshot versionado;
* reapertura;
* datos tardíos;
* permisos atómicos;
* Operational Context Memory;
* sincronización visible;
* recuperación sin duplicados;
* escenarios de falla y conflicto;
* historial de cierres y evidencia;
* priorización de excepciones;
* baseline y medición de work absorption.

### Criterio de entrada

MVP Build A supera el stage gate inicial del wedge.

### Criterio de salida

El workflow alcanza confiabilidad suficiente para ejecutarse recurrentemente, con mínima supervisión directa del equipo fundador y una señal defendible de intención de pago.

## 18.3 Product Horizon 1 — Managed Operations

**Objetivo:** validar completamente la tesis Service-as-Software y la ruta hacia mejores unit economics.

Incluye:

* review queue;
* operación asistida auditada;
* medición detallada de intervención humana;
* Resolution and Intelligence Memory;
* políticas de autonomía por tarea;
* escalamiento;
* proactividad longitudinal;
* AutomationCandidates;
* simulación y promoción de reglas;
* resumen semanal condicionado;
* automatización de excepciones repetidas de bajo riesgo;
* playbooks por segmento;
* medición de gross margin por outcome.

### Criterio de entrada

Reliable Daily Close demuestra uso recurrente, confiabilidad, delegación y señal de pago.

### Criterio de salida

La intervención humana disminuye, los patrones repetidos se convierten en producto y existe una ruta creíble hacia margen positivo.

## 18.4 Product Horizons posteriores

* Weekly Business Review;
* Payment Reconciliation;
* Inventory & Replenishment;
* Purchasing & Supplier Operations;
* External Review Package;
* Financial Operations.

## 18.5 Regla de alcance

El MVP no necesita implementar el producto completo. El producto completo sí debe permanecer visible en contratos, entidades condicionadas y principios de expansión.

# 19. Alcance condicionado

Una capacidad entra únicamente cuando elimina una excepción frecuente, mejora cobertura del cierre, reduce intervención, aumenta intención de pago o valida un diferenciador crítico.

* voz;
* fotografía de vouchers;
* autorización de tarjeta;
* productos frecuentes;
* catálogo emergente;
* inventario opcional;
* resumen semanal;
* paquete compartible;
* notificaciones push;
* múltiples usuarios avanzados;
* captura offline completa;
* resolución avanzada de conflictos.

# 20. Fuera del MVP

* facturación fiscal;
* contabilidad oficial;
* declaraciones tributarias;
* movimiento de dinero;
* conciliación bancaria universal;
* compras automáticas;
* integración universal con terminales;
* multi-sucursal avanzada;
* nómina;
* CRM completo;
* ecommerce;
* marketplace;
* pronósticos avanzados;
* autonomía sin políticas;
* asesoría regulada.

# 21. Reglas de negocio

## 21.1 Validez de una venta

Una venta es válida sin productos asociados cuando contiene:

* negocio;
* total declarado;
* fecha y hora;
* actor o dispositivo;
* estado.

## 21.2 Total declarado y detalle

Se almacenan separadamente:

* `declared_total`;
* `identified_total`;
* `unallocated_amount`.

Regla:

```text
unallocated_amount = declared_total - identified_total
```

Una diferencia no bloquea automáticamente el registro. Debe mostrarse y clasificarse.

## 21.3 Pago

Una venta puede tener:

* un pago;
* múltiples pagos;
* medio pendiente;
* pago parcial;
* pago mayor al total, solo como excepción explícita.

La suma de pagos se compara con el total declarado.

## 21.4 Medio de pago pendiente

Puede permitirse durante la jornada según política, pero bloquea `ready_to_close` salvo aceptación explícita autorizada.

## 21.5 Autorización

La autorización es configurable por método de pago. Su ausencia puede ser:

* bloqueante;
* no bloqueante con advertencia;
* no aplicable.

## 21.6 Posible duplicado

Debe evaluarse mediante reglas como:

* mismo monto;
* proximidad temporal;
* mismo medio;
* mismo actor;
* misma referencia.

Lumo no elimina automáticamente. Crea una excepción.

## 21.7 Cancelación

Cancelar una venta debe:

* conservar el registro original;
* cambiar estado;
* revertir efectos asociados cuando corresponda;
* mantener motivo;
* generar evento;
* reevaluar jornada y cierre.

## 21.8 Corrección

Toda corrección debe mantener:

* estado anterior;
* estado nuevo;
* actor;
* motivo;
* impacto;
* fecha;
* posibilidad de reversión.

## 21.9 Cierre

`ready_to_close` requiere:

* cero excepciones críticas abiertas;
* ventas y pagos procesados según cobertura conocida;
* sincronizaciones críticas completadas;
* efectivo esperado calculado;
* criterios de evidencia cumplidos.

## 21.10 Reapertura

La reapertura crea una nueva versión lógica del cierre. No sobrescribe silenciosamente el resultado anterior.

## 21.11 Datos tardíos

Cuando llega una operación después del cierre:

* se identifica como tardía;
* se vincula con la fecha operativa correcta;
* se crea excepción;
* se propone reabrir o trasladar según política;
* no modifica un cierre confirmado sin autorización.

## 21.12 Responsabilidad del outcome

Todo outcome activo debe tener:

* estado;
* owner actual;
* reason code cuando no progresa;
* Next Best Action;
* ventana o expectativa temporal;
* evidencia;
* costo acumulado;
* posibilidad de cancelación o escalamiento.

## 21.13 Resultado parcial

Lumo puede entregar un resultado parcial cuando:

* el contrato lo permite;
* los componentes completados conservan utilidad;
* las limitaciones se muestran;
* no se oculta una excepción crítica;
* el resultado se marca `partially_completed`.

## 21.14 Memoria entre jornadas

Pendientes, decisiones, cierres y excepciones relevantes deben persistir entre fechas. Abrir una jornada nueva no elimina obligaciones anteriores.

## 21.15 Offline y sincronización

El MVP debe soportar, como mínimo:

* identificador local único;
* cola de operaciones;
* estado de sincronización;
* reintentos seguros;
* idempotencia;
* detección de conflicto;
* indicador visible;
* bloqueo de cierre cuando existen operaciones críticas no sincronizadas.

# 22. Taxonomía inicial de excepciones

| Tipo | Trigger | Severidad inicial | ¿Bloquea cierre? | Resoluciones |
|---|---|---:|---|---|
| `payment_missing` | Venta sin medio de pago | Alta | Sí | Asignar método, aceptar bajo política |
| `payment_mismatch` | Suma de pagos distinta al total | Alta | Sí | Corregir pago, corregir total, aceptar diferencia |
| `authorization_missing` | Pago que requiere autorización | Media configurable | Configurable | Agregar código, aceptar, marcar no aplicable |
| `possible_duplicate` | Regla de similitud supera umbral | Alta | Sí | Confirmar ambas, cancelar una, revisar |
| `cash_difference` | Contado distinto al esperado | Alta | No necesariamente | Corregir conteo, agregar motivo, cerrar con diferencia |
| `sync_pending` | Operación local no sincronizada | Alta | Sí | Reintentar, revisar conflicto, recuperar |
| `sale_cancel_inconsistent` | Cancelación con efecto no revertido | Crítica | Sí | Recuperación obligatoria |
| `ambiguous_concept` | Interpretación insuficiente | Baja | No | Corregir, mantener texto, descartar detalle |
| `document_unreadable` | Captura no interpretable | Media | Según dependencia | Reintentar, revisión humana |
| `inventory_inconsistency` | Stock incompatible | Media | No para Daily Close | Ajustar, dejar pendiente |
| `workflow_failure` | Tarea técnica fallida | Crítica | Sí | Reintentar, revisión, recuperación |

Cada excepción debe configurar:

* severidad;
* impacto financiero;
* responsable inicial;
* evidencia requerida;
* acciones permitidas;
* política de aceptación;
* tiempo de escalamiento;
* efecto en completitud.

# 23. Definición de estado, gates y progreso

## 23.1 Principio

La completitud formal se determina mediante gates. El score de progreso es informativo y experimental.

```text
Estado formal > gates bloqueantes > score de progreso
```

El modelo puede explicar el resultado, pero no definirlo libremente.

## 23.2 Gates obligatorios para `ready_to_close`

Una jornada no puede pasar a `ready_to_close` cuando existe cualquiera de estas condiciones:

* excepción crítica abierta;
* venta registrada sin estado de pago permitido;
* diferencia de pagos no resuelta ni aceptada por política;
* operación crítica pendiente de sincronización;
* `workflow_failure` sin recuperación;
* evidencia obligatoria ausente;
* cálculo de efectivo esperado fallido.

Los gates son normativos y tienen prioridad sobre el score.

## 23.3 Recorded Operations Completeness

Mide el estado de las operaciones conocidas por Lumo:

* capturadas;
* procesadas;
* asociadas a jornada;
* con pago válido o excepción explícita;
* sincronizadas;
* auditadas.

No mide ventas que nunca ingresaron a una fuente controlada por Lumo.

## 23.4 Source Coverage

Representa qué fuentes relevantes están cubiertas:

```text
manual_capture
lumo_device_sync
voucher_capture
terminal_integration
bank_or_acquirer_feed
ecommerce_feed
other_declared_source
```

Cada fuente debe indicar:

* estado de conexión;
* periodo cubierto;
* última actualización;
* confiabilidad;
* limitaciones conocidas.

## 23.5 Score experimental de progreso

Durante el piloto puede utilizarse un score explicativo con dimensiones como:

```text
Sales Capture Processing
Payment Coverage
Exception Resolution
Synchronization & Evidence
Cash Count Status
```

Los pesos no son una regla estable. Deben almacenarse como configuración experimental, versionarse y evaluarse con datos del piloto.

## 23.6 Reglas de seguridad

* Una excepción crítica abierta impide `ready_to_close`, aunque el score sea alto.
* Una dimensión no aplicable se excluye del score.
* La interfaz debe explicar qué falta en términos concretos.
* El score nunca sustituye el estado formal.
* La comunicación debe distinguir cobertura de operaciones registradas y cobertura de fuentes.

# 24. Roles, permisos y aceptación de excepciones

## 24.1 Permisos atómicos

```text
business.configure
user.manage
sale.create
sale.enrich
sale.correct_payment
sale.correct_amount
sale.cancel
exception.view
exception.resolve
exception.accept
closing.prepare
closing.submit_cash_count
closing.confirm
closing.reopen
memory.view
memory.correct
policy.update
review.execute
review.view_sensitive_evidence
```

Los roles son conjuntos configurados de permisos. El backend debe autorizar por permiso, no únicamente por nombre de rol.

## 24.2 Matriz inicial

| Permiso | Dueño | Encargado | Colaborador | Operador interno |
|---|---:|---:|---:|---:|
| `sale.create` | Sí | Sí | Sí | No por defecto |
| `sale.enrich` | Sí | Sí | Sí limitado | Solo con tarea |
| `sale.correct_payment` | Sí | Sí | Configurable | Solo con tarea |
| `sale.correct_amount` | Sí | Configurable | No | Solo con doble control |
| `sale.cancel` | Sí | Configurable | No | No por defecto |
| `exception.resolve` | Sí | Sí | Según tipo | Según tarea |
| `exception.accept` | Sí | Configurable | No | No |
| `closing.submit_cash_count` | Sí | Sí | Configurable | No |
| `closing.confirm` | Sí | Configurable | No | No |
| `closing.reopen` | Sí | Configurable | No | No |
| `policy.update` | Sí | No | No | No |
| `review.execute` | No | No | No | Con consentimiento |

## 24.3 Política de aceptación de excepciones

Cada tipo de excepción debe declarar:

* roles autorizados;
* motivo obligatorio o no;
* evidencia mínima;
* vigencia de la aceptación;
* si bloquea el cierre;
* impacto en métricas;
* visibilidad en resumen diario y semanal;
* condiciones de reapertura automática;
* efecto de nueva evidencia.

### Diferencia de estados

* `resolved`: la inconsistencia fue corregida o dejó de existir.
* `accepted`: la inconsistencia permanece, pero un actor autorizado acepta continuar.
* `ignored`: la señal se descarta como no relevante; no debe utilizarse para ocultar una inconsistencia financiera válida.
* `dismissed`: un work item deja de requerir acción por una razón documentada.

Una excepción crítica no puede ser aceptada automáticamente en el MVP.

# 25. Requisitos funcionales

## Onboarding y configuración

**RF-001 — Crear negocio.** El usuario debe crear un negocio mediante onboarding conversacional. `MVP Build A`

**RF-002 — Configurar moneda y zona horaria.** `MVP Build A`

**RF-003 — Configurar medios de pago.** `MVP Build A`

**RF-004 — Configurar política de confirmación.** `MVP Build B`

**RF-005 — Comenzar sin catálogo.** El onboarding no debe exigir productos. `MVP Build A`

**RF-006 — Registrar consentimiento para operación asistida.** `Product Horizon 1`

**RF-007 — Administrar roles básicos.** `MVP Build B`

## Ventas

**RF-008 — Registrar venta por monto.** `MVP Build A`

**RF-009 — Registrar medio de pago o dejarlo pendiente según política.** `MVP Build A`

**RF-010 — Registrar pagos mixtos.** `MVP Build B`

**RF-011 — Registrar categoría opcional.** `MVP Build B / Conditional`

**RF-012 — Conservar conceptos libres.** `MVP Build B / Conditional`

**RF-013 — Registrar venta híbrida.** `MVP Build B / Conditional`

**RF-014 — Conservar total declarado separado del detalle.** `MVP Build A`

**RF-015 — Calcular monto no detallado.** `MVP Build B`

**RF-016 — Enriquecer una venta posteriormente.** `MVP Build B / Conditional`

**RF-017 — Corregir conversacionalmente.** `MVP Build B`

**RF-018 — Cancelar con auditoría y reversión.** `MVP Build B`

**RF-019 — Deshacer acciones reversibles.** `MVP Build B`

**RF-020 — Prevenir duplicados mediante idempotencia.** `MVP Build A`

## Jornada y pagos

**RF-021 — Asociar toda operación a una jornada.** `MVP Build A`

**RF-022 — Mantener estados de jornada.** `MVP Build A`

**RF-023 — Calcular ventas totales y número de operaciones.** `MVP Build A`

**RF-024 — Calcular distribución de pagos.** `MVP Build A`

**RF-025 — Calcular cobertura de pagos.** `MVP Build B`

**RF-026 — Calcular completitud determinística.** `MVP Build B`

**RF-027 — Explicar completitud.** `MVP Build B`

**RF-028 — Mantener pendientes hasta resolución.** `MVP Build A`

## Excepciones

**RF-029 — Detectar excepciones definidas.** `MVP Build A`

**RF-030 — Asignar responsable.** `MVP Build A`

**RF-031 — Mostrar evidencia e impacto.** `MVP Build B`

**RF-032 — Proponer resolución.** `MVP Build B`

**RF-033 — Permitir aceptar excepciones no críticas según política.** `MVP Build B`

**RF-034 — Escalar por severidad o antigüedad.** `Product Horizon 1`

**RF-035 — Reabrir una excepción resuelta cuando cambie la evidencia.** `Product Horizon 1`

## Cierre

**RF-036 — Preparar cierre automáticamente.** `MVP Build A`

**RF-037 — Calcular efectivo esperado.** `MVP Build A`

**RF-038 — Solicitar efectivo contado.** `MVP Build A`

**RF-039 — Detectar diferencia de efectivo.** `MVP Build A`

**RF-040 — Registrar motivo de diferencia.** `MVP Build B`

**RF-041 — Confirmar cierre.** `MVP Build A`

**RF-042 — Cerrar con excepciones permitidas.** `MVP Build B`

**RF-043 — Impedir cierre con excepción crítica.** `MVP Build B`

**RF-044 — Reabrir con permisos, motivo y versionado.** `MVP Build B`

**RF-045 — Generar resumen diario.** `MVP Build A`

## Memoria y proactividad

**RF-046 — Crear memoria factual a partir de eventos confirmados.** `MVP Build A`

**RF-047 — Registrar memoria de resolución.** `Product Horizon 1`

**RF-048 — Diferenciar hecho e inferencia.** `MVP Build B`

**RF-049 — Corregir u olvidar memoria.** `Conditional`

**RF-050 — Informar jornada lista para cerrar.** `MVP Build A`

**RF-051 — Generar alertas accionables con control de frecuencia.** `Product Horizon 1`

**RF-052 — Generar resumen semanal.** `Conditional`

## Operación asistida y auditoría

**RF-053 — Crear review task con contexto.** `Product Horizon 1`

**RF-054 — Registrar intervención humana.** `Product Horizon 1`

**RF-055 — Medir duración y motivo.** `Product Horizon 1`

**RF-056 — Distinguir actor usuario, regla, modelo y operador.** `MVP Build A`

**RF-057 — Mantener evidencia y audit trail.** `MVP Build A`

**RF-058 — Fallar explícitamente.** `MVP Build A`

**RF-059 — Conservar intención para reintento.** `MVP Build A`

**RF-060 — Recuperar operaciones sin duplicar.** `MVP Build A`

## Captura e integraciones

**RF-061 — Cola local y sincronización.** `MVP Build B`

**RF-062 — Mostrar estado de sincronización.** `MVP Build B`

**RF-063 — Captura por voz.** `Conditional`

**RF-064 — Captura de voucher por cámara.** `Conditional`

**RF-065 — Importar fuentes externas con procedencia.** `Future`

## Cobertura, cierre y permisos

**RF-066 — Distinguir completitud registrada y cobertura de fuentes.** La interfaz y el modelo deben comunicar ambos conceptos por separado. `MVP Build A`

**RF-067 — Evaluar gates formales antes de `ready_to_close`.** `MVP Build A`

**RF-068 — Generar `ClosingSnapshot`.** Cada cierre confirmado debe crear una versión inmutable. `MVP Build B`

**RF-069 — Registrar `CashCount`.** El conteo debe conservar actor, momento, monto, correcciones y evidencia opcional. `MVP Build A`

**RF-070 — Autorizar mediante permisos atómicos.** `MVP Build B`

**RF-071 — Aplicar política de aceptación por tipo de excepción.** `MVP Build B`

**RF-072 — Versionar configuración del score experimental.** `Product Horizon 1`

**RF-073 — Mostrar limitaciones de Source Coverage.** `MVP Build A`

**RF-074 — Aplicar nivel offline configurado para el piloto.** `MVP Build B`

**RF-075 — Registrar stage gate del wedge y decisión de continuidad.** `MVP Build A`


## Outcome, operator behavior and service

**RF-076 — Mantener Minimum Operator Behavior.** Lumo debe iniciar, mantener y llevar el workflow hasta un outcome, bloqueo o falla explícita; registrar y reportar no son suficientes. `MVP Build A`

**RF-077 — Crear Outcome Contract versionado.** Cada tipo de outcome debe tener contrato con promesa, inputs, fuentes, gates, evidencia, limitaciones y costo. `MVP Build A`

**RF-078 — Ejecutar OutcomeRun.** Cada ejecución debe conservar contrato y versión utilizados, estado, timestamps, owner y resultado. `MVP Build A`

**RF-079 — Entregar resultado parcial.** El sistema debe soportar `partially_completed` solo cuando el contrato lo permita y las limitaciones sean explícitas. `MVP Build B`

**RF-080 — Registrar reason code de outcome.** Todo bloqueo, resultado parcial, falla o cancelación debe registrar un reason code estructurado. `MVP Build A`

**RF-081 — Mantener responsabilidad visible.** Todo outcome y work item activo debe mostrar el actor o sistema responsable actual. `MVP Build A`

**RF-082 — Registrar Service Blueprint Step.** Los pasos críticos deben distinguir experiencia visible, automatización, revisión humana e infraestructura. `Product Horizon 1`

## Trabajo absorbido y economía

**RF-083 — Clasificar modo de ejecución.** Cada tarea relevante debe clasificarse como manual, asistida, preparada, ejecutada con confirmación, reversible, bajo política, revisión interna o automatizada. `MVP Build A`

**RF-084 — Registrar WorkAbsorptionRecord.** El sistema debe medir pasos antes/después, intervención, minutos estimados y nivel de automatización. `MVP Build A`

**RF-085 — Medir costo por outcome.** Cada OutcomeRun debe registrar costo de modelo, infraestructura, reintentos y trabajo humano. `MVP Build A`

## Memoria y continuidad

**RF-086 — Crear Event Memory desde la primera jornada.** Ventas, pagos, correcciones, excepciones, cierres, conteos y outcomes deben alimentar memoria factual. `MVP Build A`

**RF-087 — Mantener memoria entre jornadas.** Pendientes y decisiones relevantes deben persistir hasta resolución, expiración o descarte autorizado. `MVP Build A`

**RF-088 — Crear Operational Context Memory.** El sistema debe conservar preferencias, políticas utilizadas, comportamiento de cierre y patrones confirmados. `MVP Build B`

## Prioridad y aprendizaje

**RF-089 — Generar Next Best Action.** Lumo debe priorizar la acción que más contribuye a completar el outcome, con evidencia, actor, permiso y expiración. `MVP Build A`

**RF-090 — Respetar jerarquía de prioridades.** Gates y excepciones críticas deben preceder recomendaciones e insights. `MVP Build A`

**RF-091 — Crear AutomationCandidate.** Una resolución repetida debe poder convertirse en candidato de automatización sin habilitarse automáticamente. `Product Horizon 1`

**RF-092 — Simular AutomationCandidate.** El sistema debe evaluar candidatos con historial o shadow mode antes de promover autonomía. `Product Horizon 1`

**RF-093 — Versionar reglas y políticas promovidas.** Toda automatización aprobada debe registrar versión, evidencia, aprobador y rollback. `Product Horizon 1`

## Experiencia y posicionamiento

**RF-094 — Implementar Business Stream mínimo por build.** Las superficies deben respetar el alcance incremental definido en la sección 12. `MVP Build A`

**RF-095 — Explicar siguiente acción.** La interfaz debe indicar qué falta, por qué importa y quién debe actuar. `MVP Build A`

**RF-096 — Medir percepción anti-POS.** El piloto debe registrar cómo los usuarios describen Lumo y detectar si se percibe solo como sistema de registro. `MVP Build A`

**RF-097 — Mantener continuidad intención–resultado–memoria.** Una acción debe vincular intención, interpretación, ejecución, efecto, evidencia, memoria y siguiente acción. `MVP Build B`

## Producto completo y expansión

**RF-098 — Registrar Product Outcome Map.** Los outcomes futuros deben declarar promesa, señales, trabajo de Lumo, intervención humana y capacidades reutilizadas. `Strategic Required`

**RF-099 — Evaluar entrada de un nuevo outcome.** El sistema de gobierno del producto debe verificar frecuencia, delegación, evidencia, reutilización y economía antes de comprometer desarrollo. `Strategic Required`

**RF-100 — Mantener entidades condicionadas del producto completo.** Producto, inventario, proveedor, compra y conciliación deben estar modelados como extensiones sin convertirse en dependencia del MVP. `Future Architecture`

# 26. Requisitos no funcionales

## 26.1 Rendimiento

* confirmación de venta menor a 3 segundos después de aprobación;
* actualización de jornada menor a 5 segundos;
* detección de excepción simple menor a 10 segundos;
* cierre preparado menor a 30 segundos para hasta 500 ventas;
* interfaz inicial menor a 2 segundos en condiciones normales.

## 26.2 Confiabilidad

* idempotencia;
* consistencia transaccional;
* reintentos seguros;
* no duplicación;
* versionado de correcciones;
* recuperación de fallos;
* herramientas determinísticas para datos críticos.

## 26.3 Disponibilidad

Meta inicial del piloto: 99 % durante ventanas operativas acordadas. La indisponibilidad del modelo no debe impedir consultar datos registrados ni ejecutar funciones determinísticas disponibles.

## 26.4 Seguridad

* cifrado en tránsito y reposo;
* separación por negocio;
* control de acceso;
* auditoría;
* consentimiento;
* URLs firmadas;
* acceso interno mínimo;
* protección de referencias sensibles.

## 26.5 Privacidad

* no usar datos para entrenar modelos públicos sin consentimiento;
* permitir corregir o eliminar memoria;
* explicar qué se guarda;
* minimizar datos en notificaciones;
* registrar accesos internos.

## 26.6 Observabilidad

Registrar:

* latencia;
* intención;
* herramienta;
* confianza;
* errores;
* excepciones;
* intervenciones;
* acciones deshechas;
* outcomes incompletos;
* costo de IA;
* costo humano por workflow.

## 26.7 Accesibilidad

* lenguaje sencillo;
* tipografía legible;
* contraste;
* áreas táctiles amplias;
* soporte de voz cuando esté habilitado;
* estados comprensibles sin conocimiento técnico.

## 26.8 Niveles de operación offline

### Nivel 0 — Online con recuperación

Obligatorio para MVP Build A:

* idempotencia;
* reintentos seguros;
* conservación de intención;
* indicador de fallo;
* no duplicación.

### Nivel 1 — Cola local básica

Condicionado por conectividad del piloto:

* captura local de ventas;
* identificador local único;
* cola persistente;
* estado visible de sincronización;
* bloqueo de cierre ante operaciones críticas pendientes.

### Nivel 2 — Conflictos avanzados

Posterior, salvo evidencia de necesidad:

* ediciones concurrentes;
* resolución de versiones;
* merge asistido;
* recuperación multi-dispositivo.

El piloto debe medir conectividad antes de comprometer el Nivel 2.

---


## 26.9 Reliability de acciones AI

* outputs estructurados para acciones;
* validación de schema;
* fallback determinístico;
* thresholds y prompts versionados;
* pruebas de regresión de intents y tool calls;
* evaluación offline antes de cambiar modelos;
* monitoreo de drift;
* bloqueo de escritura cuando la validación falla;
* separación entre explicación generativa y resultado determinístico.

## 26.10 Service reliability

* todo workflow activo mantiene estado y owner;
* operación degradada debe conservar consulta y captura determinística cuando sea posible;
* las revisiones internas tienen estado y tiempo esperado;
* una indisponibilidad debe explicar impacto y recuperación;
* no puede perderse una intención aceptada sin resultado o reason code.

## 26.11 Cost observability

Cada OutcomeRun debe registrar:

* tokens y llamadas;
* costo de modelos;
* infraestructura;
* reintentos;
* segundos de negocio;
* segundos de operador interno;
* costo total estimado;
* costo por tarea;
* margen estimado cuando exista revenue.

## 26.12 Data lineage

Toda cifra o estado crítico debe permitir reconstruir:

* fuente;
* periodo cubierto;
* timestamp;
* transformación;
* regla;
* versión;
* cobertura;
* actor;
* evidencia.

## 26.13 Evaluación de outcomes

El sistema debe soportar suites de evaluación para:

* precisión de captura;
* clasificación de excepciones;
* false completion;
* calidad de explicaciones;
* selección de Next Best Action;
* consistencia de memoria;
* recuperación de fallos;
* efectos de cambios de modelo o regla.

# Parte V — Modelo técnico conceptual

# 27. Arquitectura funcional

```text
Experience Layer / Business Stream
    ↓
Outcome Orchestrator
    ↓
Outcome Contract Registry + Workflow Engine
    ↓
Policy, Risk & Permission Engine
    ↓
Next Best Action + Exception System
    ↓
Domain Tools and Deterministic Services
    ↓
Operational Memory + Work Graph
    ↓
Data, Events, Evidence & Source Coverage
    ↓
Review Operations + Automation Learning
    ↓
Evaluation, Observability & Cost Layer
```

## 27.1 Experience Layer

* Business Stream;
* tarjetas generativas;
* composer;
* superficies por build;
* timeline;
* evidencia y cobertura;
* accessibility y operación degradada.

## 27.2 Outcome Orchestrator

* interpreta intención;
* identifica outcome y contrato;
* recupera contexto;
* crea o continúa OutcomeRun;
* evalúa política;
* selecciona herramientas;
* mantiene continuidad;
* decide bloqueo, revisión o siguiente acción;
* genera explicación.

## 27.3 Outcome Contract Registry

* definiciones versionadas;
* inputs y fuentes;
* gates;
* evidencia;
* tolerancias;
* outputs;
* limitaciones;
* pricing unit y cost measurement.

## 27.4 Workflow Engine

* estados;
* tareas;
* dependencias;
* timers;
* reintentos;
* excepciones;
* owners;
* deadlines;
* criterios de outcome;
* compensaciones.

## 27.5 Policy, Risk & Permission Engine

* permisos atómicos;
* autonomía por tarea;
* límites monetarios;
* evidencia requerida;
* reversibilidad;
* confirmaciones;
* políticas de aceptación;
* versionado y rollback.

## 27.6 Next Best Action and Exception System

* detección;
* prioridad;
* agrupación;
* responsable;
* impacto;
* resolución;
* expiración;
* escalamiento;
* efecto sobre outcome.

## 27.7 Domain Tools

Herramientas determinísticas para:

* ventas;
* pagos;
* cierres;
* efectivo;
* correcciones;
* cancelaciones;
* sincronización;
* evidencia;
* futuros inventario, compras y conciliación.

## 27.8 Operational Memory and Work Graph

* eventos;
* hechos;
* relaciones;
* decisiones;
* resolución;
* preferencias;
* tareas y actores;
* lineage;
* búsqueda contextual.

## 27.9 Review Operations

* ReviewTask;
* acceso mínimo;
* doble control;
* tiempo y costo;
* contexto;
* decisión;
* aprendizaje;
* feedback al backlog.

## 27.10 Automation Learning

* detección de patrones;
* AutomationCandidate;
* simulación;
* shadow mode;
* aprobación;
* promoción de autonomía;
* monitoreo;
* rollback.

## 27.11 Evaluation, Observability and Cost

* trazas;
* evaluaciones;
* tool success;
* false completion;
* costo por OutcomeRun;
* intervención humana;
* calidad de memoria;
* métricas de negocio.

# 28. Modelo conceptual de datos

## 28.1 Entidades core

### Business

```text
id
name
business_type
currency
timezone
status
created_at
```

### User

```text
id
business_id
name
role
status
preferences
created_at
```

### OperationalDay

```text
id
business_id
business_date
status
completion_percentage
completion_breakdown
opened_at
ready_to_close_at
closed_at
version
sales_total
payments_total
exception_count
recorded_operations_completeness
source_coverage_status
source_coverage_summary
```

### OperationalOutcome

```text
id
operational_day_id
outcome_type
status
completion_criteria
evidence_ids
completed_at
completed_by_type
exception_count
```

### Sale

```text
id
business_id
operational_day_id
occurred_at
declared_total
identified_total
unallocated_amount
detail_level
status
source
sync_status
created_by_type
created_by_id
```

### SaleConcept

```text
id
sale_id
original_text
normalized_name
category
quantity
unit_price
amount
confidence
source
```

### Payment

```text
id
sale_id
method
amount
authorization_code
reference
status
confidence
source
```

### OperationalException

```text
id
business_id
operational_day_id
exception_type
severity
summary
impact
status
responsible_party_type
responsible_party_id
recommended_resolution
evidence_ids
blocks_close
resolved_at
```

### WorkItem

```text
id
workflow_type
entity_type
entity_id
status
priority
assigned_to_type
assigned_to_id
due_at
resolution
```

### ReviewTask

```text
id
work_item_id
review_type
reason
input_snapshot
status
reviewer_id
decision
started_at
completed_at
review_seconds
```

### HumanIntervention

```text
id
review_task_id
operator_id
reason
action_taken
seconds_spent
reusable_learning
created_at
```

### CompletionEvidence

```text
id
entity_type
entity_id
evidence_type
source_reference
validation_rule
validation_result
created_at
```

### ClosingSnapshot

```text
id
operational_day_id
version
status
sales_total
payment_totals
expected_cash
counted_cash
cash_difference
open_exception_ids
accepted_exception_ids
source_coverage_snapshot
confirmed_by
confirmed_at
reopened_reason
supersedes_closing_id
created_at
```

Un snapshot confirmado es inmutable. Una reapertura genera una nueva versión y conserva la anterior.

### CashCount

```text
id
operational_day_id
closing_snapshot_id
amount
currency
counted_by
counted_at
source
note
evidence_ids
supersedes_cash_count_id
created_at
```

### Product — condicionado

```text
id
business_id
name
aliases
category
unit
status
inventory_tracking_enabled
created_at
```

### SaleItem — condicionado

```text
id
sale_id
product_id
quantity
unit_price
amount
source
created_at
```

### BusinessReference — condicionado

```text
id
business_id
reference_type
name
aliases
pricing_mode
reference_price
confidence
status
created_at
```

Estas tres entidades solo entran cuando el piloto justifica venta estructurada, productos frecuentes o inventario. El modelo core no debe depender de ellas.

### BusinessEvent

```text
id
business_id
operational_day_id
event_type
entity_type
entity_id
summary
source
actor_type
actor_id
metadata
occurred_at
```

### MemoryItem

```text
id
business_id
memory_type
statement
source_event_ids
confidence
status
valid_from
valid_until
confirmed_by
```

### AutonomyPolicy

```text
id
business_id
task_type
mode
risk_level
amount_limit
conditions
requires_confirmation
requires_reversibility
```


## 28.20 OutcomeDefinition

```text
id
outcome_type
name
customer_promise
business_value
eligible_segment
current_contract_version
status
created_at
updated_at
```

## 28.21 OutcomeContract

```text
id
outcome_definition_id
version
trigger
service_window
minimum_inputs
required_sources
optional_sources
source_coverage_requirement
workflow_definition
completion_gates
success_criteria
tolerances
required_evidence
possible_exceptions
allowed_partial_results
failure_conditions
human_confirmation
output_artifact_type
service_limitations
cost_measurement
pricing_unit
status
effective_from
```

## 28.22 OutcomeRun

```text
id
business_id
outcome_type
contract_id
operational_day_id
status
reason_code
owner_type
owner_id
source_coverage_snapshot_id
started_at
ready_at
completed_at
cost_summary
output_artifact_id
created_at
updated_at
```

## 28.23 OutcomeFailureReason

```text
id
outcome_run_id
reason_code
category
summary
responsible_party
recoverable
retry_at
evidence_ids
created_at
resolved_at
```

## 28.24 WorkAbsorptionRecord

```text
id
business_id
outcome_run_id
work_item_id
task_type
previous_execution_mode
current_execution_mode
human_steps_before
human_steps_after
estimated_minutes_saved
business_intervention_seconds
internal_intervention_seconds
automation_level
evidence_ids
created_at
```

## 28.25 NextBestAction

```text
id
business_id
outcome_run_id
action_type
title
reason
expected_outcome
priority
urgency
evidence_ids
required_actor_type
required_permission
risk_level
reversible
expires_at
status
created_at
```

## 28.26 AutomationCandidate

```text
id
business_id
task_type
source_exception_types
resolution_pattern
sample_count
confidence
risk_level
proposed_rule
required_evidence
simulation_results
approval_status
approved_by
autonomy_mode
rule_version
created_at
updated_at
```

## 28.27 ServiceBlueprintStep

```text
id
outcome_contract_id
step_order
step_type
customer_visible_action
automated_action
human_action
infrastructure_dependency
owner_type
expected_duration
failure_behavior
```

## 28.28 SourceCoverageRecord

```text
id
business_id
source_type
connection_status
coverage_period_start
coverage_period_end
last_successful_sync_at
reliability_level
known_limitations
evidence_reference
created_at
updated_at
```

## 28.29 OperationalMemoryLink

```text
id
business_id
memory_item_id
source_entity_type
source_entity_id
relation_type
valid_from
valid_until
confidence
created_at
```

## 28.30 Entidades condicionadas del producto completo

Deben mantenerse como parte de la arquitectura futura, sin obligar al MVP:

* `Product`;
* `SaleItem`;
* `BusinessReference`;
* `PriceObservation`;
* `CatalogCandidate`;
* `InventoryMovement`;
* `Supplier`;
* `PurchaseProposal`;
* `ReconciliationMatch`;
* `ExternalReviewPackage`.

# 29. Eventos de dominio

## 29.1 Core MVP

```text
OperationalDayOpened
SaleCreated
SaleUpdated
SaleCancelled
SaleEnriched
PaymentRegistered
PaymentMissing
PaymentMismatchDetected
AuthorizationMissing
PossibleDuplicateDetected
ExceptionDetected
ExceptionAssigned
ExceptionAccepted
ExceptionResolved
OperationalCompletionUpdated
OperationalDayReadyToClose
ClosingPrepared
CashCountSubmitted
CashDifferenceDetected
ClosingConfirmed
OperationalDayClosed
OperationalDayClosedWithExceptions
OperationalDayReopened
SyncPending
SyncCompleted
WorkflowFailed
HumanReviewRequested
HumanReviewCompleted
HumanInterventionRecorded
MemoryCreated
MemoryCorrected
```

## 29.2 Eventos futuros

```text
PriceObserved
PriceConfirmed
CatalogCandidateDetected
InventoryReceived
InventoryAdjusted
StockRiskDetected
PurchaseSuggested
SupplierCommitmentCreated
ExternalPaymentMatched
WeeklyReviewGenerated
```

# 30. Integraciones y fuentes

## 30.1 Fuentes controladas en el MVP

* entradas capturadas dentro de Lumo;
* acciones del usuario;
* herramientas internas;
* evidencia adjunta;
* datos sincronizados desde el dispositivo.

## 30.2 Fuentes condicionadas

* cámara;
* voz;
* vouchers;
* archivos simples;
* exportaciones seleccionadas.

## 30.3 Fuentes futuras

* terminales;
* adquirentes;
* bancos;
* facturación;
* ecommerce;
* proveedores;
* contadores.

Cada integración debe declarar:

* cobertura;
* frecuencia;
* confiabilidad;
* propiedad de la fuente;
* manejo de fallos;
* efecto sobre la promesa comercial.

---

# Parte VI — Validación

# 31. Métricas

## 31.1 North Star Metric

> **Porcentaje de jornadas entregadas listas para cerrar con intervención humana mínima y sin false completion.**

## 31.2 Métrica complementaria de Service-as-Software

> **Porcentaje del trabajo administrativo del workflow absorbido por Lumo con calidad aceptable.**

## 31.3 Métricas de outcome

* OutcomeRuns iniciados;
* ready rate;
* completion rate;
* partial completion rate;
* failure rate por reason code;
* tiempo a `ready`;
* tiempo a `completed`;
* reaperturas;
* cierres correctos;
* false completion rate;
* outcomes bloqueados por fuente, negocio, revisión o política.

## 31.4 Métricas de trabajo absorbido

* tareas absorbidas;
* pasos humanos antes y después;
* minutos eliminados;
* confirmaciones por outcome;
* búsquedas y revisiones evitadas;
* porcentaje del workflow operado por Lumo;
* distribución por execution mode;
* porcentaje de outcomes sin intervención interna.

## 31.5 Métricas de input y cobertura

* operaciones registradas frente al baseline estimado;
* Source Coverage por tipo;
* salud y latencia de fuentes;
* ventas sin pago;
* datos completados posteriormente;
* operaciones fuera de cobertura declarada;
* frecuencia de sync pending.

## 31.6 Métricas de calidad

* precisión de monto y pago;
* falsos positivos de excepción;
* excepciones omitidas;
* tasa de corrección;
* tasa de deshacer;
* errores de tool call;
* consistencia de ClosingSnapshot;
* integridad de CashCount;
* calidad de Next Best Action;
* memoria incorrecta o desactualizada.

## 31.7 Métricas de delegación y confianza

* usuarios que aceptan que Lumo mantenga el workflow;
* decisiones escaladas por jornada;
* porcentaje que entiende cobertura;
* porcentaje que identifica qué revisar;
* percepción de control;
* intención de continuidad;
* willingness to pay.

## 31.8 Métricas de service operations

* minutos internos por outcome;
* ReviewTasks por jornada;
* tasa de escalamiento;
* tiempo de revisión;
* recuperación exitosa;
* trabajo manual no modelado;
* excepciones convertidas en backlog;
* AutomationCandidates creados y promovidos.

## 31.9 Métricas económicas

* revenue por comercio;
* revenue por outcome;
* costo de IA;
* costo de infraestructura;
* costo humano;
* costo total por outcome;
* gross margin;
* margen por segmento;
* reducción de costo por cohorte;
* retención;
* expansión a otros outcomes.

## 31.10 Métricas anti-POS

* usuarios que describen a Lumo como operador;
* usuarios que dicen que Lumo “se encarga”;
* acciones iniciadas por Lumo;
* porcentaje del workflow sin navegación administrativa;
* uso de Business Stream frente a pantallas estructuradas;
* porcentaje que percibe Lumo solo como registrador o POS;
* frecuencia con que Lumo prepara un outcome sin solicitud explícita.

## 31.11 Métricas de aprendizaje

* recurrencia por tipo de excepción;
* resolución reutilizable;
* tiempo desde patrón hasta AutomationCandidate;
* precisión en shadow mode;
* reglas promovidas;
* rollbacks;
* mejora de costo y calidad después de automatización.

# 32. Criterios de éxito del piloto

Los thresholds son hipótesis iniciales y deben ajustarse con baseline real. Ningún porcentaje sustituye el análisis cualitativo del workflow.

## 32.1 Input

* al menos 5 comercios dentro del arquetipo;
* mínimo 10 jornadas por comercio para la fase ampliada;
* señales suficientes para preparar el outcome en la mayoría de jornadas;
* Source Coverage comprendida por el comercio;
* operaciones fuera de cobertura registradas como limitación, no como error silencioso.

## 32.2 Execution

* Lumo mantiene estado y pendientes entre interacciones;
* al menos una acción contextual iniciada por Lumo por jornada relevante;
* cero workflows activos sin estado u owner;
* reintentos no duplican operaciones;
* Minimum Operator Behavior demostrado en operación real.

## 32.3 Outcome

* 90 % de cierres preparados correctamente como objetivo inicial;
* 100 % de diferencias conocidas visibles;
* cero false completion en excepciones críticas;
* usuario identifica qué revisar en menos de 30 segundos;
* cierre sin diferencias se confirma en menos de dos minutos;
* outcomes parciales y fallidos explicados correctamente.

## 32.4 Delegación y trabajo absorbido

* reducción observable del tiempo de cierre;
* 70 % de usuarios declara que Lumo se encarga de parte del proceso;
* disminución de pasos manuales frente al baseline;
* al menos 60 % del workflow sin navegación administrativa;
* menor necesidad de revisar todas las transacciones.

## 32.5 Trust

* precisión de monto y pago superior a 95 % como objetivo inicial;
* acciones deshechas por error inferiores a 5 %;
* cobertura y limitaciones comprendidas;
* 90 % de acciones relevantes con evidencia y corrección;
* ningún trabajo humano interno presentado como automatización.

## 32.6 Economics

* costo humano, IA e infraestructura medidos por outcome;
* menos de 10 minutos internos por comercio por jornada al final de una fase madura, como hipótesis;
* ruta identificada para reducir las intervenciones frecuentes;
* menos de 20 % de trabajo manual no modelado;
* al menos un segmento con intención clara de pago o continuidad;
* costo decreciente o automatizable por cohorte.

## 32.7 Percepción anti-POS

Debe predominar una descripción de Lumo como sistema que organiza, recuerda, avisa y prepara. Si la mayoría lo describe solamente como POS, caja o registrador, el MVP no habrá validado la categoría aunque funcione técnicamente.

# 33. Criterios de aceptación

## Experiencia

**CAE-001.** El usuario registra “385 tarjeta” desde Inicio sin abrir un formulario de POS.

**CAE-002.** La interpretación muestra monto, pago y nivel de detalle antes de ejecutar, según política.

**CAE-003.** El flujo no solicita crear un producto.

**CAE-004.** Después de registrar, se puede corregir, enriquecer o deshacer desde el contexto.

**CAE-005.** Inicio se comprende sin interpretar una cuadrícula de KPIs.

**CAE-006.** Los usuarios distinguen hecho, cálculo e inferencia.

**CAE-007.** Una excepción muestra evidencia, responsable y efecto sobre el cierre.

**CAE-008.** El usuario puede identificar qué falta en menos de 30 segundos.

**CAE-009.** Un cierre sin catálogo sigue siendo útil.

**CAE-010.** La experiencia se percibe como operación del negocio y no como POS tradicional.

## Operación

**CAM-001.** Lumo prepara el cierre desde el Business Stream.

**CAM-002.** El usuario no revisa todas las operaciones para encontrar errores.

**CAM-003.** La completitud se explica con elementos concretos.

**CAM-004.** Una jornada con excepción crítica no puede estar `ready_to_close`.

**CAM-005.** Una intervención interna queda auditada.

**CAM-006.** Un cierre con excepción conserva el detalle y motivo.

**CAM-007.** La reapertura conserva el cierre original y crea nueva versión.

**CAM-008.** Una falla no se presenta como éxito.

**CAM-009.** Una operación reintentada no se duplica.

**CAM-010.** El usuario dedica menos tiempo al cierre que con el proceso anterior.


## 33.4 Criterios de aceptación de operador

**CAO-001:** Lumo crea o continúa el outcome con la primera señal válida.

**CAO-002:** Un pendiente permanece activo aunque el usuario cambie de pantalla o cierre la aplicación.

**CAO-003:** Lumo genera Next Best Action cuando existe una acción necesaria para avanzar.

**CAO-004:** El cierre se prepara proactivamente cuando se cumplen gates.

**CAO-005:** Un outcome bloqueado muestra reason code, responsable y resolución esperada.

**CAO-006:** La interfaz distingue outcome completo, con excepciones, parcial y fallido.

**CAO-007:** Cada OutcomeRun registra costo y modo de ejecución de tareas críticas.

## 33.5 Criterios de aceptación anti-POS

**CAP-001:** La pantalla inicial prioriza estado y acciones, no catálogo o teclado de caja.

**CAP-002:** El usuario puede completar la jornada sin navegar por módulos administrativos.

**CAP-003:** Lumo inicia al menos una acción contextual relevante.

**CAP-004:** El cierre no requiere construir manualmente un reporte.

**CAP-005:** Las pruebas cualitativas verifican que el usuario comprende que Lumo mantiene el workflow.

# 34. Escenarios end-to-end

## Escenario 1 — Jornada limpia

El comercio registra 30 ventas con pagos completos. Lumo alcanza `ready_to_close`, solicita efectivo, confirma coincidencia y cierra sin excepciones.

## Escenario 2 — Venta sin medio de pago

Una venta queda pendiente. Lumo crea excepción bloqueante y la presenta antes del cierre.

## Escenario 3 — Pago mixto incompleto

Una venta de $500 tiene $300 en efectivo y $150 en tarjeta. Lumo detecta diferencia de $50.

## Escenario 4 — Diferencia de efectivo

El efectivo contado es menor al esperado. Lumo solicita motivo y permite cierre con diferencia solo a rol autorizado.

## Escenario 5 — Posible duplicado

Dos ventas similares ocurren en segundos. Lumo no elimina; solicita confirmar o cancelar.

## Escenario 6 — Corrección de medio de pago

El usuario cambia una venta de tarjeta a efectivo. Lumo muestra impacto y recalcula cierre.

## Escenario 7 — Cancelación

Se cancela una venta con pago. Lumo conserva auditoría y revierte efectos.

## Escenario 8 — Datos tardíos

Una venta sincroniza después del cierre. Lumo crea excepción y propone reapertura.

## Escenario 9 — Reapertura

El dueño reabre con motivo, corrige una venta y confirma una nueva versión del cierre.

## Escenario 10 — Operación offline

Se registran ventas sin conexión. Al reconectar se sincronizan sin duplicados y se actualiza completitud.

## Escenario 11 — Conflicto de sincronización

Una venta fue corregida localmente y en servidor. Lumo bloquea actualización silenciosa y crea revisión.

## Escenario 12 — Operación asistida

Un documento no puede interpretarse. Se crea review task, el operador resuelve y la intervención queda medida.

## Escenario 13 — Falla técnica

Una herramienta falla después de recibir intención. Lumo conserva la intención, informa fallo y permite reintentar sin duplicar.

## Escenario 14 — Comercio sin catálogo

El negocio registra únicamente monto y pago. Obtiene cierre, mezcla de pagos, efectivo y excepciones.

## Escenario 15 — Venta híbrida

Se registran productos conocidos y monto de otros. El total completo se conserva y se calcula cobertura.

## Escenario 16 — Autorización pendiente

Una venta con tarjeta carece de código. La política define si bloquea o permite cierre con advertencia.

## Escenario 17 — Excepción aceptada

Una excepción no crítica se acepta con motivo. La jornada queda `closed_with_exceptions`.

## Escenario 18 — Falsa completitud impedida

La interfaz no permite cerrar cuando existe un `workflow_failure` crítico.

## Escenario 19 — Memoria de resolución

Una excepción recurrente se resuelve varias veces de la misma forma. Lumo crea un candidato de regla, no una automatización silenciosa.

## Escenario 20 — Resumen semanal

Después de cinco cierres, Lumo genera un resumen con datos confiables y separa observaciones de inferencias.


## E21 — Lumo inicia el cierre

1. La jornada cumple gates.
2. El usuario no solicita un reporte.
3. Lumo crea Next Best Action para informar efectivo contado.
4. Presenta cierre preparado y cobertura.
5. El usuario informa CashCount.
6. Lumo completa o genera diferencia.

**Valida:** Minimum Operator Behavior, RF-076, RF-089.

## E22 — Outcome parcial por Source Coverage

1. Las operaciones registradas están completas.
2. Una fuente declarada no estuvo disponible durante parte de la jornada.
3. Lumo no declara cobertura total.
4. Entrega resultado parcial con periodo afectado.
5. Explica cómo recuperar o completar.

**Valida:** RF-066, RF-073, RF-079, RF-080.

## E23 — Outcome fallido con recuperación

1. Falla el cálculo de efectivo esperado.
2. El outcome pasa a `failed` con `failed_validation`.
3. Lumo conserva operaciones y responsabilidad.
4. Reintenta con servicio determinístico.
5. Si recupera, continúa sin duplicar; si no, crea ReviewTask.

**Valida:** RF-058 a RF-060, RF-080.

## E24 — Pendiente entre jornadas

1. Una excepción no crítica queda abierta al final del día.
2. Se cierra con aceptación autorizada.
3. La jornada siguiente muestra el pendiente histórico cuando sigue siendo relevante.
4. La resolución actualiza memoria y reportes.

**Valida:** RF-087 y memoria entre jornadas.

## E25 — Next Best Action prioriza gate

1. Existe una recomendación de reposición.
2. También existe payment mismatch bloqueante.
3. Lumo prioriza resolver el pago.
4. La recomendación permanece disponible sin interrumpir.

**Valida:** RF-089 y RF-090.

## E26 — Medición de trabajo absorbido

1. El baseline indica seis pasos manuales para el cierre.
2. En Lumo, dos pasos son preparados, dos ejecutados con confirmación y dos eliminados.
3. Se crea WorkAbsorptionRecord.
4. El piloto calcula minutos y costo evitado.

**Valida:** RF-083 a RF-085.

## E27 — AutomationCandidate seguro

1. El mismo tipo de excepción se resuelve repetidamente.
2. Lumo crea candidato, no regla activa.
3. Ejecuta simulación sobre historial.
4. Un responsable aprueba shadow mode.
5. Se promueve a ejecución reversible solo si cumple calidad.

**Valida:** RF-091 a RF-093.

## E28 — Percepción anti-POS

1. Un comercio completa onboarding y varias jornadas.
2. Se realiza entrevista sin sugerir lenguaje.
3. Se registra cómo describe el producto.
4. Si lo describe solo como POS, se crea riesgo de experiencia y acción correctiva.

**Valida:** RF-096 y CAP-001 a CAP-005.

## E29 — Continuidad intención–memoria

1. El usuario corrige el medio de pago de una venta.
2. Lumo muestra impacto en efectivo esperado.
3. La corrección queda auditada.
4. La resolución se vincula a Event Memory.
5. El cierre usa el estado corregido.

**Valida:** RF-086, RF-097.

## E30 — Nuevo outcome no aprobado

1. Se propone agregar compras automáticas.
2. El comité evalúa Product Outcome Map y contrato.
3. No existe evidencia de frecuencia, fuentes o autorización segura.
4. La capacidad queda Future y no entra al MVP.

**Valida:** RF-098 a RF-100 y gobierno de alcance.

# 35. Matriz de trazabilidad inicial

La matriz relaciona los elementos de mayor riesgo. La versión operativa completa debe mantenerse como anexo vivo.

| Requisito | Criterio | Escenario | Métrica | Build |
|---|---|---|---|---|
| RF-008 Registrar venta | CAE-001 a CAE-004 | E1, E14 | tiempo de registro, precisión | MVP Build A |
| RF-009 Pago o pendiente | CAM-004 | E2 | payment coverage | MVP Build A |
| RF-020 Idempotencia | CAM-009 | E10, E13 | duplicados por reintento | MVP Build A |
| RF-029 Detectar excepción | CAE-007 | E2 a E5 | falsos positivos, no detectadas | MVP Build A/1 |
| RF-036 Preparar cierre | CAM-001 | E1 | cierres preparados correctamente | MVP Build A |
| RF-039 Diferencia de efectivo | CAM-006 | E4 | diferencias visibles | MVP Build A |
| RF-043 Bloqueo crítico | CAM-004 | E18 | false completion rate | MVP Build B |
| RF-044 Reapertura | CAM-007 | E8, E9 | cierres reabiertos | MVP Build B |
| RF-053 Review task | CAM-005 | E12 | minutos humanos | Product Horizon 1 |
| RF-060 Recuperar sin duplicar | CAM-008, CAM-009 | E13 | recovery success | MVP Build A/1 |
| RF-066 Cobertura separada | CAE-008 | E14 | comprensión de cobertura | MVP Build A |
| RF-068 ClosingSnapshot | CAM-007 | E9 | integridad de versiones | MVP Build B |
| RF-071 Política de aceptación | CAM-006 | E17 | accepted exceptions por tipo | MVP Build B |
| RF-074 Nivel offline | CAM-009 | E10, E11 | sync failures, conflictos | MVP Build B |
| RF-076 Minimum Operator Behavior | CAO-001 a CAO-005 | E21 | acciones iniciadas, percepción operador | MVP Build A |
| RF-077 Outcome Contract | CAO-005, CAM-001 | E21 a E23 | outcome completion, version integrity | MVP Build A |
| RF-079 Resultado parcial | CAO-006 | E22 | partial completion rate | MVP Build B |
| RF-083/084 Work absorption | CAO-007 | E26 | pasos y minutos absorbidos | MVP Build A |
| RF-086 Event Memory | CAO-002 | E24, E29 | continuidad entre jornadas | MVP Build A |
| RF-089 Next Best Action | CAO-003 | E21, E25 | action completion, prioridad | MVP Build A |
| RF-091 AutomationCandidate | CAM-005 | E27 | candidatos, shadow accuracy | Product Horizon 1 |
| RF-096 Percepción anti-POS | CAP-001 a CAP-005 | E28 | operator perception rate | MVP Build A |
| RF-097 Continuidad | CAO-001, CAO-002 | E29 | trace completeness | MVP Build B |

## 35.1 Regla de mantenimiento

Todo requisito nuevo debe declarar:

* build;
* criterio de aceptación;
* escenario de prueba;
* métrica o evidencia;
* owner de producto;
* decisión de release.

# 36. Diseño del piloto como cadena de valor

## 36.1 Selección

* 5 a 10 comercios;
* cumplimiento del arquetipo operativo;
* variedad controlada, no dispersión extrema;
* dueño disponible para feedback;
* consentimiento para instrumentación y operación asistida;
* proceso actual observable.

## 36.2 Baseline obligatorio

Antes del uso medir:

* tiempo de registro;
* tiempo de cierre;
* pasos manuales;
* herramientas utilizadas;
* errores y diferencias;
* número de personas involucradas;
* frecuencia de ventas incompletas;
* proceso de pagos;
* percepción de control;
* costo estimado del trabajo;
* willingness to pay inicial;
* fuentes y Source Coverage esperada.

## 36.3 Dimensiones de validación

### Input

¿Lumo recibe suficientes señales y con qué cobertura?

### Execution

¿Mantiene estado, pendientes, prioridad y responsabilidad?

### Outcome

¿El resultado es correcto, claro, oportuno y verificable?

### Delegation

¿El comercio dejó de ejecutar trabajo o revisar toda la operación?

### Trust

¿Comprende evidencia, cobertura, limitaciones y trabajo humano?

### Economics

¿Cuánto cuesta entregar cada outcome y qué intervención puede reducirse?

### Expansion

¿Qué siguiente outcome solicita el comercio y por qué?

## 36.4 Fases

### Fase A — Operator Foundation

* onboarding;
* baseline;
* primeras jornadas acompañadas;
* validación de Minimum Operator Behavior;
* stage gate del wedge.

### Fase B — Reliable Daily Close

* más jornadas;
* excepciones reales;
* fallos, reapertura y datos tardíos;
* medición de confiabilidad y trabajo absorbido;
* prueba de intención de pago.

### Fase C — Managed Operations, solo con evidencia

* review queue;
* reducción de intervención;
* memoria de resolución;
* AutomationCandidates;
* economía por outcome.

## 36.5 Duración

Mínimo de cinco jornadas para el stage gate inicial y al menos diez jornadas por comercio para evaluar repetibilidad, sujeto al ritmo real de operación.

## 36.6 Operación

* onboarding acompañado;
* soporte en ventanas definidas;
* instrumentation desde el primer outcome;
* entrevistas semanales;
* revisión de excepciones;
* medición de tiempos y costos;
* registro de trabajo no modelado;
* comparación contra baseline.

## 36.7 Criterios de abandono o replanteamiento

* el cierre no representa dolor real;
* el comercio no puede o no quiere aportar señales mínimas;
* Lumo no demuestra comportamiento de operador;
* la intervención no disminuye ni es automatizable;
* el resultado no genera intención de pago;
* la cobertura impide controlar la promesa;
* la experiencia aumenta fricción en hora pico;
* la mayoría percibe el producto solamente como POS;
* el costo por outcome no tiene ruta creíble de mejora.

## 36.8 Evidencia de continuidad

La decisión de avanzar debe registrar:

* resultados cuantitativos;
* hallazgos cualitativos;
* segmentos con mejor desempeño;
* principales excepciones;
* costo e intervención;
* riesgos;
* decisión y responsable;
* cambios al Outcome Contract o al wedge.

# Parte VII — Negocio y ejecución

# 37. Modelo comercial

## 37.1 Principio

El precio debe relacionarse con valor y trabajo completado, no principalmente con seats.

## 37.2 Recomendación para MVP

* suscripción mensual simple por comercio;
* volumen o límites transparentes;
* piloto pagado cuando sea viable;
* medición interna por jornada;
* comunicación comercial basada en resultado.

## 37.3 Experimentos futuros

* precio por jornada organizada;
* base mensual más workflows premium;
* plan híbrido por volumen;
* paquete con conciliación o revisión semanal.

## 37.4 Evitar

* freemium indefinido;
* precio por token;
* servicios personalizados sin margen;
* promesas ilimitadas;
* seat-based pricing como unidad principal.

# 38. Go-to-market

___

1. Seleccionar un vertical.
2. Observar la operación.
3. Medir cierre actual.
4. Vender el resultado.
5. Ejecutar piloto.
6. Comparar antes y después.
7. Documentar caso.

## 38.2 Mensaje

> “Al final del día, Lumo deja tus ventas y pagos organizados, te muestra cualquier diferencia y prepara el cierre.”

## 38.3 Canales futuros

* contadores;
* adquirentes;
* fintechs;
* proveedores de terminales;
* asociaciones;
* distribuidores;
* bancos para pymes.

# 39. Moat

## 39.1 Workflow ownership

Lumo controla un proceso completo y frecuente.

## 39.2 Operational data graph

Cada jornada genera relaciones entre ventas, pagos, horarios, conceptos, excepciones, decisiones y personas.

## 39.3 Resolution memory

Lumo aprende cómo se resuelven excepciones dentro de políticas.

## 39.4 Vertical playbooks

Los patrones por vertical se convierten en reglas, agentes y flujos reutilizables.

## 39.5 Integrations

Las integraciones aumentan cobertura, precisión y switching costs.

## 39.6 Trust history

El historial verificable de cierres, decisiones y políticas crea confianza acumulativa.

## 39.7 Human feedback flywheel

```text
Más workflows
    ↓
Más excepciones observadas
    ↓
Mejores reglas y herramientas
    ↓
Menor intervención
    ↓
Mejor margen
    ↓
Mayor capacidad de expansión
```

# 40. Unit economics del servicio

## 40.1 Unidad económica

La unidad principal de análisis es el `OutcomeRun`, no el usuario, token o conversación.

## 40.2 Costos por outcome

* modelos y herramientas AI;
* infraestructura;
* almacenamiento y evidencia;
* integraciones;
* reintentos y recuperación;
* segundos de operador interno;
* soporte;
* costo de revisión y doble control.

## 40.3 Revenue

Medir:

* revenue mensual por comercio;
* revenue imputado por outcome;
* willingness to pay;
* planes o add-ons por workflow;
* expansión a outcomes posteriores.

## 40.4 Gross margin loop

```text
Más outcomes
→ más excepciones observadas
→ mejores reglas y herramientas
→ menos intervención
→ menor costo por outcome
→ mejor margen
→ mayor capacidad de expansión
```

## 40.5 Señales de viabilidad

* costo por outcome medido;
* intervención recurrente clasificada;
* reducción de costo por cohorte;
* excepciones costosas priorizadas;
* margen por segmento;
* ruta explícita desde revisión humana a automatización segura.

El objetivo del primer piloto no es alcanzar inmediatamente margen SaaS. Es demostrar una curva medible de mejora y evitar que la operación asistida se convierta en BPO no escalable.

# 41. Riesgos y mitigaciones

## 41.1 Convertirse en BPO manual

Medir intervención y eliminar trabajo no reutilizable.

## 41.2 Prometer más de lo controlable

Declarar cobertura y mostrar resultados parciales.

## 41.3 Producto horizontal demasiado pronto

Mantener wedge y vertical inicial.

## 41.4 Baja disposición de pago

Vender ahorro y control; ejecutar pilotos pagados.

## 41.5 Dependencia de captura manual

Mejorar voz, cámara e integraciones según evidencia.

## 41.6 Desconfianza

Evidencia, reversibilidad, corrección y transparencia.

## 41.7 Falsa autonomía

Distinguir actores y no ocultar revisión humana.

## 41.8 Falsa completitud

Criterios determinísticos y excepciones críticas bloqueantes.

## 41.9 Baja calidad de datos

Captura progresiva, cobertura y enriquecimiento posterior.

## 41.10 Conectividad

Cola local, sincronización e idempotencia.

## 41.11 Scope creep

Toda nueva capacidad debe mejorar outcome, confiabilidad, margen o moat.

## 41.12 Riesgo regulatorio

No presentarse como banco, contador ni asesor fiscal.

## 41.11 Ser percibido como POS

**Riesgo:** el MVP se concentra en ventas y cierre y el mercado lo interpreta como caja conversacional.

**Mitigación:** Minimum Operator Behavior, Business Stream, outcomes, memoria, métricas de percepción y narrativa de trabajo absorbido.

## 41.12 Pseudo-operador

**Riesgo:** Lumo aparenta responsabilidad, pero depende de que el usuario reconstruya todo.

**Mitigación:** WorkItems persistentes, Next Best Action, proactividad y criterio de aceptación de operador.

## 41.13 Memoria postergada

**Riesgo:** el producto funciona como workflow transaccional sin aprendizaje acumulativo.

**Mitigación:** Event Memory obligatoria desde MVP Build A.

## 41.14 Responsabilidad ambigua del servicio

**Riesgo:** el cliente no entiende qué promete Lumo o qué ocurre cuando faltan datos.

**Mitigación:** Outcome Contracts, Service Blueprint, reason codes y Source Coverage.

## 41.15 Sobrearquitectura de outcome platform

**Riesgo:** construir un framework genérico antes de validar Daily Close.

**Mitigación:** implementar solo los primitives necesarios para `daily_close_ready`, manteniendo interfaces extensibles sin generalización prematura.

# 42. Roadmap por evidencia

## Fase 0 — Definición e instrumentación

* cerrar PRD y Outcome Contract;
* seleccionar arquetipo;
* documentar fuentes;
* medir baseline;
* definir consentimiento;
* instrumentar costo, calidad y trabajo absorbido.

## MVP Build A — Operator Foundation

* captura mínima;
* OutcomeRun;
* jornada y pagos;
* WorkItems;
* Next Best Action;
* Event Memory;
* efectivo y CashCount;
* cierre preparado;
* cobertura explícita;
* reason codes;
* auditoría;
* stage gate.

## MVP Build B — Reliable Daily Close

* reglas completas;
* pagos mixtos;
* correcciones y cancelaciones;
* excepciones;
* ClosingSnapshot;
* reapertura;
* permisos;
* sincronización requerida;
* recuperación y conflictos prioritarios;
* Operational Context Memory;
* medición de percepción y willingness to pay.

## Product Horizon 1 — Managed Operations

* review queue;
* intervención medida;
* Resolution Memory;
* políticas;
* AutomationCandidates;
* shadow mode;
* proactividad longitudinal;
* unit economics por outcome.

## Product Horizons posteriores

* Weekly Business Review;
* Payment Reconciliation;
* Inventory & Replenishment;
* Purchasing & Supplier Operations;
* External Review Package;
* Financial Operations y FinTech.

Cada transición requiere evidencia del horizonte anterior. El roadmap no es una secuencia automática por fecha.

# 43. Decisiones consolidadas

1. Lumo no se presentará como POS.
2. Lumo es un operador administrativo AI-native y sistema de responsabilidad.
3. La unidad de valor es el outcome operativo.
4. La conversación es el control plane, no la arquitectura completa.
5. Daily Close es el primer outcome, no el producto completo.
6. El MVP incluye Operator Foundation y Reliable Daily Close.
7. Managed Operations es Product Horizon 1.
8. El MVP debe demostrar Minimum Operator Behavior.
9. La operación normal debe requerir mínima atención.
10. Las excepciones y WorkItems son capacidades centrales.
11. La completitud requiere evidencia y gates.
12. Source Coverage y Recorded Operations Completeness se comunican por separado.
13. Un score es informativo y experimental.
14. La intervención humana es transparente, consentida y medible.
15. La autonomía se define por tarea.
16. Ninguna resolución repetida se automatiza sin candidato, simulación y aprobación.
17. El catálogo no es requisito.
18. El total declarado es la referencia principal.
19. La memoria factual comienza en el primer build.
20. Los pendientes pueden cruzar jornadas.
21. Cada outcome tiene contrato versionado.
22. Cada OutcomeRun tiene owner, estado, reason code y costo.
23. Los resultados parciales son explícitos.
24. Un cierre original no se sobrescribe silenciosamente.
25. Cada cierre confirmado crea ClosingSnapshot inmutable.
26. Una excepción crítica impide outcome completo.
27. Los roles se implementan mediante permisos atómicos.
28. La aceptación de excepciones se define por tipo.
29. Offline avanzado entra solo con evidencia.
30. Las inferencias no se presentan como hechos.
31. Lumo prioriza Next Best Action sobre ruido informativo.
32. El trabajo absorbido se mide desde el MVP.
33. El costo se mide por outcome.
34. El éxito se mide por trabajo completado, confianza y economía, no engagement.
35. La verticalización precede a expansión horizontal.
36. Pricing inicial es simple; la medición interna se alinea con outcomes.
37. FinTech es expansión natural, no alcance funcional del MVP.
38. La POC terminó; el siguiente hito es implementación y operación real.
39. El Product Outcome Map protege la visión completa.
40. Una nueva capacidad debe mejorar outcome, confiabilidad, trabajo absorbido, margen o moat.

# 44. Preguntas abiertas

Las siguientes preguntas no deben bloquear MVP Build A salvo que afecten seguridad o promesa:

1. ¿Cuál será el primer subconjunto de comercios dentro del arquetipo?
2. ¿Qué baseline real de tiempo y pasos tiene cada tipo de comercio?
3. ¿Qué nivel mínimo de Source Coverage es suficiente para que el outcome tenga valor?
4. ¿Cuándo debe el medio de pago pendiente bloquear el cierre?
5. ¿Qué tolerancias de efectivo probará el piloto?
6. ¿Qué reason codes requieren revisión interna inmediata?
7. ¿Qué porcentaje de intervención define una señal de viabilidad?
8. ¿Qué unidad de pricing comprende mejor el comercio?
9. ¿Qué información debe mostrarse en el primer Business Stream?
10. ¿Qué offline mínimo exige el contexto real?
11. ¿Qué criterios promueven un AutomationCandidate a shadow mode?
12. ¿Qué siguiente outcome tiene mayor demanda después de Daily Close?
13. ¿Qué datos pueden conservarse como memoria y por cuánto tiempo?
14. ¿Qué umbral cualitativo indica que Lumo sigue percibiéndose como POS?
15. ¿Qué Service Level puede prometerse después del piloto?

Toda pregunta debe tener owner, fecha de decisión, evidencia requerida y efecto en el roadmap.

# 45. Contrato de alineación

Toda propuesta debe responder:

## Outcome y cliente

1. ¿Qué resultado compra el cliente?
2. ¿Existe un Outcome Contract verificable?
3. ¿El segmento siente el problema con frecuencia?
4. ¿La promesa controla sus fuentes y limitaciones?

## Producto y experiencia

5. ¿Completa un workflow de punta a punta?
6. ¿Demuestra comportamiento de operador?
7. ¿Reduce trabajo, no solo clics?
8. ¿Aísla excepciones y prioriza siguiente acción?
9. ¿Mantiene conversación, continuidad y memoria?
10. ¿Evita que Lumo parezca un POS tradicional?

## Confianza

11. ¿Tiene evidencia de completitud?
12. ¿Puede fallar o entregar parcial explícitamente?
13. ¿Mantiene corrección, reversión y auditoría?
14. ¿Distingue modelo, regla, usuario y operador?
15. ¿Respeta permisos, riesgo y cobertura?

## Economía y moat

16. ¿Mide costo por outcome?
17. ¿Tiene ruta de reducción de intervención?
18. ¿Construye memoria, work graph o datos propietarios?
19. ¿Reutiliza plataforma para outcomes posteriores?
20. ¿Mejora margen o switching cost?

## Alcance

21. ¿Pertenece al build vigente?
22. ¿Existe evidencia para adelantarla?
23. ¿Puede implementarse sin sobrearquitectura?
24. ¿Está trazada a criterio, escenario y métrica?
25. ¿Qué se elimina o posterga para incorporarla?

Una funcionalidad que no mejora outcome, confiabilidad, trabajo absorbido, margen o moat no debe entrar al MVP.

# Parte VIII — Gobierno y referencia

# 46. Glosario operativo

**AI-native:** producto y operación diseñados alrededor de modelos, herramientas, workflows, memoria, evaluación y revisión humana; no únicamente una interfaz con IA.

**Service-as-Software:** modelo donde el cliente compra un servicio o resultado terminado y el proveedor utiliza software e IA para asumir el trabajo y mejorar progresivamente el margen.

**Outcome:** resultado verificable que Lumo promete.

**Outcome Contract:** definición versionada de promesa, inputs, fuentes, gates, evidencia, limitaciones y costo.

**OutcomeRun:** ejecución concreta de un contrato para un negocio y periodo.

**Minimum Operator Behavior:** comportamiento mínimo que demuestra que Lumo mantiene responsabilidad por un workflow.

**Work absorption:** parte del trabajo antes realizado por personas que Lumo prepara, ejecuta o elimina.

**Source Coverage:** cobertura de las fuentes operativas relevantes.

**Recorded Operations Completeness:** completitud de operaciones conocidas por Lumo.

**Next Best Action:** acción prioritaria para avanzar el outcome.

**AutomationCandidate:** propuesta evaluable de automatización derivada de patrones de resolución.

**ClosingSnapshot:** versión inmutable de un cierre confirmado.

**CashCount:** declaración de efectivo contado, con actor y momento.

**Event Memory:** memoria factual de eventos y decisiones desde el primer build.

**Resolution Memory:** memoria de cómo y por qué se resolvió una excepción.

# 47. Gobierno de requisitos y decisiones

## 47.1 Estados de requisito

```text
proposed
accepted
in_design
in_build
validated
released
deprecated
rejected
```

## 47.2 Campos de gobierno

Cada requisito debe tener:

* ID;
* descripción;
* horizonte;
* owner;
* criterio;
* escenario;
* métrica;
* dependencia;
* estado;
* decisión y evidencia.

## 47.3 Cambio de alcance

Una capacidad solo cambia de horizonte cuando:

* aparece evidencia nueva;
* se identifica riesgo bloqueante;
* elimina una excepción dominante;
* reduce costo crítico;
* es necesaria para cumplir el Outcome Contract.

El cambio debe registrar qué se desplaza o elimina para proteger la capacidad del equipo.

# 48. Resumen de alcance por horizonte

| Área | MVP Build A | MVP Build B | Product Horizon 1 | Posterior |
|---|---|---|---|---|
| Outcome | contrato y ejecución básica | confiabilidad y parcial | portfolio operativo | nuevos outcomes |
| Captura | monto y pago | mixta, corrección, sync | multimodal según evidencia | integraciones amplias |
| Cierre | preparado y confirmado | snapshot, reapertura, late data | servicio gestionado | conciliación externa |
| Excepciones | core mínimo | taxonomía y política | aprendizaje y automatización | playbooks verticales |
| Memoria | Event Memory | Operational Context | Resolution Intelligence | data graph expandido |
| Experiencia | Business Stream mínimo | timeline y evidencia | Memoria y políticas completas | experiencias por outcome |
| Humano | soporte básico medido | revisión selectiva | review operations | especialistas regulados según alcance |
| Economía | costo medido | willingness to pay | gross margin loop | pricing por portfolio |

# 49. Checklist de cobertura v0.11

La versión 0.11 incorpora:

* POC terminada y estado actual;
* MVP implementable;
* Product Outcome Map;
* AI-native operator;
* Service-as-Software;
* Minimum Operator Behavior;
* Outcome Contract;
* trabajo absorbido;
* memoria desde el primer build;
* Business Stream incremental;
* anti-POS guardrails;
* Next Best Action;
* AutomationCandidate;
* outcomes parciales y fallidos;
* Source Coverage;
* Service Blueprint;
* arquetipo inicial;
* permisos, gates y cierres versionados;
* offline incremental;
* métricas de outcome, calidad, trabajo y economía;
* entidades del producto completo;
* escenarios y trazabilidad;
* GTM, pricing, moat y roadmap.

# 50. Narrativa final

Lumo no es un POS con inteligencia artificial ni un chatbot que ayuda a registrar ventas.

Lumo es un operador administrativo AI-native.

Durante el día recibe señales tan simples como:

> “385 tarjeta.”

Pero su valor no termina al registrar la venta.

Lumo mantiene el estado de la jornada, conserva pendientes, organiza pagos, detecta lo que falta, prioriza la siguiente acción, prepara el cierre y explica qué puede o no puede verificar.

El producto comienza con `daily_close_ready`: una jornada organizada y lista para revisar. Ese outcome crea la memoria, evidencia, relaciones y confianza necesarias para asumir progresivamente más trabajo: revisión semanal, conciliación, reposición, compras, proveedores y operaciones financieras.

La experiencia es:

> **No administres tu negocio. Habla con él.**

La promesa comercial es:

> **Tu negocio se mantiene organizado. Tú intervienes cuando realmente importa.**

La tesis de compañía es:

> **Lumo convierte el trabajo administrativo del pequeño comercio en outcomes operativos, verificables y progresivamente autónomos.**

El MVP no busca demostrar que una venta puede registrarse con IA. Busca demostrar que un comercio puede delegar un resultado a Lumo.
