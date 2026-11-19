# Moving the app and the models (Windows)

English | [日本語](STORAGE.ja.md)

Sync-Strata uses three places. Each can be changed with a command (not from the app's screens yet).

| Place | Default | Size | How to change |
|---|---|---|---|
| The app | `%LOCALAPPDATA%\Programs\SyncStrata` | about 2 GB | `setup.cmd -AppDir` |
| The models | `%LOCALAPPDATA%\SyncStrata\models` | 60-100 GB | `setup.cmd -ModelsDir`, `sync settings set models_dir` |
| Settings and conversations (`SYNC_HOME`) | `%LOCALAPPDATA%\SyncStrata` | small | (please keep it where it is) |

- The conversation cache (0.4-0.5 GB each, 20 GB at most in total) goes to `SyncStrata-sessions` on the models' drive by itself when the models are on another drive.
- Short folder names without non-ASCII characters are recommended.
- Run the commands below in a Command Prompt. Run `setup.cmd` in the folder the zip was extracted to.

## Moving the app

### Before installing

```
setup.cmd -AppDir E:\SyncStrata
```

### After installing

1. Close the app with "close everything".
2. Uninstall the current app. When it asks whether to delete the models and the settings and conversations, just press Enter (they are kept).

   ```
   "%LOCALAPPDATA%\Programs\SyncStrata\uninstall.cmd"
   ```

3. In the extracted zip's folder, install to the new place.

   ```
   setup.cmd -AppDir E:\SyncStrata
   ```

- The settings and the models carry over. The desktop and Start menu shortcuts point to the new place.
- **Keep this order.** Installing to the new place first and then uninstalling the old app removes the new shortcuts too.
- After the move, `sync.cmd` is `E:\SyncStrata\app\launcher\sync.cmd`.

## Moving the models

### Before installing

```
setup.cmd -ModelsDir E:\SyncStrata\models
```

To move the app as well: `setup.cmd -AppDir E:\SyncStrata -ModelsDir E:\SyncStrata\models`.

### Installed, models not downloaded yet

```
"%LOCALAPPDATA%\Programs\SyncStrata\app\launcher\sync.cmd" settings set models_dir E:\SyncStrata\models
```

Then open the app and download as it guides you.

### Moving models already downloaded

1. Close the app with "close everything".
2. Move the whole `%LOCALAPPDATA%\SyncStrata\models` folder to `E:\SyncStrata\models`.
3. Run the same `sync.cmd settings set models_dir E:\SyncStrata\models` and open the app.

- There is no need to download them again.
- After the move, the model's "files checked" mark is gone. It works the same; "Check the files" in the model's row checks them again if you like.

## Tested on

0.1.1 on Windows 11, with every step above (a new install, moving an installed app, choosing the models' place, and starting with downloaded models moved).
