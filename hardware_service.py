import logging
import time


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [HAL] - %(levelname)s - %(message)s",
)

try:
    import Jetson.GPIO as GPIO
    GPIO_AVAILABLE = True
except Exception:
    GPIO_AVAILABLE = False
    GPIO = None


class ACUHardware:
    def __init__(self, dispense_pin: int = 18, dispense_seconds: float = 2.0, presence_threshold_c: float = 35.0) -> None:
        self.dispense_pin = dispense_pin
        self.dispense_seconds = dispense_seconds
        self.presence_threshold_c = presence_threshold_c
        self._ready = False

        if GPIO_AVAILABLE:
            try:
                GPIO.setmode(GPIO.BCM)
                GPIO.setup(self.dispense_pin, GPIO.OUT, initial=GPIO.LOW)
                self._ready = True
                logging.info("Jetson GPIO mode active on pin %s.", self.dispense_pin)
            except Exception as exc:
                logging.warning("Jetson GPIO setup failed. Falling back to simulation: %s", exc)
                self._ready = False
        else:
            logging.warning("Jetson.GPIO not available. Running in HAL Development Mode (simulation).")

    def read_thermal_sensor(self) -> bool:
        logging.info("Polling thermal presence sensor (simulated stub).")
        time.sleep(0.5)
        simulated_avg_temp_c = 36.5
        return simulated_avg_temp_c >= self.presence_threshold_c

    def trigger_dispenser(self, duration_seconds: float | None = None) -> bool:
        duration = duration_seconds if duration_seconds is not None else self.dispense_seconds
        logging.info("Activating dispenser on pin %s for %.1f s.", self.dispense_pin, duration)

        if self._ready:
            GPIO.output(self.dispense_pin, GPIO.HIGH)
            time.sleep(duration)
            GPIO.output(self.dispense_pin, GPIO.LOW)
        else:
            time.sleep(duration)

        logging.info("Motor actuation complete. Returning to safe state.")
        return True

    def dispense_item(self) -> bool:
        logging.info("--- dispense_item() called ---")
        hand_present = self.read_thermal_sensor()
        if not hand_present:
            logging.warning("Thermal sensor did not confirm hand presence. Dispensing aborted.")
            return False
        return self.trigger_dispenser()

    # ── Servo helpers (dual-servo PCA9685 via Arduino) ───────────────────────
    #
    # The Arduino runs ServoPush.ino on a PCA9685 board:
    #   Command '1' → servo on channel 0 (pills: Headache / Stomach Upset)
    #   Command '2' → servo on channel 2 (gels:  Burn)
    #
    # Each sweep: 170 steps × 20 ms × 2 directions + 3 × 1 s delays ≈ 9.8 s
    # We wait 11 s to be safe.

    _SERVO_WAIT_SECONDS = 11

    def trigger_servo(
        self,
        command: str = "1",
        port: str = "/dev/ttyTHS1",   # Jetson Nano hardware UART
        baud: int = 9600,
    ) -> bool:
        """Send a single-character command ('1' or '2') to the Arduino to
        trigger one full servo sweep (170→0→170 degrees).

        Parameters
        ----------
        command : str
            '1' – pill pusher  (PCA9685 channel 0)
            '2' – gel pusher   (PCA9685 channel 2)
        port : str
            Serial port connected to the Arduino.
        baud : int
            Baud rate (must match the Arduino's Serial.begin).
        """
        logging.info(
            "Sending servo command '%s' to Arduino on %s @ %d baud.",
            command, port, baud,
        )
        try:
            import serial  # pyserial

            with serial.Serial(port, baud, timeout=2) as ser:
                ser.write(command.encode())
                logging.info(
                    "Servo command '%s' sent. Waiting ≈%d s for sweep to complete...",
                    command, self._SERVO_WAIT_SECONDS,
                )
                time.sleep(self._SERVO_WAIT_SECONDS)

            logging.info("Servo sweep for command '%s' finished.", command)
            return True

        except ImportError:
            logging.warning("pyserial is not installed – servo trigger skipped.")
            return False
        except Exception as exc:
            logging.warning("Servo trigger failed: %s", exc)
            return False

    # Convenience wrappers
    def trigger_servo_for_pill(self, **kwargs) -> bool:
        """Push pills (Headache / Stomach Upset) – servo channel 0."""
        return self.trigger_servo(command="1", **kwargs)

    def trigger_servo_for_gel(self, **kwargs) -> bool:
        """Push gel (Burn) – servo channel 2."""
        return self.trigger_servo(command="2", **kwargs)

    def cleanup(self) -> None:
        if self._ready and GPIO is not None:
            try:
                GPIO.cleanup(self.dispense_pin)
            except Exception:
                pass
