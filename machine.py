import pandas as pd
import numpy as np
from pymongo import MongoClient
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.pipeline import Pipeline
import joblib
import os

# ============================================================
# 1. CONFIGURAÇÃO E CONEXÃO MONGO
# ============================================================
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "FRUTAS_DB"
COLLECTION_NAME = "sensores"
MODEL_DIR = "./modelos" # Diretório para salvar os modelos

# ============================================================
# 2. FUNÇÕES DE CRIAÇÃO DE TARGETS (Regras Manuais - Rule-Based System)
# ============================================================
def definir_estado(dado):
    """ Define o estado da fruta ('ambiente', 'madura', 'passada') baseado em regras heurísticas. """
    mq3 = dado["mq3_raw"]
    temp = dado["temperatura"]
    umid = dado["umidade_ar"]
    if 3140 <= mq3 <= 3640 and 33 <= temp <= 34 and 78 <= umid <= 82:
        return "passada"
    elif 2260 <= mq3 <= 2440 and 29 <= temp <= 31 and 70 <= umid <= 75:
        return "madura"
    elif mq3 < 1500:
        return "ambiente"
    else:
        # Lógica de fallback para dados fora das faixas ideais
        if mq3 < 2260:
            return "ambiente"
        elif mq3 < 3140:
            return "madura"
        else:
            return "passada"

def dias_restantes(estado, temp_atual, umid_atual):
    """ Calcula os dias restantes (validade). Retorna None para 'ambiente'. """
    if estado == "madura":
        dias_base = 3
        # Ajuste de validade baseado em condições ambientais
        if temp_atual > 32 or umid_atual > 78:
            dias_base -= 1
        elif temp_atual < 30 or umid_atual < 70:
            dias_base += 1
        return max(dias_base, 0)
    elif estado == "passada":
        return 0
    return None # Retorna None para 'ambiente', pois ainda não está madura.

# ============================================================
# 3. FUNÇÕES DE TREINAMENTO (Pipeline com StandardScaler e Random Forest)
# ============================================================
def treinar_classificador(X, y, nome_modelo):
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    pipeline = Pipeline([
        ('scaler', StandardScaler()),
        ('rf', RandomForestClassifier(n_estimators=100, random_state=42))
    ])
    pipeline.fit(X_train, y_train)
    acc = pipeline.score(X_test, y_test)
    print(f"{nome_modelo} Accuracy: {acc*100:.2f}%")
    joblib.dump(pipeline, os.path.join(MODEL_DIR, f"{nome_modelo}.pkl"))
    return pipeline

def treinar_regressor(X, y, nome_modelo):
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    pipeline = Pipeline([
        ('scaler', StandardScaler()),
        ('rf', RandomForestRegressor(n_estimators=100, random_state=42))
    ])
    pipeline.fit(X_train, y_train)
    score = pipeline.score(X_test, y_test)
    print(f"{nome_modelo} R^2 Score: {score:.2f}")
    joblib.dump(pipeline, os.path.join(MODEL_DIR, f"{nome_modelo}.pkl"))
    return pipeline

# ============================================================
# 4. EXECUÇÃO PRINCIPAL
# ============================================================
if __name__ == "__main__":
    
    # Prepara diretórios
    os.makedirs(MODEL_DIR, exist_ok=True)

    # --------------------------------------------------------
    # CARREGAMENTO DOS DADOS (MONGO DB)
    # --------------------------------------------------------
    print("Conectando ao MongoDB e coletando dados...")
    try:
        client = MongoClient(MONGO_URI)
        db = client[DB_NAME]
        collection = db[COLLECTION_NAME]
        
        # Converte a coleção do MongoDB para um DataFrame Pandas
        df = pd.DataFrame(list(collection.find()))
        
        if df.empty:
            raise ValueError("O DataFrame do MongoDB está vazio. Verifique sua conexão e se há dados na coleção.")
        
        print(f"Dados coletados com sucesso. Total de {len(df)} registros.")
        client.close()
        
    except Exception as e:
        print(f"ERRO: Não foi possível conectar ao MongoDB ou carregar os dados. Erro: {e}")
        # Se a conexão falhar, o script deve parar
        exit() 

    # --------------------------------------------------------
    # PRÉ-PROCESSAMENTO, FEATURE ENGINEERING E CRIAÇÃO DE TARGETS
    # --------------------------------------------------------
    
    # 1. Limpeza e Conversão de Tipos
    # Remove a coluna '_id' se presente e garante que as colunas chaves são numéricas.
    if '_id' in df.columns:
        df.drop(columns=['_id'], inplace=True)
        
    df["dataRegistro"] = pd.to_datetime(df.get("timestamp") or df.get("dataRegistro"), errors="coerce")
    df["temperatura"] = pd.to_numeric(df.get("temperatura"), errors="coerce")
    df["umidade_ar"] = pd.to_numeric(df.get("umidade_ar"), errors="coerce")
    df["mq3_raw"] = pd.to_numeric(df.get("mq3_raw"), errors="coerce")
    
    # 2. Remoção de NaNs críticos
    df.dropna(subset=["temperatura", "umidade_ar", "mq3_raw", "tipoFruta"], inplace=True)
    
    # 3. Criação dos Targets (Y)
    df["estado"] = df.apply(definir_estado, axis=1)
    df["dias_para_passar"] = df.apply(lambda r: dias_restantes(r["estado"], r["temperatura"], r["umidade_ar"]), axis=1)

    # 4. Feature Engineering (Cálculo do Slope / Variação)
    df.sort_values(['tipoFruta', 'dataRegistro'], inplace=True)
    df['mq3_slope'] = df.groupby('tipoFruta')['mq3_raw'].diff().fillna(0)
    df['temp_slope'] = df.groupby('tipoFruta')['temperatura'].diff().fillna(0)
    df['umid_slope'] = df.groupby('tipoFruta')['umidade_ar'].diff().fillna(0)
    
    # 5. Filtragem para Regressor
    # Apenas dados que possuem um valor de dias restantes (ou seja, 'madura' ou 'passada')
    df_tempo_valido = df.dropna(subset=['dias_para_passar']).copy()
    
    features = ['mq3_raw', 'temperatura', 'umidade_ar', 'mq3_slope', 'temp_slope', 'umid_slope']

    # 6. ENCODING
    le_estado = LabelEncoder()
    df['estado_label'] = le_estado.fit_transform(df['estado'].astype(str))

    le_fruta = LabelEncoder()
    df['tipo_label'] = le_fruta.fit_transform(df['tipoFruta'].astype(str))
    
    # --------------------------------------------------------
    # TREINAMENTO DOS MODELOS
    # --------------------------------------------------------
    print("\nIniciando Treinamento dos Modelos...")
    
    # Modelo 1: Estado da fruta (Classificação) - Usa DF COMPLETO
    X_estado = df[features]
    y_estado = df['estado_label']
    treinar_classificador(X_estado, y_estado, "modelo_1_estado")

    # Modelo 2: Dias restantes (Regressão) - USA DF FILTRADO
    X_tempo = df_tempo_valido[features]
    y_tempo = df_tempo_valido['dias_para_passar'].astype(int)
    
    if X_tempo.empty:
         print("AVISO: Dados insuficientes (após filtro) para treinar o Modelo 2 (Tempo Restante). Pulando.")
    else:
         treinar_regressor(X_tempo, y_tempo, "modelo_2_tempo_restante")

    # Modelo 3: Identificação da fruta (Classificação) - Usa DF COMPLETO
    X_fruta = df[features]
    y_fruta = df['tipo_label']
    treinar_classificador(X_fruta, y_fruta, "modelo_3_identificacao_fruta")

    # SALVA ENCODERS
    joblib.dump(le_estado, os.path.join(MODEL_DIR, "encoder_estado.pkl"))
    joblib.dump(le_fruta, os.path.join(MODEL_DIR, "encoder_fruta.pkl"))
    print("\nTreinamento concluído e modelos e encoders salvos com sucesso!")