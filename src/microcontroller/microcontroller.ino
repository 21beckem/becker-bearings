#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>

// Uses default I2C address 0x40
Adafruit_PWMServoDriver boards[2] = {
  Adafruit_PWMServoDriver(0x40), // Board 0
  Adafruit_PWMServoDriver(0x41)  // Board 1
};
const uint16_t PWM_LEVELS[3] = {150, 325, 500};
struct ChannelTarget {
  uint8_t board; // 0 or 1
  uint8_t pin;   // 0 to 9
};
const ChannelTarget channelMap[20] = {
  {0, 2}, // Pinky
  {0, 8},
  {0, 7},
  {1, 9},
  {1, 7},
  
  {0, 3}, // Ring
  {0, 4},
  {1, 8},
  {1, 4},
  {1, 5},
  
  {0, 1}, // Middle
  {0, 5},
  {1, 2},
  {0, 9},
  {1, 6},
  
  {0, 6}, // Index
  {0, 0},
  {1, 0},
  {1, 1},
  {1, 3}
};

#define SDA_PIN 12  // D6
#define SCL_PIN 14  // D5

uint8_t lastState[20] = {
  0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF,
  0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF
};

const uint8_t SYNC_BYTE = 0xFF;
uint8_t rxBuffer[5];
uint8_t rxIndex = 0;
bool synced = false;

inline void handleChannel(uint8_t ch, uint8_t val) {
  // Guard against invalid values (3) and skip redundant I2C writes
  if (val > 2 || val == lastState[ch]) return;
  lastState[ch] = val;

  // Instant O(1) lookup
  uint8_t boardIdx = channelMap[ch].board;
  uint8_t pin      = channelMap[ch].pin;

  Serial.print("Setting board ");
  Serial.print(boardIdx, DEC);
  Serial.print(" pin ");
  Serial.print(pin, DEC);
  Serial.print(" to PWM level ");
  Serial.println(PWM_LEVELS[val], DEC);
  boards[boardIdx].setPWM(pin, 0, PWM_LEVELS[val]);
}

bool boardPresent(uint8_t addr) {
  Wire.beginTransmission(addr);
  return Wire.endTransmission() == 0;
}

void processSerial() {
  while (Serial.available() > 0) {
    uint8_t inByte = Serial.read();

    if (inByte == SYNC_BYTE) {
      rxIndex = 0;
      synced = true;
      continue;
    }

    if (synced) {
      rxBuffer[rxIndex++] = inByte;

      if (rxIndex == 5) {
        synced = false;
        for (uint8_t ch = 0; ch < 20; ch++) {
          uint8_t byteIdx = ch >> 2;
          uint8_t bitShift = (ch & 0x03) << 1;
          uint8_t val = (rxBuffer[byteIdx] >> bitShift) & 0x03;

          handleChannel(ch, val);
        }
      }
    }
  }
}

void setup() {
  Serial.begin(115200);
  
  Wire.begin(SDA_PIN, SCL_PIN);

  bool okA = boardPresent(0x40);
  bool okB = boardPresent(0x41);
  Serial.println();
  Serial.print(F("Board A (0x40): ")); Serial.println(okA ? F("found") : F("NOT FOUND"));
  Serial.print(F("Board B (0x41): ")); Serial.println(okB ? F("found") : F("NOT FOUND"));

  boards[0].begin();
  boards[1].begin();

  boards[0].setOscillatorFrequency(27000000);
  boards[1].setOscillatorFrequency(27000000);
  boards[0].setPWMFreq(50);
  boards[1].setPWMFreq(50);
  delay(10);
}

void loop() {
  processSerial();
}