# API

エンジンは OpenAI 互換と Anthropic 互換の API を持っています。GUI や dsh を使わず、ほかのソフトからつなぐときに使います。

- 起動: `sync up --api-only`（エンジンだけ）か、ふだんどおり `sync up`（Linux では `sync.sh`）。
- 番地: `http://127.0.0.1:8080/v1`（番号は設定 `api_port`。8080 は既定の番号です。ほかのプログラムが使っていると、`sync up` が空いている番号に替えて `settings.json` に書き、起動の表示に「番号 8080（エンジン）はほかのプログラムが使っているので，8082 にしました．」のように出します。実際の番号は `sync api` で分かります）。
- 口: `POST /v1/chat/completions`・`POST /v1/responses`・`GET /v1/models`（OpenAI 互換）、`POST /v1/messages`（Anthropic 互換）。どれも流し（stream）と一括の両方に対応します。
- モデル名とつなぎ方の例: `sync api` が表示します。

```
curl http://127.0.0.1:8080/v1/chat/completions -H "Content-Type: application/json" ^
  -d "{\"model\": \"<sync api が出す名前>\", \"messages\": [{\"role\": \"user\", \"content\": \"こんにちは\"}]}"
```

例の 8080 は、実際の番号（`sync api` が出します）に読み替えてください。

## ほかの PC からつなぐ

既定では、この PC の中（`127.0.0.1`）からしかつなげません。LAN のほかの PC からつなぐときは鍵を決めてから待ち受けを広げます。

```
set STRATA_API_KEY=<自分で決めた長い文字列>          (Windows)
export STRATA_API_KEY=<自分で決めた長い文字列>       (Linux)
sync up --host 0.0.0.0
```

つなぐ側は `Authorization: Bearer <鍵>`（または `x-api-key`）を付けます。鍵なしで `0.0.0.0` にはしないでください。

ほかの PC から届かないときは、ファイアウォールでエンジンの番号（既定 8080。実際の番号は `sync api` で分かります）を開けます。下の 8080 は実際の番号に替えてください。

```
netsh advfirewall firewall add rule name="Sync-Strata API" dir=in action=allow protocol=TCP localport=8080   (Windows。管理者のコマンドプロンプトで)
sudo ufw allow 8080/tcp                                                                                    (Linux。ufw を使っているとき)
```

## 注意

- 一度に処理する頼みは 1 つです（後から来た頼みは順に待ちます）。
- tail skip の設定（`tail_skip`）は API にも効きます。頼みごとに `"strata_tune": {"tail_skip": 4}` で変えられますが、エンジンを tail skip なし（R10）で起動したときは、頼みごとの値は効きません。
- 頼みに `repetition_penalty` を書かないときは、1.05 が入ります（同じ文の繰り返しを防ぐため）。
- エンジンの組み込みの画面（`http://127.0.0.1:8080`。番号は実際のエンジンの番号）で変えた設定は、次の `sync up` で起動の設定に戻ります。設定は `sync settings` で変えてください。
- 会話を SSD に保存して後で戻す機能は、会話の画面（dsh）を通した会話だけです。
