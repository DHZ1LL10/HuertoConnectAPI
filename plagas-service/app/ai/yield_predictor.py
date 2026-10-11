import math


class YieldPredictor:
    def __init__(self, manager):
        self.manager = manager

    def options(self):
        model = self.manager.require("rendimiento")
        options = {}
        for _, transformer, columns in model.named_steps["preprocess"].transformers_:
            if hasattr(transformer, "named_steps") and "onehot" in transformer.named_steps:
                for column, categories in zip(columns, transformer.named_steps["onehot"].categories_):
                    options[column] = [str(value) for value in categories]
        return {"categorias": options, "Anio": {"min": 2000, "max": 2100}, "objetivo": "Rendimiento"}

    def predict(self, features):
        import pandas as pd
        from shared.regions import region_key
        features = dict(features)
        model = self.manager.require("rendimiento")
        names = list(model.feature_names_in_)
        if set(features) != set(names):
            raise ValueError(f"Las entradas requeridas son: {', '.join(names)}")
        preprocess = model.named_steps["preprocess"]
        for _, transformer, columns in preprocess.transformers_:
            if hasattr(transformer, "named_steps") and "onehot" in transformer.named_steps:
                encoder = transformer.named_steps["onehot"]
                for column, categories in zip(columns, encoder.categories_):
                    if features[column] not in categories:
                        match = next((str(c) for c in categories if region_key(str(c)) == region_key(str(features[column]))), None)
                        if match is None:
                            raise ValueError(f"{column}: valor no soportado; consulta /ai/rendimiento/opciones")
                        features[column] = match
        if isinstance(features["Anio"], bool) or not isinstance(features["Anio"], int) or not 2000 <= features["Anio"] <= 2100:
            raise ValueError("Anio debe ser un entero entre 2000 y 2100")
        from app.ai.model_manager import ModelBusy
        lock = self.manager.locks["rendimiento"]
        if not lock.acquire(blocking=False):
            raise ModelBusy()
        try:
            value = float(model.predict(pd.DataFrame([features], columns=names))[0])
        finally:
            lock.release()
        if not math.isfinite(value) or value < 0:
            raise RuntimeError("Predicción inválida")
        return {
            "rendimiento": value, "objetivo": "Rendimiento", "modelo": self.manager.paths["rendimiento"].stem,
            "features": features, "metadata": self.manager.metadata["rendimiento"],
            "recomendaciones": [
                "Usa esta estimación histórica como referencia, no como garantía de cosecha.",
                "Valida suelo, agua, ciclo y condiciones locales antes de planificar la siembra.",
            ],
            "nota": "Estimación histórica municipal. Categorías verificadas individualmente; el artefacto no incluye el catálogo de combinaciones municipio-cultivo observadas.",
        }
