import math
from app.ai.model_manager import ModelBusy


class ImageClassifier:
    def __init__(self, manager, kind):
        self.manager = manager
        self.kind = kind

    def predict(self, image):
        model = self.manager.require(self.kind)
        lock = self.manager.locks[self.kind]
        if not lock.acquire(blocking=False):
            raise ModelBusy()
        try:
            results = model.predict(image, imgsz=320, device=self.manager.device, verbose=False)
        finally:
            lock.release()
        if not results or results[0].probs is None:
            raise ValueError("Clasificación sin probabilidades")
        values = results[0].probs.data.cpu().tolist()
        if not values or len(values) != len(model.names) or any(not math.isfinite(v) or v < 0 or v > 1 for v in values) or not math.isclose(sum(values), 1.0, abs_tol=1e-4):
            raise ValueError("Probabilidades inválidas")
        indices = sorted(range(len(values)), key=values.__getitem__, reverse=True)
        top = [{"clase": model.names[i], "confianza": float(values[i])} for i in indices[:3]]
        confidence = top[0]["confianza"]
        margin = confidence - (top[1]["confianza"] if len(top) > 1 else 0)
        detected = confidence >= self.manager.config.AI_MIN_CONFIDENCE and margin >= self.manager.config.AI_MIN_MARGIN
        label = top[0]["clase"] if detected else "No detectada / no soportada"
        return {
            "tipo": self.kind, "detectado": detected, "clase": label,
            "confianza": confidence, "margen": margin, "top": top,
            "modelo": self.manager.paths[self.kind].stem, "version": "v6",
            "nota": "Síntomas compatibles con HLB; requiere validación por especialista." if detected and label == "hlb" else "La clasificación de una imagen no sustituye un diagnóstico agronómico.",
        }


class PlagueClassifier(ImageClassifier):
    def __init__(self, manager):
        super().__init__(manager, "plaga")
