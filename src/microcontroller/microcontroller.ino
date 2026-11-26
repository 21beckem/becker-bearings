#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>

// ===================== Hardware =====================
Adafruit_PWMServoDriver boards[2] = {
  Adafruit_PWMServoDriver(0x40), // Board 0
  Adafruit_PWMServoDriver(0x41)  // Board 1
};
const uint16_t PWM_LEVELS[3] = {0, 87, 175}; // Amplitude (counts) for level 0/1/2
const uint16_t PWM_CENTER = 325;
const uint16_t PWM_FULL_OFF = 4096;          // PCA9685 "full off" bit: no pulses at all

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

// ===================== Motion tuning =====================
// How fast a servo is allowed to move, in PWM counts per second.
// Rough guide: ~205 counts is about 1 ms of pulse width (~180 degrees), and an
// SG90 tops out somewhere around 600-700 counts/s. A full level-2 swing is 350
// counts, so 400 means that swing takes ~0.9 s. Set very high (e.g. 100000)
// to get the old instant-snap behavior back.
const float SLEW_COUNTS_PER_SEC = 400.0f;

// The PCA9685 runs at 50 Hz, so a servo only sees a new target every 20 ms.
// Updating faster than this does nothing.
const uint16_t UPDATE_INTERVAL_MS = 20;

// ===================== Test mode =====================
// Lets you test without the PC program. Three ways to use it:
//   1. Set TEST_MODE_AT_BOOT to true and upload.
//   2. Send the character 't' from the IDE's serial monitor to toggle it.
//   3. (Automatic) It switches itself OFF the moment a real frame arrives
//      from the PC program, so it can never fight the host.
// Each second the test servo reverses direction (like one "tick" of the clock).
// It oscillates for TEST_ON_TICKS seconds, then is cut OFF for TEST_OFF_TICKS
// seconds, then repeats, so you can also feel how the cutoff behaves.
const bool     TEST_MODE_AT_BOOT = false;
const uint8_t  TEST_CHANNEL      = 0;   // Which servo (0-19)
const uint8_t  TEST_LEVEL        = 2;   // 1 or 2
const uint8_t  TEST_ON_TICKS     = 6;
const uint8_t  TEST_OFF_TICKS    = 2;
const uint16_t TEST_TICK_MS      = 1000;

// ===================== State =====================
const uint8_t SYNC_BYTE = 0xFF;
uint8_t rxBuffer[5];
uint8_t rxIndex = 0;
bool synced = false;
int toggle = 1;
bool shouldToggle = false;

float   pos[20];          // Where we last told each servo to be (counts)
float   target[20];       // Where each servo is heading (counts)
bool    enabled[20];      // false = signal is cut (servo limp, no pulses)
uint32_t lastUpdateMs = 0;

bool     testMode = TEST_MODE_AT_BOOT;
uint32_t lastTestTickMs = 0;
uint8_t  testTick = 0;

// ===================== Channel control =====================

// Stop sending pulses to this channel. The servo stays wherever it is
// (nothing is commanded to move), and pos[] remembers that spot so the next
// time it turns on it starts from there instead of jumping.
void cutChannel(uint8_t ch) {
  enabled[ch] = false;
  boards[channelMap[ch].board].setPWM(channelMap[ch].pin, 0, PWM_FULL_OFF);
}

// Called once per channel per frame. It only sets the goal; actual movement
// happens (rate-limited) in updateServos().
inline void handleChannel(uint8_t ch, uint8_t val) {
  if (val > 2) return; // Guard against invalid value (3)

  if (val == 0) {
    if (enabled[ch]) cutChannel(ch); // OFF = stop, don't move anywhere
    return;
  }

  target[ch] = PWM_CENTER + (int)PWM_LEVELS[val] * toggle;
  enabled[ch] = true;
}

// Moves every enabled servo toward its target at no more than
// SLEW_COUNTS_PER_SEC, and only touches I2C when a value actually changes.
void updateServos() {
  uint32_t now = millis();
  uint32_t dt = now - lastUpdateMs;
  if (dt < UPDATE_INTERVAL_MS) return;
  lastUpdateMs = now;

  float maxStep = SLEW_COUNTS_PER_SEC * (float)dt / 1000.0f;

  for (uint8_t ch = 0; ch < 20; ch++) {
    if (!enabled[ch]) continue;

    float diff = target[ch] - pos[ch];
    if (diff > maxStep)       pos[ch] += maxStep;
    else if (diff < -maxStep) pos[ch] -= maxStep;
    else                      pos[ch] = target[ch];

    // Re-send every tick, even if unchanged. A lost or garbled I2C write then
    // heals itself on the next tick, like the original per-frame behavior.
    int16_t out = (int16_t)(pos[ch] + 0.5f);
    boards[channelMap[ch].board].setPWM(channelMap[ch].pin, 0, out);
  }
}

// ===================== Test mode =====================

void setTestMode(bool on) {
  testMode = on;
  if (on) {
    testTick = 0;
    lastTestTickMs = millis() - TEST_TICK_MS; // First tick fires right away
    Serial.println(F("TEST MODE: on"));
  } else {
    for (uint8_t ch = 0; ch < 20; ch++) handleChannel(ch, 0);
    Serial.println(F("TEST MODE: off"));
  }
}

void runTest() {
  uint32_t now = millis();
  if (now - lastTestTickMs < TEST_TICK_MS) return;
  lastTestTickMs = now;

  bool on = (testTick % (TEST_ON_TICKS + TEST_OFF_TICKS)) < TEST_ON_TICKS;
  testTick++;
  toggle = -toggle; // Reverse direction every tick

  for (uint8_t ch = 0; ch < 20; ch++) {
    handleChannel(ch, (on && ch == TEST_CHANNEL) ? TEST_LEVEL : 0);
  }

  Serial.print(F("TEST tick: "));
  if (on) {
    Serial.print(F("ON, dir "));
    Serial.println(toggle > 0 ? F("+") : F("-"));
  } else {
    Serial.println(F("OFF (signal cut)"));
  }
}

// ===================== Serial =====================

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

    if (!synced) {
      // Outside a frame, 't' toggles test mode (for the IDE's serial monitor).
      if (inByte == 't') setTestMode(!testMode);
      continue;
    }

    rxBuffer[rxIndex++] = inByte;

    if (rxIndex == 5) {
      synced = false;

      // A real frame means the PC program is driving; test mode steps aside.
      if (testMode) setTestMode(false);

      for (uint8_t ch = 0; ch < 20; ch++) {
        uint8_t byteIdx = ch >> 2;
        uint8_t bitShift = (ch & 0x03) << 1;
        uint8_t val = (rxBuffer[byteIdx] >> bitShift) & 0x03;

        handleChannel(ch, val);
      }
      shouldToggle = !shouldToggle; // Toggle every other frame
      if (shouldToggle) {
        toggle = -toggle; // Alternate the PWM direction
      }
    }
  }
}

// ===================== Arduino entry points =====================

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

  for (uint8_t ch = 0; ch < 20; ch++) {
    pos[ch] = PWM_CENTER;
    target[ch] = PWM_CENTER;
    enabled[ch] = false;
  }

  lastUpdateMs = millis();
  if (testMode) setTestMode(true);
}

void loop() {
  processSerial();
  if (testMode) runTest();
  updateServos();
}