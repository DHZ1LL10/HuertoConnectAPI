"""
test_agent.py - QA Audit Script para el Agent Service de Huerto Connect
=======================================================================
Prueba el flujo completo:
  Frontend -> Gateway (:8000) -> /api/agent -> agent-service (:8006) -> Ollama (gemma3:4b)

Uso:
  pip install requests
  python test_agent.py
"""

import io
import json
import sys
import time

# Forzar UTF-8 en stdout para evitar UnicodeEncodeError en terminales Windows (cp1252)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import requests

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────────────────────────────────────────
GATEWAY_BASE_URL = "http://localhost:8000"
AGENT_DIRECT_URL = "http://localhost:8006"   # directo al agente (sin gateway)

# La API Key que configuramos en docker-compose environment.APP_API_KEY
API_KEY = "development-only-change-this-api-key-1234567890"

# ID de usuario simulado (debe coincidir con el patrón: [A-Za-z0-9._:@-]+)
TEST_USER_ID = "qa-tester-01"

HEADERS = {
    "Content-Type": "application/json",
    "X-API-Key": API_KEY,
    "X-User-ID": TEST_USER_ID,
}

SEP = "-" * 65


def print_section(title: str) -> None:
    print(f"\n{SEP}")
    print(f"  {title}")
    print(SEP)


def pretty_json(data: dict) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False)


# ─────────────────────────────────────────────────────────────────────────────
# TEST 1: Gateway health check
# ─────────────────────────────────────────────────────────────────────────────
def test_gateway_health() -> bool:
    print_section("TEST 1 — Gateway Health Check")
    url = f"{GATEWAY_BASE_URL}/api/health"
    print(f"GET {url}")
    try:
        r = requests.get(url, timeout=10)
        print(f"Status: {r.status_code}")
        print(pretty_json(r.json()))
        ok = r.status_code == 200
        print(f"{'✅ PASS' if ok else '❌ FAIL'}")
        return ok
    except requests.exceptions.ConnectionError:
        print("❌ FAIL — Gateway no responde en puerto 8000. ¿Está corriendo?")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# TEST 2: Agent liveness directo (sin pasar por gateway)
# ─────────────────────────────────────────────────────────────────────────────
def test_agent_live_direct() -> bool:
    print_section("TEST 2 — Agent Liveness (directo :8006)")
    url = f"{AGENT_DIRECT_URL}/health/live"
    print(f"GET {url}")
    try:
        r = requests.get(url, timeout=10)
        print(f"Status: {r.status_code}")
        print(pretty_json(r.json()))
        ok = r.status_code == 200
        print(f"{'✅ PASS' if ok else '❌ FAIL'}")
        return ok
    except requests.exceptions.ConnectionError:
        print("❌ FAIL — agent-service no responde en puerto 8006.")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# TEST 3: Agent readiness directo (verifica Ollama + base de datos)
# ─────────────────────────────────────────────────────────────────────────────
def test_agent_ready_direct() -> bool:
    print_section("TEST 3 — Agent Readiness / Ollama Check (directo :8006)")
    url = f"{AGENT_DIRECT_URL}/health/ready"
    print(f"GET {url}")
    try:
        r = requests.get(url, timeout=15)
        print(f"Status: {r.status_code}")
        print(pretty_json(r.json()))
        ok = r.status_code == 200
        if not ok:
            print("⚠️  Ollama o la BD no están listos. Revisa:")
            print("    • ollama serve  (¿está corriendo Ollama en tu host?)")
            print("    • ollama pull gemma3:4b  (¿está descargado el modelo?)")
        print(f"{'✅ PASS' if ok else '❌ FAIL (ver advertencia arriba)'}")
        return ok
    except requests.exceptions.ConnectionError:
        print("❌ FAIL — agent-service no responde.")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# TEST 4: Chat a través del GATEWAY (flujo completo)
# ─────────────────────────────────────────────────────────────────────────────
def test_chat_via_gateway() -> str | None:
    print_section("TEST 4 — Chat via Gateway (flujo completo)")
    url = f"{GATEWAY_BASE_URL}/api/agent/v1/chat"
    payload = {
        "message": "Hola, ¿cuál es tu función en este huerto?",
        "conversation_id": None,
    }
    print(f"POST {url}")
    print(f"Headers: X-User-ID={TEST_USER_ID}, X-API-Key=***")
    print(f"Body: {pretty_json(payload)}")
    print("\n⏳ Esperando respuesta de Ollama (puede tardar hasta 2 min)...")

    start = time.time()
    try:
        r = requests.post(url, json=payload, headers=HEADERS, timeout=180)
        elapsed = time.time() - start
        print(f"\nTiempo de respuesta: {elapsed:.2f}s")
        print(f"Status: {r.status_code}")
        data = r.json()
        print(pretty_json(data))

        ok = r.status_code == 200 and data.get("status") in ("answered", "redirected")
        print(f"\n{'✅ PASS' if ok else '❌ FAIL'}")

        if ok:
            print(f"\n🤖 Respuesta de Brot ({data.get('model', 'modelo desconocido')}):")
            print(f'   "{data.get("answer")}"')
            return data.get("conversation_id")
        return None
    except requests.exceptions.Timeout:
        print("❌ TIMEOUT — Ollama tardó más de 3 minutos. Revisa los recursos del modelo.")
        return None
    except requests.exceptions.ConnectionError:
        print("❌ FAIL — Gateway no responde.")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# TEST 5: Continuidad de conversación (mismo conversation_id)
# ─────────────────────────────────────────────────────────────────────────────
def test_conversation_continuity(conversation_id: str) -> bool:
    print_section("TEST 5 — Continuidad de Conversación")
    if not conversation_id:
        print("⏭️  SKIP — No hay conversation_id del test anterior.")
        return False

    url = f"{GATEWAY_BASE_URL}/api/agent/v1/chat"
    payload = {
        "message": "¿Y qué tipo de plagas puedes ayudarme a identificar?",
        "conversation_id": conversation_id,
    }
    print(f"POST {url}")
    print(f"Body: {pretty_json(payload)}")
    print("\n⏳ Enviando mensaje de seguimiento...")

    start = time.time()
    try:
        r = requests.post(url, json=payload, headers=HEADERS, timeout=180)
        elapsed = time.time() - start
        print(f"\nTiempo de respuesta: {elapsed:.2f}s")
        print(f"Status: {r.status_code}")
        data = r.json()
        print(pretty_json(data))

        same_conv = data.get("conversation_id") == conversation_id
        ok = r.status_code == 200 and same_conv
        print(f"\n{'✅ PASS — mismo conversation_id' if ok else '❌ FAIL'}")
        if ok:
            print(f'\n🤖 Brot: "{data.get("answer")}"')
        return ok
    except Exception as e:
        print(f"❌ FAIL — {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# TEST 6: Filtro de seguridad (prompt fuera de scope)
# ─────────────────────────────────────────────────────────────────────────────
def test_out_of_scope_filter() -> bool:
    print_section("TEST 6 — Filtro de Seguridad (out-of-scope)")
    url = f"{GATEWAY_BASE_URL}/api/agent/v1/chat"
    payload = {
        "message": "¿Quién ganó el partido de fútbol ayer?",
        "conversation_id": None,
    }
    print(f"POST {url}")
    print(f"Body: {pretty_json(payload)}")
    print("\n⏳ Enviando mensaje fuera del dominio agrícola...")

    try:
        r = requests.post(url, json=payload, headers=HEADERS, timeout=30)
        print(f"\nStatus: {r.status_code}")
        data = r.json()
        print(pretty_json(data))

        # Debe responder rápido (sin pasar a Ollama) con status 'redirected'
        blocked = data.get("status") == "redirected"
        ok = r.status_code == 200 and blocked
        print(f"\n{'✅ PASS — filtro activo, respuesta sin llamar a Ollama' if ok else '❌ FAIL — el filtro no bloqueó el mensaje'}")
        return ok
    except Exception as e:
        print(f"❌ FAIL — {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# TEST 7: Rate limit (autenticación inválida)
# ─────────────────────────────────────────────────────────────────────────────
def test_invalid_api_key() -> bool:
    print_section("TEST 7 — Rechazo por API Key inválida")
    url = f"{GATEWAY_BASE_URL}/api/agent/v1/chat"
    bad_headers = {**HEADERS, "X-API-Key": "clave-incorrecta"}
    payload = {"message": "test", "conversation_id": None}
    print(f"POST {url} (con API key incorrecta)")

    try:
        r = requests.post(url, json=payload, headers=bad_headers, timeout=10)
        print(f"Status: {r.status_code}")
        print(pretty_json(r.json()))
        ok = r.status_code == 401
        print(f"\n{'✅ PASS — 401 Unauthorized' if ok else '❌ FAIL — debería haber retornado 401'}")
        return ok
    except Exception as e:
        print(f"❌ FAIL — {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# MAIN — Resumen final
# ─────────────────────────────────────────────────────────────────────────────
def main() -> None:
    print("\n" + "=" * 65)
    print("  [QA] Huerto Connect Agent Service - Audit")
    print("  Flujo: Frontend -> Gateway (:8000) -> agent-service (:8006) -> Ollama")
    print("=" * 65)

    results: dict[str, bool] = {}

    results["gateway_health"]      = test_gateway_health()
    results["agent_live_direct"]   = test_agent_live_direct()
    results["agent_ready_direct"]  = test_agent_ready_direct()

    # El chat completo solo se ejecuta si el agente está listo
    conversation_id = None
    if results["agent_ready_direct"]:
        conversation_id = test_chat_via_gateway()
        results["chat_via_gateway"] = conversation_id is not None
        results["conversation_continuity"] = test_conversation_continuity(conversation_id)
    else:
        print("\n⏭️  SKIP tests de chat — agente/Ollama no está listo (ver TEST 3).")
        results["chat_via_gateway"] = False
        results["conversation_continuity"] = False

    results["out_of_scope_filter"] = test_out_of_scope_filter()
    results["invalid_api_key"]     = test_invalid_api_key()

    # ── Resumen ──────────────────────────────────────────────────────────────
    print_section("RESUMEN FINAL")
    icons = {True: "✅", False: "❌"}
    labels = {
        "gateway_health":           "Gateway Health Check",
        "agent_live_direct":        "Agent Liveness (directo)",
        "agent_ready_direct":       "Agent Readiness / Ollama OK",
        "chat_via_gateway":         "Chat completo vía Gateway",
        "conversation_continuity":  "Continuidad de conversación",
        "out_of_scope_filter":      "Filtro out-of-scope activo",
        "invalid_api_key":          "Rechazo API Key inválida",
    }
    for key, passed in results.items():
        print(f"  {icons[passed]}  {labels[key]}")

    total = len(results)
    passed = sum(results.values())
    print(f"\n  Resultado: {passed}/{total} tests pasados")

    if passed == total:
        print("\n  🎉 ¡Flujo completo operativo! El agente responde correctamente.")
    else:
        print("\n  ⚠️  Algunos tests fallaron. Revisa los detalles arriba.")

    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
