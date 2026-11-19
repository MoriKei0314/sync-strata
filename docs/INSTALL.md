# Installing, updating and removing Sync-Strata

Sections 1-6 are for Windows. For Linux, read the "Linux" section at the end.

## Windows

Sync-Strata is a local LLM app that runs on your own PC's GPU. The chat app (dsh) and the engine come together.

## 1. What you need

| | |
|---|---|
| OS | Windows 10 (1803 or later) or Windows 11, 64-bit |
| GPU | NVIDIA RTX 20 to 50 series, GTX 10 series, Tesla P100, Tesla V100 or Titan V; AMD Radeon RX 6000, 7000 and 9000 series (discrete cards including laptop ones such as the RX 7600M, experimental). The full list is the table in the [README](../README.md). With 8 GB of GPU memory or more (12 GB or more recommended). Only one GPU is used, even if the PC has several (the one with the most memory among the supported ones). NVIDIA driver R580 or newer (a version that runs CUDA 13.0); for the GTX 10 series, P100, V100 and Titan V (CUDA 12 engine), 576.57 or newer |
| CPU | AVX2 is required |
| RAM | Depends on the model: Sync-XS is for PCs with 24 GB or less, Sync-S for 32 GB, Sync-M for 48 GB or more (the app chooses by the RAM installed) |
| Free disk space | About 2 GB for the app (plus the same again for the one previous version kept during an update), plus about 35 GB of shared parts that every model needs, plus the model (Sync-XS about 24 GB, Sync-S about 28 GB, Sync-M about 35 GB). Put the model on a fast SSD (NVMe) |
| Admin rights, Python or Node on the PC | Not needed (everything is inside the app) |
| Network | Not needed to install (everything is in the zip). Only to download models and to update |

## 2. Install (first time, repair or another PC: all the same)

1. Unzip the downloaded zip (for example into a folder named `SyncStrata-0.1.0-1115`). A path without non-ASCII characters is recommended.
2. Double-click `setup.cmd` inside.
   - It checks what is already installed and installs **only what is missing, old or broken**. Running it again gives the same result.
   - At the end it prints one line per part: installed, repaired or skipped.
   - The app goes into `%LOCALAPPDATA%\Programs\SyncStrata`. To use another place, run in a command prompt:
     `setup.cmd -AppDir <install location>`
3. Double-click **Sync-Strata** on the desktop. If there is no model yet, the first screen helps you install one.

### If you already have a model

If you have a model downloaded for example by a benchmark kit (a layout with `sync-s-sb\` and the like inside `models\`), setup looks for it and uses that place
**without downloading again** (it searches next to the unzipped zip, up to two levels down from the drive root, and inside your user folder).
If it is not found, or you want to use another place, point to it, for example `setup.cmd -ModelsDir <models folder>`.
To move the app or the models after installing, see [STORAGE.md](STORAGE.md).

## 3. Update

### From the app's screen

Open **Updates** in the settings (the start settings).

- **Check for updates** shows the version now, the new version, the parts that would be replaced and their size, and the release notes. It only checks; nothing is downloaded. Nothing is checked until you press it.
- **Close and update** (after a yes) closes Sync-Strata, updates it and starts it again. A window shows the progress (on Linux a terminal, or `SYNC_HOME/logs/update-<date>.log` when there is none). Chats and downloads stop.
- Closing and updating works **from the PC's screen** only. A phone can check, nothing more.
- When the place of new versions cannot be reached, it says why and shows the by-hand way (the folders to put the release zip in).
  A zip in the Downloads folder is not used by itself (from 0.1.2). To use a downloaded zip, point to it: `update.cmd --source <zip>`.

### From the Start menu

Double-click **Sync-Strata update** in the Start menu (`update.cmd` in the install folder).

- It reads the list of the new version and downloads and replaces **only the parts that changed**.
- **It does not replace anything while the app is running.** Close the app with "close everything" first.
- It does not touch the models, or your settings and chats (`SYNC_HOME`).
- It keeps the previous version. If the new version gives you trouble, use **Roll back Sync-Strata** in the Start menu (`rollback.cmd`).
- The update source can be changed in the settings (`update_feed` in `settings.json`). To point to a local folder or a URL, for example
  `update.cmd -Source <the new version feed folder>`.

## 4. Uninstall

Use **Uninstall Sync-Strata** in the Start menu (`uninstall.cmd` in the install folder).

- It removes the app and the icons that setup made.
- It asks whether to remove the models, and your settings and chats (`SYNC_HOME`, by default `%LOCALAPPDATA%\SyncStrata`) (the default keeps them).

## 5. Where things are

| Place | What is in it | On update |
|---|---|---|
| App (`%LOCALAPPDATA%\Programs\SyncStrata`) | The app shell, the launcher, the chat screen, the engine, Python, Node, dsh | Replaced (the previous version is kept) |
| Models (`models_dir` in `settings.json`) | The model files | Not touched |
| Your data (`SYNC_HOME`, by default `%LOCALAPPDATA%\SyncStrata`) | `settings.json`, dsh's settings and chats (`dsh-home\`) | Not touched |

## 6. If something goes wrong

- "It is running, so it is not replaced": close the app with "close everything". From the command line: `sync down --all`.
- "sha256 does not match the list": the downloaded zip is broken. Download it again and run `setup.cmd` once more.
- If you think a part may be broken: `setup.cmd -Full` re-measures every file and reinstalls only the broken parts.

## Linux

1. Download the Linux release (`SyncStrata-<version>-linux.zip`), extract it, and run `./setup.sh` in a terminal. It installs only what is missing, and running it again gives the same result.
2. Open **Sync-Strata** from the application menu (an icon is also placed on the desktop).
3. The command is `sync.sh` (`./sync.sh up`, `./sync.sh down` and so on; the same as `sync` on Windows).
4. The app goes into `~/.local/share/SyncStrata`, and settings and chats (`SYNC_HOME`) into `~/.config/SyncStrata`. The models folder is `models_dir` in `settings.json`.
5. To update or uninstall, use "Sync-Strata update" and "Uninstall Sync-Strata" in the application menu (`~/.local/share/SyncStrata/update.sh` and `uninstall.sh`). To go back to the previous version, use "Roll back Sync-Strata" in the application menu (`~/.local/share/SyncStrata/rollback.sh`).
6. What you need: 64-bit Linux (glibc 2.28 or later; the author's machine runs Ubuntu 24.04, other distributions are not checked), NVIDIA driver R580 or newer (580.95.05 or newer on Linux; 575.57.08 or newer for the GTX 10 series, V100 and Titan V). Radeon (RX 6000, 7000 and 9000 series, discrete cards including laptop ones) uses the HIP engine; experimental, not checked on real hardware.
7. On a PC with no screen (a server over SSH), start with `./sync.sh up --no-gui` instead of the application menu. It starts the engine and dsh without opening a window. WSL2 and Macs: see the notes under "Supported GPUs" in the [README](../README.md).
