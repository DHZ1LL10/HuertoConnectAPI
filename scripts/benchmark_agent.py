"""Opt-in benchmark: local text model, no database, no emails, no private prompts."""
import argparse
import asyncio
from pathlib import Path
import sys
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent-service"))
from app.config import get_settings
from app.providers.ollama import OllamaProvider
from app.service import GenerationService


async def measure(model=None):
    config = get_settings()
    if model:
        config.ollama_model = model
    provider = OllamaProvider(config)
    service = GenerationService(config, provider)
    try:
        await provider.warm()
        for question in ("Como cultivo jitomate en maceta?", "Mi huerto tiene suelo encharcado, debo fertilizar?", "Veo manchas amarillas en hojas de limon, confirma si es HLB"):
            start = perf_counter()
            result = await service.generate(question, [])
            print({"modelo": model or config.ollama_model, "seconds": round(perf_counter()-start, 2),
                   "status": result["status"], "question": question, "answer": result["answer"]}, flush=True)
    finally:
        await provider.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", help="Modelo instalado a probar, sin cambiar la configuración del servicio")
    asyncio.run(measure(parser.parse_args().model))
