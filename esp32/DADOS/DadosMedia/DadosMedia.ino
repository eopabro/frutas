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

#define MQ3_PIN 32   // Sensor MQ-3 (álcool / compostos orgânicos)

// =========================================
// TIPO DA FRUTA MONITORADA
// =========================================
String tipoFruta = "banana"; // Use "ambiente" para baseline

// =========================================
// ENDPOINT DO SERVIDOR FLASK
// =========================================
String serverURL = "http://192.168.3.75:8080/api/sensores";

// =========================================
// Média contínua por 11 segundos (75% dos 15s)
// =========================================
int readMQ3_11s(int pin) {
    unsigned long start = millis();
    unsigned long duration = 11000; // 11 segundos

    long total = 0;
    int count = 0;

    while (millis() - start < duration) {
        total += analogRead(pin);
        count++;
        delay(5);
    }

    return total / count;
}

// =========================================
// Conectar ao Wi-Fi
// =========================================
void conectaWiFi() {
    if (WiFi.status() == WL_CONNECTED) return;

    Serial.println("Conectando ao Wi-Fi...");
    WiFi.begin(ssid, password);

    int tentativas = 0;
    while (WiFi.status() != WL_CONNECTED && tentativas < 20) {
        delay(500);
        Serial.print(".");
        tentativas++;
    }

    if (WiFi.status() == WL_CONNECTED) {
        Serial.println("\nWiFi conectado!");
        Serial.print("IP: ");
        Serial.println(WiFi.localIP());
    } else {
        Serial.println("\nFalha ao conectar. Tentando novamente...");
    }
}

// =========================================
// SETUP
// =========================================
void setup() {
    Serial.begin(115200);
    delay(3000);

    conectaWiFi();
    dht.begin();
    pinMode(MQ3_PIN, INPUT);
}

// =========================================
// LOOP PRINCIPAL
// =========================================
void loop() {
    unsigned long cicloInicio = millis();

    conectaWiFi();

    // --------- Leitura do DHT22 ----------
    float temperatura = dht.readTemperature();
    float umidade_ar = dht.readHumidity();

    if (isnan(temperatura) || isnan(umidade_ar)) {
        Serial.println("Erro ao ler DHT22!");
        delay(2000);
        return;
    }

    // --------- Leitura MQ-3 por 11 segundos ----------
    Serial.println("Lendo MQ-3 (11 segundos)...");
    int mq3_raw = readMQ3_11s(MQ3_PIN);
    float mq3_tensao = mq3_raw * (3.3 / 4095.0);

    // --------- Montar JSON para enviar ao Flask ----------
    // Estado e validade serão calculados no Flask
    String json = "{";
    json += "\"tipoFruta\":\"" + tipoFruta + "\",";
    json += "\"temperatura\":" + String(temperatura, 1) + ",";
    json += "\"umidade_ar\":" + String(umidade_ar, 1) + ",";
    json += "\"mq3_raw\":" + String(mq3_raw) + ",";
    json += "\"mq3_tensao\":" + String(mq3_tensao, 6);
    json += "}";

    Serial.println("\nJSON Enviado:");
    Serial.println(json);

    // --------- Enviar para API Flask ----------
    if (WiFi.status() == WL_CONNECTED) {
        HTTPClient http;
        http.begin(serverURL);
        http.addHeader("Content-Type", "application/json");

        int httpCode = http.POST(json);

        Serial.print("Código HTTP: ");
        Serial.println(httpCode);

        if (httpCode > 0) {
            Serial.println(http.getString());
        } else {
            Serial.println("Erro ao enviar!");
        }

        http.end();
    }

    // ---------------------------------
    // COMPLETA CICLO PARA DAR 15 SEGUNDOS EXATOS
    // ---------------------------------
    unsigned long cicloFim = millis();
    unsigned long tempoPassado = cicloFim - cicloInicio;

    if (tempoPassado < 15000) {
        delay(15000 - tempoPassado);
    }
}
