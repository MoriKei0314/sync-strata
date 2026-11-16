<!-- 案（11/15 係 D）。口は serve/server.py と sync.py の説明に合わせた。 -->

# API

エンジンは OpenAI 互換と Anthropic 互換の API を持っています。GUI や dsh を使わず、ほかのソフトからつなぐときに使います。

- 起動: `sync up --api-only`（エンジンだけ）か、ふだんどおり `sync up`（Linux では `sync.sh`）。
- 番地: `http://127.0.0.1:8080/v1`（番号は設定 `api_port`）。
- 口: `POST /v1/chat/completions`・`POST /v1/responses`・`GET /v1/models`（OpenAI 互換）、`POST /v1/messages`（Anthropic 互換）。どれも流し（stream）と一括の両方に対応します。
- モデル名とつなぎ方の例: `sync api` が表示します。

```
curl http://127.0.0.1:8080/v1/chat/completions -H "Content-Type: application/json" ^
  -d "{\"model\": \"<sync api が出す名前>\", \"messages\": [{\"role\": \"user\", \"content\": \"こんにちは\"}]}"
```

## ほかの PC からつなぐ

既定では、この PC の中（`127.0.0.1`）からしかつなげません。LAN のほかの PC からつなぐときは鍵を決めてから待ち受けを広げます。

```
set STRATA_API_KEY=<自分で決めた長い文字列>          (Windows)
export STRATA_API_KEY=<自分で決めた長い文字列>       (Linux)
sync up --host 0.0.0.0
```

つなぐ側は `Authorization: Bearer <鍵>`（または `x-api-key`）を付けます。鍵なしで `0.0.0.0` にはしないでください。

## 注意

- 一度に処理する頼みは 1 つです（後から来た頼みは順に待ちます）。
- tail skip の設定（`tail_skip`）は API にも効きます。
