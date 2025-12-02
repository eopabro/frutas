#include <WiFi.h>
#include <HTTPClient.h>
#include "DHT.h"

// =========================================
// CONFIGURAÇÃO DO WI-FI
// =========================================
const char* ssid = "Geovanna - NETMAIS Fibra";
const char* password = "14112003";

// =========================================
// CONFIGURAÇÃO DOS SENSORES
// =========================================
#define DHTPIN 19
#define DHTTYPE DHT22
DHT dht(DHTPIN, DHTTYPE);

#define MQ3_PIN 32   // Sensor MQ-3

// =========================================
// VARIÁVEIS CONFIGURÁVEIS
// =========================================
String tipoFruta = "tomate";
String lote = "lote1";
String estado_real = "sem risco";

// =========================================
// ENDPOINT DO SERVIDOR FLASK
// =========================================
String serverURL = "http://192.168.3.75:8080/api/sensores";

// =========================================
// RECONEXÃO MÉDIA
// =========================================
void reconectaWiFi() {
    if (WiFi.status() == WL_CONNECTED) return;

    Serial.println("WiFi desconectado! Tentando reconectar...");

    int tentativas = 0;
    WiFi.disconnect(true);
    WiFi.begin(ssid, password);

    while (WiFi.status() != WL_CONNECTED && tentativas < 5) {
        delay(800);
        Serial.print(".");
        tentativas++;
    }

    if (WiFi.status() == WL_CONNECTED) {
        Serial.println("\nWiFi reconectado.");
    } else {
        Serial.println("\nFalha ao reconectar. Tentará no próximo ciclo.");
    }
}

// =========================================
// Função: EMA + 100 leituras em 45s
// =========================================
int readMQ3_EMA(int pin) {

    const int totalLeituras = 100;  // agora 100 leituras
    const int intervalo = 450;      // 450 ms → 100 leituras ≈ 45s
    const float alpha = 0.05;       // suavização do EMA (5%)

    float ema = analogRead(pin);    // inicializa EMA

    for (int i = 1; i < totalLeituras; i++) {
        int leitura = analogRead(pin);
        ema = alpha * leitura + (1 - alpha) * ema;
        delay(intervalo);
    }

    return (int)ema;
}

// =========================================
// Setup
// =========================================
void setup() {
    Serial.begin(115200);
    delay(3000);

    WiFi.begin(ssid, password);
    Serial.println("Conectando ao Wi-Fi inicial...");

    int tentativas = 0;
    while (WiFi.status() != WL_CONNECTED && tentativas < 15) {
        delay(500);
        Serial.print(".");
        tentativas++;
    }

    if (WiFi.status() == WL_CONNECTED) {
        Serial.println("\nConectado!");
    } else {
        Serial.println("\nFalha ao conectar no setup.");
    }

    dht.begin();
    pinMode(MQ3_PIN, INPUT);

    Serial.println("Comandos Serial:");
    Serial.println("  lote:<nome>");
    Serial.println("  estado_real:<sem risco|madura|alerta|risco de perda>");
}

// =========================================
// Loop principal
// =========================================
void loop() {
    unsigned long cicloInicio = millis();

    // Reconexão
    reconectaWiFi();

    // Leitura Serial para lote e estado_real
    if (Serial.available() > 0) {
        String cmd = Serial.readStringUntil('\n');
        cmd.trim();

        if (cmd.startsWith("lote:")) {
            lote = cmd.substring(5);
            lote.trim();
            Serial.print("Lote definido: ");
            Serial.println(lote);

        } else if (cmd.startsWith("estado_real:")) {
            estado_real = cmd.substring(12);
            estado_real.trim();
            Serial.print("Estado real definido: ");
            Serial.println(estado_real);
        }
    }

    // --------- DHT22 ----------
    float temperatura = dht.readTemperature();
    float umidade_ar = dht.readHumidity();

    if (isnan(temperatura) || isnan(umidade_ar)) {
        Serial.println("Erro ao ler DHT22!");
        delay(2000);
        return;
    }

    // --------- MQ-3 (EMA) ----------
    Serial.println("Lendo MQ-3 com EMA (~45 segundos)...");
    int mq3_raw = readMQ3_EMA(MQ3_PIN);
    float mq3_tensao = mq3_raw * (3.3 / 4095.0);

    // --------- JSON ----------
    String json = "{";
    json += "\"tipoFruta\":\"" + tipoFruta + "\",";
    json += "\"temperatura\":" + String(temperatura, 1) + ",";
    json += "\"umidade_ar\":" + String(umidade_ar, 1) + ",";
    json += "\"mq3_raw\":" + String(mq3_raw) + ",";
    json += "\"mq3_tensao\":" + String(mq3_tensao, 6) + ",";
    json += "\"lote\":\"" + lote + "\"";

    if (estado_real.length() > 0) {
        String sr = estado_real;
        sr.replace("\"", "'");
        json += ",\"estado_real\":\"" + sr + "\"";
    }

    json += "}";

    Serial.println("\nJSON Enviado:");
    Serial.println(json);

    // --------- Envio ----------
    if (WiFi.status() == WL_CONNECTED) {
        HTTPClient http;
        http.begin(serverURL);
        http.addHeader("Content-Type", "application/json");

        int httpCode = http.POST(json);

        Serial.print("HTTP: ");
        Serial.println(httpCode);

        if (httpCode > 0)
            Serial.println(http.getString());

        http.end();

    } else {
        Serial.println("WiFi OFF → Não enviado. Tentará de novo no próximo ciclo.");
    }

    // --------- 60 segundos de ciclo ----------
    unsigned long cicloFim = millis();
    unsigned long tempoPassado = cicloFim - cicloInicio;

    if (tempoPassado < 60000) {
        delay(60000 - tempoPassado);
    }
}


