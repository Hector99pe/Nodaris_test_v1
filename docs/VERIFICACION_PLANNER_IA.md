# ✅ Verificación: Planner IA Real + Graph Implementados

## Estado: Implementación Completa

### 1. ✅ Planner IA Real con LLM

**Ubicación:** [src/agent/nodes/planner.py](../src/agent/nodes/planner.py)

**Implementación:**

```python
from langchain_openai import ChatOpenAI
from agent.config import Config

# Initialize LLM for intelligent planning
llm = ChatOpenAI(
    model=Config.OPENAI_MODEL,
    temperature=0.0,  # Deterministic for planning
    api_key=Config.OPENAI_API_KEY
)

@traceable(name="plannerNode")
def planner_node(state: AcademicAuditState) -> AcademicAuditState:
    """Plan the execution workflow using LLM reasoning.

    Uses ChatOpenAI to intelligently decide which analyses to run based on:
    - Available data (exam_data, students_data, dni/nota)
    - Data characteristics (number of students, timing info, etc.)
    - Audit objectives
    """
    # Build context for LLM
    context = {
        "has_exam_data": bool(state.exam_data),
        "has_students_data": bool(state.students_data),
        "has_individual_data": bool(state.dni),
        "num_students": len(state.students_data) if state.students_data else 0,
        "has_timing_data": False,
        "has_questions": False,
        "has_empty_responses": False
    }

    # ... analyze data characteristics ...

    # Build LLM prompt
    prompt = f"""You are an intelligent academic audit planner. Analyze the context and decide which analyses should run.

**Available Analyses:**
- validation: Validate data structure and integrity
- basic_statistics: Calculate basic exam statistics
- grade_analysis: Analyze grade distribution
- detectar_copia: Detect plagiarism between students (requires ≥2 students)
- analizar_abandono: Analyze student abandonment (NR/empty responses)
- analizar_tiempos: Analyze suspicious timing patterns
- evaluar_dificultad: Evaluate question difficulty
- individual_analysis: Individual student audit

**Context:**
{json.dumps(context, indent=2)}

**Rules:**
1. Always include "validation" first
2. For full exam audits: include basic_statistics and grade_analysis
3. Only include detectar_copia if num_students >= 2
4. Only include analizar_abandono if has_empty_responses is true
5. Only include analizar_tiempos if has_timing_data is true
6. Only include evaluar_dificultad if has_questions is true
7. For individual audits: include individual_analysis

**Output Format (JSON only):**
{{
  "mode": "full_exam" or "individual",
  "analysis_to_run": ["list", "of", "analyses"],
  "reasoning": "brief explanation"
}}
"""

    try:
        # Invoke LLM
        response = llm.invoke(prompt)
        response_text = response.content.strip()

        # Parse LLM response
        plan_data = json.loads(response_text)

        analysis_to_run = plan_data.get("analysis_to_run", ["validation"])
        mode = plan_data.get("mode", "unknown")
        reasoning = plan_data.get("reasoning", "Plan generado por IA")

    except Exception as e:
        # Fallback to rule-based planning if LLM fails
        analysis_to_run = ["validation"]
        # ... simple rule-based fallback ...
```

**Características:**
✅ Usa `ChatOpenAI` de `langchain-openai`
✅ Configurado con `Config.OPENAI_MODEL` (gpt-4o-mini por defecto)
✅ Temperature=0.0 para decisiones determinísticas
✅ Prompt estructurado con reglas claras
✅ Parseo de respuesta JSON del LLM
✅ Fallback a lógica basada en reglas si el LLM falla
✅ Razonamiento explicable (campo "reasoning")

---

### 2. ✅ Graph con Planner

**Ubicación:** [src/agent/graph/graph.py](../src/agent/graph/graph.py)

**Implementación:**

```python
from langgraph.graph import StateGraph, END

# Build workflow
workflow = StateGraph(AcademicAuditState, context_schema=Context)

# LAYER 2: PLANNER IA
workflow.add_node("planner", planner_node)

# LAYER 3: ANALYSIS NODES
workflow.add_node("validate", validate_academic_data)
workflow.add_node("analyze", analyze_with_llm)
workflow.add_node("verify", generate_verification)

# LAYER 5: REFLECTION & REPORT
workflow.add_node("reflection", reflection_node)
workflow.add_node("report", report_node)

# Define Workflow Edges (5-Layer Flow)
workflow.add_edge("__start__", "planner")      # Entry point
workflow.add_edge("planner", "validate")
workflow.add_conditional_edges(
    "validate",
    should_continue_after_validation,
    {
        "analyze": "analyze",
        "__end__": END
    }
)
workflow.add_edge("analyze", "verify")
workflow.add_edge("verify", "reflection")
workflow.add_conditional_edges(
    "reflection",
    should_continue_after_reflection,
    {
        "report": "report",
    }
)
workflow.add_edge("report", END)

# Compile graph
graph = workflow.compile(name="Nodaris Academic Auditor")
```

**Flujo Completo:**

```
__start__
    ↓
planner (IA con LLM)
    ↓
validate
    ↓ (conditional)
analyze
    ↓
verify
    ↓
reflection
    ↓ (conditional)
report
    ↓
__end__
```

**Características:**
✅ Entry point: `__start__ → planner`
✅ Planner como primer nodo (Layer 2)
✅ Conditional routing después de validation y reflection
✅ Arquitectura de 5 capas completa
✅ Compilado con nombre "Nodaris Academic Auditor"

---

## Ejemplo de Uso

### Caso 1: Auditoría de Examen Completo

**Input:**

```python
from agent.state import AcademicAuditState
from agent.graph.graph import graph

state = AcademicAuditState(
    exam_data={
        "id": "EX001",
        "curso": "Programacion I",
        "preguntas": [
            {"id": 1, "tema": "fundamentos", "correcta": "B"},
            {"id": 2, "tema": "variables", "correcta": "A"}
        ]
    },
    students_data=[
        {
            "dni": "72014589",
            "nombre": "Juan Perez",
            "respuestas": ["B", "A"],
            "tiempo_total": 1800
        },
        {
            "dni": "73589621",
            "nombre": "Ana Lopez",
            "respuestas": ["B", "A"],
            "tiempo_total": 1750
        }
    ]
)

result = graph.invoke(state)
```

**Planner IA Output:**

```json
{
  "mode": "full_exam",
  "analysis_to_run": [
    "validation",
    "basic_statistics",
    "grade_analysis",
    "detectar_copia",
    "evaluar_dificultad",
    "analizar_tiempos"
  ],
  "reasoning": "Examen completo con 2 estudiantes. Se detectó data de timing y preguntas. Se incluye detección de copia ya que hay ≥2 estudiantes."
}
```

### Caso 2: Auditoría Individual

**Input:**

```python
state = AcademicAuditState(
    dni="72014589",
    nota=15
)

result = graph.invoke(state)
```

**Planner IA Output:**

```json
{
  "mode": "individual",
  "analysis_to_run": ["validation", "individual_analysis"],
  "reasoning": "Auditoría individual con DNI y nota. No hay datos de examen completo disponibles."
}
```

---

## Dependencias Instaladas

```bash
pip install langchain-openai
```

**Paquetes requeridos:**

- `langchain-openai`: Para ChatOpenAI
- `openai`: Cliente de OpenAI (dependencia de langchain-openai)
- `langchain-core`: Core de LangChain
- `langgraph`: Para StateGraph

---

## Variables de Entorno Requeridas

En `.env`:

```env
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
OPENAI_TEMPERATURE=0.3
```

---

## Comparación: Antes vs Ahora

### ❌ Antes (Rule-Based)

```python
def planner_node(state):
    analysis_to_run = []

    if state.exam_data or state.students_data:
        analysis_to_run.extend(["validation", "basic_statistics"])

        if len(state.students_data) >= 2:
            analysis_to_run.append("detectar_copia")
    else:
        analysis_to_run.extend(["validation", "individual_analysis"])

    return state
```

### ✅ Ahora (LLM-Based)

```python
def planner_node(state):
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.0)

    prompt = f"""Decide which analyses should run.
Available: {available_analyses}
Context: {context}
Output JSON: {{"mode": "...", "analysis_to_run": [...], "reasoning": "..."}}
"""

    response = llm.invoke(prompt)
    plan_data = json.loads(response.content)

    # Use LLM decision
    analysis_to_run = plan_data["analysis_to_run"]
    reasoning = plan_data["reasoning"]

    return state
```

---

## Ventajas del Planner IA Real

1. **🧠 Inteligencia Adaptativa:** El LLM puede adaptar las decisiones a contextos complejos
2. **📝 Razonamiento Explicable:** Cada plan incluye el razonamiento del LLM
3. **🔄 Fácil Extensión:** Agregar nuevos análisis solo requiere actualizar el prompt
4. **🛡️ Fallback Robusto:** Si el LLM falla, usa lógica basada en reglas
5. **🎯 Decisiones Contextuales:** Puede considerar múltiples factores simultáneamente

---

## Testing

Para probar el planner con LLM:

```python
from agent.nodes.planner import planner_node
from agent.state import AcademicAuditState

# Test case
state = AcademicAuditState(
    exam_data={"id": "EX001", "preguntas": [...]},
    students_data=[{"dni": "123", "respuestas": [...]}]
)

result = planner_node(state)

print(f"Plan: {result.plan}")
print(f"Analysis to run: {result.analysis_to_run}")
```

---

## ✅ Conclusión

**Ambos componentes están completamente implementados:**

1. ✅ **Planner IA Real:** Usa `ChatOpenAI` para decisiones inteligentes
2. ✅ **Graph con Planner:** Entry point configurado como `__start__ → planner`

El sistema ahora tiene un **planner inteligente** que usa razonamiento de LLM para decidir qué análisis ejecutar, con fallback a lógica basada en reglas para máxima robustez.
