# yStore

**yStore** is an open-source, alternative client for the Google Play Store designed with modern Material 3 guidelines. It allows users to search, download, and update Android applications with privacy and ease.

- **App Name:** yStore
- **Application ID (Package Name):** `y.Store`
- **License:** GPL-3.0

---

## Features

- **Modern Material Design:** Built following the latest Material 3 expressive design principles.
- **Account Flexibility:** Supports signing in with either a Google account or anonymous credentials.
- **Privacy First:** Native integration with Exodus Privacy to review trackers and permissions before installing.
- **Compatibility & Spoofing:** Spoof device configuration and locale to access region-locked applications.
- **Download & Update Manager:** Reliable background updates and downloads.
- **Multiple Installers Supported:** Session Installer, Native, Shizuku, and Root installation options.
- **Update Filtering:** Blacklist specific apps from update checks and notifications.

---

## Limitations

- Uses reverse-engineered Google Play APIs; changes on the upstream server side may occasionally require updates.
- Paid applications and Play Asset Delivery items are not supported for download.
- Some personalized features (purchase history, library management) require signing in with a personal account.

---

## Building from Source

### Prerequisites

- **JDK:** Java 21 (or Java 17 with Gradle toolchain support)
- **Android SDK:** API Level 37 compile SDK, minimum SDK 23

### Build Commands

Clone the repository and run:

```bash
# Debug build (flavor: vanilla)
./gradlew assembleVanillaDebug

# Release build (flavor: vanilla)
./gradlew assembleVanillaRelease
```

The resulting APK will be located in `app/build/outputs/apk/vanilla/`.

---

## Permissions

- `android.permission.INTERNET`: Connect to Play Store servers for searching and downloading.
- `android.permission.ACCESS_NETWORK_STATE`: Monitor network connectivity.
- `android.permission.FOREGROUND_SERVICE` & `FOREGROUND_SERVICE_DATA_SYNC`: Uninterrupted background downloads and updates.
- `android.permission.REQUEST_IGNORE_BATTERY_OPTIMIZATIONS`: Prevent background downloads from being paused by battery saver.
- `android.permission.MANAGE_EXTERNAL_STORAGE` / `READ_EXTERNAL_STORAGE` / `WRITE_EXTERNAL_STORAGE`: Manage OBB and APK expansion files.
- `android.permission.QUERY_ALL_PACKAGES`: Check for updates across installed applications.
- `android.permission.REQUEST_INSTALL_PACKAGES`: Trigger app installation.
- `android.permission.REQUEST_DELETE_PACKAGES`: Allow uninstalling apps directly from the manager.
- `android.permission.ENFORCE_UPDATE_OWNERSHIP`: Maintain update ownership consistency.
- `android.permission.POST_NOTIFICATIONS`: Inform about download progress and updates.

---

## License

This project is licensed under the terms of the **GNU General Public License v3.0** (GPL-3.0). See [LICENSE](LICENSE) for details.
