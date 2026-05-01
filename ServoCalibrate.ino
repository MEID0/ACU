// Servo range-finder & centering for AGFRC IA73BHLW
// Hardware: Arduino UNO R4 Minima + PCA9685 + ACS712 + servo with analog feedback
//   A0 = ACS712 output (current sense)
//   A1 = servo position feedback
//   I2C = PCA9685 (default address 0x40), servo on channel SERVO_CH
//
// Procedure:
//   1) Measure ACS712 zero-current baseline with the servo briefly idle.
//   2) Step PWM upward from center until current spike => upper mechanical stop.
//   3) Step PWM downward from center until current spike => lower mechanical stop.
//   4) Record feedback voltage at each stop, compute center, drive to center.
//   5) Print results over Serial.

#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>

// ---------- User-tunable parameters ----------
constexpr uint8_t  SERVO_CH        = 0;     // PCA9685 channel
constexpr uint16_t PWM_FREQ_HZ     = 50;    // standard servo frame rate
constexpr uint16_t PWM_START       = 307;   // ~1500 us, nominal center (4096 * 1.5ms / 20ms)
constexpr uint16_t PWM_MIN_LIMIT   = 100;   // hard floor (~488 us) -- never command below
constexpr uint16_t PWM_MAX_LIMIT   = 600;   // hard ceiling (~2930 us) -- never command above
constexpr uint16_t PWM_STEP        = 2;     // counts per step during sweep
constexpr uint16_t STEP_DELAY_MS   = 40;    // settle time per step

// ACS712 settings (5A=185, 20A=100, 30A=66 mV/A)
constexpr float    ACS_MV_PER_AMP  = 185.0f;
constexpr float    VREF_MV         = 5000.0f;
constexpr uint8_t  ADC_BITS        = 12;    // R4 Minima supports 12/14
constexpr float    STALL_THRESH_A  = 0.35f; // current rise above idle that means "hit a stop"
constexpr uint8_t  STALL_CONFIRM   = 1.5;     // consecutive over-threshold reads required

// Pins
constexpr uint8_t  PIN_CURRENT     = A0;
constexpr uint8_t  PIN_FEEDBACK    = A1;

// ---------- Globals ----------
Adafruit_PWMServoDriver pwm = Adafruit_PWMServoDriver();
float adc_counts_max;
float idle_current_mv = 0.0f;   // ACS712 zero-current output (~VCC/2)

// ---------- Helpers ----------
float readADC_mV(uint8_t pin, uint8_t samples = 16) {
  uint32_t acc = 0;
  for (uint8_t i = 0; i < samples; i++) acc += analogRead(pin);
  float counts = acc / (float)samples;
  return (counts / adc_counts_max) * VREF_MV;
}

float readCurrent_A() {
  float mv = readADC_mV(PIN_CURRENT);
  return (mv - idle_current_mv) / ACS_MV_PER_AMP;
}

float readFeedback_V() {
  return readADC_mV(PIN_FEEDBACK) / 1000.0f;
}

void commandPWM(uint16_t counts) {
  if (counts < PWM_MIN_LIMIT) counts = PWM_MIN_LIMIT;
  if (counts > PWM_MAX_LIMIT) counts = PWM_MAX_LIMIT;
  pwm.setPWM(SERVO_CH, 0, counts);
}

// Sweep from `start` toward `limit` (step is signed). Returns the last safe PWM
// before stall, and writes the feedback voltage there into `fb_out`.
uint16_t sweepUntilStall(uint16_t start, int16_t step, uint16_t limit, float& fb_out) {
  uint16_t pwm_val = start;
  uint16_t last_safe = start;
  uint8_t  over = 0;

  while (true) {
    int32_t next = (int32_t)pwm_val + step;
    if (step > 0 && next > limit) break;
    if (step < 0 && next < limit) break;
    pwm_val = (uint16_t)next;

    commandPWM(pwm_val);
    delay(STEP_DELAY_MS);

    float i_a = fabs(readCurrent_A());
    if (i_a > STALL_THRESH_A) {
      over++;
      if (over >= STALL_CONFIRM) {
        // back off one step and report
        int32_t safe = (int32_t)pwm_val - step;
        last_safe = (uint16_t)safe;
        commandPWM(last_safe);
        delay(150);
        fb_out = readFeedback_V();
        return last_safe;
      }
    } else {
      over = 0;
      last_safe = pwm_val;
    }
  }
  // hit configured limit without stalling
  commandPWM(last_safe);
  delay(150);
  fb_out = readFeedback_V();
  return last_safe;
}

void setup() {
  Serial.begin(115200);
  while (!Serial && millis() < 3000) {}

  analogReadResolution(ADC_BITS);
  adc_counts_max = (float)((1UL << ADC_BITS) - 1);

  pinMode(PIN_CURRENT, INPUT);
  pinMode(PIN_FEEDBACK, INPUT);

  Wire.begin();
  pwm.begin();
  pwm.setOscillatorFrequency(27000000);
  pwm.setPWMFreq(PWM_FREQ_HZ);

  // Park at nominal center, then measure quiescent ACS712 output
  commandPWM(PWM_START);
  delay(800);
  idle_current_mv = readADC_mV(PIN_CURRENT);

  Serial.println(F("=== Servo Calibration ==="));
  Serial.print(F("ACS712 idle output: ")); Serial.print(idle_current_mv, 1); Serial.println(F(" mV"));
  Serial.print(F("Stall threshold:    ")); Serial.print(STALL_THRESH_A, 2); Serial.println(F(" A"));
  Serial.println();

  // --- Find upper mechanical stop ---
  Serial.println(F("Sweeping toward PWM_MAX..."));
  float fb_high = 0.0f;
  uint16_t pwm_high = sweepUntilStall(PWM_START, +PWM_STEP, PWM_MAX_LIMIT, fb_high);
  Serial.print(F("  upper safe PWM = ")); Serial.print(pwm_high);
  Serial.print(F("  feedback = "));       Serial.print(fb_high, 3); Serial.println(F(" V"));

  // Return through center before sweeping the other way
  commandPWM(PWM_START);
  delay(600);

  // --- Find lower mechanical stop ---
  Serial.println(F("Sweeping toward PWM_MIN..."));
  float fb_low = 0.0f;
  uint16_t pwm_low = sweepUntilStall(PWM_START, -PWM_STEP, PWM_MIN_LIMIT, fb_low);
  Serial.print(F("  lower safe PWM = ")); Serial.print(pwm_low);
  Serial.print(F("  feedback = "));       Serial.print(fb_low, 3); Serial.println(F(" V"));

  // --- Compute and drive to center ---
  uint16_t pwm_center = (pwm_high + pwm_low) / 2;
  commandPWM(pwm_center);
  delay(800);
  float fb_center = readFeedback_V();

  Serial.println();
  Serial.println(F("=== Results (record these per motor) ==="));
  Serial.print(F("PWM low / center / high : "));
  Serial.print(pwm_low);    Serial.print(F(" / "));
  Serial.print(pwm_center); Serial.print(F(" / "));
  Serial.println(pwm_high);
  Serial.print(F("FB  low / center / high : "));
  Serial.print(fb_low, 3);    Serial.print(F(" V / "));
  Serial.print(fb_center, 3); Serial.print(F(" V / "));
  Serial.print(fb_high, 3);   Serial.println(F(" V"));
  Serial.print(F("Travel (PWM counts)     : ")); Serial.println(pwm_high - pwm_low);
  Serial.println(F("Holding at center. Power down to swap motors."));
}

void loop() {
  // Idle hold + occasional status so you can confirm it's still centered.
  static uint32_t last = 0;
  if (millis() - last > 2000) {
    last = millis();
    Serial.print(F("hold  fb=")); Serial.print(readFeedback_V(), 3);
    Serial.print(F(" V  I=")); Serial.print(readCurrent_A(), 3); Serial.println(F(" A"));
  }
}
