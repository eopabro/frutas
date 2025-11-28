from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_socketio import SocketIO
from pymongo import MongoClient
from datetime import datetime
import pandas as pd
import os
import joblib
import csv # Movido para o topo

# ============================================================
# CONFIGURAÇÕES
# ============================================================
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "FRUTAS_DB"
COLLECTION = "sensores"

DATA_DIR = "data"
STATIC_DIR = "static"

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)

app = Flask(__name__, static_folder=STATIC_DIR, template_folder=STATIC_DIR)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

client = MongoClient(MONGO_URI)
db = client[DB_NAME]
colecao = db[COLLECTION]

# ============================================================
# FUNÇÕES DE ESTADO E VALIDADE (Rule-Based System)
# ============================================================
def definir_estado(dado):
    mq3 = dado["mq3_raw"]
    temp = dado["temperatura"]
    umid = dado["umidade_ar"]
    
    # AMBIENTE
    if mq3 < 1500:
        return "ambiente"
    
    # FRUTA MADURA
    elif 2260 <= mq3 <= 2440 and 29 <= temp <= 31 and 70 <= umid <= 75:
        return "madura"
    
    # FRUTA PASSADA
    elif 3140 <= mq3 <= 3640 and 33 <= temp <= 34 and 78 <= umid <= 82:
        return "passada"
    
    else:
        # Fallback (para valores entre os ranges definidos)
        if mq3 < 2260:
            return "ambiente"
        elif mq3 < 3140:
            return "madura"
        else:
            return "passada"

def calcular_validade(estado, temp, umid):
    if estado == "madura":
        dias_base = 3
        
        # Estresse térmico (acelera)
        if temp > 32 or umid > 78:
            dias_base -= 1
        
        # Condições favoráveis (desacelera)
        elif temp < 30 or umid < 70:
            dias_base += 1
            
        return max(dias_base, 0)
    
    elif estado == "passada":
        return 0
    
    else:  # ambiente
        return None

# ============================================================
# CARREGAMENTO DE MODELOS (opcional)
# ============================================================
MODEL_DIR = "./modelos"
modelo_ident = modelo_estado = modelo_tempo = None

def load_models():
    global modelo_ident, modelo_estado, modelo_tempo
    
    try:
        modelo_ident = joblib.load(os.path.join(MODEL_DIR, "modelo_3_identificacao_fruta.pkl"))
    except: 
        modelo_ident = None
        
    try:
        modelo_estado = joblib.load(os.path.join(MODEL_DIR, "modelo_1_estado.pkl"))
    except: 
        modelo_estado = None
        
    try:
        modelo_tempo = joblib.load(os.path.join(MODEL_DIR, "modelo_2_tempo_restante.pkl"))
    except: 
        modelo_tempo = None
        
load_models()

# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================
def fetch_raw_df(tipoFruta=None, limit=1000):
    query = {}
    if tipoFruta:
        query["tipoFruta"] = tipoFruta
        
    docs = list(colecao.find(query).sort("dataRegistro", -1).limit(limit))
    
    if not docs:
        return pd.DataFrame()
        
    df = pd.DataFrame(docs)
    
    df["temperatura"] = pd.to_numeric(df.get("temperatura"), errors="coerce")
    df["umidade_ar"] = pd.to_numeric(df.get("umidade_ar"), errors="coerce")
    df["mq3_raw"] = pd.to_numeric(df.get("mq3_raw"), errors="coerce")
    df["mq3_tensao"] = pd.to_numeric(df.get("mq3_tensao"), errors="coerce")
    df["timestamp"] = pd.to_datetime(df["dataRegistro"], errors="coerce")
    
    return df

def clean_and_engineer(df):
    if df.empty:
        return df
        
    df = df.sort_values("timestamp")
    # Usa ffill/bfill para lidar com NaNs
    df = df.ffill().bfill() 
    
    cols_numericas = ["temperatura", "umidade_ar", "mq3_raw", "mq3_tensao"]
    df_num = df.set_index("timestamp")[cols_numericas]
    
    # Agregação por média de 30 minutos
    agg = df_num.resample("30min").mean().dropna().reset_index() 
    
    # Feature Engineering do slope (inclinação)
    agg["mq3_slope"] = agg["mq3_raw"].diff().fillna(0) 
    
    return agg

def exportar_csv_por_fruta(tipoFruta):
    # Incluindo 'estado' e 'validade' na query para exportação
    registros = list(colecao.find({"tipoFruta": tipoFruta}).sort("dataRegistro", 1)) 
    
    if not registros:
        return None
        
    caminho = os.path.join(DATA_DIR, f"{tipoFruta}.csv")
    
    with open(caminho, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow([
            "timestamp", "tipoFruta", "temperatura",
            "umidade_ar", "mq3_raw", "mq3_tensao", "estado", "validade"
        ])
        
        for r in registros:
            writer.writerow([
                r.get("dataRegistro"),
                r.get("tipoFruta"),
                r.get("temperatura"),
                r.get("umidade_ar"),
                r.get("mq3_raw"),
                r.get("mq3_tensao"),
                r.get("estado"),
                r.get("validade")
            ])
            
    return caminho

# ============================================================
# ROTAS
# ============================================================
# Rota corrigida para aceitar o parâmetro tipoFruta
@app.route("/exportar/<tipoFruta>", methods=["GET"]) 
def exportar_tipo(tipoFruta):
    if tipoFruta.lower() == "todas":
        frutas = colecao.distinct("tipoFruta")
        caminhos = []
        for f in frutas:
            c = exportar_csv_por_fruta(f)
            if c:
                caminhos.append(c)
        return jsonify({"status": "ok", "arquivos": caminhos})

    caminho = exportar_csv_por_fruta(tipoFruta)
    
    if caminho:
        return jsonify({"status": "ok", "arquivo": caminho})
        
    return jsonify({"erro": "Nenhum dado encontrado para essa fruta"}), 404

@app.route("/api/sensores", methods=["POST"])
def receber_dados():
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"erro": "JSON vazio"}), 400
            
        required = ["tipoFruta", "temperatura", "umidade_ar", "mq3_raw", "mq3_tensao"]
        for r in required:
            if r not in data:
                return jsonify({"erro": f"Campo {r} ausente"}), 400
                
        # Calcula estado e validade (Rule-Based)
        estado = definir_estado(data)
        validade = calcular_validade(estado, data["temperatura"], data["umidade_ar"])
        
        data["estado"] = estado
        data["validade"] = validade
        data["dataRegistro"] = datetime.utcnow()

        result = colecao.insert_one(data)

        payload = {
            "id": str(result.inserted_id),
            "tipoFruta": data["tipoFruta"],
            "temperatura": float(data["temperatura"]),
            "umidade_ar": float(data["umidade_ar"]),
            "mq3_raw": float(data["mq3_raw"]),
            "mq3_tensao": float(data["mq3_tensao"]),
            "estado": estado,
            "validade": validade,
            "timestamp": data["dataRegistro"].isoformat()
        }

        socketio.emit("new_data", payload)
        print("[SALVO]", payload)
        
        return jsonify({"mensagem": "OK", "id": str(result.inserted_id)})

    except Exception as e:
        print("Erro na rota /api/sensores:", e)
        return jsonify({"erro": str(e)}), 500

# Rota corrigida para aceitar o parâmetro tipoFruta
@app.route("/api/fruta/<tipoFruta>/limpo") 
def fruta_limpa(tipoFruta):
    df = fetch_raw_df(tipoFruta)
    
    if df.empty:
        return jsonify([])
        
    df_clean = clean_and_engineer(df)
    
    # Assegura que o timestamp é string para o JSON
    df_clean["timestamp"] = df_clean["timestamp"].astype(str) 
    
    return df_clean.to_json(orient="records")

@app.route("/dashboard")
def dash():
    return render_template("dashboard.html")

# Rota corrigida para aceitar o path corretamente
@app.route("/static/<path:path>") 
def static_files(path):
    return send_from_directory("static", path)

# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    print("Servidor rodando em http://192.168.3.75:8080/dashboard")
    socketio.run(app, host="192.168.3.75", port=8080)