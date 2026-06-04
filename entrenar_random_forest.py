"""
Script de entrenamiento del Random Forest para HuertoConnect.

Uso:
    pip install scikit-learn pandas
    python entrenar_random_forest.py

Genera: random_forest_huerto.pkl
Coloca ese archivo en:
    huertos-service/app/models/ml/random_forest_huerto.pkl

Dataset requerido: modelado_random_forest.csv (en el mismo directorio)
"""

import pickle
import sys
import os

try:
    import pandas as pd
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import train_test_split
    from sklearn.preprocessing import LabelEncoder
    from sklearn.metrics import accuracy_score, classification_report
except ImportError:
    print("ERROR: Instala las dependencias primero:")
    print("  pip install scikit-learn pandas")
    sys.exit(1)


# ─── Configuración ────────────────────────────────────────────────────────────
CSV_PATH = "modelado_random_forest.csv"
OUTPUT_PKL = "random_forest_huerto.pkl"
TARGET_COL = "cultivo_recomendado_zona"

# Features numéricas (siempre disponibles)
NUMERIC_FEATURES = [
    "temperatura",
    "humedad_ambiental",
    "probabilidad_lluvia",
    "lluvia_acumulada",
    "velocidad_viento",
    "radiacion_uv",
    "humedad_suelo",
    "ultimo_riego",
    "dias_desde_siembra",
    "altitud_aproximada",
]

# Features categóricas (se codifican con LabelEncoder)
CATEGORICAL_FEATURES = [
    "municipio",
    "region",
    "tipo_suelo",
    "temporada_ano",
    "etapa_cultivo",
    "historial_plagas",
]

ALL_FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES


# ─── Carga de datos ───────────────────────────────────────────────────────────
print(f"\n{'='*60}")
print("  HuertoConnect — Entrenamiento Random Forest")
print(f"{'='*60}")
print(f"\n[1/5] Cargando dataset: {CSV_PATH}")

if not os.path.exists(CSV_PATH):
    print(f"ERROR: No se encontró '{CSV_PATH}'")
    print("  Asegúrate de ejecutar este script desde la raíz del proyecto.")
    sys.exit(1)

df = pd.read_csv(CSV_PATH)
print(f"      -> {len(df)} filas, {len(df.columns)} columnas")
print(f"      -> Cultivos objetivo: {sorted(df[TARGET_COL].unique())}")


# ─── Limpieza ─────────────────────────────────────────────────────────────────
print("\n[2/5] Preparando features...")

# Verificar columnas disponibles
available_features = [f for f in ALL_FEATURES if f in df.columns]
missing_features = [f for f in ALL_FEATURES if f not in df.columns]

if missing_features:
    print(f"      ⚠ Features no encontradas (se omitirán): {missing_features}")

available_numeric = [f for f in NUMERIC_FEATURES if f in df.columns]
available_categorical = [f for f in CATEGORICAL_FEATURES if f in df.columns]

print(f"      -> Numéricas: {available_numeric}")
print(f"      -> Categóricas: {available_categorical}")

# Eliminar filas con NaN en target o features
df = df.dropna(subset=[TARGET_COL])
df = df.fillna({col: 0 for col in available_numeric})
df = df.fillna({col: "desconocido" for col in available_categorical})


# ─── Encoders ─────────────────────────────────────────────────────────────────
label_encoders: dict[str, LabelEncoder] = {}

for col in available_categorical:
    le = LabelEncoder()
    df[col] = le.fit_transform(df[col].astype(str))
    label_encoders[col] = le
    print(f"      -> Encoded '{col}': {list(le.classes_[:5])}{'...' if len(le.classes_) > 5 else ''}")

# Encoder del target
target_encoder = LabelEncoder()
y = target_encoder.fit_transform(df[TARGET_COL].astype(str))
print(f"      -> Clases objetivo: {list(target_encoder.classes_)}")

X = df[available_features].values


# ─── Split y entrenamiento ────────────────────────────────────────────────────
print("\n[3/5] Entrenando modelo...")

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)

print(f"      -> Train: {len(X_train)} muestras | Test: {len(X_test)} muestras")

modelo = RandomForestClassifier(
    n_estimators=200,
    max_depth=15,
    min_samples_leaf=2,
    class_weight="balanced",
    random_state=42,
    n_jobs=-1,
)
modelo.fit(X_train, y_train)
print("      -> Entrenamiento completado")


# ─── Evaluación ───────────────────────────────────────────────────────────────
print("\n[4/5] Evaluando modelo...")
y_pred = modelo.predict(X_test)
acc = accuracy_score(y_test, y_pred)
print(f"      -> Accuracy: {acc:.2%}")

if acc >= 0.85:
    print("      -> [OK] Accuracy aceptable para produccion")
elif acc >= 0.70:
    print("      -> [!] Accuracy moderada, considera mas datos")
else:
    print("      -> [X] Accuracy baja, revisar dataset o features")

print("\n      Reporte detallado:")
print(classification_report(
    y_test, y_pred,
    target_names=target_encoder.classes_,
    zero_division=0,
))

# Importancia de features
importances = sorted(
    zip(available_features, modelo.feature_importances_),
    key=lambda x: x[1], reverse=True,
)
print("      Top 5 features mas importantes:")
for feat, imp in importances[:5]:
    bar = "*" * int(imp * 40)
    print(f"        {feat:25s} {bar} {imp:.3f}")


# ─── Guardar modelo ───────────────────────────────────────────────────────────
print(f"\n[5/5] Guardando modelo en '{OUTPUT_PKL}'...")

modelo_bundle = {
    "modelo": modelo,
    "target_encoder": target_encoder,
    "label_encoders": label_encoders,
    "features_numericas": available_numeric,
    "features_categoricas": available_categorical,
    "all_features": available_features,
    "clases": list(target_encoder.classes_),
    "accuracy": round(acc, 4),
    "version": "random_forest-veracruz-v1.0",
}

with open(OUTPUT_PKL, "wb") as f:
    pickle.dump(modelo_bundle, f)

print(f"      -> Archivo guardado: {os.path.abspath(OUTPUT_PKL)}")
print(f"      -> Tamaño: {os.path.getsize(OUTPUT_PKL) / 1024:.1f} KB")

print(f"\n{'='*60}")
print("  [OK] Listo. Copia el archivo a:")
print("     huertos-service/app/models/ml/random_forest_huerto.pkl")
print(f"{'='*60}\n")
