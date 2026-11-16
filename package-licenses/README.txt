Sync-Strata: licenses of the bundled parts / 同梱する部品のライセンス

Sync-Strata itself is MIT-licensed (sync-strata/LICENSE-Strata.txt; the authors of the fork are added there
[TBD]). The parts below are bundled in this release and keep their own licenses.

Folder / file                          What
sync-strata/LICENSE-Strata.txt         Strata (MIT): the engine, the server and the app are a fork of it
engine/LICENSE-ggml-llama.cpp.txt      llama.cpp / ggml (MIT), compiled into the engine
engine/LICENSE-project-maya.txt        Project Maya (MIT), compiled into the engine
engine/NOTICE-project-maya.md          Project Maya: which files come from it
nvidia/NOTICE-NVIDIA-cuBLAS.txt        NVIDIA cuBLAS DLLs beside the engine (CUDA Toolkit EULA)
node/LICENSE-Node.js-24.19.0.txt      Node.js (dsh-node.exe is node.exe 24.19.0), with the licenses of what Node bundles
dsh/LICENSE-dsh.txt                    dsh by DeepSeek (MIT), the chat app
npm/THIRD-PARTY-NOTICES-npm.txt        All 537 npm packages under dsh, each with its license text
                                       (19 of them ship no license file; their notice was made from package.json)
python/LICENSE-Python.txt              Python 3.12 (embeddable) and the parts it bundles
python/THIRD-PARTY-NOTICES-python.txt  The 27 Python packages, each with its license files
rust/THIRD-PARTY-NOTICES-app.txt       The app (Tauri 2): Strata's license and the list of 229 Rust crates
rust/LICENSE-TEXTS-rust.txt            Full license texts of those crates (145 distinct texts)
copyleft/LGPL-3.0.txt, GPL-3.0.txt     For libvips (LGPL-3.0-or-later)
copyleft/MPL-2.0.txt                   For LibreOffice Kit, certifi, tqdm and five Rust crates
copyleft/SOURCES.txt                   Where to get the source of the LGPL and MPL parts
fonts/OFL-ZenKakuGothicNew.txt         Zen Kaku Gothic New (SIL OFL 1.1), the chat page's font
fonts/OFL-Outfit.txt                   Outfit (SIL OFL 1.1), the engine's web page font
models/LICENSE-Qwen-Community-1.0.txt  The models (Sync-XS, Sync-S, Sync-M and the shared parts) are derived from
                                       Qwen3.8-Flash-Next and are under this license. They are downloaded
                                       separately from Hugging Face; the license is here for reference.

Not bundled: Microsoft Edge WebView2 Runtime (the app uses the one installed in Windows).
