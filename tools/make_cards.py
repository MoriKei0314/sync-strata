#!/usr/bin/env python3
"""Hugging Face のモデルの説明（README.md）の案を，モデルの一覧（models.json）のファイルと大きさから作る（係 D，11/15）．

  py -3 -X utf8 make_cards.py --models <モデルの一覧（models.json）> [--out ../hf]

一覧の道のり・置き場の名前（hf.repo）は説明に書かない．<account> は新しいアカウントの名前に置き換える．
測りの値は書かない（枠だけ．値は測りの記録から手で入れる）．pack がまだ無いモデル（pending）は「準備中」の説明になる．
"""
import argparse, json, os

HERE = os.path.dirname(os.path.abspath(__file__))

ROLE = {
    'MANIFEST.json': 'Index of the pack (file names, sizes, checksums)',
    'experts.v2.bin': 'Routed experts (re-quantized)',
    'dense.bin': 'Dense weights read by the engine from the pack',
    'dense_nq.bin': 'Dense weights read by the engine from the pack (second part)',
}
# 11/16 本人の決定: アプリの auto は積んでいる RAM の段で選ぶ（画面の説明と同じ）
RECO = {
    'sync-xs': 'PCs with 24 GB of RAM or less',
    'sync-s': 'PCs with 32 GB of RAM',
    'sync-m': 'PCs with 48 GB of RAM or more',
}
# 品質（Colab の本番 eval_v4．NOTES 11/16 13:5x）．測っていないモデルは書かない（[measuring] のまま）
QUALITY = {
    'sync-xs': """Measured on Colab with the production eval_v4 (8 domains, 1,400 windows; the teacher is the Q8_0 GGUF of the original model). [TBD: number of tokens]

| | Sync-XS |
|---|---:|
| KL to the original model (all positions, lower is better) | 0.2851 |
| Top-1 agreement with the original model | 81.46% |
| Perplexity | 4.958 |
| p99 | 3.47 |

**It is on par with the earlier form of Sync-XS** (table-lookup points, the same dense part; KL 0.2845): +0.60% on "scale B" (95% range -0.23 to +1.34%), and -0.01% over all positions (-0.71 to +0.67%), both within the measurement noise. By domain (Sync-XS against that earlier form): english +2.1%, ja_docs -0.4%, ja_lit +0.1%, ja_chat -2.2%, code +0.7%, docs -0.6%, multilingual -0.2%, agent +5.5% (the worst).

Against other models (scale B; a minus sign means Sync-XS is closer to the original model):

| Compared with | Sync-XS is |
|---|---:|
| Gyro-S (upstream) | -16.1% (better; only docs is +1.2%) |
| IQ3_XXS | +48.7% |
| Gyro-M (upstream) | +39.3% |
| Sync-S (KL 0.2310) | +34.8% |
| Sync-M (KL 0.1642) | +102.2% |

Scale B is the ratio of KL where, for the agent domain, only the assistant's reply positions are counted (the other domains use all positions). A ratio is the change in KL relative to the other model.
""",
}
# 配布の一覧（chat-pack/models/models.dist.json）の local_dir と同じ名前
DIST_DIR = {'sync-xs': 'sync-xs-sb', 'sync-s': 'sync-s-sb', 'sync-m': 'sync-r1q2-sb'}
SHARED_NOTE = {
    'native-gguf': ('Shared weights cut from agentionai\'s Gyro-S GGUF (embeddings, n-gram/PLE table and the other '
                    'non-expert tensors the engine reads with `--native` / `--ple-gguf`). [TBD: file list after the split]'),
    'mtp-rt': 'The multi-token-prediction (draft) layer, converted from the original BF16 checkpoint for the engine; `draft_vocab.bin` comes from upstream Strata (MIT).',
    'tokenizer': 'The tokenizer and chat template of Qwen3.8-Flash-Next.',
    'mmproj': ('Optional vision encoder and projector (BF16). **Not hosted here**: the Sync-Strata app downloads it from its original repository, '
               '[ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF](https://huggingface.co/ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF). '
               'Its card says the files inherit the license of the base model (Qwen Community License 1.0); the repository metadata says Apache-2.0.'),
}


def gb(b):
    return f'{b / 1e9:,.2f} GB ({b / 2**30:,.2f} GiB)'


def header(name):
    return f"""---
license: other
license_name: qwen-community-1.0
license_link: LICENSE
base_model:
- Qwen/Qwen3.8-Flash-Next
base_model_relation: quantized
tags:
- qwen3.8-flash-next
- moe
- sync-strata
- experimental
---

<!-- Draft (11/15, D; 11/16 D2). Replace <account>; remove [TBD] / [measuring] before release. -->

# {name}
"""


COMMON_TAIL = """
## Calibration

The quantization was calibrated on public text (code, documentation, encyclopedia articles, several languages, agent
traces) and on some text made from the author's own chat logs. The calibration text is not distributed.

## Credits

- Base model: [Qwen/Qwen3.8-Flash-Next](https://huggingface.co/Qwen/Qwen3.8-Flash-Next) by the Qwen team.
- [agentionai](https://huggingface.co/agentionai): the Gyro trellis format and kernels, and the
  [Gyro-S GGUF](https://huggingface.co/agentionai/Qwen3.8-Flash-Next-Gyro-GGUF) that the shared parts are cut from.
- [Strata](https://github.com/Niko1221/Strata) by Niko1221 and the Strata contributors (MIT), which Sync-Strata forks.
- QTIP (Tseng et al., 2024); [llama.cpp / ggml](https://github.com/ggml-org/llama.cpp) (MIT).

## License

These files are derived from Qwen3.8-Flash-Next and are under the **Qwen Community License 1.0** (`LICENSE`,
Copyright (c) 2026 Qwen). Keep `LICENSE` with every copy. Commercial products with more than 100 million monthly active
users or US$20 million monthly revenue must show the model name, and a Model-as-a-Service or AI work assistant business
needs a separate license from Qwen for commercial use. Read the full text.
"""


def model_card(m, shared):
    name = m['name']
    total = sum(f['bytes'] for f in m.get('files', []))
    lines = [header(f'Qwen3.8-Flash-Next {name} (experimental)')]
    lines.append(f"""A re-quantized expert pack of **Qwen3.8-Flash-Next** for one consumer NVIDIA GPU, made to run faster than upstream
Strata's Gyro. It runs only on **[Sync-Strata](https://github.com/hiruhiru2005/sync-strata)** (a fork of
[Strata](https://github.com/Niko1221/Strata)). **This is not a GGUF: it does not load in llama.cpp or upstream Strata.**

Recommended for: **{RECO.get(m['id'], '')}**.

## What was done

- The routed experts were re-quantized to a trellis format of the Gyro / QTIP family, with the bit width chosen per
  expert. The pack also carries the dense weights that the engine reads from it.
- The remaining weights (embeddings, the n-gram/PLE table and so on) are not in this repository: they are in the
  shared parts, [hiru2005/Sync-shared](https://huggingface.co/hiru2005/Sync-shared), which every Sync model uses.
""")
    if m.get('pending') or not m.get('files'):
        lines.append('## Files\n\n[TBD] The pack is being prepared. Quality and speed: [measuring].\n')
    else:
        lines.append(f'## Files\n\nTotal: **{gb(total)}**, plus the shared parts.\n\n| File | Size | What |\n|---|---:|---|')
        for f in m['files']:
            role = ROLE.get(f['path'], 'Layout and conversion tables read by the engine' if f['path'].endswith(('.txt', '.json')) else '')
            lines.append(f"| `{f['path']}` | {f['bytes']:,} B | {role} |")
        lines.append('| `LICENSE` | | Qwen Community License 1.0 |\n')
    need = [s for s in shared if s['id'] in m.get('needs', [])]
    quality = QUALITY.get(m['id'], '[measuring] Not measured yet.\n')
    lines.append(f"""## Requirements

- Windows 10/11 or 64-bit Linux. Supported GPUs: NVIDIA RTX 30/40 series (driver R580 or newer); RTX 20, GTX 16, RTX 50 are expected to work, and GTX 10, Radeon RX 6000/7000/9000 and the integrated Radeon of Ryzen AI Max (Strix Halo: 8060S, 8050S, 8040S; Windows and Linux) are experimental, all not checked on real hardware. Other integrated GPUs and Intel GPUs are not supported ([the GPU table](https://github.com/hiruhiru2005/sync-strata#supported-gpus)). A CPU with AVX2.
- RAM and VRAM: see "Recommended for" above. The app picks the model by the RAM installed in the PC; if the free RAM is short it warns you instead of choosing a smaller model. [TBD: minimum]
- Disk: this pack plus the shared parts ({', '.join('`' + s['id'] + '`' + (' (optional)' if s.get('optional') else '') for s in need)}). An NVMe SSD is recommended.

## Use with Sync-Strata

The Sync-Strata app downloads this model for you: open the app and pick **{name}** on the first screen (or let
"auto" choose). To download by hand, put the files in a folder named `{DIST_DIR.get(m['id'], m['id'])}` inside the app's models folder (`models_dir` in `settings.json`), together with the shared parts.

```
sync settings set model {m['id']}
sync up
```

## Quality

{quality}
## Speed

[measuring] Measured on the author's PC (Ryzen 7 7800X3D, 32 GB DDR5, RTX 3080 12 GB, NVMe SSD; Windows 11 and Linux). No numbers for GTX 10 or Radeon: no hardware to measure on.

| | tail skip | jbench decode (tok/s) | dsh chat (tok/s) |
|---|---|---:|---:|
| {name} | R4 | | |
| {name} | R7 | | |
| {name} | R10 | | |
| Gyro-S (upstream) | | | |
| Gyro-M (upstream) | | | |

Speed depends strongly on the PC. The measured values are in the table of the [Sync-Strata README](https://github.com/hiruhiru2005/sync-strata#benchmarks).
""")
    lines.append(COMMON_TAIL)
    return '\n'.join(lines)


def shared_card(shared):
    lines = [header('Sync shared parts for Qwen3.8-Flash-Next (experimental)')]
    lines.append("""The parts every Sync model (Sync-XS, Sync-S, Sync-M) needs besides its own pack. Download them once.
They are used only by **[Sync-Strata](https://github.com/hiruhiru2005/sync-strata)**; the Sync-Strata app downloads them for you.

## Files
""")
    for s in shared:
        files = s.get('files', [])
        tot = sum(f['bytes'] for f in files)
        lines.append(f"### `{s['id']}/`{' (optional)' if s.get('optional') else ''}\n\n{SHARED_NOTE.get(s['id'], '')}\n")
        if s['id'] == 'mmproj':
            lines.append('| File | Size |\n|---|---:|')
            lines += [f"| `{f['path']}` (original repository) | {f['bytes']:,} B |" for f in files]
            lines.append('')
            continue
        if s['id'] == 'native-gguf':
            lines.append('[TBD: files and sizes after the split. The whole Gyro-S file is 58.49 GB; the split keeps only the parts the engine reads.]\n')
            continue
        lines.append(f'Total: {gb(tot)}\n\n| File | Size |\n|---|---:|')
        lines += [f"| `{f['path']}` | {f['bytes']:,} B |" for f in files]
        lines.append('')
    lines.append("""## Where they come from

- `native-gguf` is cut from [agentionai/Qwen3.8-Flash-Next-Gyro-GGUF](https://huggingface.co/agentionai/Qwen3.8-Flash-Next-Gyro-GGUF)
  (Gyro-S, revision [TBD]) without changing the bytes of the tensors kept. [TBD: confirm with the split tool]
- `mtp-rt` is converted from [Qwen/Qwen3.8-Flash-Next](https://huggingface.co/Qwen/Qwen3.8-Flash-Next) (BF16) with upstream Strata's tools.
- `tokenizer` is the base model's tokenizer.
- `mmproj` is not in this repository; it is downloaded from [ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF](https://huggingface.co/ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF) (converted there from the base checkpoint).

## Credits

- Base model: [Qwen/Qwen3.8-Flash-Next](https://huggingface.co/Qwen/Qwen3.8-Flash-Next) by the Qwen team.
- [agentionai](https://huggingface.co/agentionai) (Gyro-S), [ISTA-DASLab](https://huggingface.co/ISTA-DASLab) (vision projector),
  [Strata](https://github.com/Niko1221/Strata) (MIT; tools and `draft_vocab.bin`).

## License

Derived from Qwen3.8-Flash-Next: **Qwen Community License 1.0** (`LICENSE`, Copyright (c) 2026 Qwen). Keep `LICENSE`
with every copy. See the full text for the conditions on large commercial products and on Model-as-a-Service / AI work
assistant businesses.
""")
    return '\n'.join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--models', required=True, help='the model list (models.json)')
    ap.add_argument('--out', default=os.path.join(os.path.dirname(HERE), 'hf'))
    a = ap.parse_args()
    cat = json.load(open(a.models, encoding='utf-8'))
    for m in cat['models']:
        d = os.path.join(a.out, m['name'])
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, 'README.md'), 'w', encoding='utf-8', newline='\n').write(model_card(m, cat['shared']))
    d = os.path.join(a.out, 'Sync-shared')
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, 'README.md'), 'w', encoding='utf-8', newline='\n').write(shared_card(cat['shared']))
    print('作った:', ', '.join([m['name'] for m in cat['models']] + ['Sync-shared']))


if __name__ == '__main__':
    main()
