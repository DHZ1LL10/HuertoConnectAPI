from .plague_classifier import ImageClassifier


class DiseaseClassifier(ImageClassifier):
    def __init__(self, manager):
        super().__init__(manager, "enfermedad")
