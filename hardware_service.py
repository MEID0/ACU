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

    def trigger_servo_for_pill(
        self,
        port: str = "/dev/ttyTHS1",   # Jetson Nano hardware UART (TX→D0, RX→D1)
        baud: int = 9600,
    ) -> bool:
        """Trigger the Arduino servo sweep exactly once.

        The Arduino listens on Serial1 (hardware UART, pins D0/D1) at 9600 baud.
        Sending 'S' starts the one-shot sweep (0→170→0 degrees).
        After the sweep is done, 'R' is sent so the Arduino is ready for the
        next patient without needing a physical reset.

        Sweep timing:
          - 170 steps forward  × 20 ms = 3.4 s
          - 1 s delay in the middle
          - 170 steps backward × 20 ms = 3.4 s
          - Total ≈ 7.8 s  → we wait 9 s to be safe
        """
        logging.info("Sending servo trigger 'S' to Arduino on %s @ %d baud.", port, baud)
        try:
            import serial  # pyserial

            with serial.Serial(port, baud, timeout=2) as ser:
                # The Mega's Serial1 does not reset on a serial connection,
                # so we can send immediately.
                ser.write(b"S")
                logging.info("Servo trigger 'S' sent. Waiting for sweep to complete...")

                # Wait for the full 0→170→0 sweep to finish before returning.
                time.sleep(9)

                # Reset the Arduino's hasRun flag so it is ready for the next patient.
                ser.write(b"R")
                logging.info("Reset command 'R' sent. Arduino ready for next use.")

            return True

        except ImportError:
            logging.warning("pyserial is not installed – servo trigger skipped.")
            return False
        except Exception as exc:
            logging.warning("Servo trigger failed: %s", exc)
            return False

    def cleanup(self) -> None:
        if self._ready and GPIO is not None:
            try:
                GPIO.cleanup(self.dispense_pin)
            except Exception:
                pass
