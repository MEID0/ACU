from __future__ import annotations

from pathlib import Path

from audit import AuditLogger
from config import AppConfig


PLAINTEXT_MARKERS = [
    b"Laceration",
    b"Burn",
    b"Headache",
    b"Stomach Upset",
    b"safety_check",
    b"dispense_complete",
    b"emergency_stop",
]


def main() -> None:
    config = AppConfig()
    log_path = Path(config.session_log_file)
    key_path = Path(config.log_encryption_key_file)

    print("=== ACU encrypted log proof ===")
    print(f"Encrypted log file: {log_path}")
    print(f"Encryption key file: {key_path}")
    print()

    if not log_path.exists():
        print("No encrypted log file found yet.")
        print("Run the app once, trigger a few actions, then run this script again.")
        return

    raw = log_path.read_bytes()
    print(f"Encrypted log size: {len(raw)} bytes")

    first_line = raw.splitlines()[0] if raw.splitlines() else b""
    print("Raw first line sample:")
    print(first_line[:120])
    print()

    found_plaintext = [marker.decode("utf-8") for marker in PLAINTEXT_MARKERS if marker in raw]
    if found_plaintext:
        print("FAIL: plaintext markers found inside encrypted log file:")
        for item in found_plaintext:
            print(f"  - {item}")
    else:
        print("PASS: no obvious plaintext diagnosis/event words found in the encrypted file.")

    print()
    audit = AuditLogger(config.session_log_file, config.log_encryption_key_file)
    entries = audit.read_entries()

    if not entries:
        print("FAIL: no entries could be decrypted.")
        return

    print(f"PASS: decrypted {len(entries)} log entries with the key.")
    print("Last 3 decrypted entries:")
    for entry in entries[-3:]:
        print(entry)

    print()
    if key_path.exists():
        print("PASS: encrypted log requires a separate key file.")
    else:
        print("FAIL: key file not found.")


if __name__ == "__main__":
    main()