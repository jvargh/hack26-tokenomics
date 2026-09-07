"""Builds the narrated demo video from the script and the silent screen capture.

    python tools/narrate_demo.py                 # generate audio + mux
    python tools/narrate_demo.py --check         # report fit only, write nothing
    python tools/narrate_demo.py --voice David   # pick a Windows voice
    python tools/narrate_demo.py --timings-only  # emit scene lengths for re-recording

Why per-scene audio rather than one long track: the recording holds each scene on
screen for a fixed number of seconds. A single continuous narration drifts a
little further out of sync with every scene. Generating one clip per scene and
placing it at that scene's exact start offset keeps the words on the right frames.

Narration text is read from `samples/DEMO-SCRIPT.md`, so the script stays the one
source of truth. Scene boundaries come from `demo-timings.json`, written by
`tests/browser/demo_recording.py`.

Audio uses the Windows speech synthesiser, which needs no installation. For a
submission-quality voice, record yourself or use a neural voice service and drop
the per-scene WAV files into the `narration/` directory before re-running.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import wave
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT_MD = REPO / "tokenos" / "samples" / "DEMO-SCRIPT.md"

# A scene's narration needs a little air at each end, or the first word lands on
# the previous scene's last frame.
LEAD_IN_SECONDS = 0.6
TAIL_SECONDS = 0.4


def fail(message: str):
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def parse_narration(markdown: Path) -> list[tuple[str, str]]:
    """Returns [(scene title, spoken text)] in script order.

    Only blockquote lines are spoken. Stage directions (`**Cue:** ...`) and
    everything outside a scene section are ignored.
    """
    if not markdown.exists():
        fail(f"script not found: {markdown}")

    scenes: list[tuple[str, list[str]]] = []
    in_scene = False
    for raw in markdown.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        heading = re.match(r"^##\s+Scene\s+\d+\s*[\u2014-]\s*(.+?)\s*\(", line)
        if heading:
            scenes.append((heading.group(1), []))
            in_scene = True
            continue
        if line.startswith("## "):
            in_scene = False
            continue
        if in_scene and line.startswith(">"):
            spoken = line.lstrip("> ").strip()
            if spoken and not spoken.startswith("**Cue:"):
                scenes[-1][1].append(spoken)

    cleaned: list[tuple[str, str]] = []
    for title, lines in scenes:
        # Markdown emphasis is for the reader, not the speaker.
        text = " ".join(lines)
        text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
        text = re.sub(r"\*(.+?)\*", r"\1", text)
        text = text.replace("\u2014", ", ").replace("\u2013", "-")
        text = text.replace("\u2019", "'").replace("\u201c", "").replace("\u201d", "")
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            cleaned.append((title, text))
    return cleaned


def synthesise(text: str, destination: Path, voice: str, rate: int) -> None:
    """Windows speech synthesiser -> WAV. No third-party install required."""
    script = f"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$match = $s.GetInstalledVoices() | Where-Object {{ $_.VoiceInfo.Name -like '*{voice}*' }} | Select-Object -First 1
if ($match) {{ $s.SelectVoice($match.VoiceInfo.Name) }}
$s.Rate = {rate}
$s.SetOutputToWaveFile('{destination}')
$s.Speak([Console]::In.ReadToEnd())
$s.Dispose()
"""
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        input=text, capture_output=True, text=True, encoding="utf-8",
    )
    if result.returncode != 0 or not destination.exists():
        fail(f"speech synthesis failed: {result.stderr.strip() or 'no output produced'}")


def wav_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as handle:
        return handle.getnframes() / float(handle.getframerate())


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--demo-dir", default=str(REPO / "_bkp" / "demo"),
                        help="directory holding tokenos-demo.webm and demo-timings.json")
    parser.add_argument("--voice", default="Zira", help="Windows voice name fragment: Zira, David, Mark")
    parser.add_argument("--rate", type=int, default=-1,
                        help="-10 (slow) to 10 (fast); slightly slow reads better on demos")
    parser.add_argument("--check", action="store_true", help="report fit only; write no video")
    parser.add_argument("--timings-only", action="store_true",
                        help="print SCENE_SECONDS so the video can be re-paced to the narration")
    args = parser.parse_args()

    demo_dir = Path(args.demo_dir)
    timings_file = demo_dir / "demo-timings.json"
    video = demo_dir / "tokenos-demo.webm"

    narration = parse_narration(SCRIPT_MD)
    if not narration:
        fail("no narration found; expected blockquote lines under '## Scene N' headings")

    if not timings_file.exists():
        fail(f"{timings_file} not found. Record the video first:\n"
             "  pytest -c pytest-browser.ini tests/browser/demo_recording.py -q -s")
    scenes = json.loads(timings_file.read_text(encoding="utf-8"))["scenes"]

    if len(narration) != len(scenes):
        fail(f"script has {len(narration)} scenes but the recording has {len(scenes)}. "
             "Re-record, or align the script's scene headings.")

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg and not (args.check or args.timings_only):
        fail("ffmpeg not found on PATH. Install it (winget install Gyan.FFmpeg) or use --check.")

    audio_dir = demo_dir / "narration"
    audio_dir.mkdir(parents=True, exist_ok=True)

    print(f"Voice: {args.voice}   Rate: {args.rate}\n")
    clips: list[tuple[Path, float, dict, str]] = []
    overruns: list[str] = []

    for (title, text), scene in zip(narration, scenes):
        clip = audio_dir / f"{scene['scene']}.wav"
        synthesise(text, clip, args.voice, args.rate)
        spoken = wav_seconds(clip)
        window = scene["endSeconds"] - scene["startSeconds"]
        needed = spoken + LEAD_IN_SECONDS + TAIL_SECONDS
        fits = needed <= window
        print(f"  [{'ok ' if fits else 'OVER'}] {scene['scene']:<22} "
              f"{spoken:5.1f}s spoken / {window:5.1f}s on screen   {title}")
        if not fits:
            overruns.append(f"{scene['scene']} needs {needed:.1f}s but has {window:.1f}s")
        clips.append((clip, spoken, scene, title))

    if args.timings_only:
        print("\nPaste into tests/browser/demo_recording.py so the video paces itself:\n")
        print("SCENE_SECONDS = {")
        for _clip, spoken, scene, _title in clips:
            print(f'    "{scene["scene"]}": {int(spoken + LEAD_IN_SECONDS + TAIL_SECONDS) + 1},')
        print("}")
        return 0

    if overruns:
        print("\nNarration does not fit the recording:")
        for item in overruns:
            print(f"  - {item}")
        print("\nFix it one of two ways, and prefer the first:")
        print("  1. Re-pace the video to the narration (best sync):")
        print("       python tools/narrate_demo.py --timings-only")
        print("     then update SCENE_SECONDS and re-record.")
        print("  2. Shorten that scene's narration in samples/DEMO-SCRIPT.md.")
        print("\nNot doing: speeding the audio up to fit. It sounds rushed.")
        if not args.check:
            return 2

    if args.check:
        print("\nCheck only; nothing written.")
        return 0 if not overruns else 2

    if not video.exists():
        fail(f"{video} not found. Record the video first.")

    # Place each clip at its scene's start offset, then mix into one track. This
    # is what keeps the words on the right frames.
    inputs: list[str] = []
    filters: list[str] = []
    for index, (clip, _spoken, scene, _title) in enumerate(clips):
        inputs += ["-i", str(clip)]
        delay_ms = int((scene["startSeconds"] + LEAD_IN_SECONDS) * 1000)
        filters.append(f"[{index}:a]adelay={delay_ms}|{delay_ms},aresample=48000[a{index}]")
    mix = "".join(f"[a{i}]" for i in range(len(clips)))
    filters.append(f"{mix}amix=inputs={len(clips)}:normalize=0:dropout_transition=0[out]")

    track = demo_dir / "narration.m4a"
    subprocess.run(
        [ffmpeg, "-y", *inputs, "-filter_complex", ";".join(filters),
         "-map", "[out]", "-c:a", "aac", "-b:a", "192k", str(track)],
        check=True, capture_output=True,
    )

    final = demo_dir / "tokenos-demo-narrated.mp4"
    subprocess.run(
        [ffmpeg, "-y", "-i", str(video), "-i", str(track),
         # The screen capture is VP8/VP9; re-encode once to H.264 so the result
         # plays anywhere a submission might be opened.
         "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "192k", "-shortest", str(final)],
        check=True, capture_output=True,
    )

    size_mb = final.stat().st_size / (1024 * 1024)
    print(f"\nNarrated video: {final}  ({size_mb:.1f} MB)")
    print(f"Audio track:    {track}")
    print(f"Per-scene WAVs: {audio_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
