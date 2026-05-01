#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>

Adafruit_PWMServoDriver pwm = Adafruit_PWMServoDriver(0x40);

const int CURRENT_PIN = A0;
const int FEEDBACK_PIN = A1;

int PULSE_MIN = 101;
int PULSE_MAX = 599;
int targetPulse;
int midPulse;

void setup() {
  Serial.begin(115200);
  analogReadResolution(14);
  pwm.begin();
  pwm.setPWMFreq(50);
  
  int initialPos = 0;
  while(initialPos < 4000) {
    initialPos = analogRead(FEEDBACK_PIN);
    delay(50);
  }

  targetPulse = map(initialPos, 7500-((PULSE_MIN-270)*17.22), 4400-((PULSE_MAX-450)*17.22), PULSE_MIN, PULSE_MAX);
  targetPulse = constrain(targetPulse, PULSE_MIN, PULSE_MAX);

  midPulse = 350;
  pwm.setPWM(0, 0, midPulse);
  Serial.println("Armed.");
}

void loop() {
  if (Serial.available() > 0) {
    char peekCmd = Serial.peek();
    
    if (peekCmd == 'q') {
      Serial.read();
      targetPulse += 1;
    } else if (peekCmd == 'a') {
      Serial.read();
      targetPulse -= 1;
    } else if (isDigit(peekCmd)) {
      targetPulse = Serial.parseInt();
    } else {
      Serial.read();
    }
    
    targetPulse = constrain(targetPulse, PULSE_MIN, PULSE_MAX);
    pwm.setPWM(0, 0, targetPulse);
    
    Serial.print("Target_PWM:");
    Serial.print(targetPulse);
    Serial.print(",Current_Raw:");
    Serial.println(analogRead(CURRENT_PIN));
  }
}