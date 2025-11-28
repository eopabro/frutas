#include <WiFi.h>
#include <HTTPClient.h>
#include "DHT.h"

// ========= CONFIG WI-FI =========
const char* ssid = "Geovanna - NETMAIS Fibra";
const char* password = "14112003";

// ========= CONFIG DHT22 =========
#define DHTPIN 19
#define DHTTYPE DHT22
DHT dht(DHTPIN, DHTTYPE);

// ========= CONFIG MQ-3 =========
#define MQ3_PIN 32

// ========= TIPO DA FRUTA =========
String tipoFruta = "banana";  // >>> ALTERE O NOME DA FRUTA AQUI <<<

// ========= ENDEREÇO DO SERVIDOR FLASK =========
String serverURL = "http://192.168.3.75/api/sensores";

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

void setup() {
  Serial.begin(115200);
  delay(3000);

  conectaWiFi();
  dht.begin();

  pinMode(MQ3_PIN, INPUT);
}

void loop() {
  conectaWiFi(); // reconecta se cair

  // ======= COLETA DHT22 =======
  float temperatura = dht.readTemperature();
  float umidade_ar = dht.readHumidity();

  if (isnan(temperatura) || isnan(umidade_ar)) {
    Serial.println("Erro ao ler DHT22!");
    delay(2000);
    return;
  }

  // ======= COLETA MQ-3 =======
  int mq3_raw = analogRead(MQ3_PIN);
  float mq3_tensao = mq3_raw * (3.3 / 4095.0);

  // ======= MONTA JSON =======
  String json;
  json += "{";
  json += "\"tipoFruta\":\"" + tipoFruta + "\",";
  json += "\"temperatura\":" + String(temperatura, 1) + ",";
  json += "\"umidade_ar\":" + String(umidade_ar, 1) + ",";
  json += "\"mq3_raw\":" + String(mq3_raw) + ",";
  json += "\"mq3_tensao\":" + String(mq3_tensao, 6);
  json += "}";

  Serial.println("\nJSON Enviado:");
  Serial.println(json);

  // ======= ENVIA PARA FLASK =======
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    http.begin(serverURL);
    http.addHeader("Content-Type", "application/json");

    int httpCode = http.POST(json);

    Serial.print("Código HTTP: ");
    Serial.println(httpCode);

    if (httpCode > 0) {
      String resposta = http.getString();
      Serial.println(resposta);
    } else {
      Serial.println("Erro ao enviar!");
    }

    http.end();
  }

  delay(5000); // envia a cada 5s
}
