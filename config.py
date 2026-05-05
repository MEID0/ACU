from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Tuple


BASE_DIR = Path(__file__).resolve().parent


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw.strip())
    except ValueError:
        return default


def _get_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw.strip())
    except ValueError:
        return default


def _get_path(name: str, default_filename: str) -> str:
    raw = os.getenv(name)
    path = Path(raw.strip()) if raw and raw.strip() else Path(default_filename)
    if not path.is_absolute():
        path = BASE_DIR / path
    return str(path)


DIAGNOSIS_TREATMENT_MAP: Dict[str, str] = {
    "Laceration": os.getenv("ACU_TREATMENT_LACERATION", "New-Skin Liquid Bandage"),
    "Burn": os.getenv("ACU_TREATMENT_BURN", "General Medi Burn Gel"),
    "Headache": os.getenv("ACU_TREATMENT_HEADACHE", "Panadol"),
    "Stomach Upset": os.getenv("ACU_TREATMENT_STOMACH", "Panadol"),
    "Unknown": os.getenv("ACU_TREATMENT_UNKNOWN", "Manual Check Required"),
}

DIAGNOSIS_ALLERGEN_MAP: Dict[str, str] = {
    "Laceration": os.getenv("ACU_ALLERGEN_LACERATION", "Benzethonium Chloride"),
    "Burn": os.getenv("ACU_ALLERGEN_BURN", "Tea Tree Oil / Glycerin"),
    "Headache": os.getenv("ACU_ALLERGEN_HEADACHE", "Paracetamol"),
    "Stomach Upset": os.getenv("ACU_ALLERGEN_STOMACH", "Paracetamol"),
    "Unknown": os.getenv("ACU_ALLERGEN_UNKNOWN", "Unknown Ingredient"),
}


@dataclass(slots=True)
class AppConfig:
    base_dir: Path = field(default_factory=lambda: BASE_DIR)

    fullscreen: bool = field(default_factory=lambda: _get_bool("ACU_FULLSCREEN", False))

    design_width: int = 600
    design_height: int = 1024
    window_width: int = field(default_factory=lambda: _get_int("ACU_WINDOW_WIDTH", 600))
    window_height: int = field(default_factory=lambda: _get_int("ACU_WINDOW_HEIGHT", 1024))

    font_dir: str = "assets/fonts"
    logo_path: str = "assets/images/logo.png"
    scan_preview_candidates: Tuple[str, ...] = (
        "assets/images/scan_hand.png",
        "assets/images/scan_preview.png",
        "assets/images/scan_reference.png",
    )

    session_log_file: str = field(default_factory=lambda: _get_path("ACU_LOG_FILE", "session_logs.enc"))
    log_encryption_key_file: str = field(default_factory=lambda: _get_path("ACU_LOG_KEY_FILE", "session_logs.key"))
    session_log_csv: str = field(init=False)

    use_jetson_csi: bool = field(default_factory=lambda: _get_bool("ACU_USE_JETSON_CSI", False))
    camera_index: int = field(default_factory=lambda: _get_int("ACU_CAMERA_INDEX", 0))
    camera_width: int = field(default_factory=lambda: _get_int("ACU_CAMERA_WIDTH", 1280))
    camera_height: int = field(default_factory=lambda: _get_int("ACU_CAMERA_HEIGHT", 720))
    camera_fps: int = field(default_factory=lambda: _get_int("ACU_CAMERA_FPS", 30))
    camera_flip_method: int = field(default_factory=lambda: _get_int("ACU_CAMERA_FLIP_METHOD", 0))
    warmup_seconds: float = field(default_factory=lambda: _get_float("ACU_CAMERA_WARMUP_SECONDS", 1.5))
    flush_frames: int = field(default_factory=lambda: _get_int("ACU_CAMERA_FLUSH_FRAMES", 0))
    inference_size: Tuple[int, int] = (640, 480)
    preview_update_ms: int = field(default_factory=lambda: _get_int("ACU_PREVIEW_UPDATE_MS", 30))
    process_every_n_frames: int = field(default_factory=lambda: max(1, _get_int("ACU_PROCESS_EVERY_N_FRAMES", 8)))
    stabilization_frames: int = field(default_factory=lambda: max(1, _get_int("ACU_STABILIZATION_FRAMES", 3)))
    scan_timeout_seconds: float = field(default_factory=lambda: _get_float("ACU_SCAN_TIMEOUT_SECONDS", 12.0))

    camera_open_retries: int = field(default_factory=lambda: _get_int("ACU_CAMERA_OPEN_RETRIES", 3))
    camera_probe_rounds: int = field(default_factory=lambda: _get_int("ACU_CAMERA_PROBE_ROUNDS", 2))
    camera_startup_timeout: float = field(default_factory=lambda: _get_float("ACU_CAMERA_STARTUP_TIMEOUT", 8.0))
    camera_stale_frame_timeout: float = field(default_factory=lambda: _get_float("ACU_CAMERA_STALE_FRAME_TIMEOUT", 2.0))
    camera_reopen_delay: float = field(default_factory=lambda: _get_float("ACU_CAMERA_REOPEN_DELAY", 1.0))
    camera_round_delay: float = field(default_factory=lambda: _get_float("ACU_CAMERA_ROUND_DELAY", 2.0))
    camera_initial_delay: float = field(default_factory=lambda: _get_float("ACU_CAMERA_INITIAL_DELAY", 1.0))
    camera_reader_failure_limit: int = field(default_factory=lambda: _get_int("ACU_CAMERA_READER_FAILURE_LIMIT", 20))
    workflow_timeout_seconds: float = field(default_factory=lambda: _get_float("ACU_WORKFLOW_TIMEOUT_SECONDS", 3.0))

    roboflow_api_url: str = field(default_factory=lambda: os.getenv("ROBOFLOW_API_URL", "http://127.0.0.1:9001"))
    roboflow_api_key: str = field(default_factory=lambda: os.getenv("ROBOFLOW_API_KEY", "F2KG4LO7SndaWk2m3PnN"))
    roboflow_workspace: str = field(default_factory=lambda: os.getenv("ROBOFLOW_WORKSPACE", "meids-workspace"))
    roboflow_workflow_id: str = field(default_factory=lambda: os.getenv("ROBOFLOW_WORKFLOW_ID", "detect-count-and-visualize"))
    roboflow_use_cache: bool = field(default_factory=lambda: _get_bool("ROBOFLOW_USE_CACHE", False))

    min_prediction_confidence: float = field(default_factory=lambda: _get_float("ACU_MIN_CONFIDENCE", 0.75))
    class_thresholds: Dict[str, float] = field(default_factory=lambda: {
        "Laceration": _get_float("ACU_LACERATION_THRESHOLD", 0.75),
        "Burn": _get_float("ACU_BURN_THRESHOLD", 0.75),
    })

    label_aliases: Dict[str, str] = field(default_factory=lambda: {
        "cut": "Laceration",
        "cuts": "Laceration",
        "paper cut": "Laceration",
        "laceration": "Laceration",
        "wound": "Laceration",
        "open wound": "Laceration",

        "burn": "Burn",
        "burns": "Burn",
        "first degree burn": "Burn",
        "second degree burn": "Burn",
        "third degree burn": "Burn",

        "headache": "Headache",
        "head pain": "Headache",

        "stomach upset": "Stomach Upset",
        "upset stomach": "Stomach Upset",
        "stomach ache": "Stomach Upset",
        "stomach pain": "Stomach Upset",
    })

    diagnosis_treatment_map: Dict[str, str] = field(default_factory=lambda: dict(DIAGNOSIS_TREATMENT_MAP))
    diagnosis_allergen_map: Dict[str, str] = field(default_factory=lambda: dict(DIAGNOSIS_ALLERGEN_MAP))

    allow_simulation_fallback: bool = field(default_factory=lambda: _get_bool("ACU_ALLOW_SIMULATION", False))
    simulated_diagnosis: str = field(default_factory=lambda: os.getenv("ACU_SIMULATED_DIAGNOSIS", "Laceration"))
    simulated_confidence: float = field(default_factory=lambda: _get_float("ACU_SIMULATED_CONFIDENCE", 0.88))

    save_debug_images: bool = field(default_factory=lambda: _get_bool("ACU_SAVE_DEBUG_IMAGES", False))
    debug_dir: str = field(default_factory=lambda: str(BASE_DIR / "debug_frames"))

    dispense_pin: int = field(default_factory=lambda: _get_int("ACU_DISPENSE_PIN", 18))
    dispense_seconds: float = field(default_factory=lambda: _get_float("ACU_DISPENSE_SECONDS", 2.0))
    presence_threshold_c: float = field(default_factory=lambda: _get_float("ACU_PRESENCE_THRESHOLD_C", 35.0))

    def __post_init__(self) -> None:
        self.session_log_csv = self.session_log_file


CONFIG = AppConfig()

CAMERA_INDEX = CONFIG.camera_index
FRAME_WIDTH = CONFIG.camera_width
FRAME_HEIGHT = CONFIG.camera_height
PROCESS_EVERY_N_FRAMES = CONFIG.process_every_n_frames

ROBOFLOW_API_URL = CONFIG.roboflow_api_url
ROBOFLOW_API_KEY = CONFIG.roboflow_api_key
WORKSPACE_NAME = CONFIG.roboflow_workspace
WORKFLOW_ID = CONFIG.roboflow_workflow_id

CUT_THRESHOLD = CONFIG.class_thresholds["Laceration"]
BURN_THRESHOLD = CONFIG.class_thresholds["Burn"]

SAVE_DEBUG_IMAGES = CONFIG.save_debug_images
DEBUG_DIR = CONFIG.debug_dir

DIAGNOSIS_TREATMENTS = CONFIG.diagnosis_treatment_map
DIAGNOSIS_ALLERGENS = CONFIG.diagnosis_allergen_map
