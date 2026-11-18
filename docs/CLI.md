# Command reference (CLI)

English | [日本語](CLI.ja.md)

The `sync` commands let you do from a terminal what the app does, and give other software a way in.

- Windows: `sync ...` (the command in the Start menu, or `sync.cmd` in the app's folder).
- Linux: `./sync.sh ...` (`sync.sh` in the app's folder). It does the same as `sync` on Windows.
- `sync` with no arguments shows a small numbered menu (start, API only, stop, status, PC check, help).
- `sync help` (`-h`, `--help`) prints the list too.
- Add `--lang en|ja` to any command to choose the language of the output (default: Japanese; English on a text-only console, `TERM=linux`; you can also set the environment variable `SYNC_LANG`).

The examples use the Windows form. On Linux, read `sync` as `./sync.sh`.

## The commands at a glance

| Command | What it does |
|---|---|
| [`sync up`](#sync-up) | Start the engine and dsh |
| [`sync down`](#sync-down) | Stop |
| [`sync status`](#sync-status) | Running? Model, recent speed |
| [`sync settings`](#sync-settings) | Show or change settings |
| [`sync ctx`](#sync-ctx) | Context settings and the length that fits |
| [`sync gui-url`](#sync-gui-url) | The URL of the chat screen |
| [`sync api`](#sync-api) | How to connect other software (address, model name, examples) |
| [`sync chat`](#sync-chat) | Chat in the terminal |
| [`sync doctor`](#sync-doctor) | PC state and advice |
| [`sync env`](#sync-env) | Whether this PC is supported |
| [`sync mem`](#sync-mem) | The current memory state |
| [`sync remote-url`, `sync remote-apply`](#sync-remote-url-sync-remote-apply) | Phone connection |
| [`sync update`](#sync-update) | Check for and apply updates |

## `sync up`

Starts the engine and dsh. Settings are decided in the order `settings.json`, then the options below; items set to `auto` are decided by checking your PC. With no options it starts the engine, dsh and the relay of the chat screen. No window is opened.

```
sync up [--gui | --no-gui | --api-only] [--open] [--json]
        [--preset speed|quality|auto] [--tail-skip 4|7|10|auto]
        [--model auto|<model name>]   (alias --pack)
        [--ram-max-gib N] [--vram-reserve-mib N] [--ram-squeeze auto|off]
        [--context N] [--kv k8v4|k8|k4|auto]   (alias --kv-format)
        [--port N] [--host ADDRESS] [--api-key KEY]
        [--env NAME=VALUE ...] [--engine ENGINE_EXE] [--dry] [--stop]
```

| Option | Description |
|---|---|
| `--gui`, `--no-gui` | Start the engine and dsh (no window). The two do the same; `--no-gui` is the name for people who use it from a phone. Same as giving neither |
| `--api-only` | Start the engine only (no dsh, no chat screen). For people who connect other software. Cannot be combined with `--gui` or `--no-gui` |
| `--open` | After starting, open the chat screen in a window |
| `--json` | Print the result as one line of JSON at the end (progress goes to standard error) |
| `--preset` | `quality` (tail skip R7) or `speed` (R4). An alias of `--tail-skip` |
| `--tail-skip` | Tail skip at start-up: `4`, `7`, `10` (10 = no skipping) or `auto` (R4 or R7 to suit your PC). It only matters when you use the API from other software (dsh chats follow the model chosen for each chat) |
| `--model` (`--pack`) | `auto`, or the name of a model in the list (for example `sync-s`) |
| `--ram-max-gib` | Upper limit of RAM for the copy of the model (GiB) |
| `--vram-reserve-mib` | VRAM to leave free for other apps (MiB) |
| `--ram-squeeze` | Whether to push other apps' RAM out at start-up: `auto` (default; yes) or `off` |
| `--context` | Context length (tokens) |
| `--kv` (`--kv-format`) | Quantization of the conversation memory (K/V): `k8v4`, `k8`, `k4`, `auto` |
| `--port` | Port of the engine (API) (the `api_port` setting) |
| `--host` | Address to listen on (the `api_host` setting). Anything other than `127.0.0.1` needs a key ([API.md](API.md)) |
| `--api-key` | The API key. Passing it in the environment variable `STRATA_API_KEY` is recommended, so it does not stay on screen |
| `--env NAME=VALUE` | Add an environment variable for the engine (can be given several times) |
| `--engine` | The engine executable to start (not needed normally) |
| `--dry` | Do not start; only print the settings that were decided |
| `--stop` | The older name for stopping the engine (same as `sync down --engine`) |

A busy port is replaced automatically. If another program is using one of the default ports (engine 8080, relay 8081, dsh 3080, chat screen 3081), `sync up` picks a free one nearby, saves it in `settings.json` and says so, for example "Port 8080 (engine) is used by another program, so 8082 is used instead." `sync api` and `sync status` show the actual ports.

Exit codes: `0` success; `2` a wrong setting or option (also a missing key when listening beyond `127.0.0.1`); `3` the PC could not be checked; `4` the model or the shared parts are not installed yet; `6` dsh or the relay of the chat screen did not start; `8` this PC is not supported. Any other non-zero value means the engine failed to start.

Examples:

```
sync up                          # start the engine and dsh
sync up --api-only               # the API only
sync up --open --preset speed    # start for speed and open the chat screen
sync up --model sync-s --context 131072
sync up --env NAME=VALUE         # pass an environment variable to the engine
sync up --dry                    # only look at the decided settings
```

## `sync down`

```
sync down [--all | --engine | --dsh] [--json]
```

| Option | Description |
|---|---|
| `--all` | Stop the engine and the dsh and relay that Sync started (default) |
| `--engine` | Stop the engine only (dsh keeps running) |
| `--dsh` | Stop dsh and the relay only (the engine and the API keep running) |
| `--json` | Print the result as one line of JSON |

It stops only the dsh that `sync up` or the app started itself. Any other dsh is left alone.

## `sync status`

```
sync status [--json] [--port N]
```

Shows whether it is running, the model, whether images work, whether a key is set and the recent speed. When it is stopped it says so and returns exit code 1. `--json` prints one line of JSON: engine, dsh, relay, installed models, settings, whether it is the first run, the environment check and the context (the ports are in it too).

## `sync settings`

```
sync settings get [--json]
sync settings set <name> <value|auto> [--json]
```

Show or change the settings (`settings.json`). A changed value takes effect from the next start. The names and their meanings are in [SETTINGS.md](SETTINGS.md).

```
sync settings get
sync settings set tail_skip 4
sync settings set context auto
sync settings set lan_remote lan
```

## `sync ctx`

```
sync ctx [--json]
```

For the context length and the K/V quantization it shows the current setting, the automatic value and the value in use, the combinations that fit in VRAM, and "up to about N tokens with this setting". To change them, use `sync settings set context ...` and `sync settings set kv_format ...`.

## `sync gui-url`

```
sync gui-url [--json]
```

Prints the URL that opens the chat screen (for a dsh that Sync started, a URL that takes care of the login). `--json` prints `{"url": "..."}`.

## `sync api`

```
sync api [--port N] [--host ADDRESS]
```

Prints how to connect other software: the address, the model name, how to send the key, examples with environment variables, curl and Python (openai). The port is the actual value of the `api_port` setting (the new one, if it was moved to a free port). When the engine is stopped it tells you that `sync up --api-only` starts it.

## `sync chat`

```
sync chat [--system TEXT] [--preset speed|quality] [--tail-skip N] [--port N]
```

Chat right in the terminal (it connects straight to the engine's API, so run `sync up --api-only` or `sync up` first). An empty line or Ctrl-C ends it. `--system` sets a first instruction. The tail skip is R7 by default; `--preset speed` gives R4 and `--tail-skip` sets the number directly. The tok/s is shown after each reply.

## `sync doctor`

```
sync doctor [--ssd]
```

Prints the state of the PC and advice: RAM, GPU, the model it recommends, notes about the supported environment, apps whose closing would make it faster, and the other apps that are using the CPU or GPU right now. `--ssd` also checks the speed of the SSD that holds the models.

## `sync env`

```
sync env [--json [--ascii]]
```

Tells you whether this PC is supported (the reasons it is not, and notes). The exit code is `0` when it is supported and `8` when it is not. `--json` prints the result as one line of JSON, and `--ascii` writes non-ASCII characters as `\u` escapes.

## `sync mem`

```
sync mem
```

Prints the current memory state (RAM, commit, VRAM, the top other apps, and Sync-Strata's own share) as one line of JSON. It is the source of the "Memory" box in the app. The exit code is 1 when it could not be checked.

## `sync remote-url`, `sync remote-apply`

```
sync remote-url [--json] [--pair]
sync remote-apply
```

For the phone connection (the `lan_remote` setting; see [REMOTE.md](REMOTE.md)).

| Command | Description |
|---|---|
| `sync remote-url` | Print the URL to open on the phone |
| `sync remote-url --pair` | Show a one-time QR code in the terminal (it expires in 3 minutes). Use it the first time you open the app on a phone |
| `sync remote-url --json` | The same information as JSON |
| `sync remote-apply` | Restart the dsh and relay that Sync started so that the setting takes effect now (the engine and the chat proxy are left as they are) |

## `sync update`

```
sync update check [--json] [--local] [--source PLACE] [--root APP_FOLDER]
sync update apply [--json] [--root APP_FOLDER] [--no-close] [--no-relaunch] [--dry]
```

| Command | Description |
|---|---|
| `sync update check` | Without downloading anything, check whether there is a new version and which parts would change. `--local` does not use the network and only checks the current version |
| `sync update apply` | A detached helper closes everything, updates, and starts the app again. Progress is shown in a window (on Linux without a terminal, only in a log file). `--no-close` does not close anything, `--no-relaunch` does not start again, and `--dry` only prints what it would do |

The result is printed as JSON. How updating works and how to go back to the previous version are in [INSTALL.md](INSTALL.md).

## Environment variables

| Name | Description |
|---|---|
| `STRATA_API_KEY` | The API key. Required when you listen beyond `127.0.0.1`, as in `sync up --host 0.0.0.0`. `sync status`, `sync api` and `sync chat` also use it to talk to the engine |
| `SYNC_LANG` | The language of the output (`en`, `ja`). `--lang` takes precedence |
