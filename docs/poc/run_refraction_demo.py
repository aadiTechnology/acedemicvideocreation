"""Refraction lesson with built-in animated illustrations, through the real chain (Academic API -> engine -> worker -> MP4).
Needs the same setup as run_poc.py.   python docs/poc/run_refraction_demo.py"""
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_poc as R  # noqa: E402

SAMPLE = Path(__file__).resolve().parents[1] / "user-guide" / "sample" / "refraction"
OUT = Path(__file__).resolve().parent / "results-refraction"
OUT.mkdir(exist_ok=True)

c = R.call("POST", "/classes", json={"name": "Class 10"})
s = R.call("POST", "/subjects", json={"class_id": c["id"], "name": "Science"})
ch = R.call("POST", "/chapters", json={"subject_id": s["id"], "number": 10, "title": "Light: Reflection and Refraction"})
t = R.call("POST", "/topics", json={"chapter_id": ch["id"], "title": "Refraction of light"})
lesson = R.call("POST", "/lessons", json={"topic_id": t["id"], "title": "Refraction of light", "expected_duration_minutes": 3, "languages": ["en-IN"]})
vid = lesson["versions"][0]["id"]
files = [("files", ("lesson.csv", (SAMPLE / "lesson.csv").read_bytes(), "text/csv")),
         ("files", ("lesson_plan.json", (SAMPLE / "lesson_plan.json").read_bytes(), "application/json"))]
imp = R.http.post(f"/lesson-versions/{vid}/import", files=files)
assert imp.status_code == 200, imp.text
print("import warnings:", [w["code"] for w in imp.json()["warnings"]])
R.call("POST", f"/lesson-versions/{vid}/review", json={"action": "submit"})
R.call("POST", f"/lesson-versions/{vid}/review", json={"action": "approve", "note": "Demo"})
job = R.call("POST", f"/lesson-versions/{vid}/video", json={"provider": "colab", "profile": "1080p24", "subtitles": True, "style": "animated"})["job"]
batch = R.call("GET", f"/video-jobs/{job['id']}/narration-batch")
zip_bytes, durs = R.audio_zip(batch, "en-IN", Path(tempfile.mkdtemp()))
up = R.http.post(f"/video-jobs/{job['id']}/audio", files={"audio": ("narration_audio.zip", zip_bytes, "application/zip")})
assert up.status_code == 200, up.text
R.run_worker()
summary = R.call("GET", f"/lesson-versions/{vid}/video")
assert summary["job"]["state"] == "succeeded", summary["job"]
mp4 = OUT / "refraction-animated.mp4"
mp4.write_bytes(R.http.get(f"/video-jobs/{summary['job']['id']}/download").content)
info = R.probe(mp4)
print({k: info[k] for k in ("duration_s", "resolution", "fps", "video_codec", "has_audio", "decode_errors", "size_mb")})

# frames across the first illustration slide (slide 3): one per stage, to check the animation visually
start3 = sum(durs[:2])
times = [start3 + durs[2] * f for f in (0.06, 0.2, 0.36, 0.52, 0.68, 0.9)]
tiles = []
for i, tm in enumerate(times):
    png = OUT / f"_t{i}.png"
    subprocess.run([R.FFMPEG, "-y", "-ss", f"{tm:.2f}", "-i", str(mp4), "-frames:v", "1", "-vf", "scale=960:-1", str(png)], check=True, capture_output=True)
    tiles.append(Image.open(png).convert("RGB"))
w, h = tiles[0].size
sheet = Image.new("RGB", (w * 2, h * 3))
for i, tile in enumerate(tiles):
    sheet.paste(tile, ((i % 2) * w, (i // 2) * h))
sheet.save(OUT / "slide3-stages.png")
for p in OUT.glob("_t*.png"):
    p.unlink()
R.contact_sheet(mp4, [sum(durs[:i]) for i in range(len(durs))], durs, OUT / "contact.png") if len(durs) == 10 else None
print("saved", OUT)
