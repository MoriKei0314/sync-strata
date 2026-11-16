<!-- Draft (11/16, D2). Translated from INSTALL.ja.md (the Japanese file is the source). [TBD] marks go before release. -->

# Installing, updating and removing Sync-Strata

Sections 1-6 are for Windows. For Linux, read the "Linux" section at the end.

## Windows

Sync-Strata is a local LLM app that runs on your own PC's GPU. The chat app (dsh) and the engine come together.

## 1. What you need

| | |
|---|---|
| OS | Windows 10 (1803 or later) or Windows 11, 64-bit |
| GPU | NVIDIA RTX 30 or 40 series (the full list of supported GPUs is the table in the [README](../README.md)). Driver R580 or newer (a version that runs CUDA 13.0); for the GTX 10 series (CUDA 12 engine), 576.57 or newer |
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

## 3. Update

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
5. To update or uninstall, use "Sync-Strata update" and "Uninstall Sync-Strata" in the application menu (`~/.local/share/SyncStrata/update.sh` and `uninstall.sh`). How to roll back to the previous version: [TBD].
6. What you need: 64-bit Linux (glibc 2.28 or later; the author's machine runs Ubuntu 24.04, other distributions are not checked), NVIDIA driver R580 or newer (580.95.05 or newer on Linux; 575.57.08 or newer for the GTX 10 series). Radeon uses the HIP engine; experimental, not checked on real hardware.
