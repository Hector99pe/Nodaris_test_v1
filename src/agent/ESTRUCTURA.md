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
