
#include <Wire.h>
#include <Adafruit_INA219.h>

// ---------- Pins ----------
#define SDA_PIN   21
#define SCL_PIN   22
#define LM35_PIN  34

#define PIN_PWMA  25
#define PIN_AIN1  26
#define PIN_AIN2  27
#define PIN_STBY  14

#define TEST_SPEED     150
#define TEMP_OFFSET_C  0.0

// MPU6050 registers
#define MPU_ADDR       0x68
#define REG_PWR_MGMT_1 0x6B
#define REG_ACCEL_XOUT_H 0x3B
#define REG_GYRO_XOUT_H  0x43
#define REG_WHO_AM_I   0x75

Adafruit_INA219 ina;
bool mpuOk = false;
bool inaOk = false;
bool motorOn = false;

#if ESP_ARDUINO_VERSION_MAJOR >= 3
void pwmInit() { ledcAttach(PIN_PWMA, 20000, 8); }
void pwmDuty(uint8_t d) { ledcWrite(PIN_PWMA, d); }
#else
void pwmInit() {
  ledcSetup(0, 20000, 8);
  ledcAttachPin(PIN_PWMA, 0);
}
void pwmDuty(uint8_t d) { ledcWrite(0, d); }
#endif

void motorRun(uint8_t speed) {
  digitalWrite(PIN_STBY, HIGH);
  digitalWrite(PIN_AIN1, HIGH);
  digitalWrite(PIN_AIN2, LOW);
  pwmDuty(speed);
  motorOn = true;
}

void motorStop() {
  pwmDuty(0);
  digitalWrite(PIN_AIN1, LOW);
  digitalWrite(PIN_AIN2, LOW);
  digitalWrite(PIN_STBY, LOW);
  motorOn = false;
}

bool writeReg(uint8_t reg, uint8_t value) {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(reg);
  Wire.write(value);
  return Wire.endTransmission() == 0;
}

bool readRegs(uint8_t reg, uint8_t *buf, uint8_t len) {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) return false;

  uint8_t received = Wire.requestFrom(MPU_ADDR, len, true);
  if (received != len) return false;

  for (uint8_t i = 0; i < len; i++) {
    buf[i] = Wire.read();
  }
  return true;
}

int16_t readInt16(uint8_t *b) {
  return (int16_t)((uint16_t)b[0] << 8 | b[1]);
}

bool initMPU() {
  uint8_t who = 0;

  if (!readRegs(REG_WHO_AM_I, &who, 1)) {
    Serial.println("MPU: WHO_AM_I read failed");
    return false;
  }

  Serial.printf("MPU WHO_AM_I = 0x%02X\n", who);

  // MPU6050 normally returns 0x68
  
if (who != 0x68 && who != 0x70) {
  Serial.println("Unknown chip ID; check module");
  return false;
}

if (who == 0x70) {
  Serial.println("MPU6500-compatible sensor detected");
}


  // Wake up the sensor
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

bool readMPU(float &ax, float &ay, float &az,
             float &gx, float &gy, float &gz) {
  uint8_t b[14];

  if (!readRegs(REG_ACCEL_XOUT_H, b, 14)) return false;

  int16_t rawAx = readInt16(&b[0]);
  int16_t rawAy = readInt16(&b[2]);
  int16_t rawAz = readInt16(&b[4]);

  // Temperature raw value at b[6..7] is not needed here

  int16_t rawGx = readInt16(&b[8]);
  int16_t rawGy = readInt16(&b[10]);
  int16_t rawGz = readInt16(&b[12]);

  // +/-8g: 4096 LSB/g. Convert to m/s^2.
  ax = rawAx / 4096.0 * 9.80665;
  ay = rawAy / 4096.0 * 9.80665;
  az = rawAz / 4096.0 * 9.80665;

  // +/-500 degrees/s: 65.5 LSB per degree/s.
  // Convert degrees/s to radians/s.
  const float DEG_TO_RAD_VALUE = 0.01745329252;
  gx = rawGx / 65.5 * DEG_TO_RAD_VALUE;
  gy = rawGy / 65.5 * DEG_TO_RAD_VALUE;
  gz = rawGz / 65.5 * DEG_TO_RAD_VALUE;

  return true;
}

float readTempC() {
  uint32_t sum = 0;

  for (int i = 0; i < 20; i++) {
    sum += analogReadMilliVolts(LM35_PIN);
    delay(2);
  }

  return (sum / 20.0) / 10.0 + TEMP_OFFSET_C;
}

void i2cScan() {
  Serial.println("\n--- I2C scan ---");
  int found = 0;

  for (uint8_t addr = 1; addr < 127; addr++) {
    Wire.beginTransmission(addr);
    if (Wire.endTransmission() == 0) {
      Serial.printf("Device at 0x%02X\n", addr);
      found++;
    }
  }

  if (found == 0) Serial.println("No I2C devices found");
  Serial.println("--- scan end ---");
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("\n===== HARDWARE TEST: DIRECT MPU =====");

  pinMode(PIN_AIN1, OUTPUT);
  pinMode(PIN_AIN2, OUTPUT);
  pinMode(PIN_STBY, OUTPUT);
  pwmInit();
  motorStop();

  analogSetPinAttenuation(LM35_PIN, ADC_11db);

  Wire.begin(SDA_PIN, SCL_PIN);
  Wire.setClock(100000);
  delay(100);

  i2cScan();

  mpuOk = initMPU();
  Serial.printf("MPU6050 direct I2C: %s\n",
                mpuOk ? "OK" : "FAIL");

  inaOk = ina.begin(&Wire);
  Serial.printf("INA219: %s\n", inaOk ? "OK" : "FAIL");

  Serial.println("Commands: f = motor ON, s = motor OFF");
  Serial.println("====================================");
}

void loop() {
  while (Serial.available()) {
    char c = Serial.read();

    if (c == 'f' || c == 'F') {
      motorRun(TEST_SPEED);
      Serial.println(">> MOTOR ON");
    }

    if (c == 's' || c == 'S') {
      motorStop();
      Serial.println(">> MOTOR OFF");
    }
  }

  static unsigned long last = 0;
  if (millis() - last < 500) return;
  last = millis();

  Serial.printf("Temp %.1fC", readTempC());

  if (mpuOk) {
    float ax, ay, az, gx, gy, gz;

    if (readMPU(ax, ay, az, gx, gy, gz)) {
      Serial.printf(
        " | Acc %.2f %.2f %.2f m/s2"
        " | Gyro %.3f %.3f %.3f rad/s",
        ax, ay, az, gx, gy, gz
      );
    } else {
      Serial.print(" | MPU READ ERROR");
    }
  } else {
    Serial.print(" | MPU NOT INITIALIZED");
  }

  if (inaOk) {
    Serial.printf(" | V %.2f V | Shunt %.3f mV | I %.2f mA",
              ina.getBusVoltage_V(),
              ina.getShuntVoltage_mV(),
              ina.getCurrent_mA());
  } else {
    Serial.print(" | INA219 FAIL");
  }

  Serial.printf(" | Motor %s\n", motorOn ? "ON" : "OFF");
}
