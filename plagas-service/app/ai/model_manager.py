import json
import logging
from pathlib import Path
from threading import Lock

from shared.config import settings

logger = logging.getLogger(__name__)


class ModelUnavailable(RuntimeError):
    pass


class ModelBusy(RuntimeError):
    pass


class ModelManager:
    def __init__(self, config=settings):
        self.config = config
        local = Path(__file__).resolve().parents[1] / "models" / "ml"
        root = Path(__file__).resolve().parents[3]
        self.paths = {
            "plaga": Path(config.PLAGUE_MODEL_PATH) if config.PLAGUE_MODEL_PATH else local / "yolo_plagas_veracruz_v6.pt",
            "enfermedad": Path(config.DISEASE_MODEL_PATH) if config.DISEASE_MODEL_PATH else local / "yolo_enfermedades_veracruz_v6.pt",
            "rendimiento": Path(config.RF_MODEL_PATH) if config.RF_MODEL_PATH else root / "huertos-service/app/models/ml/random_forest_veracruz.joblib",
        }
        self.models = {}
        self.metadata = {}
        self.locks = {key: Lock() for key in self.paths}
        self.device = "cpu"
        self._loaded = False

    def load(self):
        if self._loaded:
            return
        self._loaded = True
        for kind, path in self.paths.items():
            try:
                if not path.is_file():
                    raise FileNotFoundError()
                if kind == "rendimiento":
                    import joblib
                    model = joblib.load(path)
                    if not hasattr(model, "feature_names_in_") or not hasattr(model, "predict"):
                        raise ValueError("Invalid regression pipeline")
                    metadata_path = path.with_name("random_forest_metadata.json")
                else:
                    import torch
                    if self.config.AI_DEVICE != "cpu" and torch.cuda.is_available():
                        self.device = self.config.AI_DEVICE
                    from ultralytics import YOLO
                    model = YOLO(str(path), task="classify")
                    if model.task != "classify" or not model.names:
                        raise ValueError("Expected classifier")
                    metadata_path = path.with_name("metadata_ia_veracruz_v6.json")
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                if not isinstance(metadata, dict):
                    raise ValueError("Invalid metadata")
                self.models[kind] = model
                self.metadata[kind] = metadata
            except Exception as exc:
                logger.error("model_load_failed kind=%s error=%s", kind, type(exc).__name__)

    def require(self, kind):
        if kind not in self.models:
            raise ModelUnavailable(f"Modelo de {kind} no disponible")
        return self.models[kind]

    def health(self):
        return {kind: {"loaded": kind in self.models, "modelo": path.stem} for kind, path in self.paths.items()}
