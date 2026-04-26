from __future__ import annotations

import base64
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

from PIL import Image

from config import DIAGNOSIS_ALLERGEN_MAP, AppConfig


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [VISION] - %(levelname)s - %(message)s",
)

try:
    import cv2

    CV2_AVAILABLE = True
except Exception:
    cv2 = None
    CV2_AVAILABLE = False

try:
    import requests

    REQUESTS_AVAILABLE = True
except Exception:
    requests = None
    REQUESTS_AVAILABLE = False


@dataclass(slots=True)
class VisionDecision:
    diagnosis: str
    confidence: float
    raw_label: str
    allergen: str
    accepted: bool
    frames_confirmed: int = 0
    reason: str = ""


class VisionService:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

        self.cap = None
        self._frame_counter = 0
        self._camera_ready = False
        self._last_read_error_logged = False

        self._frame_lock = threading.Lock()
        self._open_lock = threading.Lock()

        self._latest_frame = None
        self._latest_frame_ts = 0.0

        self._reader_thread: Optional[threading.Thread] = None
        self._reader_stop = threading.Event()
        self._reader_failures = 0

        self._first_start_attempt = True

        if not REQUESTS_AVAILABLE:
            logging.warning("requests not available; HTTP inference will be unavailable.")

    def _camera_fps(self) -> int:
        return int(getattr(self.config, "camera_fps", 15))

    def _flip_method(self) -> int:
        return int(getattr(self.config, "camera_flip_method", 0))

    def _camera_width(self) -> int:
        return int(getattr(self.config, "camera_width", 1280))

    def _camera_height(self) -> int:
        return int(getattr(self.config, "camera_height", 720))

    def _open_retries(self) -> int:
        return int(getattr(self.config, "camera_open_retries", 3))

    def _probe_rounds(self) -> int:
        return int(getattr(self.config, "camera_probe_rounds", 2))

    def _startup_timeout(self) -> float:
        return float(getattr(self.config, "camera_startup_timeout", 8.0))

    def _stale_frame_timeout(self) -> float:
        return float(getattr(self.config, "camera_stale_frame_timeout", 2.0))

    def _reopen_delay(self) -> float:
        return float(getattr(self.config, "camera_reopen_delay", 1.0))

    def _round_delay(self) -> float:
        return float(getattr(self.config, "camera_round_delay", 2.0))

    def _initial_delay(self) -> float:
        return float(getattr(self.config, "camera_initial_delay", 1.0))

    def _reader_failure_limit(self) -> int:
        return int(getattr(self.config, "camera_reader_failure_limit", 20))

    def _build_pipeline(self, width: int, height: int, fps: int, use_bufapi: bool) -> str:
        sensor = self.config.camera_index
        flip = self._flip_method()
        bufapi = " bufapi-version=true" if use_bufapi else ""
        return (
            f"nvarguscamerasrc sensor-id={sensor}{bufapi} ! "
            f"video/x-raw(memory:NVMM), "
            f"width=(int){width}, height=(int){height}, framerate=(fraction){fps}/1 ! "
            f"nvvidconv flip-method={flip} ! "
            f"video/x-raw, format=(string)BGRx ! "
            f"videoconvert ! "
            f"video/x-raw, format=(string)BGR ! "
            f"appsink max-buffers=1 drop=true sync=false"
        )

    def _build_bare_pipeline(self, use_bufapi: bool) -> str:
        sensor = self.config.camera_index
        flip = self._flip_method()
        bufapi = " bufapi-version=true" if use_bufapi else ""
        return (
            f"nvarguscamerasrc sensor-id={sensor}{bufapi} ! "
            f"nvvidconv flip-method={flip} ! "
            f"video/x-raw, format=(string)BGRx ! "
            f"videoconvert ! "
            f"video/x-raw, format=(string)BGR ! "
            f"appsink max-buffers=1 drop=true sync=false"
        )

    def _gstreamer_pipelines(self) -> list[str]:
        requested_w = self._camera_width()
        requested_h = self._camera_height()
        requested_fps = self._camera_fps()

        specs = [
            (requested_w, requested_h, requested_fps, True),
            (requested_w, requested_h, requested_fps, False),
            (1280, 720, 30, True),
            (1280, 720, 60, True),
            (1920, 1080, 30, True),
            (1640, 1232, 30, True),
            (1280, 720, 30, False),
            (1280, 720, 60, False),
            (1920, 1080, 30, False),
            (1640, 1232, 30, False),
        ]

        pipelines: list[str] = []
        seen: set[str] = set()

        for width, height, fps, use_bufapi in specs:
            pipeline = self._build_pipeline(width, height, fps, use_bufapi)
            if pipeline not in seen:
                seen.add(pipeline)
                pipelines.append(pipeline)

        for use_bufapi in (True, False):
            pipeline = self._build_bare_pipeline(use_bufapi)
            if pipeline not in seen:
                seen.add(pipeline)
                pipelines.append(pipeline)

        return pipelines

    def _reader_loop(self) -> None:
        while not self._reader_stop.is_set():
            cap = self.cap
            if cap is None or not cap.isOpened():
                break

            ok, frame = cap.read()

            if ok and frame is not None:
                with self._frame_lock:
                    self._latest_frame = frame.copy()
                    self._latest_frame_ts = time.monotonic()

                self._reader_failures = 0
                continue

            self._reader_failures += 1

            if self._reader_failures == 1:
                logging.warning("Camera reader got an empty frame.")
            elif self._reader_failures >= self._reader_failure_limit():
                logging.error("Camera reader stopped after repeated empty frames.")
                self._camera_ready = False
                break

            time.sleep(0.05)

    def _wait_for_first_frame(self, timeout_seconds: float) -> bool:
        deadline = time.monotonic() + timeout_seconds

        while time.monotonic() < deadline:
            with self._frame_lock:
                if self._latest_frame is not None:
                    return True
            time.sleep(0.05)

        return False

    def _open_capture(self, pipeline: str):
        cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)

        for _ in range(8):
            if cap is not None and cap.isOpened():
                return cap
            time.sleep(0.15)

        return cap

    def start_camera(self) -> bool:
        if not CV2_AVAILABLE:
            logging.warning("OpenCV not found; camera is unavailable.")
            return False

        with self._open_lock:
            if self.cap is not None and self.cap.isOpened() and self._camera_ready:
                with self._frame_lock:
                    has_frame = self._latest_frame is not None
                    frame_age = (
                        time.monotonic() - self._latest_frame_ts
                        if self._latest_frame_ts > 0
                        else 9999.0
                    )

                if has_frame and frame_age <= self._stale_frame_timeout():
                    return True

            self.stop_camera()

            if self._first_start_attempt:
                time.sleep(self._initial_delay())
                self._first_start_attempt = False
            else:
                time.sleep(self._reopen_delay())

            pipelines = self._gstreamer_pipelines()

            for round_index in range(self._probe_rounds()):
                if round_index > 0:
                    logging.warning("Retrying camera probe round %d...", round_index + 1)
                    time.sleep(self._round_delay())

                for pipeline in pipelines:
                    logging.info("Opening Jetson CSI camera with pipeline: %s", pipeline)

                    for attempt in range(self._open_retries()):
                        cap = self._open_capture(pipeline)

                        if cap is not None and cap.isOpened():
                            try:
                                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                            except Exception:
                                pass

                            self.cap = cap
                            self._frame_counter = 0
                            self._camera_ready = True
                            self._last_read_error_logged = False
                            self._reader_failures = 0

                            with self._frame_lock:
                                self._latest_frame = None
                                self._latest_frame_ts = 0.0

                            self._reader_stop.clear()
                            self._reader_thread = threading.Thread(
                                target=self._reader_loop,
                                name="vision-camera-reader",
                                daemon=True,
                            )
                            self._reader_thread.start()

                            startup_wait = max(
                                float(getattr(self.config, "warmup_seconds", 1.5)),
                                self._startup_timeout(),
                            )

                            if self._wait_for_first_frame(startup_wait):
                                logging.info("Jetson CSI camera opened successfully.")
                                return True

                            logging.warning(
                                "Camera opened but no frames arrived on attempt %d.",
                                attempt + 1,
                            )
                            self.stop_camera()
                        else:
                            if cap is not None:
                                try:
                                    cap.release()
                                except Exception:
                                    pass

                        logging.warning("Camera open attempt %d failed.", attempt + 1)
                        time.sleep(self._reopen_delay())

            logging.error("Could not open Jetson CSI camera through OpenCV GStreamer.")
            return False

    def stop_camera(self) -> None:
        self._camera_ready = False
        self._last_read_error_logged = False
        self._reader_stop.set()

        reader = self._reader_thread
        cap = self.cap

        if reader is not None and reader.is_alive():
            reader.join(timeout=0.3)

        self.cap = None

        if cap is not None:
            try:
                cap.release()
            except Exception:
                pass

        if reader is not None and reader.is_alive():
            reader.join(timeout=1.2)

        self._reader_thread = None

        with self._frame_lock:
            self._latest_frame = None
            self._latest_frame_ts = 0.0

        self._reader_failures = 0

    def cleanup(self) -> None:
        self.stop_camera()

    def _restart_camera(self) -> bool:
        logging.warning("Restarting CSI camera...")
        self.stop_camera()
        time.sleep(self._reopen_delay())
        return self.start_camera()

    def read_frame(self, allow_recover: bool = True):
        if self.cap is None or not self._camera_ready:
            if allow_recover and self.start_camera():
                return self.read_frame(allow_recover=False)
            return None

        with self._frame_lock:
            frame = None if self._latest_frame is None else self._latest_frame.copy()
            frame_ts = self._latest_frame_ts

        if frame is None:
            if not self._last_read_error_logged:
                logging.error("Frame read failed: no frame available from reader thread.")
                self._last_read_error_logged = True

            if allow_recover and self._restart_camera():
                return self.read_frame(allow_recover=False)

            return None

        age = time.monotonic() - frame_ts
        if age > self._stale_frame_timeout():
            if not self._last_read_error_logged:
                logging.error("Frame read failed: latest frame is stale (%.2fs old).", age)
                self._last_read_error_logged = True

            if allow_recover and self._restart_camera():
                return self.read_frame(allow_recover=False)

            return None

        self._last_read_error_logged = False
        return frame

    def _prepare_frame_for_inference(self, frame):
        if not CV2_AVAILABLE:
            return frame
        return cv2.resize(frame, self.config.inference_size, interpolation=cv2.INTER_LINEAR)

    def frame_to_preview(self, frame, target_size: tuple[int, int]):
        if not CV2_AVAILABLE or frame is None:
            return None

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        target_w, target_h = target_size
        if target_w <= 0 or target_h <= 0:
            return None

        stretched = cv2.resize(rgb, (target_w, target_h), interpolation=cv2.INTER_LINEAR)
        return Image.fromarray(stretched)

    def _collect_predictions(self, result: Any) -> list[dict]:
        predictions: list[dict] = []

        if isinstance(result, list):
            for item in result:
                predictions.extend(self._collect_predictions(item))
            return predictions

        if not isinstance(result, dict):
            return predictions

        pred_block = result.get("predictions")
        if isinstance(pred_block, dict):
            nested = pred_block.get("predictions")
            if isinstance(nested, list):
                predictions.extend([p for p in nested if isinstance(p, dict)])
        elif isinstance(pred_block, list):
            predictions.extend([p for p in pred_block if isinstance(p, dict)])

        outputs = result.get("outputs")
        if isinstance(outputs, list):
            for output in outputs:
                predictions.extend(self._collect_predictions(output))

        return predictions

    def _extract_count_objects(self, result: Any) -> int:
        if not isinstance(result, dict):
            return 0

        outputs = result.get("outputs")
        if not isinstance(outputs, list):
            return 0

        total = 0
        for output in outputs:
            if isinstance(output, dict):
                count = output.get("count_objects", 0)
                try:
                    total += int(count)
                except Exception:
                    pass
        return total

    def normalize_label(self, raw_label: str) -> str:
        raw = raw_label.strip()
        if not raw:
            return "Unknown"

        lowered = raw.lower()
        if lowered in self.config.label_aliases:
            return self.config.label_aliases[lowered]
        if "burn" in lowered:
            return "Burn"
        if "cut" in lowered or "lacer" in lowered or "wound" in lowered:
            return "Laceration"
        return raw.title()

    def get_allergen(self, diagnosis: str) -> str:
        return DIAGNOSIS_ALLERGEN_MAP.get(diagnosis, "Unknown Ingredient")

    def _threshold_for(self, diagnosis: str) -> float:
        return self.config.class_thresholds.get(
            diagnosis,
            self.config.min_prediction_confidence,
        )

    def _passes_threshold(self, diagnosis: str, confidence: float) -> bool:
        if diagnosis == "Unknown":
            return False
        return confidence >= self._threshold_for(diagnosis)

    def _frame_to_jpeg_bytes(self, frame) -> bytes:
        ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
        if not ok:
            raise RuntimeError("Could not JPEG-encode frame for HTTP inference.")
        return encoded.tobytes()

    def _workflow_url(self) -> str:
        base = self.config.roboflow_api_url.rstrip("/")
        workspace = self.config.roboflow_workspace.strip()
        workflow = self.config.roboflow_workflow_id.strip()
        return f"{base}/{workspace}/workflows/{workflow}"

    def _workflow_describe_url(self) -> str:
        base = self.config.roboflow_api_url.rstrip("/")
        workspace = self.config.roboflow_workspace.strip()
        workflow = self.config.roboflow_workflow_id.strip()
        return f"{base}/{workspace}/workflows/{workflow}/describe_interface"

    def _post_workflow_json(self, url: str, image_bytes: bytes) -> Optional[dict]:
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")

        payload = {
            "api_key": self.config.roboflow_api_key,
            "inputs": {
                "image": {
                    "type": "base64",
                    "value": image_b64,
                }
            },
        }

        timeout_seconds = float(getattr(self.config, "workflow_timeout_seconds", 3.0))

        try:
            response = requests.post(url, json=payload, timeout=timeout_seconds)
        except Exception as exc:
            logging.error("HTTP workflow JSON call failed for %s: %s", url, exc)
            return None

        if response.ok:
            try:
                result = response.json()
                logging.info("Workflow HTTP call succeeded on %s", url)
                return result
            except Exception as exc:
                logging.error("Workflow response was not valid JSON for %s: %s", url, exc)
                return None

        body_preview = response.text[:300] if response.text else ""
        logging.error(
            "Workflow HTTP call failed on %s with status %s. Body: %s",
            url,
            response.status_code,
            body_preview,
        )
        return None

    def _describe_interface(self) -> None:
        url = self._workflow_describe_url()
        payload = {"api_key": self.config.roboflow_api_key}
        try:
            response = requests.post(url, json=payload, timeout=5)
            if response.ok:
                logging.info("Workflow interface: %s", response.text[:500])
            else:
                logging.info("Describe interface failed with status %s", response.status_code)
        except Exception as exc:
            logging.info("Describe interface request failed: %s", exc)

    def _run_http_workflow(self, frame) -> dict:
        if not REQUESTS_AVAILABLE:
            raise RuntimeError("requests is not installed, so HTTP inference cannot run.")

        image_bytes = self._frame_to_jpeg_bytes(frame)
        url = self._workflow_url()

        result = self._post_workflow_json(url, image_bytes)
        if result is not None:
            return result

        self._describe_interface()
        raise RuntimeError(
            f"Workflow endpoint failed at {url}. "
            "Check request body keys against /docs or the workflow deploy snippet."
        )

    def _run_local_workflow(self, frame) -> VisionDecision:
        try:
            result = self._run_http_workflow(frame)
        except Exception as exc:
            logging.error("HTTP workflow inference failed: %s", exc)
            return VisionDecision(
                diagnosis="Unknown",
                confidence=0.0,
                raw_label="Unknown",
                allergen=self.get_allergen("Unknown"),
                accepted=False,
                reason="workflow_http_failed",
            )

        predictions = self._collect_predictions(result)
        if predictions:
            best = max(predictions, key=lambda p: float(p.get("confidence", 0.0)))
            raw_label = str(best.get("class", "Unknown"))
            confidence = float(best.get("confidence", 0.0))
            diagnosis = self.normalize_label(raw_label)
            accepted = self._passes_threshold(diagnosis, confidence)

            logging.info(
                "Best prediction: raw_label=%s normalized=%s confidence=%.4f accepted=%s",
                raw_label,
                diagnosis,
                confidence,
                accepted,
            )

            return VisionDecision(
                diagnosis=diagnosis,
                confidence=confidence,
                raw_label=raw_label,
                allergen=self.get_allergen(diagnosis),
                accepted=accepted,
                reason="accepted" if accepted else "below_threshold",
            )

        count_objects = self._extract_count_objects(result)
        logging.info("Workflow returned no explicit predictions. count_objects=%s", count_objects)

        return VisionDecision(
            diagnosis="Unknown",
            confidence=0.0,
            raw_label="Unknown",
            allergen=self.get_allergen("Unknown"),
            accepted=False,
            reason="no_predictions" if count_objects == 0 else "count_without_labels",
        )

    def _simulation_stub(self) -> VisionDecision:
        diagnosis = self.normalize_label(self.config.simulated_diagnosis)
        confidence = float(self.config.simulated_confidence)
        return VisionDecision(
            diagnosis=diagnosis,
            confidence=confidence,
            raw_label=self.config.simulated_diagnosis,
            allergen=self.get_allergen(diagnosis),
            accepted=True,
            frames_confirmed=self.config.stabilization_frames,
            reason="simulation",
        )

    def get_prediction(self) -> tuple[str, float]:
        if not self.start_camera():
            decision = (
                self._simulation_stub()
                if self.config.allow_simulation_fallback
                else VisionDecision(
                    diagnosis="Unknown",
                    confidence=0.0,
                    raw_label="Unknown",
                    allergen=self.get_allergen("Unknown"),
                    accepted=False,
                    reason="camera_unavailable",
                )
            )
            return decision.diagnosis, decision.confidence

        frame = self.read_frame()
        if frame is None:
            decision = (
                self._simulation_stub()
                if self.config.allow_simulation_fallback
                else VisionDecision(
                    diagnosis="Unknown",
                    confidence=0.0,
                    raw_label="Unknown",
                    allergen=self.get_allergen("Unknown"),
                    accepted=False,
                    reason="frame_unavailable",
                )
            )
            return decision.diagnosis, decision.confidence

        decision = self._run_local_workflow(self._prepare_frame_for_inference(frame))
        return decision.diagnosis, decision.confidence

    def scan_until_stable(
        self,
        preview_callback: Optional[Callable[[Any, str, str], None]] = None,
        should_cancel: Optional[Callable[[], bool]] = None,
    ) -> VisionDecision:
        logging.info("=== Vision scan start ===")

        if not CV2_AVAILABLE:
            decision = (
                self._simulation_stub()
                if self.config.allow_simulation_fallback
                else VisionDecision(
                    diagnosis="Unknown",
                    confidence=0.0,
                    raw_label="Unknown",
                    allergen=self.get_allergen("Unknown"),
                    accepted=False,
                    reason="opencv_unavailable",
                )
            )
            logging.info("=== Vision scan end - diagnosis: '%s' ===", decision.diagnosis)
            return decision

        if not self.start_camera():
            decision = (
                self._simulation_stub()
                if self.config.allow_simulation_fallback
                else VisionDecision(
                    diagnosis="Unknown",
                    confidence=0.0,
                    raw_label="Unknown",
                    allergen=self.get_allergen("Unknown"),
                    accepted=False,
                    reason="camera_open_failed",
                )
            )
            logging.info("=== Vision scan end - diagnosis: '%s' ===", decision.diagnosis)
            return decision

        stable_label: Optional[str] = None
        stable_count = 0
        best_decision: Optional[VisionDecision] = None
        started = time.monotonic()
        missing_frames = 0

        process_every_n = max(1, int(getattr(self.config, "process_every_n_frames", 8)))
        preview_sleep = max(
            0.01,
            float(getattr(self.config, "preview_update_ms", 30)) / 1000.0,
        )

        while time.monotonic() - started < self.config.scan_timeout_seconds:
            if should_cancel and should_cancel():
                return VisionDecision(
                    diagnosis="Unknown",
                    confidence=0.0,
                    raw_label="Unknown",
                    allergen=self.get_allergen("Unknown"),
                    accepted=False,
                    reason="cancelled",
                )

            frame = self.read_frame()

            if frame is None:
                missing_frames += 1
                if missing_frames >= 10:
                    self._restart_camera()
                    missing_frames = 0
                time.sleep(0.05)
                continue

            missing_frames = 0
            self._frame_counter += 1

            status_text = "Align the injury inside the frame..."
            status_color = "#F8FFFF"

            if preview_callback:
                preview_callback(frame, status_text, status_color)

            if self._frame_counter % process_every_n != 0:
                time.sleep(preview_sleep)
                continue

            inference_frame = self._prepare_frame_for_inference(frame)
            decision = self._run_local_workflow(inference_frame)

            if decision.accepted:
                if best_decision is None or decision.confidence > best_decision.confidence:
                    best_decision = decision

                if stable_label == decision.diagnosis:
                    stable_count += 1
                else:
                    stable_label = decision.diagnosis
                    stable_count = 1

                status_text = f"Injury detected: {decision.diagnosis}. Verifying..."
                status_color = "#7AE2EB"

                if preview_callback:
                    preview_callback(frame, status_text, status_color)

                if stable_count >= self.config.stabilization_frames:
                    decision.frames_confirmed = stable_count
                    decision.reason = "stable_detection"
                    logging.info("=== Vision scan end - diagnosis: '%s' ===", decision.diagnosis)
                    return decision
            else:
                stable_label = None
                stable_count = 0
                status_text = "Scanning..."
                status_color = "#F4C27A"

                if preview_callback:
                    preview_callback(frame, status_text, status_color)

            time.sleep(preview_sleep)

        if best_decision is not None:
            best_decision.reason = "timeout_best_match"
            best_decision.accepted = True
            logging.info("=== Vision scan end - diagnosis: '%s' ===", best_decision.diagnosis)
            return best_decision

        decision = VisionDecision(
            diagnosis="Unknown",
            confidence=0.0,
            raw_label="Unknown",
            allergen=self.get_allergen("Unknown"),
            accepted=False,
            reason="timeout_no_detection",
        )
        logging.info("=== Vision scan end - diagnosis: '%s' ===", decision.diagnosis)
        return decision
