#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>

Adafruit_PWMServoDriver pca = Adafruit_PWMServoDriver(0x40);

// Servo channels
const int SERVO1_CHANNEL = 0;
const int SERVO2_CHANNEL = 2;

// Pulse range for most 180-degree servos
const int SERVOMIN = 110;
const int SERVOMAX = 500;

int offset = 170; // starting position

int angleToPulse(int angle) {
  angle = constrain(angle, 0, 180);
  return map(angle, 0, 180, SERVOMIN, SERVOMAX);
}

void servoWrite(int channel, int angle) {
  int pulse = angleToPulse(angle);
  pca.setPWM(channel, 0, pulse);
}

void moveOneServo(int channel) {
  // go to starting position
  servoWrite(channel, offset);
  delay(1000);

  // move from 170 → 0
  for (int pos = 170; pos >= 0; pos--) {
    servoWrite(channel, pos);
    delay(20);
  }

  delay(1000);

  // move from 0 → 170
  for (int pos = 0; pos <= 170; pos++) {
    servoWrite(channel, pos);
    delay(20);
  }

  delay(1000);
}

void setup() {
  Serial.begin(9600);

  pca.begin();
  pca.setPWMFreq(50);
  delay(500);

  Serial.println("Ready");
  Serial.println("Type 1 for servo on channel 0");
  Serial.println("Type 2 for servo on channel 2");
}

void loop() {
  if (Serial.available() > 0) {
    char command = Serial.read();

    if (command == '1') {
      Serial.println("Running servo on channel 0");
      moveOneServo(SERVO1_CHANNEL);
      Serial.println("Done channel 0");
    }

    else if (command == '2') {
      Serial.println("Running servo on channel 2");
      moveOneServo(SERVO2_CHANNEL);
      Serial.println("Done channel 2");
    }

    else if (command == '\n' || command == '\r') {
      // ignore newline
    }

    else {
      Serial.println("Unknown command");
      Serial.println("Type 1 or 2");
    }
  }
}
