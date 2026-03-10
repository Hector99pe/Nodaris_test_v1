Sistema de Auditoría de Exámenes con IA

Este documento explica cómo funciona el formato de datos utilizado para auditar exámenes académicos mediante un sistema de inteligencia artificial.

El sistema recibe la información del examen a través de una API en formato JSON. Luego estos datos son analizados para detectar problemas como preguntas difíciles, posibles copias o respuestas inválidas.

1. Información del examen

La sección examen contiene los datos generales del examen.

Campos:

id → Identificador único del examen.

curso → Nombre del curso.

codigo_curso → Código académico del curso.

fecha → Fecha en la que se realizó el examen.

duracion_min → Duración del examen en minutos.

Ejemplo:

"examen": {
"id": "EX001",
"curso": "Programacion I",
"codigo_curso": "PROG101",
"fecha": "2026-03-09",
"duracion_min": 60
} 2. Información del docente

El objeto docente identifica al profesor responsable del examen.

Campos:

dni → Documento nacional de identidad.

nombre → Nombre del docente.

apellido → Apellido del docente.

Ejemplo:

"docente": {
"dni": "45896321",
"nombre": "Carlos",
"apellido": "Ramirez"
}

Esto permite identificar quién diseñó el examen para fines de auditoría académica.

3. Supervisores del examen

La sección supervisores contiene los docentes o personal encargado de vigilar el examen.

Campos:

dni

nombre

apellido

Ejemplo:

"supervisores": [
{
"dni": "40125678",
"nombre": "Laura",
"apellido": "Gomez"
}
]

Estos datos se utilizan en auditorías para verificar quién supervisó el proceso de evaluación.

4. Rango de respuestas válidas

El campo respuestas_validas define el rango de respuestas que el sistema acepta.

Ejemplo:

"respuestas_validas": ["A","B","C","D","NR"]

Significado:

A → opción A

B → opción B

C → opción C

D → opción D

NR → No Respondió

Si el sistema recibe otra respuesta, se genera una alerta de auditoría.

5. Preguntas del examen

La sección preguntas contiene las preguntas del examen.

Campos:

id → número de pregunta

tema → tema académico

correcta → respuesta correcta

Ejemplo:

{
"id":1,
"tema":"fundamentos",
"correcta":"B"
}

Esto permite analizar:

dificultad de la pregunta

rendimiento por tema

calidad del examen

6. Información de estudiantes

La sección estudiantes contiene los datos básicos de cada alumno.

Campos:

id → identificador interno

dni → documento de identidad

nombre

apellido

semestre

Ejemplo:

{
"id": "E01",
"dni": "72014589",
"nombre": "Juan",
"apellido": "Perez",
"semestre": 3
}

Estos datos permiten identificar quién realizó el examen.

7. Resultados del examen

La sección resultados contiene las respuestas de cada estudiante.

Campos:

estudiante_id → referencia al estudiante

tiempo_total_seg → tiempo total del examen

respuestas → respuestas del estudiante

tiempo_pregunta_seg → tiempo que tardó en cada pregunta

timestamp_inicio → hora de inicio

timestamp_fin → hora de finalización

Ejemplo:

{
"estudiante_id": "E01",
"tiempo_total_seg": 2700,
"respuestas": ["B","A","C","D","A","B","C","D","A","B"]
} 8. Qué analiza el sistema

Con esta estructura el sistema puede analizar:

Dificultad de preguntas

Calculando cuántos estudiantes respondieron correctamente.

Respuestas no respondidas

Detectando valores NR.

Respuestas fuera del rango

Comparando con respuestas_validas.

Posible copia

Comparando patrones de respuestas entre estudiantes.

Comportamientos sospechosos

Analizando tiempos de respuesta por pregunta.

9. Flujo del sistema

El flujo del sistema es el siguiente:

El sistema de examen envía los datos mediante API.

La API recibe el JSON.

Los datos se validan.

El motor de auditoría analiza los resultados.

El sistema genera alertas si detecta anomalías.

Se genera un reporte final para supervisores y directores.

10. Uso con IA

El sistema puede utilizar agentes de inteligencia artificial para:

analizar calidad de preguntas

detectar patrones de copia

generar reportes automáticos

sugerir mejoras en evaluaciones

Esto permite realizar auditorías académicas automáticas en grandes cantidades de exámenes.
