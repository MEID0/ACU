from __future__ import annotations

import atexit
import signal
import sys

import customtkinter as ctk

from audit import AuditLogger
from config import AppConfig
from hardware_service import ACUHardware
from ui import MedicalKiosk
from vision_service import VisionService


def main() -> None:
    ctk.set_appearance_mode("light")

    config = AppConfig()
    audit = AuditLogger(config.session_log_file, config.log_encryption_key_file)
    hardware = ACUHardware(
        dispense_pin=config.dispense_pin,
        dispense_seconds=config.dispense_seconds,
        presence_threshold_c=config.presence_threshold_c,
    )
    vision = VisionService(config)
    app = MedicalKiosk(config=config, audit=audit, hardware=hardware, vision=vision)

    cleaned_up = False

    def cleanup() -> None:
        nonlocal cleaned_up
        if cleaned_up:
            return
        cleaned_up = True

        try:
            vision.cleanup()
        except Exception:
            pass

        try:
            hardware.cleanup()
        except Exception:
            pass

    def handle_exit_signal(signum, frame) -> None:
        cleanup()

        try:
            app._scan_cancelled = True
        except Exception:
            pass

        try:
            app.after(0, app.destroy)
        except Exception:
            try:
                app.destroy()
            except Exception:
                pass

        raise SystemExit(0)

    atexit.register(cleanup)

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, handle_exit_signal)

    if hasattr(signal, "SIGHUP"):
        signal.signal(signal.SIGHUP, handle_exit_signal)

    try:
        app.mainloop()
    finally:
        cleanup()


if __name__ == "__main__":
    main()
