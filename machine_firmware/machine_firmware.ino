
#include <WiFi.h>
#include "secrets.h"
#include <Wire.h>
#include <PubSubClient.h>
#include <Adafruit_INA219.h>



const int MQTT_PORT = 1883;

// ================= PINS =================
#define SDA_PIN   21
#define SCL_PIN   22
#define LM35_PIN  34

#define PIN_PWMA  25
#define PIN_AIN1  26
#define PIN_AIN2  27
#define PIN_STBY  14

#define MOTOR_SPEED       150
#define SAMPLE_MS         500
#define TEMP_OFFSET_C     0.0

// Local safety limits
#define FS_MAX_TEMP_C     75.0
#define FS_MAX_CURRENT_A  2
#define LINK_TIMEOUT_MS   3000

// Startup/noise tolerance (motor start ke waqt inrush current aur I2C noise aata hai)
#define STARTUP_GRACE_MS      1500   // start ke baad itni der current limit = FS_ABS_MAX_CURRENT_A
#define FS_ABS_MAX_CURRENT_A  3.0    // grace me bhi ye limit hamesha active (INA219 ~3.2A pe saturate hota hai)
#define SENSOR_FAIL_LIMIT     3      // lagatar itne samples fail hon tabhi motor roko (3 x SAMPLE_MS)

// ================= MPU6050 =================
#define MPU_ADDR          0x68
#define REG_PWR_MGMT_1    0x6B
#define REG_ACCEL_XOUT_H  0x3B
#define REG_TEMP_OUT_H    0x41
#define REG_WHO_AM_I      0x75

// ================= MQTT TOPICS =================
const char* TOPIC_SENSORS = "machine/sensors";
const char* TOPIC_CONTROL = "machine/control";
const char* TOPIC_STATUS  = "machine/status";

WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);
Adafruit_INA219 ina;

bool mpuOk = false;
bool inaOk = false;
bool motorRunning = false;

// Motor will NOT auto-start after boot or reconnection.
bool stopLatched = true;

unsigned long motorStartMs = 0;
uint8_t sensorFailCount = 0;

unsigned long lastLinkOk = 0;
unsigned long lastSample = 0;
unsigned long lastMqttTry = 0;
unsigned long lastWifiTry = 0;

// ================= PWM: ESP32 CORE 2.x / 3.x =================
#if ESP_ARDUINO_VERSION_MAJOR >= 3
void pwmInit() {
  ledcAttach(PIN_PWMA, 20000, 8);
}
void pwmDuty(uint8_t duty) {
  ledcWrite(PIN_PWMA, duty);
}
#else
void pwmInit() {
  ledcSetup(0, 20000, 8);
  ledcAttachPin(PIN_PWMA, 0);
}
void pwmDuty(uint8_t duty) {
  ledcWrite(0, duty);
}
#endif

// ================= MOTOR =================
void publishStatus() {
  if (mqtt.connected()) {
    mqtt.publish(
      TOPIC_STATUS,
      motorRunning ? "RUNNING" : "STOPPED",
      true
    );
  }
}

void motorStop(const char* reason) {
  pwmDuty(0);
  digitalWrite(PIN_AIN1, LOW);
  digitalWrite(PIN_AIN2, LOW);
  digitalWrite(PIN_STBY, LOW);

  if (motorRunning) {
    Serial.printf("MOTOR STOP: %s\n", reason);
  }

  motorRunning = false;
  stopLatched = true;
  publishStatus();
}

void motorStart() {
  if (!mpuOk || !inaOk) {
  Serial.println("START rejected: required sensor unavailable");
  return;
}
  if (!mqtt.connected() || WiFi.status() != WL_CONNECTED) {
    Serial.println("START rejected: MQTT/WiFi disconnected");
    return;
  }

  stopLatched = false;

  digitalWrite(PIN_STBY, HIGH);
  digitalWrite(PIN_AIN1, HIGH);
  digitalWrite(PIN_AIN2, LOW);
  pwmDuty(MOTOR_SPEED);

  motorStartMs = millis();
  sensorFailCount = 0;
  motorRunning = true;
  lastLinkOk = millis();

  Serial.println("MOTOR START");
  publishStatus();
}

// ================= MPU6050 DIRECT I2C =================
bool writeReg(uint8_t reg, uint8_t value) {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(reg);
  Wire.write(value);
  return Wire.endTransmission() == 0;
}

bool readRegs(uint8_t reg, uint8_t* buf, uint8_t len) {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(reg);

  uint8_t err = Wire.endTransmission(false);
  if (err != 0) {
    Serial.printf("I2C register select failed: reg=0x%02X err=%u\n",
                  reg, err);
    return false;
  }

  uint8_t received = Wire.requestFrom(MPU_ADDR, len, (uint8_t)true);

  if (received != len) {
    Serial.printf("I2C short read: reg=0x%02X expected=%u got=%u\n",
                  reg, len, received);

    while (Wire.available()) {
      Wire.read();
    }
    return false;
  }

  for (uint8_t i = 0; i < len; i++) {
    if (!Wire.available()) {
      Serial.printf("I2C buffer ended early: reg=0x%02X\n", reg);
      return false;
    }
    buf[i] = Wire.read();
  }

  return true;
}


int16_t readInt16(uint8_t* b) {
  return (int16_t)(((uint16_t)b[0] << 8) | b[1]);
}

bool initMPU() {
  uint8_t who = 0;

  if (!readRegs(REG_WHO_AM_I, &who, 1)) {
    Serial.println("MPU: WHO_AM_I read failed");
    return false;
  }

  Serial.printf("MPU WHO_AM_I = 0x%02X\n", who);

  if (who != 0x68 && who != 0x70) {
    Serial.println("Unknown MPU chip ID");
    return false;
  }

  if (!writeReg(REG_PWR_MGMT_1, 0x00)) return false;
  delay(100);

  // Accelerometer +/- 8g
  if (!writeReg(0x1C, 0x10)) return false;

  // Gyroscope +/- 500 degrees/second
  if (!writeReg(0x1B, 0x08)) return false;

  // Digital low-pass filter
  if (!writeReg(0x1A, 0x04)) return false;

  return true;
}

bool readMPU(
  float& ax, float& ay, float& az,
  float& gx, float& gy, float& gz
) {
  uint8_t b[14];

  if (!readRegs(REG_ACCEL_XOUT_H, b, 14)) {
    return false;
  }

  int16_t rawAx = readInt16(&b[0]);
  int16_t rawAy = readInt16(&b[2]);
  int16_t rawAz = readInt16(&b[4]);

  int16_t rawGx = readInt16(&b[8]);
  int16_t rawGy = readInt16(&b[10]);
  int16_t rawGz = readInt16(&b[12]);

  // Acceleration in m/s^2
  ax = rawAx / 4096.0 * 9.80665;
  ay = rawAy / 4096.0 * 9.80665;
  az = rawAz / 4096.0 * 9.80665;

  // Gyroscope in rad/s
  const float DEG_TO_RAD_VALUE = 0.01745329252;

  gx = rawGx / 65.5 * DEG_TO_RAD_VALUE;
  gy = rawGy / 65.5 * DEG_TO_RAD_VALUE;
  gz = rawGz / 65.5 * DEG_TO_RAD_VALUE;

  return true;
}

bool readMPUWithRetry(
  float& ax, float& ay, float& az,
  float& gx, float& gy, float& gz
) {
  for (int attempt = 0; attempt < 3; attempt++) {
    if (readMPU(ax, ay, az, gx, gy, gz)) return true;
    delay(3);
  }
  return false;
}

// ================= TEMPERATURE: MPU6050 internal sensor =================
// (LM35 abhi use nahi ho raha; LM35_PIN sirf ADC setup ke liye hai)


float readTempC() {
  uint8_t b[2];

  // Retry up to 3 times if the I2C read fails
  for (int attempt = 0; attempt < 5; attempt++) {
    if (mpuOk && readRegs(REG_TEMP_OUT_H, b, 2)) {
      int16_t raw = readInt16(b);
      return (raw / 340.0f) + 36.53f;
    }

    delay(5);
  }

  return -999.0f;  // All retries failed
}



// ================= MQTT CONTROL =================
void onMessage(char* topic, byte* payload, unsigned int len) {
  if (strcmp(topic, TOPIC_CONTROL) != 0) {
    return;
  }

  char msg[64];

  if (len >= sizeof(msg)) {
    len = sizeof(msg) - 1;
  }

  memcpy(msg, payload, len);
  msg[len] = '\0';

  Serial.printf("MQTT control: %s\n", msg);

  if (strstr(msg, "STOP") != nullptr) {
    motorStop("command from backend");
  }
  else if (strstr(msg, "START") != nullptr) {
    motorStart();
  }
}

// ================= CONNECTIONS =================

void ensureConnections() {
  // WiFi.begin() is already called in setup().
  // Do not repeatedly restart the initial connection attempt.
  if (WiFi.status() != WL_CONNECTED) {
    return;
  }

  if (!mqtt.connected()) {
    if (millis() - lastMqttTry >= 2000) {
      lastMqttTry = millis();
      Serial.print("MQTT connect... ");

      if (mqtt.connect("esp32-machine")) {
        Serial.println("OK");

        mqtt.subscribe(TOPIC_CONTROL, 1);
        lastLinkOk = millis();
        publishStatus();
      } else {
        Serial.printf("FAIL rc=%d\n", mqtt.state());
      }
    }
  }
}


// ================= SETUP =================
void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("\n=== MACHINE HEALTH MONITOR ===");

  pinMode(PIN_AIN1, OUTPUT);
  pinMode(PIN_AIN2, OUTPUT);
  pinMode(PIN_STBY, OUTPUT);

  pwmInit();
  motorStop("boot");

  analogSetPinAttenuation(LM35_PIN, ADC_11db);

  Wire.begin(SDA_PIN, SCL_PIN);
  Wire.setClock(100000);
  delay(100);

  mpuOk = initMPU();
  Serial.printf("MPU6050 direct I2C: %s\n", mpuOk ? "OK" : "FAIL");

  inaOk = ina.begin(&Wire);
  Serial.printf("INA219: %s\n", inaOk ? "OK" : "FAIL");

  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.println("WiFi connection started");

  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(onMessage);
  mqtt.setBufferSize(512);
  mqtt.setSocketTimeout(2);

  lastLinkOk = millis();

  Serial.println("Motor starts OFF.");
  Serial.println("Waiting for WiFi and MQTT...");
}

// ================= MAIN LOOP =================
void loop() {
  ensureConnections();
  static unsigned long lastWiFiCheck = 0;

  if (millis() - lastWiFiCheck >= 3000) {
    lastWiFiCheck = millis();

    Serial.print("WiFi status: ");
    Serial.println(WiFi.status());

    if (WiFi.status() == WL_CONNECTED) {
      Serial.print("ESP32 IP: ");
      Serial.println(WiFi.localIP());
    }
  }
  mqtt.loop();

  if (mqtt.connected() && WiFi.status() == WL_CONNECTED) {
    lastLinkOk = millis();
  }

  // Failsafe: stop motor if the connection is lost.
  if (motorRunning && millis() - lastLinkOk > LINK_TIMEOUT_MS) {
    motorStop("WiFi/MQTT link lost");
  }

  if (millis() - lastSample < SAMPLE_MS) {
    return;
  }

  lastSample = millis();

  float temp = readTempC();

  float ax = 0, ay = 0, az = 0;
  float gx = 0, gy = 0, gz = 0;

  bool mpuReadOk = mpuOk && readMPUWithRetry(ax, ay, az, gx, gy, gz);

  float busV = 0;
  float curA = 0;

  if (inaOk) {
    busV = ina.getBusVoltage_V();
    curA = ina.getCurrent_mA() / 1000.0;
  }

  Serial.printf(
    "Temp %.1f C | V %.2f V | I %.3f A",
    temp, busV, curA
  );

  if (mpuReadOk) {
    Serial.printf(
      " | Acc %.2f %.2f %.2f m/s2"
      " | Gyro %.3f %.3f %.3f rad/s",
      ax, ay, az, gx, gy, gz
    );
  } else {
    Serial.print(" | MPU READ FAIL");
  }

  Serial.printf(" | Motor %s\n", motorRunning ? "ON" : "OFF");

  bool tempValid = (temp != -999.0f);
  bool sampleValid = mpuReadOk && inaOk && tempValid;

  // Hard limits (startup ke pehle GRACE time me sirf absolute ceiling lagti hai)
  bool inGrace = motorRunning && (millis() - motorStartMs) < STARTUP_GRACE_MS;
  float currentLimit = inGrace ? FS_ABS_MAX_CURRENT_A : FS_MAX_CURRENT_A;

  if (motorRunning &&
      ((tempValid && temp > FS_MAX_TEMP_C) || (inaOk && curA > currentLimit))) {
    Serial.printf("LIMIT HIT: temp=%.1f C, current=%.3f A (limit %.2f A%s)\n",
                  temp, curA, currentLimit, inGrace ? ", startup grace" : "");
    motorStop("local hard limit");
  }

  // Sensor failure: ek glitch pe nahi, SENSOR_FAIL_LIMIT lagatar fail hone par roko
  if (motorRunning) {
    if (sampleValid) {
      sensorFailCount = 0;
    } else {
      sensorFailCount++;
      Serial.printf("SENSOR FAIL %u/%u (mpuRead=%d ina=%d temp=%d)\n",
                    sensorFailCount, SENSOR_FAIL_LIMIT, mpuReadOk, inaOk, tempValid);
      if (sensorFailCount >= SENSOR_FAIL_LIMIT) {
        motorStop("sensor read failure (repeated)");
      }
    }
  }

  // Sirf valid readings publish karo (warna 0 / -999 wale packets healthy data kharab karte hain)
  if (mqtt.connected() && sampleValid) {
    char buf[256];

    snprintf(
      buf, sizeof(buf),
      "{\"temp\":%.2f,\"ax\":%.3f,\"ay\":%.3f,\"az\":%.3f,"
      "\"gx\":%.3f,\"gy\":%.3f,\"gz\":%.3f,\"v\":%.2f,\"i\":%.4f}",
      temp, ax, ay, az, gx, gy, gz, busV, curA
    );

    if (!mqtt.publish(TOPIC_SENSORS, buf)) {
      Serial.println("MQTT publish failed");
    }
  }
}

