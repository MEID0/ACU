# Autonomous Care Unit (ACU)

ACU is a Python kiosk prototype for an autonomous first-aid station. It provides a touchscreen-style UI, live injury scanning, symptom selection, allergy/safety confirmation, hardware dispensing, emergency WhatsApp alerting, and encrypted audit logging.

> Important: This is a prototype support system, not a replacement for a clinician, emergency responder, or regulated medical device. Keep a human operator available during testing and deployment.

## Features

- CustomTkinter kiosk UI with home, service selection, injury scan, symptom selection, safety check, dispensing, emergency, and discharge screens.
- Live Jetson CSI camera workflow for scanning visible injuries.
- Roboflow local workflow integration over HTTP.
- Stable detection gate before moving from scanning to the safety screen.
- Treatment/allergen mapping for laceration, burn, headache, stomach upset, and unknown cases.
- Hardware abstraction layer for Jetson GPIO dispensing and Arduino UART servo triggering.
- Emergency WhatsApp message support through Twilio.
- Fernet-encrypted session audit logs.
- Utility scripts for camera confidence testing, Twilio testing, privacy proof, and encrypted log verification.

## Project structure

```text
acu_project/
  main.py                         # Main application entry point
  ui.py                           # Kiosk UI and screen flow
  config.py                       # AppConfig and environment-based settings
  vision_service.py               # Camera, preview, inference, and stable scan logic
  hardware_service.py             # Jetson GPIO / Arduino dispensing hardware layer
  emergency_service.py            # Twilio WhatsApp emergency alert helper
  audit.py                        # Encrypted audit logger
  con.py                          # Camera + confidence test utility
  twilio_test.py                  # Twilio credential/message test utility
  privacy_proof.py                # Checks that scans do not create image files
  verify_logs_encryption.py       # Checks encrypted audit log behavior
  requirements.txt                # Base Python dependencies
  env.example                     # Environment variable template; do not commit real secrets
  rf.env                          # Optional Roboflow local server environment file
  assets/
    fonts/
      Nippo-Bold.otf
      Nippo-Regular.otf
    images/
      logo.png
      scan_hand.png               # optional scan placeholder
      scan_preview.png            # optional scan placeholder
      scan_reference.png          # optional scan placeholder
```

Generated/runtime files such as `session_logs.enc`, `session_logs.key`, `.env`, `rf.env`, and `debug_frames/` should be kept out of version control.

## Requirements

- Python 3.10 or newer is recommended.
- Linux or Jetson environment for hardware/camera deployment.
- A Jetson CSI camera for the live scan path.
- Roboflow local inference server running and reachable from the kiosk machine.
- Twilio WhatsApp credentials for the emergency alert feature.
- Optional: Arduino Mega connected to Jetson UART for pill/tablet servo dispensing.

The current `requirements.txt` contains the base UI, image, OpenCV, inference, and encryption packages. The app also imports Twilio directly, and the servo helper uses pyserial when pill dispensing is enabled. Install these if they are not already present.

## Installation

```bash
cd acu_project
python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

# Needed by emergency_service.py and optional Arduino servo control
python -m pip install twilio pyserial requests
```

On Jetson, install platform packages needed by OpenCV/GStreamer and the CSI camera stack through the Jetson/Linux package manager. `Jetson.GPIO` is used automatically when it is available; otherwise the hardware layer runs in simulation mode.

## Configuration

The app reads configuration from environment variables using `os.getenv`. It does not automatically load a `.env` file, so export variables in your shell before launching the app.

Create a local environment file from the example, then replace all secrets with your own values:

```bash
cp env.example .env
nano .env
```

Load the file before running:

```bash
set -a
source .env
set +a
```

### Core Roboflow settings

```bash
ROBOFLOW_API_URL=http://127.0.0.1:9001
ROBOFLOW_API_KEY=replace_with_your_key
ROBOFLOW_WORKSPACE=replace_with_workspace
ROBOFLOW_WORKFLOW_ID=replace_with_workflow_id
ROBOFLOW_USE_CACHE=false
```

### Camera and scan settings

```bash
ACU_CAMERA_INDEX=0
ACU_CAMERA_WIDTH=1280
ACU_CAMERA_HEIGHT=720
ACU_CAMERA_FPS=15
ACU_CAMERA_FLIP_METHOD=0
ACU_PROCESS_EVERY_N_FRAMES=8
ACU_STABILIZATION_FRAMES=3
ACU_SCAN_TIMEOUT_SECONDS=12
ACU_PREVIEW_UPDATE_MS=30
ACU_WORKFLOW_TIMEOUT_SECONDS=3
```

### UI settings

```bash
ACU_FULLSCREEN=false
ACU_WINDOW_WIDTH=600
ACU_WINDOW_HEIGHT=1024
```

### Confidence thresholds and simulation

```bash
ACU_MIN_CONFIDENCE=0.75
ACU_LACERATION_THRESHOLD=0.75
ACU_BURN_THRESHOLD=0.75

# Useful for non-hardware demos only
ACU_ALLOW_SIMULATION=false
ACU_SIMULATED_DIAGNOSIS=Laceration
ACU_SIMULATED_CONFIDENCE=0.88
```

### Treatment and allergen text

```bash
ACU_TREATMENT_LACERATION="New-Skin Liquid Bandage"
ACU_TREATMENT_BURN="General Medi Burn Gel"
ACU_TREATMENT_HEADACHE="Panadol"
ACU_TREATMENT_STOMACH="Panadol"
ACU_TREATMENT_UNKNOWN="Manual Check Required"

ACU_ALLERGEN_LACERATION="Benzethonium Chloride"
ACU_ALLERGEN_BURN="Tea Tree Oil / Glycerin"
ACU_ALLERGEN_HEADACHE="Paracetamol"
ACU_ALLERGEN_STOMACH="Paracetamol"
ACU_ALLERGEN_UNKNOWN="Unknown Ingredient"
```

### Logging and privacy settings

```bash
ACU_LOG_FILE=session_logs.enc
ACU_LOG_KEY_FILE=session_logs.key
ACU_SAVE_DEBUG_IMAGES=false
```

Keep `session_logs.key` private. Anyone with both the encrypted log file and the key file can decrypt the audit entries.

### Hardware settings

```bash
ACU_DISPENSE_PIN=18
ACU_DISPENSE_SECONDS=2.0
ACU_PRESENCE_THRESHOLD_C=35.0
```

For pill/tablet cases, `hardware_service.py` sends `S` and then `R` over `/dev/ttyTHS1` at 9600 baud by default. Make sure the Arduino firmware expects those commands and that Jetson TX/RX wiring is correct.

### Twilio emergency WhatsApp settings

```bash
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=replace_with_twilio_auth_token
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
TWILIO_WHATSAPP_TO=whatsapp:+966xxxxxxxxx
TWILIO_CONTENT_SID=HXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_CONTENT_VARIABLES={}
```

Do not put real Twilio or Roboflow credentials in public commits. If a real credential was ever committed or shared, rotate it before deployment.

## Running the app

Start the Roboflow local inference server first. The exact command depends on how the workflow was exported or deployed, but the kiosk expects an endpoint shaped like this:

```text
http://127.0.0.1:9001/<workspace>/workflows/<workflow_id>
```

Then launch the kiosk:

```bash
source .venv/bin/activate
set -a
source .env
set +a
python main.py
```

Keyboard shortcuts:

- `Esc`: exit fullscreen or close the app.
- `F11`: toggle fullscreen.

## User flow

1. Start from the ACU home screen.
2. Choose one of the available services:
   - `SCAN INJURY` for camera-based laceration/burn detection.
   - `SELECT SYMPTOMS` for headache or stomach upset.
   - `EMERGENCY` to send the configured WhatsApp alert.
3. Confirm the safety/allergy warning.
4. Proceed to dispensing.
5. The app logs the safety check and dispensing completion, then returns to the home screen after discharge.

## Utility scripts

### Camera confidence test

```bash
python con.py
```

This opens the camera preview, runs inference every few frames, and overlays the latest diagnosis, confidence, and status. Press `q` to quit.

### Twilio test

```bash
python twilio_test.py
```

This prints whether the required Twilio variables are set and attempts to send the configured content template.

### Privacy proof

```bash
python privacy_proof.py
```

This checks that the vision service uploads frames from memory and does not create new image files during a scan when debug image saving is disabled.

### Encrypted log verification

```bash
python verify_logs_encryption.py
```

Run the app first so it creates log entries, then use this script to verify that the raw log file does not contain obvious plaintext event/diagnosis words and can be decrypted with the key file.

## Deployment notes

- Test in simulation mode before connecting real dispensing hardware.
- Keep the dispenser motor in a safe default-off state.
- Verify the thermal/presence sensor logic before dispensing physical items.
- Keep emergency contacts and Twilio templates current.
- Validate each treatment/allergen mapping with an appropriate supervisor before demo or deployment.
- Protect API keys, Twilio credentials, encrypted logs, and log key files.
- Add `.env`, `rf.env`, `session_logs.enc`, `session_logs.key`, and `debug_frames/` to `.gitignore`.

## Troubleshooting

### Camera does not start

- Confirm the CSI camera is detected by the Jetson.
- Confirm GStreamer support is available in OpenCV.
- Try lowering `ACU_CAMERA_WIDTH`, `ACU_CAMERA_HEIGHT`, or `ACU_CAMERA_FPS`.
- Check whether another process is using the camera.
- For demos without camera hardware, set `ACU_ALLOW_SIMULATION=true`.

### Inference returns `Unknown`

- Confirm the Roboflow local server is running.
- Confirm `ROBOFLOW_API_URL`, `ROBOFLOW_WORKSPACE`, and `ROBOFLOW_WORKFLOW_ID` match the deployed workflow.
- Confirm `ROBOFLOW_API_KEY` is valid.
- Lower thresholds only for testing; do not lower them for deployment without validation.

### Emergency message fails

- Confirm `twilio` is installed.
- Confirm all Twilio environment variables are exported in the same terminal used to run the app.
- Confirm the WhatsApp recipient is allowed by your Twilio sandbox/template configuration.
- If using template variables, make sure `TWILIO_CONTENT_VARIABLES` is valid JSON.

### Dispensing does not trigger

- Confirm Jetson GPIO is available or that simulation mode is expected.
- Confirm `ACU_DISPENSE_PIN` matches the actual wiring.
- Confirm the thermal/presence sensor threshold is realistic.
- For pill/tablet dispensing, confirm `pyserial` is installed and `/dev/ttyTHS1` is accessible.
