# Android App — Track-It App (sensor-toolkit v3.0.1)

Android client application for synchronized multi-device sensor data logging and synchronized video capture, designed to upload directly to `server-processing`.

---

## Architecture & Modules

| Module | Role |
|---|---|
| `Clients/HIAACApp` | Main application package (`br.org.eldorado.hiaacapp`), UI activities, and navigation. |
| `HiaacLib` | Core library: data collection services, CameraX video recording, clock synchronization, settings, and network upload. |
| `SensorSDK`, `SensorAgent` | Sensor management layer and abstraction service. |

**Supported Sensors:** Accelerometer, Linear Acceleration, Gyroscope, Magnetometer, Gravity, Ambient Light, Proximity, Ambient Temperature, and GPS.

---

## Installation

The app can be built locally from source (**Option B**). A Google Play Store release is coming soon (**Option A**) but is not published yet.

### Option A: Google Play Store (coming soon)

> **Not available yet.** A signed release of **Track-It App** is being prepared for the Google Play Store. Once published, it will install directly on the experimental smartphones, with no USB debugging or developer options required. Until then, use the local build in **Option B**.

### Option B: Local Build & ADB (USB Debugging)
Requirements: JDK 17, Android SDK (`compileSdk 34`, `minSdk 29`).

1. **Enable Developer Options & USB Debugging:**
   - Go to phone **Settings → About Phone**.
   - Tap **Build Number** 7 times until you see the message *"You are now a developer!"*.
   - Go to **Settings → System → Developer Options** and enable **USB Debugging**.
   - Connect the phone via USB cable and accept the RSA host fingerprint prompt (*"Always allow from this computer"*).
2. **Build and install debug APK:**
   ```bash
   ./gradlew :Clients:HIAACApp:app:assembleDebug
   adb install -r Clients/HIAACApp/app/build/outputs/apk/debug/app-debug.apk
   ```

---

## Phone Preparation Checklist & Field Setup

Before recording a data collection experiment across one or multiple smartphones:

1. **Wi-Fi Connectivity:**
   - Connect all recording phones and the server workstation to the **same Wi-Fi network**, so the phones can reach the server by its local IP.
   - This works over a normal (internet-connected) network. For privacy-sensitive collections, the recommended practice is to install and update the server while it has internet access, then **disconnect it and run the collection on an isolated local network** (a dedicated Wi-Fi router with no internet/WAN). Keeping the server offline only during recording keeps the data off any external network and also avoids connection drops and institutional firewall limits.
2. **Server Address (CRITICAL):**
   - In the app, navigate to **Settings → Server Upload → Server Address**.
   - Set the address to your workstation's local LAN IP (e.g. `http://192.168.1.100:8080`).
   - **⚠️ NEVER use `127.0.0.1` or `localhost`** — on mobile devices, `127.0.0.1` refers to the phone itself, causing connection failure!
   - *Firewall Troubleshooting:* If the app shows a red clock sync indicator or reports connection timeout, ensure port **8080** is open on the server machine's firewall.
3. **Multi-Device Configuration:**
   - In experiments with multiple devices (such as the 5-device validation setup):
     - **Video / Reference Device:** Configure one smartphone under **Settings → Device Position** as `Camera`, with video capture enabled.
     - **Body-Worn Sensor Devices:** Configure other smartphones with their respective placement under **Device Position** (e.g., `Right Pocket`, `Left Pocket`, `Right Hand`, `Crossbody Bag`).
     - Ensure all devices use identical **Experiment** and **Subject** profile names so the server postprocessor automatically associates them into a single session.
4. **App Permissions:**
   - **Camera & Microphone:** Must be granted on the reference device for synchronized video recording.
   - **Location / GPS:** If collecting GPS data, grant **"Allow all the time"** (Background Location) to prevent Android from halting GPS updates.
5. **Battery Optimization Exemptions (Mandatory):**
   - Android power management (Doze mode) aggressively pauses background sensor threads and camera services.
   - Go to phone **Settings → Apps → Track-It App → Battery**.
   - Change setting to **"Unrestricted"** (or disable battery optimization).
6. **Dataset Flow Mode:**
   - In **Settings → Server Upload**, ensure **"Track-It Dataset Flow"** is **enabled (ON)** (the default). This instructs the app to bundle session metadata into `session_manifest.json` for automated downstream pipeline processing.

---

## Workflow

1. **Settings:** Set server address (`http://192.168.x.x:8080`), device position/location (e.g. Right Pocket, Chest), and UI Theme (**Appearance → Theme**: Light, Dark, or System).
2. **Experiment Setup:** Create or select an experiment profile, choose desired sensor streams and sampling rates, and select the activity label.
3. **Clock Synchronization:** The collection screen displays Server Time and Local Time. Clock offsets are computed continuously via round-trip HTTP pings. If disconnected, a warning indicates local clock fallback.
4. **Recording & Upload:** Tap **START** to record. Tap **STOP** to finalize CSV files (`[subject]_[experiment]_[activity]_[device]__[timestamp].csv`) and `session_manifest.json`, automatically uploading the package to the server.
5. **Statistics:** Inspect sample counts and synchronization offset history across all recorded sensors.

---

## Credits & License

Released under the **MIT License** (see `../LICENSE`). Copyright &copy; 2026 H.IAAC Hub &mdash; Universidade Estadual de Campinas (Unicamp).

Based on [H-IAAC/sensor-toolkit](https://github.com/H-IAAC/sensor-toolkit) (v3.0.1) developed by H.IAAC and Instituto de Pesquisas Eldorado (Felipe Augusto, Saulo A. Moraes, Daniel Adam Miranda, and contributors). The in-app **Open Source Licenses** screen (`LicenseActivity`) displays full open-source library attributions.
