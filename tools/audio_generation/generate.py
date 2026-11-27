"""Generate pre-deployment WAV assets with Kokoro."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys


SAMPLE_RATE = 24_000
KOKORO_VERSION = "0.9.4"
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--catalog",
        type=Path,
        default=Path(__file__).with_name("catalog.json"),
        help="JSON phrase catalog (default: catalog.json)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="directory for WAV files and manifest.json",
    )
    parser.add_argument("--voice", help="override the catalog voice")
    parser.add_argument("--language", help="override the catalog language")
    parser.add_argument("--speed", type=float, help="override the catalog speed")
    parser.add_argument(
        "--force",
        action="store_true",
        help="regenerate files even when their catalog entry is unchanged",
    )
    return parser.parse_args()


def load_catalog(path):
    with path.open(encoding="utf-8") as stream:
        catalog = json.load(stream)
    phrases = catalog.get("phrases")
    if not isinstance(phrases, list) or not phrases:
        raise ValueError("catalog must contain a non-empty 'phrases' list")

    seen = set()
    for phrase in phrases:
        phrase_id = phrase.get("id")
        text = phrase.get("text")
        if not isinstance(phrase_id, str) or not _SAFE_ID.fullmatch(phrase_id):
            raise ValueError(
                f"invalid phrase id {phrase_id!r}; use letters, numbers, '.', '_' or '-'")
        if phrase_id in seen:
            raise ValueError(f"duplicate phrase id: {phrase_id}")
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"phrase {phrase_id!r} must have non-empty text")
        seen.add(phrase_id)
    return catalog


def generate_phrase(pipeline, text, voice, speed):
    import numpy as np

    chunks = []
    for result in pipeline(text, voice=voice, speed=speed, split_pattern=r"\n+"):
        # Kokoro 0.7.x exposes each result as (graphemes, phonemes, audio),
        # while newer releases also provide an ``audio`` property.
        audio = getattr(result, "audio", None)
        if audio is None:
            audio = result[2]
        if audio is not None:
            if hasattr(audio, "detach"):
                audio = audio.detach().cpu().numpy()
            chunks.append(np.asarray(audio))
    if not chunks:
        raise RuntimeError(f"Kokoro produced no audio for {text!r}")
    return np.concatenate(chunks)


def main():
    args = parse_args()
    catalog_path = args.catalog.resolve()
    catalog = load_catalog(catalog_path)
    voice = args.voice or catalog.get("voice", "af_bella")
    language = args.language or catalog.get("language", voice[0])
    speed = args.speed if args.speed is not None else catalog.get("speed", 1.0)
    if speed <= 0:
        raise ValueError("speed must be greater than zero")

    output_dir = (args.output or Path(__file__).parents[2] / "src" / "assets" / "audio").resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "manifest.json"
    old_manifest = {}
    if manifest_path.exists() and not args.force:
        with manifest_path.open(encoding="utf-8") as stream:
            old_manifest = json.load(stream)

    try:
        from kokoro import KPipeline
        import soundfile as sf
    except ImportError as error:
        raise SystemExit(
            "Audio-generation dependencies are missing. Run setup.bat first."
        ) from error

    print(f"Loading Kokoro ({language=}, {voice=}, {speed=})...")
    pipeline = KPipeline(lang_code=language)
    entries = []
    for phrase in catalog["phrases"]:
        phrase_id = phrase["id"]
        text = phrase["text"]
        filename = f"{phrase_id}.wav"
        destination = output_dir / filename
        fingerprint = hashlib.sha256(
            json.dumps(
                {"text": text, "language": language, "voice": voice, "speed": speed},
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        previous = next(
            (entry for entry in old_manifest.get("phrases", []) if entry["id"] == phrase_id),
            None,
        )
        if (not args.force and previous and previous.get("fingerprint") == fingerprint
                and destination.exists()):
            print(f"Keeping {filename}")
        else:
            print(f"Generating {filename}: {text}")
            audio = generate_phrase(pipeline, text, voice, speed)
            sf.write(destination, audio, SAMPLE_RATE, subtype="PCM_16", format="WAV")
        entries.append({
            "id": phrase_id,
            "type": phrase.get("type", ""),
            "text": text,
            "file": filename,
            "fingerprint": fingerprint,
        })

    manifest = {
        "format": 1,
        "engine": "kokoro",
        "engine_version": KOKORO_VERSION,
        "language": language,
        "voice": voice,
        "speed": speed,
        "sample_rate": SAMPLE_RATE,
        "channels": 1,
        "sample_format": "PCM_16",
        "phrases": entries,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(entries)} phrases to {output_dir}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Audio generation failed: {error}", file=sys.stderr)
        raise
