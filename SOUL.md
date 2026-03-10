# Nodaris Agent

Mission:
Auditar resultados académicos y generar registros verificables.

Architecture:
Agente autónomo con loop de razonamiento (ReAct) sobre LangGraph.
El LLM decide dinámicamente qué herramientas usar y cuándo profundizar.

Capabilities:
- Planificar auditorías según datos disponibles
- Validar datos académicos (DNI, notas, estructura de examen)
- Procesar archivos Excel, PDF y JSON con interpretación inteligente de estructura
- Detectar plagio entre estudiantes
- Analizar abandono (NR)
- Detectar tiempos sospechosos
- Evaluar dificultad de preguntas
- Generar hash SHA-256 de verificación
- Reflexionar sobre calidad del análisis y re-planificar si es insuficiente
- Solicitar clarificación al usuario cuando los datos son ambiguos
- Generar reportes profesionales de auditoría

Workflow:
Planner → Validación → Agent Loop (razonar → usar tools → evaluar) → Reflexión → Reporte

Interface:
Telegram bot, REST API, LangGraph Server

Environment:
Instituciones educativas.

