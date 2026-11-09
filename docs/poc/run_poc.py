"""Sprint 7 POC: three Class 7 Science videos (English, Hindi, Marathi) through the real Academic API and the real Video Engine.

Needs: Academic API on :8100 (AUTH_MODE=dev, VIDEO_ENGINE_URL/KEY set), engine API container on :18000, the engine image
`aadi-video-engine:test` for the worker, and Python with httpx + Pillow + imageio-ffmpeg.   python docs/poc/run_poc.py

Narration: English uses the free Windows voice (Zira). Hindi and Marathi have no local voice here, so they get SILENT PLACEHOLDER
audio timed from the text length. Those two videos validate the pipeline, slides and captions, NOT pronunciation or audio sync.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import httpx
import imageio_ffmpeg
from PIL import Image

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "results"
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
API = "http://localhost:8100/api"
ENGINE_DB = os.environ.get("ENGINE_WORKER_DB", "postgresql://postgres:postgres@host.docker.internal:15441/engine_docker")
LANGS = {"en-IN": "English", "hi-IN": "Hindi", "mr-IN": "Marathi"}
ALL = {"X-Dev-Roles": "admin"}
http = httpx.Client(base_url=API, timeout=120, headers=ALL)


def call(method, path, **kw):
    r = http.request(method, path, **kw)
    if r.status_code >= 400:
        raise SystemExit(f"{method} {path} -> {r.status_code} {r.text[:400]}")
    return r.json() if r.content else None


def seconds_for(text: str) -> float:
    return max(3.0, len(text) / 13.0)  # about 13 characters per second of speech


def silent_mp3(path: Path, seconds: float) -> None:
    subprocess.run([FFMPEG, "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", f"{seconds:.2f}", "-q:a", "9", str(path)], check=True, capture_output=True)


def windows_voice_mp3(text: str, path: Path) -> None:
    wav = Path(str(path) + ".wav")
    script = ("Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; $s.SelectVoice('Microsoft Zira Desktop'); "
              "$s.Rate = -1; $s.SetOutputToWaveFile($env:POC_WAV); $s.Speak($env:POC_TEXT); $s.Dispose()")
    subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True, env={**os.environ, "POC_WAV": str(wav), "POC_TEXT": text}, capture_output=True)
    subprocess.run([FFMPEG, "-y", "-i", str(wav), "-q:a", "4", str(path)], check=True, capture_output=True)
    wav.unlink(missing_ok=True)


def duration(path: Path) -> float:
    err = subprocess.run([FFMPEG, "-i", str(path)], capture_output=True, text=True).stderr
    h, m, s = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err).groups()
    return int(h) * 3600 + int(m) * 60 + float(s)


def audio_zip(batch: dict, lang: str, workdir: Path) -> tuple[bytes, list[float]]:
    durations = []
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for item in batch["slides"]:
            mp3 = workdir / f"{item['slide']:02d}.mp3"
            if lang == "en-IN":
                windows_voice_mp3(item["text"], mp3)
            else:
                silent_mp3(mp3, seconds_for(item["text"]))
            durations.append(duration(mp3))
            zf.write(mp3, mp3.name)
    return buf.getvalue(), durations


def run_worker() -> None:
    subprocess.run(["docker", "run", "--rm", "-v", "engine-test-data:/data", "-e", f"ENGINE_DATABASE_URL={ENGINE_DB}", "aadi-video-engine:test",
                    "python", "-m", "engine.worker", "--once"], check=True, capture_output=True, timeout=1800)


def decoded_md5(path: Path, stream: str) -> str:
    out = subprocess.run([FFMPEG, "-v", "error", "-i", str(path), "-map", stream, "-f", "md5", "-"], capture_output=True, text=True)
    return out.stdout.strip()


def probe(path: Path) -> dict:
    err = subprocess.run([FFMPEG, "-v", "error", "-i", str(path), "-f", "null", "-"], capture_output=True, text=True).stderr.strip()
    info = subprocess.run([FFMPEG, "-i", str(path)], capture_output=True, text=True).stderr
    size = re.search(r"Video: (\w+).*?(\d{3,4}x\d{3,4}).*?(\d+(?:\.\d+)?) fps", info, re.S)
    return {"duration_s": round(duration(path), 2), "video_codec": size.group(1), "resolution": size.group(2), "fps": float(size.group(3)),
            "has_audio": "Audio:" in info, "decode_errors": err.splitlines()[:3], "size_mb": round(path.stat().st_size / 1048576, 2),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def contact_sheet(video: Path, starts: list[float], durs: list[float], target: Path) -> None:
    """One frame from the middle of each slide's audio window; the on-screen counter must match the slide number."""
    tiles = []
    for i, (s, d) in enumerate(zip(starts, durs), 1):
        png = target.parent / f"_f{i}.png"
        subprocess.run([FFMPEG, "-y", "-ss", f"{s + d / 2:.2f}", "-i", str(video), "-frames:v", "1", "-vf", "scale=640:-1", str(png)], check=True, capture_output=True)
        tiles.append(Image.open(png).convert("RGB"))
    w, h = tiles[0].size
    sheet = Image.new("RGB", (w * 2, h * 5))
    for i, t in enumerate(tiles):
        sheet.paste(t, ((i % 2) * w, (i // 2) * h))
    sheet.save(target)
    for png in target.parent.glob("_f*.png"):
        png.unlink()


def main() -> None:
    OUT.mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp())
    c = call("POST", "/classes", json={"name": "Class 7"})
    s = call("POST", "/subjects", json={"class_id": c["id"], "name": "Science"})
    ch = call("POST", "/chapters", json={"subject_id": s["id"], "number": 1, "title": "Nutrition in Plants"})
    t = call("POST", "/topics", json={"chapter_id": ch["id"], "title": "Photosynthesis"})
    lesson = call("POST", "/lessons", json={"topic_id": t["id"], "title": "How plants make food: photosynthesis", "expected_duration_minutes": 5,
                                            "learning_objectives": ["Define photosynthesis"], "languages": list(LANGS)})
    versions = {v["language"]: v["id"] for v in lesson["versions"]}
    results: dict[str, dict] = {}
    audio_cache: dict[str, tuple[bytes, list[float]]] = {}

    for lang, vid in versions.items():
        folder = ROOT / lang
        files = [("files", ("lesson.csv", (folder / "lesson.csv").read_bytes(), "text/csv")),
                 ("files", ("lesson_plan.json", (folder / "lesson_plan.json").read_bytes(), "application/json"))]
        imp = http.post(f"/lesson-versions/{vid}/import", files=files)
        assert imp.status_code == 200, imp.text
        call("POST", f"/lesson-versions/{vid}/review", json={"action": "submit"})
        call("POST", f"/lesson-versions/{vid}/review", json={"action": "approve", "note": "POC: approved for pipeline validation (not yet reviewed by a subject expert)."})
        gen = call("POST", f"/lesson-versions/{vid}/video", json={"provider": "colab", "profile": "1080p24", "subtitles": True})
        job = gen["job"]
        assert job["state"] == "awaiting_audio", job
        batch = call("GET", f"/video-jobs/{job['id']}/narration-batch")
        zip_bytes, durs = audio_zip(batch, lang, work)
        audio_cache[lang] = (zip_bytes, durs)
        up = http.post(f"/video-jobs/{job['id']}/audio", files={"audio": ("narration_audio.zip", zip_bytes, "application/zip")})
        assert up.status_code == 200, up.text
        run_worker()
        summary = call("GET", f"/lesson-versions/{vid}/video")
        assert summary["job"]["state"] == "succeeded", summary["job"]
        target = OUT / f"photosynthesis-{lang}.mp4"
        target.write_bytes(http.get(f"/video-jobs/{summary['job']['id']}/download").content)
        starts = [sum(durs[:i]) for i in range(len(durs))]
        info = probe(target)
        info.update({"language": LANGS[lang], "slides": len(durs), "narration_total_s": round(sum(durs), 1), "job_id": summary["job"]["id"],
                     "version_id": vid, "narration": "Windows voice (Zira), test voice" if lang == "en-IN" else "SILENT PLACEHOLDER (no local voice)",
                     "warnings": [w["message"] for w in imp.json()["warnings"]]})
        contact_sheet(target, starts, durs, OUT / f"contact-{lang}.png")
        results[lang] = info
        print(lang, info["duration_s"], "s", info["resolution"], "decode errors:", info["decode_errors"], flush=True)

    # reproducibility: render the English version again from the same package and the same audio
    vid = versions["en-IN"]
    again = call("POST", f"/lesson-versions/{vid}/video", json={"provider": "colab", "profile": "1080p24", "subtitles": True, "rerender": True})["job"]
    http.post(f"/video-jobs/{again['id']}/audio", files={"audio": ("narration_audio.zip", audio_cache["en-IN"][0], "application/zip")})
    run_worker()
    second = call("GET", f"/lesson-versions/{vid}/video")["job"]
    assert second["state"] == "succeeded" and second["id"] == again["id"], second
    second_file = OUT / "photosynthesis-en-IN-rerender.mp4"
    second_file.write_bytes(http.get(f"/video-jobs/{second['id']}/download").content)
    first_file = OUT / "photosynthesis-en-IN.mp4"
    repro = {"video_frames_identical": decoded_md5(first_file, "0:v:0") == decoded_md5(second_file, "0:v:0"),
             "audio_identical": decoded_md5(first_file, "0:a:0") == decoded_md5(second_file, "0:a:0"),
             "file_bytes_identical": first_file.read_bytes() == second_file.read_bytes()}
    results["reproducibility_english"] = repro
    (OUT / "poc_results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(repro))


if __name__ == "__main__":
    sys.exit(main())
