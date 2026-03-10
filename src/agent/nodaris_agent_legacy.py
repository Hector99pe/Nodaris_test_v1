import hashlib
import asyncio

from langsmith import traceable


@traceable(name="formatPrompt")
def format_prompt(subject):
    return [
        {"role": "system", "content": "Eres un auditor academico."},
        {"role": "user", "content": subject},
    ]


@traceable(run_type="llm", name="invokeLLM")
async def invoke_llm(messages):
    # Placeholder de LLM: mantiene el pipeline funcional sin proveedor externo.
    return {
        "content": f"Analisis preliminar generado para: {messages[-1]['content']}"
    }


@traceable(name="parseOutput")
def parse_output(response):
    return response.get("content", "")


@traceable(name="runPipeline")
async def run_pipeline(subject):
    messages = format_prompt(subject)
    response = await invoke_llm(messages)
    return parse_output(response)

@traceable(name="nodarisAgentAsync")
async def nodaris_agent_async(dni, nota):

    # validar resultado
    if nota < 0 or nota > 20:
        return {
            "status": "error",
            "mensaje": "nota invalida"
        }

    # generar hash
    texto = dni + str(nota)
    hash_value = hashlib.sha256(texto.encode()).hexdigest()
    analisis = await run_pipeline(f"dni={dni}, nota={nota}")

    return {
        "status": "ok",
        "dni": dni,
        "nota": nota,
        "hash": hash_value,
        "analisis": analisis
    }


def nodaris_agent(dni, nota):
    # Wrapper sincronico para usos fuera de contextos async.
    return asyncio.run(nodaris_agent_async(dni, nota))
