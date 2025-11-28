import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
import joblib

# -------------------------------
# 1. GERANDO DATASET SINTÉTICO
# -------------------------------

np.random.seed(42)

N = 3000  # quantidade de amostras
frutas = np.random.choice([0, 1, 2], size=N)  # 0=banana,1=maçã,2=tomate

temperatura = np.random.uniform(18, 30, size=N)
umidade = np.random.uniform(40, 90, size=N)

# MQ03 baseado na fruta: cada fruta solta gases em velocidades diferentes
mq03 = []
for f in frutas:
    base = 1300
    if f == 0:  # banana amadurece rápido
        noise = np.random.randint(0, 2000)
    elif f == 1:  # maçã tem degradação lenta
        noise = np.random.randint(0, 1500)
    else:  # tomate média
        noise = np.random.randint(0, 1800)

    value = base + noise
    value = np.clip(value, 1300, 4095)
    mq03.append(value)

mq03 = np.array(mq03)

# -------------------------------
# RÓTULO MODELO 1 — Estado atual
# -------------------------------
estado = []
for g in mq03:
    if g < 1600:
        estado.append(0)  # normal
    elif g < 2400:
        estado.append(1)  # atenção
    else:
        estado.append(2)  # crítico

estado = np.array(estado)

# -------------------------------
# RÓTULO MODELO 2 — Tempo restante
# -------------------------------
tempo_restante = []

for e in estado:
    if e == 0:
        tempo_restante.append(np.random.uniform(48, 120))  # 2 a 5 dias
    elif e == 1:
        tempo_restante.append(np.random.uniform(12, 48))   # 12h - 2 dias
    else:
        tempo_restante.append(np.random.uniform(0, 12))    # urgente

tempo_restante = np.array(tempo_restante)

# -------------------------------
# MODELO NOVO — Alerta Venda Rápida
# ativado quando tempo_restante < 48h
# -------------------------------
alerta_venda_rapida = (tempo_restante < 48).astype(int)

# -------------------------------
# DATAFRAME FINAL
# -------------------------------
df = pd.DataFrame({
    "fruta": frutas,
    "temperatura": temperatura,
    "umidade": umidade,
    "mq03": mq03,
    "estado": estado,
    "tempo_restante": tempo_restante,
    "alerta_venda_rapida": alerta_venda_rapida
})

print(df.head())

# =====================================
# TREINAMENTO DOS MODELOS
# =====================================

# -------- MODELO 1 --------
# Classificação do estado da fruta
X1 = df[["temperatura", "umidade", "mq03"]]
y1 = df["estado"]

modelo_1 = RandomForestClassifier(n_estimators=300)
modelo_1.fit(X1, y1)

joblib.dump(modelo_1, "modelo_1_estado.pkl")

# -------- MODELO 2 --------
# Regressão tempo restante
X2 = df[["temperatura", "umidade", "mq03", "fruta"]]
y2 = df["tempo_restante"]

modelo_2 = RandomForestRegressor(n_estimators=300)
modelo_2.fit(X2, y2)

joblib.dump(modelo_2, "modelo_2_tempo_restante.pkl")

# -------- MODELO 4 --------
# Classificador tipo da fruta
X4 = df[["temperatura", "umidade", "mq03"]]
y4 = df["fruta"]

modelo_4 = RandomForestClassifier(n_estimators=300)
modelo_4.fit(X4, y4)

joblib.dump(modelo_4, "modelo_4_identificacao_fruta.pkl")

# -------- MODELO EXTRA --------
# alerta de venda rápida
X_extra = df[["temperatura", "umidade", "mq03", "fruta", "estado"]]
y_extra = df["alerta_venda_rapida"]

modelo_extra = RandomForestClassifier(n_estimators=300)
modelo_extra.fit(X_extra, y_extra)

joblib.dump(modelo_extra, "modelo_extra_alerta.pkl")

print("\nModelos treinados e salvos com sucesso!")
