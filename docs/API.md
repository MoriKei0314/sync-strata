# API

The engine has OpenAI-compatible and Anthropic-compatible APIs. Use them to connect other software without the app or dsh.

- Start: `sync up --api-only` (the engine only), or as usual `sync up` (`sync.sh` on Linux).
- Address: `http://127.0.0.1:8080/v1` (the port is the `api_port` setting; 8080 is the default. If another program is using it, `sync up` switches to a free port, saves it in `settings.json` and says so at start-up, for example "Port 8080 (engine) is used by another program, so 8082 is used instead."). `sync api` shows the actual port.
- Endpoints: `POST /v1/chat/completions`, `POST /v1/responses`, `GET /v1/models` (OpenAI-compatible) and `POST /v1/messages` (Anthropic-compatible). All of them support both streaming and a single response.
- The model name and examples of how to connect: `sync api` prints them.

```
curl http://127.0.0.1:8080/v1/chat/completions -H "Content-Type: application/json" ^
  -d "{\"model\": \"<the name that sync api prints>\", \"messages\": [{\"role\": \"user\", \"content\": \"Hello\"}]}"
```

Read 8080 in the example as the actual port (`sync api` prints it).

## Connecting from another PC

By default you can connect only from inside this PC (`127.0.0.1`). To connect from another PC on the LAN, set a key first and then widen the listening address.

```
set STRATA_API_KEY=<a long string you choose>          (Windows)
export STRATA_API_KEY=<a long string you choose>       (Linux)
sync up --host 0.0.0.0
```

The connecting side sends `Authorization: Bearer <key>` (or `x-api-key`). Do not use `0.0.0.0` without a key.

If other PCs cannot reach it, open the engine's port (8080 by default; `sync api` shows the actual one) in the firewall. Replace 8080 below with the actual port.

```
netsh advfirewall firewall add rule name="Sync-Strata API" dir=in action=allow protocol=TCP localport=8080   (Windows, in an administrator command prompt)
sudo ufw allow 8080/tcp                                                                                    (Linux, when ufw is on)
```

## Notes

- It handles one request at a time (later requests wait in turn).
- The tail skip setting (`tail_skip`) applies to the API too. You can change it per request with `"strata_tune": {"tail_skip": 4}`, but when the engine was started without tail skip (R10), the per-request value has no effect.
- When a request does not set `repetition_penalty`, 1.05 is used (to keep the same sentence from repeating).
- Settings changed in the engine's built-in page (`http://127.0.0.1:8080`; use the engine's actual port) go back to the start-up settings at the next `sync up`. Change settings with `sync settings`.
- Saving a conversation to the SSD and restoring it later works only for conversations through the chat screen (dsh).
