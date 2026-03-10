# 🔧 Qué Hace Cada Componente - Guía Funcional

## ✅ Implementación Completa

Todos los componentes están implementados con lógica funcional.

---

## 1️⃣ INTERFACE LAYER

**Ubicación:** `src/agent/interfaces/`

### 📱 Telegram Bot (`telegram_bot.py`)

- **Función:** Interfaz conversacional para usuarios
- **Recibe:**
  - Comandos: `/auditar`, `/start`, `/ayuda`
  - DNI y nota de estudiantes
  - Consultas en lenguaje natural
- **Devuelve:** Reportes de auditoría formateados

### 🌐 API Interface (`api_interface.py`)

- **Función:** API REST para integraciones
- **Recibe:**
  - POST `/audit` con datos académicos
  - GET `/health` para health checks
- **Devuelve:** JSON con resultados de auditoría

**Ejemplo de entrada:**

```json
{
  "exam_data": {
    "titulo": "Examen de Matemáticas",
    "preguntas": [...]
  },
  "students_data": [
    {"dni": "12345678", "respuestas": ["...", "..."]},
    {"dni": "87654321", "respuestas": ["...", "..."]}
  ]
}
```

---

## 2️⃣ PLANNER NODE (IA)

**Archivo:** `src/agent/nodes/planner.py`

### 🎯 Función Principal

El Planner **decide qué análisis ejecutar** basándose en los datos disponibles.

### 📋 Decisiones que Toma

| Condición Detectada         | Análisis Activado     |
| --------------------------- | --------------------- |
| Múltiples estudiantes (≥2)  | `detectar_copia`      |
| Respuestas vacías/NR        | `analizar_abandono`   |
| Datos de tiempo disponibles | `analizar_tiempos`    |
| Preguntas en exam_data      | `evaluar_dificultad`  |
| Solo DNI + nota             | `individual_analysis` |

### 🔄 Flujo de Decisión

```python
if hay_multiples_estudiantes:
    ✓ ejecutar detectar_copia

if hay_respuestas_vacias:
    ✓ ejecutar analizar_abandono

if hay_datos_tiempo:
    ✓ ejecutar analizar_tiempos

if hay_preguntas:
    ✓ ejecutar evaluar_dificultad
```

### 📤 Output

- `state.plan`: Descripción del plan de auditoría
- `state.analysis_to_run`: Lista de análisis a ejecutar
- `state.status`: "planned"

**Ejemplo de plan generado:**

```
📊 Modo: Auditoría de examen completo
🔍 Detectar copias entre 30 estudiantes
⚠️ Analizar abandono (NR)
📝 Evaluar dificultad de 20 preguntas

📋 Análisis a ejecutar: validation, detectar_copia, analizar_abandono, evaluar_dificultad
```

---

## 3️⃣ ANALYSIS NODES

**Ubicación:** `src/agent/nodes/`

### ✅ Validation Node (`validation.py`)

**Función:** Valida la integridad de los datos

**Validaciones:**

- DNI: 8 dígitos numéricos
- Nota: Rango 0-20
- Estructura de datos de examen
- Consistencia de respuestas

**Output:**

```python
state.status = "ok" | "error"
state.mensaje = "Validación exitosa" | "DNI inválido"
```

---

### 🤖 Analysis Node (`analysis.py`)

**Función:** Análisis con LLM (OpenAI)

**Analiza:**

- Clasificación de resultados académicos
- Detección de patrones inusuales
- Observaciones cualitativas
- Alertas de anomalías

**Usa:** `tools/prompts.py` para construir prompts

**Output:**

```python
state.analisis = "Análisis LLM completo..."
state.anomalia_detectada = True | False
```

---

### 🔐 Verification Node (`verification.py`)

**Función:** Genera hash criptográfico para trazabilidad

**Genera:**

- Hash SHA-256 de los datos
- Timestamp de la auditoría
- Registro inmutable

**Usa:** `tools/crypto.py`

**Output:**

```python
state.hash = "a3f5b2c8..."
state.timestamp = "2026-03-09T15:30:00"
```

---

## 4️⃣ TOOLS (Herramientas)

**Ubicación:** `src/agent/tools/`

Los nodos usan estas herramientas reutilizables.

### 🔍 detectar_copia.py

**Función:** Detecta plagio entre estudiantes

```python
from agent.tools import detectar_copia

copias = detectar_copia(respuestas_estudiantes, umbral_similitud=0.85)
# Retorna: [{"estudiante1": "...", "estudiante2": "...", "similitud_promedio": 0.92, ...}]
```

**Algoritmo:**

1. Compara respuestas de cada par de estudiantes
2. Calcula similitud de texto (SequenceMatcher)
3. Si ≥2 preguntas similares → Flag como posible copia
4. Clasifica: ALTO riesgo (>95% similitud) o MEDIO

**Output:**

```python
{
  "estudiante1": "12345678",
  "estudiante2": "87654321",
  "preguntas_similares": 5,
  "similitud_promedio": 0.92,
  "nivel_sospecha": "ALTO"
}
```

---

### ⚠️ analizar_abandono.py

**Función:** Identifica estudiantes que no respondieron (NR)

```python
from agent.tools import identificar_nr, analizar_abandono

nr_cases = identificar_nr(respuestas_estudiantes, umbral_vacias=0.5)
analysis = analizar_abandono(nr_cases, total_estudiantes=30)
```

**Detecta:**

- Respuestas vacías
- Textos "NR", "No respondió"
- Respuestas muy cortas (<5 caracteres)

**Clasifica:**

- **ABANDONO_TOTAL:** >80% respuestas vacías
- **ABANDONO_PARCIAL:** 50-80% respuestas vacías

**Output:**

```python
{
  "total_nr": 5,
  "abandono_total": 2,
  "tasa_abandono": 16.7,
  "nivel": "MEDIO",
  "recomendaciones": ["Investigar causas..."]
}
```

---

### ⏱️ tiempos.py

**Función:** Analiza tiempos de respuesta

```python
from agent.tools import calcular_tiempo_restante, validar_tiempo_examen

tiempo_info = calcular_tiempo_restante(hora_inicio, duracion_minutos)
validacion = validar_tiempo_examen(duracion=90, tipo_examen="parcial")
```

**Detecta:**

- Respuestas demasiado rápidas
- Respuestas demasiado lentas
- Patrones anómalos de timing

---

### 📊 dificultad.py

**Función:** Evalúa dificultad de preguntas

```python
from agent.tools import evaluar_dificultad

dificultad = evaluar_dificultad(pregunta="...", tema="álgebra")
# Retorna: {"nivel": "medio", "justificacion": "..."}
```

**Niveles:**

- FÁCIL
- MEDIO
- DIFÍCIL
- MUY_DIFÍCIL

---

### ✔️ validacion.py

**Función:** Validaciones académicas

```python
from agent.tools import validar_dni, validar_nota, validar_estructura_examen

valido, error = validar_dni("12345678")
valido, error = validar_nota(15, escala_min=0, escala_max=20)
resultado = validar_estructura_examen(exam_data)
```

---

### 📁 copia.py

**Función:** Backup y gestión de copias

```python
from agent.tools import copiar_examen, respaldar_datos

resultado = copiar_examen("exam.json", "exam_backup.json")
backup = respaldar_datos(datos, "auditoria_2026")
```

---

### 🔐 crypto.py

**Función:** Generación de hashes

```python
from agent.tools import generate_verification_hash

hash_value = generate_verification_hash(data_dict)
# Retorna: "a3f5b2c8d9e1f4..."
```

---

### 💬 prompts.py

**Función:** Construcción de prompts para LLM

```python
from agent.tools import build_audit_prompt

messages = build_audit_prompt(dni="12345678", nota=15)
# Retorna: [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]
```

---

## 5️⃣ REFLECTION NODE

**Archivo:** `src/agent/nodes/reflection.py`

### 🔎 Función Principal

El agente **revisa su propio análisis** para asegurar calidad.

### ✅ Verificaciones

| Aspecto              | Pregunta                                              | Acción                     |
| -------------------- | ----------------------------------------------------- | -------------------------- |
| **Evidencia**        | ¿Hay suficiente evidencia para las copias detectadas? | Calcula nivel de confianza |
| **Consistencia**     | ¿Los datos son consistentes entre sí?                 | Identifica inconsistencias |
| **Completitud**      | ¿Se ejecutaron todos los análisis planeados?          | Verifica plan vs ejecución |
| **Falsos positivos** | ¿Las anomalías están bien fundamentadas?              | Reduce confianza si dudoso |

### 📊 Output

```python
state.reflection_notes = """
✓ Detectadas 3 posibles copias
  - 2 casos de alto riesgo con evidencia fuerte
✓ Identificados 5 estudiantes con abandono
✓ Ejecutados 4 análisis según plan

📊 Calidad del análisis: BUENA
📈 Nivel de confianza: 87%
"""

state.confidence_score = 0.87
```

### 🎯 Ejemplo: Prevención de Falsos Positivos

```
Copias detectadas: 2
¿Alto riesgo? Solo 1
→ Confianza reducida a 60%
→ Recomendación: "Verificar manualmente"
```

---

## 6️⃣ REPORT GENERATOR

**Archivo:** `src/agent/nodes/report.py`

### 📄 Función Principal

Genera el **reporte final profesional** de la auditoría.

### 📋 Estructura del Reporte

```
======================================================================
              📊 REPORTE DE AUDITORÍA ACADÉMICA
======================================================================

🕐 Fecha: 2026-03-09T15:30:00
🔐 Hash de verificación: a3f5b2c8...

──────────────────────────────────────────────────────────────────────
📋 RESUMEN EJECUTIVO
──────────────────────────────────────────────────────────────────────

Tipo: Auditoría de examen completo
Estudiantes analizados: 30
Examen: Matemáticas 101 - Álgebra

Estado: ✅ OK
Mensaje: Auditoría completada exitosamente

──────────────────────────────────────────────────────────────────────
📊 ESTADÍSTICAS
──────────────────────────────────────────────────────────────────────

Promedio general: 14.5
Clasificación: Bueno
Preguntas difíciles: 3

Distribución de notas:
  0-10:   5 ██
  11-13: 10 █████
  14-16: 12 ██████
  17-20:  3 █

──────────────────────────────────────────────────────────────────────
🔍 HALLAZGOS PRINCIPALES
──────────────────────────────────────────────────────────────────────

🔍 DETECCIÓN DE COPIAS

Total de casos sospechosos: 2
  🔴 Caso 1: 12345678 ↔ 23456789
     Similitud: 92.0% en 5 preguntas
  🟡 Caso 2: 34567890 ↔ 45678901
     Similitud: 87.0% en 3 preguntas

⚠️ ABANDONO (NR)

Estudiantes con respuestas vacías: 5
  • 56789012
  • 67890123
  • ...

──────────────────────────────────────────────────────────────────────
🤖 ANÁLISIS DETALLADO
──────────────────────────────────────────────────────────────────────

[Análisis LLM completo aquí...]

──────────────────────────────────────────────────────────────────────
🔎 EVALUACIÓN DE CALIDAD
──────────────────────────────────────────────────────────────────────

✓ Detectadas 2 posibles copias
  - 1 casos de alto riesgo con evidencia fuerte
✓ Identificados 5 estudiantes con abandono
✓ Ejecutados 4 análisis según plan

📊 Calidad del análisis: BUENA
📈 Nivel de confianza: 85%

──────────────────────────────────────────────────────────────────────
💡 RECOMENDACIONES
──────────────────────────────────────────────────────────────────────

• URGENTE: Investigar casos de copia de alto riesgo
• Revisar manualmente las respuestas similares detectadas
• Realizar seguimiento con estudiantes que no respondieron

======================================================================
                  Confianza del análisis: 85%
              Generado por Nodaris Academic Auditor
======================================================================
```

### 📤 Output

```python
state.reporte_final = "[Reporte completo formateado]"
state.status = "completed"
```

---

## 7️⃣ MEMORY

**Archivo:** `src/agent/memory/memory_manager.py`

### 💾 Función Principal

Guarda auditorías anteriores para análisis histórico.

### 📚 Usos

#### 1. Detectar Patrones Históricos

```python
from agent.memory import MemoryManager

memory = MemoryManager()
memory.add_entry(
    user_input="Auditar examen 2026-Q1",
    agent_response="Reporte...",
    context={"exam_id": "math_2026_q1", "copias": 3}
)

# Recuperar historial
recent = memory.get_recent(n=5)
```

#### 2. Comparar Resultados

```python
# Obtener contexto de auditorías previas
context = memory.get_context_summary()
# "En las últimas 3 auditorías se detectaron copias en promedio de 2.3 casos..."
```

#### 3. Trazabilidad

- Cada auditoría se guarda con timestamp
- Permite rastrear evolución de patrones
- Facilita auditorías de auditorías

### 📊 Estructura de Memoria

```python
{
    "timestamp": "2026-03-09T15:30:00",
    "user_input": "Auditar examen de matemáticas",
    "agent_response": "Reporte generado...",
    "context": {
        "exam_id": "math_101",
        "students": 30,
        "copias": 2,
        "promedio": 14.5
    }
}
```

---

## 🔄 Flujo Completo de Ejemplo

### Entrada:

```json
{
  "exam_data": {
    "titulo": "Matemáticas 101",
    "preguntas": [...]
  },
  "students_data": [
    {"dni": "12345678", "respuestas": ["x=4", "6", "NR"]},
    {"dni": "87654321", "respuestas": ["x=4", "6", "10"]}
  ]
}
```

### Procesamiento:

1. **Planner:** Detecta 2 estudiantes → Activa `detectar_copia` y `analizar_abandono`
2. **Validation:** Valida DNIs y estructura ✓
3. **Analysis:** LLM analiza patrones
4. **Verification:** Genera hash `a3f5`
5. **Planner ejecuta tools:**
   - `detectar_copia()` → 92% similitud en 2 respuestas
   - `identificar_nr()` → 1 estudiante con NR
6. **Reflection:** Confianza 85% - Buena calidad
7. **Report:** Genera reporte profesional
8. **Memory:** Guarda para historial

### Salida:

```
Reporte completo con:
- Similitud del 92% entre estudiantes
- 1 caso de abandono (NR)
- Recomendaciones de acción
- Hash de verificación
```

---

## 📊 Resumen de Componentes

| Componente       | Función                       | Input           | Output                 |
| ---------------- | ----------------------------- | --------------- | ---------------------- |
| **Interfaces**   | Recibir datos                 | API/Telegram    | State inicial          |
| **Planner**      | Decidir análisis              | State           | plan + analysis_to_run |
| **Validation**   | Validar datos                 | State           | status ok/error        |
| **Analysis**     | Analizar con LLM              | State + prompts | analisis               |
| **Verification** | Generar hash                  | State           | hash + timestamp       |
| **Tools**        | Ejecutar análisis específicos | Datos           | Resultados detallados  |
| **Reflection**   | Evaluar calidad               | State completo  | confidence_score       |
| **Report**       | Generar reporte               | State completo  | reporte_final          |
| **Memory**       | Guardar historial             | All audits      | Contexto histórico     |

---

**Todos los componentes están implementados y funcionales** ✅
