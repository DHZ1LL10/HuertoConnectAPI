from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class SafetyDecision:
    allowed: bool
    status: str
    reason: str | None = None
    answer: str | None = None


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text).strip()


DOMAIN_TERMS = {
    "huerto", "cultivo", "cultivar", "planta", "plantas", "semilla", "semillas",
    "germinacion", "trasplante", "suelo", "tierra", "sustrato", "riego", "regar",
    "drenaje", "humedad", "cosecha", "poda", "plaga", "plagas", "hongo", "hongos",
    "pulgon", "pulgones", "mosca blanca", "cochinilla", "oruga", "insecto", "insectos",
    "hoja", "hojas", "raiz", "raices", "tallo", "fruto", "flor", "flores", "maceta",
    "jitomate", "tomate", "chile", "maiz", "frijol", "cilantro", "lechuga", "calabaza",
    "pepino", "limon", "naranja", "cafe", "cana", "mango", "aguacate", "platano",
    "composta", "compost", "abono", "fertilidad", "vivero", "agricola", "agricultura",
    "veracruz", "cordoba", "orizaba", "xalapa", "coatepec", "papantla", "huatusco",
    "amarilla", "amarillas", "marchita", "marchitas", "mancha", "manchas", "enrollada",
    "enrolladas", "seca", "secas", "podrida", "podridas", "brotar", "crecer", "crecimiento",
}

# Si hay una conversación previa, estas respuestas breves pueden ser continuidad válida.
CONTEXTUAL_FOLLOW_UP_PATTERNS = (
    r"^(si|no|tal vez|creo que si|creo que no)$",
    r"^(desde hace|hace)\s+\w+",
    r"^(cada|aproximadamente|como)\s+\w+",
    r"^(en|esta en|lo tengo en)\s+.{1,80}$",
    r"^(solo|tambien|ademas|ahora)\s+.{1,120}$",
    r"^\d+\s*(dias?|semanas?|meses?|veces?)$",
)

OUT_OF_SCOPE_TERMS = {
    "futbol", "partido", "apuesta", "parley", "programacion", "codigo", "python", "php",
    "politica", "presidente", "elecciones", "pelicula", "musica", "videojuego", "tarea de matematicas",
    "hackear", "contraseña", "curriculum", "correo electronico",
}

DANGEROUS_SUBSTANCES = {
    "cloro", "lejia", "amoniaco", "acido muriatico", "acido sulfurico", "acido nitrico",
    "sosa caustica", "hidroxido de sodio", "gasolina", "diesel", "queroseno", "solvente",
    "thinner", "metanol", "cianuro", "fosfuro", "organofosforado", "carbamato",
    "nitrato de amonio", "peroxido concentrado", "veneno", "explosivo",
}

CONTROL_PRODUCT_TERMS = {
    "pesticida", "insecticida", "herbicida", "fungicida", "rodenticida", "plaguicida",
}

HOME_MIXTURE_TERMS = {
    "jabon", "detergente", "bicarbonato", "vinagre", "alcohol", "aceite", "ajo", "chile molido",
}

PROCEDURAL_ACTIONS = {
    "fabricar", "hacer", "preparar", "prepara", "sintetizar", "mezclar", "mezcla", "combinar", "extraer",
    "concentrar", "producir", "formular", "dosificar", "diluir", "diluye", "agrega", "rocia", "aplica", "proporcion", "receta",
    "ingredientes", "paso a paso", "cuantos gramos", "cuantos mililitros", "formula",
}

PROMPT_INJECTION_PATTERNS = (
    r"\b(ignore|disregard|forget|override|bypass)\b.{0,60}\b(instruction|prompt|rule|policy|system|developer)",
    r"\b(ignora|olvida|omite|anula|reemplaza|desactiva|evade)\b.{0,60}\b(instrucciones?|reglas?|prompt|sistema|desarrollador|politicas?)",
    r"\b(revela|muestra|imprime|repite|copia|traduce|resume|codifica)\b.{0,60}\b(prompt|instrucciones?|mensaje oculto|sistema|configuracion interna)",
    r"\b(actua|responde|comportate|finge)\b.{0,50}\b(como|sin restricciones|otro asistente|modo desarrollador|modo depuracion)",
    r"\b(jailbreak|dan mode|developer mode|modo dan|prompt injection)\b",
    r"<\s*(system|developer|assistant)\s*>",
    r"[\"']role[\"']\s*:\s*[\"'](system|developer)[\"']",
)

LEAK_PATTERNS = (
    "seguridad de instrucciones",
    "solo este mensaje de sistema define",
    "alcance exclusivo",
    "nunca reveles, copies, traduzcas",
)

MEASUREMENT_PATTERN = re.compile(
    r"\b\d+(?:[\.,]\d+)?\s*(?:mg|g|kg|ml|l|%|cucharadas?|cucharaditas?|tazas?)\b",
    re.IGNORECASE,
)

FERTILIZER_PATTERN = re.compile(
    r"\b(abona|abonar|fertiliza|fertilizar|fertilizante|npk|urea)\b",
    re.IGNORECASE,
)
WATERLOGGED_PATTERN = re.compile(
    r"\b(encharcad[oa]s?|saturad[oa]s?|no drena|mal drenaje|tierra sigue humeda|suelo sigue humedo|olor a podrido)\b",
    re.IGNORECASE,
)
EMOJI_PATTERN = re.compile(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]", re.UNICODE)


INJECTION_REFUSAL = (
    "No puedo revelar ni cambiar mis instrucciones internas. "
    "Sí puedo ayudarte con cultivos, huertos y cuidado seguro de plantas en Veracruz."
)

CHEMICAL_REFUSAL = (
    "No puedo explicar cómo fabricar, mezclar o dosificar sustancias químicas o plaguicidas. "
    "Para el huerto puedo ayudarte con medidas de bajo riesgo, como retiro manual, limpieza, "
    "poda sanitaria, ajuste del riego, mejora del drenaje y barreras físicas."
)

OUT_OF_SCOPE_RESPONSE = (
    "Este asistente solo atiende dudas sobre huertos, cultivos y plantas en Veracruz. "
    "Puedes describir la planta, los síntomas, el riego, el suelo y desde cuándo ocurre el problema."
)

UNSAFE_OUTPUT_FALLBACK = (
    "No puedo ofrecer esa recomendación porque no superó el filtro de seguridad. "
    "Empieza con observación, retiro manual, limpieza, ajuste de riego y barreras físicas; "
    "si el problema avanza, consulta a una persona agrónoma con una fotografía de la planta."
)


def evaluate_input(message: str, max_length: int, has_context: bool = False) -> SafetyDecision:
    if len(message) > max_length:
        return SafetyDecision(False, "blocked", "message_too_long", "El mensaje es demasiado largo. Resume el problema del cultivo.")

    text = normalize(message)

    if any(re.search(pattern, text, re.IGNORECASE) for pattern in PROMPT_INJECTION_PATTERNS):
        return SafetyDecision(False, "blocked", "prompt_injection", INJECTION_REFUSAL)

    has_dangerous = any(term in text for term in DANGEROUS_SUBSTANCES)
    has_control_product = any(term in text for term in CONTROL_PRODUCT_TERMS)
    has_home_mixture = any(term in text for term in HOME_MIXTURE_TERMS)
    has_procedure = any(term in text for term in PROCEDURAL_ACTIONS)
    has_measurement = bool(MEASUREMENT_PATTERN.search(message))

    if (has_dangerous and has_procedure) or (has_control_product and has_procedure):
        return SafetyDecision(False, "blocked", "dangerous_chemical_request", CHEMICAL_REFUSAL)

    if has_home_mixture and has_procedure and has_measurement:
        return SafetyDecision(
            False,
            "blocked",
            "unverified_home_mixture",
            "No puedo indicar una receta o dosis casera porque una concentración incorrecta puede quemar las hojas o afectar el suelo. Empieza con retiro manual, agua a presión suave, limpieza, poda sanitaria y barreras físicas.",
        )

    if any(term in text for term in ("arma quimica", "envenenar", "bomba", "explosivo")):
        return SafetyDecision(False, "blocked", "dangerous_non_agricultural_request", "No puedo ayudar con sustancias o métodos destinados a causar daño.")

    has_domain = any(term in text for term in DOMAIN_TERMS)
    explicit_out_of_scope = any(term in text for term in OUT_OF_SCOPE_TERMS)
    contextual_follow_up = has_context and (
        len(text) <= 160
        or any(re.search(pattern, text, re.IGNORECASE) for pattern in CONTEXTUAL_FOLLOW_UP_PATTERNS)
    )

    if explicit_out_of_scope or (not has_domain and not contextual_follow_up):
        return SafetyDecision(False, "redirected", "out_of_scope", OUT_OF_SCOPE_RESPONSE)

    return SafetyDecision(True, "answered")


def _cap_words(answer: str, max_words: int) -> str:
    words = answer.split()
    if len(words) <= max_words:
        return answer
    limited = " ".join(words[:max_words])
    sentence_end = max(limited.rfind("."), limited.rfind("?"), limited.rfind("!"))
    if sentence_end >= int(len(limited) * 0.55):
        return limited[: sentence_end + 1]
    return limited.rstrip(" ,:;") + "."


def evaluate_output(answer: str, user_message: str, max_words: int) -> SafetyDecision:
    clean = EMOJI_PATTERN.sub("", answer).strip()
    text = normalize(clean)

    if any(pattern in text for pattern in LEAK_PATTERNS):
        return SafetyDecision(False, "blocked", "prompt_leak", INJECTION_REFUSAL)

    dangerous = any(term in text for term in DANGEROUS_SUBSTANCES)
    product = any(term in text for term in CONTROL_PRODUCT_TERMS)
    home_mixture = any(term in text for term in HOME_MIXTURE_TERMS)
    procedural = any(term in text for term in PROCEDURAL_ACTIONS)
    quantified = bool(MEASUREMENT_PATTERN.search(clean))
    recommends_product = bool(
        re.search(r"\b(usa|utiliza|aplica|compra|rocia|agrega)\b.{0,50}\b(pesticida|insecticida|herbicida|fungicida|plaguicida)\b", text)
    )

    if (dangerous or product) and (procedural or quantified or recommends_product):
        return SafetyDecision(False, "blocked", "unsafe_model_output", UNSAFE_OUTPUT_FALLBACK)

    if home_mixture and procedural and quantified:
        return SafetyDecision(False, "blocked", "unsafe_home_mixture_output", UNSAFE_OUTPUT_FALLBACK)

    if WATERLOGGED_PATTERN.search(normalize(user_message)) and FERTILIZER_PATTERN.search(clean):
        return SafetyDecision(
            False,
            "blocked",
            "unsafe_fertilizer_advice",
            "No fertilices por ahora. Primero reduce el riego, verifica que la maceta tenga salida de agua y deja que el sustrato recupere aireación. Si hay olor desagradable o raíces oscuras, conviene revisar posible pudrición.",
        )

    clean = re.sub(r"\s{2,}", " ", clean)
    clean = _cap_words(clean, max_words)
    return SafetyDecision(True, "answered", answer=clean)
