# 🏗️ Arquitectura de 5 Capas - Nodaris Agent

## ✅ Implementación Completa

La arquitectura completa de 5 capas ha sido implementada exitosamente en `src/agent/graph/graph.py`.

## 📐 Diagrama de Arquitectura

```
┌─────────────────────────────────────────────────────────────┐
│                    CAPA 1: INTERFACES                        │
│  ┌─────────────────┐              ┌────────────────────┐   │
│  │  Telegram Bot   │              │   API Interface    │   │
│  │ telegram_bot.py │              │ api_interface.py   │   │
│  └────────┬────────┘              └─────────┬──────────┘   │
└───────────┼──────────────────────────────────┼──────────────┘
            │                                  │
            └──────────────┬───────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    CAPA 2: PLANNER IA                        │
│                     planner_node                             │
│                                                              │
│  • Analiza consultas del usuario                            │
│  • Diseña plan de ejecución                                 │
│  • Determina qué validaciones aplicar                       │
│                                                              │
│  Prompt Guide: prompts/planner_prompt.md                    │
└────────────────────────────┬────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                 CAPA 3: ANALYSIS NODES                       │
│                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐ │
│  │ Validation   │ →  │  Analysis    │ →  │ Verification │ │
│  │              │    │              │    │              │ │
│  │ • Valida DNI │    │ • Analiza    │    │ • Genera     │ │
│  │ • Valida     │    │   con LLM    │    │   hash SHA   │ │
│  │   nota       │    │ • Detecta    │    │ • Timestamp  │ │
│  │ • Reglas     │    │   anomalías  │    │ • Auditoría  │ │
│  └──────────────┘    └──────────────┘    └──────────────┘ │
│                                                              │
│  Usa: nodes/validation.py, analysis.py, verification.py     │
└────────────────────────────┬────────────────────────────────┘
                             ▼
                ┌────────────────────────┐
                │    CAPA 4: TOOLS       │
                │                        │
                │  Herramientas usadas   │
                │  por los nodos:        │
                │                        │
                │  • crypto.py           │
                │  • prompts.py          │
                │  • dificultad.py       │
                │  • copia.py            │
                │  • tiempos.py          │
                │  • validacion.py       │
                └────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│              CAPA 5: REPORT + MEMORY                         │
│                                                              │
│  ┌──────────────────┐         ┌─────────────────────┐      │
│  │  Reflection      │    →    │  Report Generator   │      │
│  │                  │         │                     │      │
│  │ • Revisa         │         │ • Genera reporte    │      │
│  │   análisis       │         │   profesional       │      │
│  │ • Identifica     │         │ • Formatea          │      │
│  │   mejoras        │         │   resultados        │      │
│  │ • Valida         │         │ • Incluye hash      │      │
│  │   calidad        │         │                     │      │
│  └──────────────────┘         └─────────┬───────────┘      │
│                                          │                  │
│  Usa: nodes/reflection.py, report.py    │                  │
│  Prompt: prompts/report_prompt.md       │                  │
└─────────────────────────────────────────┼──────────────────┘
                                          ▼
                              ┌─────────────────────┐
                              │  Memory Manager     │
                              │  memory_manager.py  │
                              │                     │
                              │  • Almacena         │
                              │    historial        │
                              │  • Contexto         │
                              │  • Trazabilidad     │
                              └─────────────────────┘
```

## 🔄 Flujo de Ejecución

### Flujo Completo (Happy Path):

```
1. User/API/Telegram
        ↓
2. Interface Layer (telegram_bot.py / api_interface.py)
        ↓
3. Planner Node
        ↓
4. Validation Node
        ↓
5. Analysis Node
        ↓
6. Verification Node
        ↓
7. Reflection Node
        ↓
8. Report Node
        ↓
9. Memory/Storage
        ↓
10. Response to User
```

### Flujo con Error:

```
1-4. (Same)
        ↓
5. Validation Node → ERROR
        ↓
6. END (Sin continuar procesamiento)
```

## 📝 Código de Implementación

El flujo está implementado en [`src/agent/graph/graph.py`](../src/agent/graph/graph.py):

```python
# Entry: Start → Planner
workflow.add_edge("__start__", "planner")

# Layer 2 → Layer 3: Planner → Validation
workflow.add_edge("planner", "validate")

# Layer 3: Analysis Pipeline
workflow.add_conditional_edges(
    "validate",
    should_continue_after_validation,
    {"analyze": "analyze", END: END}
)
workflow.add_edge("analyze", "verify")

# Layer 3 → Layer 5: Verification → Reflection
workflow.add_edge("verify", "reflection")

# Layer 5: Reflection → Report
workflow.add_conditional_edges(
    "reflection",
    should_continue_after_reflection,
    {"report": "report"}
)

# Exit: Report → End
workflow.add_edge("report", END)
```

## 🎯 Responsabilidades por Capa

### CAPA 1: INTERFACES

**Ubicación:** `src/agent/interfaces/`

| Componente   | Archivo            | Responsabilidad                       |
| ------------ | ------------------ | ------------------------------------- |
| Telegram Bot | `telegram_bot.py`  | Interfaz conversacional via Telegram  |
| REST API     | `api_interface.py` | Interfaz HTTP/REST para integraciones |

**Estado:** ✅ Implementado

---

### CAPA 2: PLANNER IA

**Ubicación:** `src/agent/nodes/planner.py`

**Responsabilidades:**

- Interpretar la consulta del usuario
- Determinar el tipo de auditoría necesaria
- Planificar qué validaciones ejecutar
- Preparar el estado para los nodos de análisis

**Prompt Guide:** `src/agent/prompts/planner_prompt.md`

**Estado:** ⚠️ Estructura lista, lógica pendiente de implementación

---

### CAPA 3: ANALYSIS NODES

**Ubicación:** `src/agent/nodes/`

| Nodo         | Archivo           | Responsabilidad                          |
| ------------ | ----------------- | ---------------------------------------- |
| Validation   | `validation.py`   | Valida DNI, nota y reglas de negocio     |
| Analysis     | `analysis.py`     | Análisis con LLM, detección de anomalías |
| Verification | `verification.py` | Genera hash criptográfico y timestamp    |

**Estado:** ✅ Implementado y funcionando

---

### CAPA 4: TOOLS

**Ubicación:** `src/agent/tools/`

| Tool       | Archivo         | Funcionalidad                        |
| ---------- | --------------- | ------------------------------------ |
| Crypto     | `crypto.py`     | Generación de hashes SHA-256         |
| Prompts    | `prompts.py`    | Construcción de prompts para LLM     |
| Dificultad | `dificultad.py` | Evaluación de dificultad de exámenes |
| Copia      | `copia.py`      | Backup y gestión de copias           |
| Tiempos    | `tiempos.py`    | Gestión de tiempos de examen         |
| Validación | `validacion.py` | Validaciones académicas              |

**Estado:** ✅ Implementado (6 herramientas disponibles)

---

### CAPA 5: REPORT + MEMORY

**Ubicación:** `src/agent/nodes/` y `src/agent/memory/`

| Componente     | Archivo             | Responsabilidad                      |
| -------------- | ------------------- | ------------------------------------ |
| Reflection     | `reflection.py`     | Auto-evaluación de resultados        |
| Report         | `report.py`         | Generación de reportes profesionales |
| Memory Manager | `memory_manager.py` | Gestión de historial y contexto      |

**Prompt Guide:** `src/agent/prompts/report_prompt.md`

**Estado:**

- Memory Manager: ✅ Implementado
- Reflection: ⚠️ Estructura lista, lógica pendiente
- Report: ⚠️ Estructura lista, lógica pendiente

---

## 🧪 Estado de Implementación

| Componente                 | Estado      | Próximos Pasos                      |
| -------------------------- | ----------- | ----------------------------------- |
| **Graph Architecture**     | ✅ Completo | Testing de flujo completo           |
| **Layer 1: Interfaces**    | ✅ Completo | -                                   |
| **Layer 2: Planner**       | ⚠️ Parcial  | Implementar lógica de planificación |
| **Layer 3: Analysis**      | ✅ Completo | -                                   |
| **Layer 4: Tools**         | ✅ Completo | -                                   |
| **Layer 5: Report/Memory** | ⚠️ Parcial  | Implementar reflection y report     |

## 🚀 Ventajas de la Arquitectura

### 1. **Modularidad**

Cada capa tiene responsabilidades claras y puede modificarse independientemente.

### 2. **Escalabilidad**

Fácil agregar nuevos nodos, herramientas o interfaces sin afectar otras capas.

### 3. **Mantenibilidad**

Código organizado por función, facilitando debugging y updates.

### 4. **Trazabilidad**

Cada paso del flujo está documentado y puede ser rastreado.

### 5. **Flexibilidad**

El routing condicional permite diferentes flujos según el resultado de cada nodo.

## 📚 Referencias

- **Graph Definition:** [`src/agent/graph/graph.py`](../src/agent/graph/graph.py)
- **State Schema:** [`src/agent/state/state.py`](../src/agent/state/state.py)
- **Node Implementations:** [`src/agent/nodes/`](../src/agent/nodes/)
- **Tools:** [`src/agent/tools/`](../src/agent/tools/)
- **Configuration:** [`src/agent/config/config.py`](../src/agent/config/config.py)

## 🔍 Testing del Flujo

Para probar el flujo completo:

```python
from agent.graph import graph
from agent.state import AcademicAuditState

# Crear estado inicial
state = AcademicAuditState(
    dni="12345678",
    nota=15
)

# Ejecutar el grafo
result = graph.invoke(state)

# El resultado pasa por:
# planner → validate → analyze → verify → reflection → report
```

## 📊 Métricas de Arquitectura

- **Total de Capas:** 5
- **Total de Nodos:** 6 (planner, validate, analyze, verify, reflection, report)
- **Total de Tools:** 6
- **Total de Interfaces:** 2 (Telegram + API)
- **Puntos de Decisión:** 2 (después de validation y reflection)

---

**Última Actualización:** 9 de marzo de 2026
**Versión:** 2.0 (Arquitectura de 5 Capas)
