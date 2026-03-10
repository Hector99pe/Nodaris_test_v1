# Nodaris Agent - Estructura

Agente LangGraph para auditoría académica con análisis OpenAI.

## 🎯 Misión

Auditar resultados académicos y generar registros verificables.

## 📁 Estructura del Código

```
src/agent/
├── __init__.py                  # Exportaciones principales
├── graph.py                     # Orquestador LangGraph (workflow principal)
├── state.py                     # Definiciones de estado compartido
├── config.py                    # Configuración centralizada
│
├── nodes/                       # Nodos del grafo (procesamiento)
│   ├── __init__.py
│   ├── validation.py            # Validación de datos académicos
│   ├── analysis.py              # Análisis con LLM (OpenAI)
│   └── verification.py          # Generación de hash SHA-256
│
├── tools/                       # Utilidades reutilizables
│   ├── __init__.py
│   ├── crypto.py                # Funciones de hashing
│   └── prompts.py               # Templates de prompts para LLM
│
└── nodaris_agent_legacy.py      # Implementación original (archivo)
```

## 🔄 Flujo del Grafo

```
START → validate → [si error] → END
                 ↓ [si ok]
               analyze → verify → END
```

1. **validate**: Verifica DNI y rango de nota (0-20)
2. **analyze**: Análisis con LLM usando OpenAI API
3. **verify**: Genera hash SHA-256 para verificación

## 🚀 Uso

### Probar localmente

```powershell
$env:PYTHONPATH='src'
python -c "import asyncio; from agent.graph import graph; print(asyncio.run(graph.ainvoke({'dni':'12345678','nota':15})))"
```

### Con LangGraph CLI

```bash
langgraph dev
```

## 🔧 Configuración (OpenAI)

### Variables de entorno (.env)

```bash
# OpenAI
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4
OPENAI_TEMPERATURE=0.3

# Telegram (futuro)
TELEGRAM_BOT_TOKEN=...

# LangSmith (opcional)
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=...
```

### Habilitar OpenAI API

Edita `src/agent/nodes/analysis.py` línea 15-25:

```python
# Reemplazar placeholder con:
from openai import AsyncOpenAI
from agent.config import Config

async def _invoke_llm(messages: list) -> Dict[str, str]:
    client = AsyncOpenAI(api_key=Config.OPENAI_API_KEY)
    response = await client.chat.completions.create(
        model=Config.OPENAI_MODEL,
        messages=messages,
        temperature=Config.OPENAI_TEMPERATURE
    )
    return {"content": response.choices[0].message.content}
```

Instalar dependencia:

```bash
pip install openai
```

## 📱 Integración Telegram (Roadmap)

Crear `src/agent/interfaces/telegram_bot.py`:

```python
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler
from agent.graph import graph

async def handle_grade(update: Update, context):
    # Parsear: /auditar <DNI> <NOTA>
    args = context.args
    result = await graph.ainvoke({'dni': args[0], 'nota': int(args[1])})
    await update.message.reply_text(f"✅ {result['analisis']}\n🔐 Hash: {result['hash']}")

app = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()
app.add_handler(CommandHandler("auditar", handle_grade))
```

## 🧪 Tests

```bash
pytest tests/unit_tests/          # Tests unitarios
pytest tests/integration_tests/   # Tests de integración
```

## 🏗️ Buenas Prácticas Implementadas

✅ **Separación de responsabilidades**: Cada nodo tiene una función clara
✅ **Configuración centralizada**: Un solo archivo `config.py`
✅ **Reutilización**: Tools compartidas (`crypto`, `prompts`)
✅ **Trazabilidad**: Decoradores `@traceable` de LangSmith
✅ **Escalabilidad**: Fácil agregar nuevos nodos al workflow
✅ **Imports robustos**: Fallback para desarrollo local
✅ **Tipos explícitos**: TypedDict, dataclass para estado

## 📋 Próximos Pasos

1. ✅ Estructura modular implementada
2. ⏳ Conectar OpenAI API real (reemplazar placeholder)
3. ⏳ Implementar interfaz Telegram
4. ⏳ Agregar persistencia de auditorías (base de datos)
5. ⏳ Dashboard de visualización de anomalías
6. ⏳ Sistema de alertas automáticas

---

**Ambiente**: Instituciones educativas
**Stack**: LangGraph + OpenAI + Python 3.11+

```json
{
  "examen": {
    "id": "EX001",
    "curso": "Programacion I",
    "codigo_curso": "PROG101",
    "fecha": "2026-03-09",
    "duracion_min": 60,
    "docente": {
      "dni": "45896321",
      "nombre": "Carlos",
      "apellido": "Ramirez"
    },
    "supervisores": [
      {
        "dni": "40125678",
        "nombre": "Laura",
        "apellido": "Gomez"
      },
      {
        "dni": "41789456",
        "nombre": "Miguel",
        "apellido": "Torres"
      }
    ],
    "respuestas_validas": ["A", "B", "C", "D", "NR"]
  },

  "preguntas": [
    { "id": 1, "tema": "fundamentos", "correcta": "B" },
    { "id": 2, "tema": "variables", "correcta": "A" },
    { "id": 3, "tema": "control", "correcta": "C" },
    { "id": 4, "tema": "estructuras", "correcta": "D" },
    { "id": 5, "tema": "funciones", "correcta": "A" },
    { "id": 6, "tema": "salida", "correcta": "B" },
    { "id": 7, "tema": "estructuras", "correcta": "C" },
    { "id": 8, "tema": "control", "correcta": "D" },
    { "id": 9, "tema": "algoritmos", "correcta": "A" },
    { "id": 10, "tema": "debugging", "correcta": "B" }
  ],

  "estudiantes": [
    {
      "id": "E01",
      "dni": "72014589",
      "nombre": "Juan",
      "apellido": "Perez",
      "semestre": 3
    },
    {
      "id": "E02",
      "dni": "73589621",
      "nombre": "Ana",
      "apellido": "Lopez",
      "semestre": 3
    },
    {
      "id": "E03",
      "dni": "74896521",
      "nombre": "Luis",
      "apellido": "Torres",
      "semestre": 3
    },
    {
      "id": "E04",
      "dni": "75632148",
      "nombre": "Maria",
      "apellido": "Diaz",
      "semestre": 3
    },
    {
      "id": "E05",
      "dni": "76985214",
      "nombre": "Pedro",
      "apellido": "Silva",
      "semestre": 3
    }
  ],

  "resultados": [
    {
      "estudiante_id": "E01",
      "tiempo_total_seg": 2700,
      "respuestas": ["B", "A", "C", "D", "A", "B", "C", "D", "A", "B"],
      "tiempo_pregunta_seg": [20, 25, 30, 35, 40, 22, 18, 25, 20, 30],
      "timestamp_inicio": "2026-03-09T10:00:00",
      "timestamp_fin": "2026-03-09T10:45:00"
    },

    {
      "estudiante_id": "E02",
      "tiempo_total_seg": 2800,
      "respuestas": ["B", "A", "C", "A", "A", "B", "C", "D", "A", "NR"],
      "tiempo_pregunta_seg": [18, 22, 28, 30, 35, 20, 17, 23, 21, 0],
      "timestamp_inicio": "2026-03-09T10:01:00",
      "timestamp_fin": "2026-03-09T10:47:00"
    },

    {
      "estudiante_id": "E03",
      "tiempo_total_seg": 2400,
      "respuestas": ["A", "A", "B", "D", "C", "B", "C", "D", "B", "B"],
      "tiempo_pregunta_seg": [10, 12, 15, 20, 18, 14, 13, 17, 11, 12],
      "timestamp_inicio": "2026-03-09T10:02:00",
      "timestamp_fin": "2026-03-09T10:40:00"
    },

    {
      "estudiante_id": "E04",
      "tiempo_total_seg": 2900,
      "respuestas": ["B", "C", "C", "D", "A", "A", "C", "D", "A", "B"],
      "tiempo_pregunta_seg": [25, 30, 35, 32, 28, 30, 29, 31, 27, 33],
      "timestamp_inicio": "2026-03-09T10:00:30",
      "timestamp_fin": "2026-03-09T10:48:50"
    },

    {
      "estudiante_id": "E05",
      "tiempo_total_seg": 2700,
      "respuestas": ["B", "A", "C", "D", "A", "B", "C", "D", "A", "B"],
      "tiempo_pregunta_seg": [19, 24, 29, 33, 38, 21, 17, 24, 19, 28],
      "timestamp_inicio": "2026-03-09T10:01:10",
      "timestamp_fin": "2026-03-09T10:45:20"
    }
  ]
}
```
