from __future__ import annotations

import inspect
from pathlib import Path

from config import AppConfig
from vision_service import VisionService


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}


def snapshot_images(root: Path) -> set[str]:
    found: set[str] = set()
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
            found.add(str(path.relative_to(root)))
    return found


def main() -> None:
    root = Path(__file__).resolve().parent
    config = AppConfig()

    print("=== ACU privacy proof ===")
    print(f"Project folder: {root}")
    print(f"Debug image saving enabled: {config.save_debug_images}")
    print(f"Debug folder: {config.debug_dir}")
    print()

    source = inspect.getsource(VisionService)

    checks = {
        "uses_direct_memory_upload": 'images={"image": frame}' in source,
        "does_not_call_cv2_imwrite": "cv2.imwrite(" not in source,
        "does_not_call_pil_save": ".save(" not in source,
    }

    print("Static code checks:")
    for name, ok in checks.items():
        print(f"  {name}: {'PASS' if ok else 'FAIL'}")

    print()
    before = snapshot_images(root)
    print(f"Image files before scan: {len(before)}")
    print("Run one scan in the main app now.")
    input("When the scan is finished, press Enter here... ")

    after = snapshot_images(root)
    print(f"Image files after scan: {len(after)}")

    new_files = sorted(after - before)
    removed_files = sorted(before - after)

    if new_files:
        print("\nNew image files detected:")
        for item in new_files:
            print(f"  + {item}")
    else:
        print("\nNo new image files were created during the scan.")

    if removed_files:
        print("\nImage files removed during the scan:")
        for item in removed_files:
            print(f"  - {item}")

    passed = all(checks.values()) and not new_files and not config.save_debug_images
    print()
    print("RESULT:", "PASS" if passed else "FAIL")


if __name__ == "__main__":
    main()