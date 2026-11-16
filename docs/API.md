<!-- Draft (11/16, D2). Translated from API.ja.md (the Japanese file is the source). -->

# API

The engine has OpenAI-compatible and Anthropic-compatible APIs. Use them to connect other software without the app or dsh.

- Start: `sync up --api-only` (the engine only), or as usual `sync up` (`sync.sh` on Linux).
- Address: `http://127.0.0.1:8080/v1` (the port is the `api_port` setting).
- Endpoints: `POST /v1/chat/completions`, `POST /v1/responses`, `GET /v1/models` (OpenAI-compatible) and `POST /v1/messages` (Anthropic-compatible). All of them support both streaming and a single response.
- The model name and examples of how to connect: `sync api` prints them.

```
curl http://127.0.0.1:8080/v1/chat/completions -H "Content-Type: application/json" ^
  -d "{\"model\": \"<the name that sync api prints>\", \"messages\": [{\"role\": \"user\", \"content\": \"Hello\"}]}"
```

## Connecting from another PC

By default you can connect only from inside this PC (`127.0.0.1`). To connect from another PC on the LAN, set a key first and then widen the listening address.

```
set STRATA_API_KEY=<a long string you choose>          (Windows)
export STRATA_API_KEY=<a long string you choose>       (Linux)
sync up --host 0.0.0.0
```

The connecting side sends `Authorization: Bearer <key>` (or `x-api-key`). Do not use `0.0.0.0` without a key.

## Notes

- It handles one request at a time (later requests wait in turn).
- The tail skip setting (`tail_skip`) applies to the API too.
