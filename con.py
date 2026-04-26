from __future__ import annotations

import time
import cv2

from config import AppConfig
from vision_service import VisionService


def main():
    config = AppConfig()
    vision = VisionService(config)

    if not vision.start_camera():
        print("Could not start camera.")
        return

    print("Camera started. Press Q to quit.")

    last_label = "Unknown"
    last_conf = 0.0
    last_reason = ""
    frame_count = 0

    # Run inference less often so preview stays smoother
    infer_every_n_frames = 6

    try:
        while True:
            frame = vision.read_frame()
            if frame is None:
                # Small wait so loop does not spin too hard
                time.sleep(0.03)
                continue

            frame_count += 1

            if frame_count % infer_every_n_frames == 0:
                try:
                    small_frame = vision._prepare_frame_for_inference(frame)
                    decision = vision._run_local_workflow(small_frame)

                    last_label = decision.diagnosis
                    last_conf = float(decision.confidence)
                    last_reason = decision.reason
                except Exception as exc:
                    last_label = "Error"
                    last_conf = 0.0
                    last_reason = str(exc)

            # Choose overlay color
            if last_label == "Unknown":
                color = (0, 165, 255)   # orange
            elif last_conf >= 0.75:
                color = (0, 255, 0)     # green
            else:
                color = (0, 0, 255)     # red

            # Draw overlay background
            cv2.rectangle(frame, (10, 10), (620, 120), (0, 0, 0), -1)

            # Show diagnosis
            cv2.putText(
                frame,
                f"Diagnosis: {last_label}",
                (20, 45),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.9,
                color,
                2,
                cv2.LINE_AA,
            )

            # Show confidence
            cv2.putText(
                frame,
                f"Confidence: {last_conf:.4f}",
                (20, 80),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.9,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )

            # Show reason/status
            cv2.putText(
                frame,
                f"Status: {last_reason}",
                (20, 110),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (200, 200, 200),
                2,
                cv2.LINE_AA,
            )

            cv2.imshow("ACU Camera Confidence Test", frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break

    finally:
        vision.cleanup()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
