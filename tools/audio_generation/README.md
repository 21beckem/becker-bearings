# Pre-deployment audio generation

This folder contains the optional build-time tools for generating fixed speech
clips with Kokoro. They are separate from the live application environment.

The live application does not need Kokoro, `soundfile`, or any other package in
this folder. Do not add these dependencies to `src/requirements.py` or
`activate.bat`.

## What this produces

The generator reads [`catalog.json`](catalog.json) and writes one WAV file per
phrase plus a `manifest.json`. By default, output goes to
`src/assets/audio/`, which is the eventual runtime asset location.

The generated files are 24 kHz, mono, 16-bit PCM WAV files. Boundary silence
is trimmed automatically while preserving a short natural buffer, so composed
settings parts can play together without long pauses. The files are intended
to be preloaded and played immediately by the live audio service later.

## One-time setup on a new Windows computer

Prerequisites:

- Windows 10 or newer
- Python 3.12, 3.11, or 3.10 available as `python3.12`, `python3.11`,
  `python3.10`, or `python`
- Internet access for installing packages and downloading Kokoro assets

From the repository root:

```bat
tools\audio_generation\setup.bat
```

This creates `tools\audio_generation\.venv`, an isolated environment used
only by these generation tools. It does not modify the live application's
`.venv`. The script prefers Python 3.12, then 3.11, then 3.10. Python 3.13
is not supported by Kokoro's current dependency chain because `misaki` does
not publish a compatible package for it.

If `uv` is installed, the setup uses it only to create and seed the isolated
environment when the selected Python installation does not include the normal
`venv` bootstrap tools. `uv` is not a required live-application dependency;
an ordinary Python 3.12/3.11/3.10 installation works without it.

The setup installs Kokoro 0.9.4 and `soundfile` in the compatible Python
environment. It deliberately
does not install eSpeak NG or require an MSI. Kokoro's American-English Misaki
path can generate the project's ordinary fixed phrases without that optional
fallback. If a phrase contains an unusual word that is skipped or
mispronounced, add a Kokoro pronunciation hint to that phrase or install
eSpeak NG separately and rerun generation. The official Windows installation
uses an eSpeak NG MSI:

<https://github.com/espeak-ng/espeak-ng/releases>

That optional dependency is intentionally documented here rather than hidden
inside the live application's setup.

If setup previously created a failed Python 3.13 environment, running
`setup.bat` again will rebuild only `tools\audio_generation\.venv` with the
compatible Python installation.

## Generate the clips

Edit `catalog.json`, then run:

```bat
tools\audio_generation\generate.bat
```

The first generation downloads the Kokoro model and the selected voice from
Hugging Face. Later runs reuse the local Hugging Face cache. The generated WAV
files and `manifest.json` are written to `src/assets/audio/`.

To use another voice listed by Kokoro:

```bat
tools\audio_generation\generate.bat --voice af_heart
```

To regenerate every clip:

```bat
tools\audio_generation\generate.bat --force
```

The generator normally skips unchanged phrases by comparing their text,
language, voice, and speed fingerprint in `manifest.json`.

## Catalog format

Each phrase needs a stable ID and the exact text to synthesize:

```json
{
  "language": "a",
  "voice": "af_bella",
  "speed": 1.0,
  "phrases": [
    {
      "id": "menu.settings",
      "type": "MenuOption",
      "concatenate": false,
      "text": "Settings"
    }
  ]
}
```

`type` is one of `LensEntry`, `MenuOption`, `Instruction`, or `Error`. It is
copied into the generated manifest so each recording retains its queue type.

Set `concatenate` to `true` for clips that will be played directly beside
other clips, such as settings audio parts. Those clips have both leading and
trailing silence trimmed. Standalone clips default to `false`: only leading
silence is trimmed, preserving a small natural pause after the message.

`language: "a"` is American English. The voice and language must match. IDs
may contain letters, numbers, periods, hyphens, and underscores; they become
WAV filenames.

## Reproducibility and distribution

Keep the catalog, selected voice, Kokoro version, and generated manifest
together. If generated audio is committed or distributed, also include the
applicable Kokoro and voice-model license notices. Kokoro and the Kokoro model
are Apache-2.0, but dependencies and optional pronunciation tools have their
own licenses.

The live application may continue using its current runtime TTS for text that
cannot be known ahead of deployment. Kokoro is used here only to create fixed
assets before deployment.
