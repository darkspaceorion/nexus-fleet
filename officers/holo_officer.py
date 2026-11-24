"""Holo Officer: image generation through ComfyUI (Z-Image Turbo), plus a code-made hologram animation.

  python officers/holo_officer.py "prompt" [--name nexus-portrait] [--animate] [--seed 123]

Needs ComfyUI running on config comfyui_host. The workflow is built from the bundled Z-Image Turbo
int8 template settings (8 steps, cfg 1, res_multistep/simple, AuraFlow shift 3).
"""
import argparse
import io
import random
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fleet_lib import NEXUS_ROOT, Ollama, load_config, slugify  # noqa: E402

OUT_DIR = NEXUS_ROOT / "Inbox" / "holo"  # hand-run output; roster jobs use config officers.holo.output_dir


def workflow(prompt, seed, width=1024, height=1024, face=None):
    """face = name of an image already uploaded to ComfyUI; if set, ReActor swaps that face in after drawing."""
    wf = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "z_image_turbo_int8_convrot.safetensors", "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen_3_4b_fp8_mixed.safetensors", "type": "lumina2", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "ae.safetensors"}},
        "4": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["1", 0], "shift": 3}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": prompt}},
        "6": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["5", 0]}},
        "7": {"class_type": "EmptySD3LatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
        "8": {"class_type": "KSampler", "inputs": {"model": ["4", 0], "positive": ["5", 0], "negative": ["6", 0],
                                                   "latent_image": ["7", 0], "seed": seed, "steps": 8, "cfg": 1,
                                                   "sampler_name": "res_multistep", "scheduler": "simple", "denoise": 1}},
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["3", 0]}},
        "10": {"class_type": "SaveImage", "inputs": {"images": ["9", 0], "filename_prefix": "holo"}},
    }
    if face:
        # ReActor face swap (inswapper_128 + GFPGAN restore). inswapper is NON-COMMERCIAL: personal images only.
        wf["11"] = {"class_type": "LoadImage", "inputs": {"image": face}}
        wf["12"] = {"class_type": "ReActorFaceSwap", "inputs": {
            "enabled": True, "input_image": ["9", 0], "source_image": ["11", 0],
            "swap_model": "inswapper_128.onnx", "facedetection": "retinaface_resnet50",
            "face_restore_model": "GFPGANv1.4.pth", "face_restore_visibility": 1, "codeformer_weight": 0.5,
            "detect_gender_input": "no", "detect_gender_source": "no",
            "input_faces_index": "0", "source_faces_index": "0", "console_log_level": 1}}
        wf["10"]["inputs"]["images"] = ["12", 0]
    return wf


MOTION_NEGATIVE = ("blurry, distorted face, melting, morphing armour, extra limbs, extra fingers, flicker, jitter, "
                   "static frozen frame, text, watermark, subtitles, low quality")


def motion_workflow(still, motion, seed, w, h, frames=49, face=None):
    """Wan 2.2 TI2V 5B: animate an uploaded still from a short motion instruction. Optional ReActor per frame."""
    wf = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "wan2.2_ti2v_5B_fp16.safetensors", "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors", "type": "wan", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "wan2.2_vae.safetensors"}},
        "4": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["1", 0], "shift": 8}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": motion}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": MOTION_NEGATIVE}},
        "7": {"class_type": "LoadImage", "inputs": {"image": still}},
        "8": {"class_type": "Wan22ImageToVideoLatent", "inputs": {"vae": ["3", 0], "width": w, "height": h,
                                                                  "length": frames, "batch_size": 1, "start_image": ["7", 0]}},
        "9": {"class_type": "KSampler", "inputs": {"model": ["4", 0], "positive": ["5", 0], "negative": ["6", 0],
                                                   "latent_image": ["8", 0], "seed": seed, "steps": 20, "cfg": 5,
                                                   "sampler_name": "uni_pc", "scheduler": "simple", "denoise": 1}},
        "10": {"class_type": "VAEDecode", "inputs": {"samples": ["9", 0], "vae": ["3", 0]}},
        "13": {"class_type": "SaveImage", "inputs": {"images": ["10", 0], "filename_prefix": "holo-motion"}},
    }
    if face:
        wf["11"] = {"class_type": "LoadImage", "inputs": {"image": face}}
        wf["12"] = {"class_type": "ReActorFaceSwap", "inputs": {
            "enabled": True, "input_image": ["10", 0], "source_image": ["11", 0],
            "swap_model": "inswapper_128.onnx", "facedetection": "retinaface_resnet50",
            "face_restore_model": "GFPGANv1.4.pth", "face_restore_visibility": 1, "codeformer_weight": 0.5,
            "detect_gender_input": "no", "detect_gender_source": "no",
            "input_faces_index": "0", "source_faces_index": "0", "console_log_level": 1}}
        wf["13"]["inputs"]["images"] = ["12", 0]
    return wf


def run_workflow(cfg, wf, timeout=600):
    """Queue a workflow, wait, return every output image as bytes (in order)."""
    host = cfg["comfyui_host"].rstrip("/")
    r = requests.post(f"{host}/prompt", json={"prompt": wf}, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"ComfyUI refused the workflow: {r.text[:500]}")
    pid, t0 = r.json()["prompt_id"], time.time()
    while time.time() - t0 < timeout:
        hist = requests.get(f"{host}/history/{pid}", timeout=10).json()
        if pid in hist:
            entry = hist[pid]
            if entry.get("status", {}).get("status_str") == "error":
                raise RuntimeError(f"ComfyUI error: {str(entry['status'])[:500]}")
            if entry.get("status", {}).get("completed"):
                imgs = [img for node in entry.get("outputs", {}).values() for img in node.get("images", [])]
                return [requests.get(f"{host}/view", params=img, timeout=60).content for img in imgs]
        time.sleep(2)
    raise TimeoutError("workflow not finished in time")


def make_motion(cfg, png_path, motion, seed, face, out_stem, log, frames=49, fps=24, long_side=832):
    """Animate a finished still. Writes <stem>-motion.gif and .mp4 next to it. Returns (gif, mp4, seconds)."""
    import shutil
    import subprocess
    import tempfile
    from PIL import Image

    im = Image.open(png_path)
    s = long_side / max(im.size)
    w, h = (max(32, round(d * s / 32) * 32) for d in im.size)
    still = upload_face(cfg, png_path)  # same upload call works for any image
    t0 = time.time()
    data = run_workflow(cfg, motion_workflow(still, motion, seed, w, h, frames, face), timeout=1800)
    secs = round(time.time() - t0)
    if len(data) < frames // 2:
        raise RuntimeError(f"motion returned {len(data)} frames, wanted {frames}")
    gif, mp4 = out_stem.with_name(out_stem.name + "-motion.gif"), out_stem.with_name(out_stem.name + "-motion.mp4")
    pics = [Image.open(io.BytesIO(d)).convert("RGB") for d in data]
    pics[0].save(gif, save_all=True, append_images=pics[1:], duration=round(1000 / fps), loop=0, optimize=True)
    if shutil.which("ffmpeg"):
        with tempfile.TemporaryDirectory() as td:
            for i, p in enumerate(pics):
                p.save(Path(td) / f"f{i:04d}.png")
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps), "-i", str(Path(td) / "f%04d.png"),
                            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", str(mp4)], check=True)
    else:
        mp4 = None
    log(f"motion {len(pics)} frames {w}x{h} in {secs}s -> {gif.name}")
    return gif, mp4, secs


def upload_face(cfg, path):
    """Send a reference face photo to ComfyUI's input folder; returns the name LoadImage uses."""
    path = Path(path)
    if not path.is_absolute():
        path = NEXUS_ROOT / path
    with open(path, "rb") as f:
        r = requests.post(f"{cfg['comfyui_host'].rstrip('/')}/upload/image",
                          files={"image": (path.name, f, "image/png")}, data={"overwrite": "true"}, timeout=30)
    r.raise_for_status()
    return r.json()["name"]


def generate(cfg, prompt, seed=None):
    oc = cfg["officers"]["holo"]
    return generate_sized(cfg, prompt, seed, oc["width"], oc["height"])


def hologram_gif(png_bytes, out_path, frames=40, size=560):
    """Turn a still into a looping hologram: slow drift, cyan tint, moving scanlines, flicker, glitch lines."""
    from PIL import Image, ImageChops, ImageEnhance

    src = Image.open(io.BytesIO(png_bytes)).convert("RGB").resize((size, size), Image.LANCZOS)
    tint = Image.new("RGB", src.size, (40, 200, 255))
    base = ImageChops.multiply(ImageEnhance.Color(src).enhance(0.35), tint)
    base = Image.blend(base, src, 0.35)
    rng = random.Random(7)
    out = []
    for i in range(frames):
        phase = i / frames
        zoom = 1.0 + 0.035 * (0.5 - 0.5 * __import__("math").cos(2 * 3.14159 * phase))
        w = int(size * zoom)
        fr = base.resize((w, w), Image.LANCZOS)
        off = (w - size) // 2
        fr = fr.crop((off, off, off + size, off + size))
        px = fr.load()
        shift = int(phase * 8)
        for y in range(0, size):  # scanlines that roll down
            if (y + shift) % 4 == 0:
                for x in range(0, size, 1):
                    r, g, b = px[x, y]
                    px[x, y] = (r // 2, g // 2, b // 2)
        if rng.random() < 0.18:  # glitch band
            y0 = rng.randint(0, size - 20)
            band = fr.crop((0, y0, size, y0 + rng.randint(4, 16)))
            fr.paste(band, (rng.randint(-14, 14), y0))
        fr = ImageEnhance.Brightness(fr).enhance(0.85 + 0.25 * rng.random())
        out.append(fr.convert("P", palette=Image.ADAPTIVE, colors=128))
    out[0].save(out_path, save_all=True, append_images=out[1:], duration=70, loop=0, optimize=True)


# ------------------------------------------------------------ duty roster hooks

_proc = None  # ComfyUI process we started ourselves (None if it was already running)


def comfy_up(cfg):
    try:
        return requests.get(f"{cfg['comfyui_host'].rstrip('/')}/system_stats", timeout=3).ok
    except requests.RequestException:
        return False


def ensure_comfy(cfg, log):
    """Start ComfyUI headless if it isn't running. Local only (127.0.0.1), no browser."""
    global _proc
    if comfy_up(cfg):
        return
    import subprocess
    oc = cfg["officers"]["holo"]
    root = Path(oc["comfyui_dir"])
    port = cfg["comfyui_host"].rstrip("/").rsplit(":", 1)[-1]
    log_file = open(Path(__file__).resolve().parents[1] / "roster" / "comfyui.log", "a", encoding="utf-8")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    _proc = subprocess.Popen([str(root / oc["comfyui_python"]), "-s", "ComfyUI/main.py", "--windows-standalone-build",
                              "--listen", "127.0.0.1", "--port", port, "--disable-auto-launch"],
                             cwd=root, stdout=log_file, stderr=subprocess.STDOUT, creationflags=flags)
    log(f"starting ComfyUI (pid {_proc.pid})")
    t0 = time.time()
    while time.time() - t0 < oc["startup_timeout_seconds"]:
        if _proc.poll() is not None:
            raise RuntimeError(f"ComfyUI exited on startup (code {_proc.returncode}); see roster/comfyui.log")
        if comfy_up(cfg):
            log(f"ComfyUI ready in {round(time.time() - t0)}s")
            return
        time.sleep(2)
    raise TimeoutError("ComfyUI did not start in time; see roster/comfyui.log")


def shutdown(cfg, log):
    """Called by the roster when the queue is empty: free VRAM, stop ComfyUI if we started it."""
    global _proc
    try:
        requests.post(f"{cfg['comfyui_host'].rstrip('/')}/free", json={"unload_models": True, "free_memory": True}, timeout=5)
    except requests.RequestException:
        pass
    if _proc and _proc.poll() is None:
        _proc.terminate()
        try:
            _proc.wait(timeout=20)
        except Exception:  # noqa: BLE001
            _proc.kill()
        log("ComfyUI stopped, GPU free")
    _proc = None


def run(job, cfg, log):
    """Roster entry point. Job fields: brief (the prompt), count, width, height, seed, animate."""
    from PIL import Image

    oc = cfg["officers"]["holo"]
    out_dir = NEXUS_ROOT / oc["output_dir"]
    out_dir.mkdir(parents=True, exist_ok=True)
    w, h = int(job.get("width") or oc["width"]), int(job.get("height") or oc["height"])
    if w % 16 or h % 16 or not (256 <= w <= 2048 and 256 <= h <= 2048):
        raise ValueError(f"size {w}x{h} not allowed: use 256-2048, multiples of 16")
    count = max(1, min(int(job.get("count", 1)), oc["max_count"]))
    risky = prompt_risks(job["brief"])
    if risky:
        log(f"prompt has risky words {risky}; see officers/holo-officer.md")
    first_seed = job.get("seed")
    ensure_comfy(cfg, log)
    face = upload_face(cfg, job["face"]) if job.get("face") else None
    if face:
        log(f"face swap on, reference {job['face']}")
    t0, images, problems = time.time(), [], []
    stem = f"{datetime.now():%Y-%m-%d-%H%M}-{slugify(job.get('name') or job['brief'], 30)}"
    for i in range(count):
        seed = (int(first_seed) + i) if first_seed is not None else None
        data, used_seed, secs = generate_sized(cfg, job["brief"], seed, w, h, face)
        path = out_dir / f"{stem}-{i + 1}.png"
        path.write_bytes(data)
        # gate: real image, right size, not blank
        try:
            im = Image.open(path)
            ok_size = im.size == (w, h)
            lo, hi = im.convert("L").getextrema()
            if not ok_size:
                problems.append(f"{path.name}: size {im.size}, wanted {(w, h)}")
            if hi - lo < 20:
                problems.append(f"{path.name}: looks blank (contrast {hi - lo})")
        except Exception as e:  # noqa: BLE001
            problems.append(f"{path.name}: unreadable ({e})")
        entry = {"file": path, "seed": used_seed, "seconds": secs}
        if job.get("animate"):
            gif = path.with_name(path.stem + "-holo.gif")
            hologram_gif(data, gif)
            entry["gif"] = gif
        if job.get("motion"):
            try:
                secs_wanted = float(job.get("motion_seconds") or 2)
                n_frames = int(round(secs_wanted * 24 / 4)) * 4 + 1  # Wan wants 4k+1 frames
                entry["motion_gif"], entry["motion_mp4"], _ = make_motion(
                    cfg, path, job["motion"], used_seed % 2**32, face, path.with_suffix(""), log, frames=n_frames)
            except Exception as e:  # noqa: BLE001
                problems.append(f"{path.name}: motion failed ({e})")
        images.append(entry)
        log(f"image {i + 1}/{count} seed {used_seed} in {secs}s -> {path.name}")
    if risky:
        problems.append(f"prompt uses words that make the model draw fake text or web pages: {risky}")
    return {"images": images, "size": (w, h), "gate": {"passed": not problems, "problems": problems},
            "stats": {"seconds": round(time.time() - t0), "model": "z-image-turbo int8"}}


def prompt_risks(prompt):
    """Banned words from officers/holo-officer.md that appear in the prompt (whole words only)."""
    import re
    orders = (Path(__file__).resolve().parent / "holo-officer.md").read_text(encoding="utf-8")
    block = orders.split("## Banned words", 1)[-1].split("\n", 1)[-1]
    words = [w.strip().lower() for w in block.replace("\n", " ").split(",") if w.strip()]
    text = prompt.lower()
    return [w for w in words if re.search(rf"\b{re.escape(w)}\b", text)]


def generate_sized(cfg, prompt, seed, w, h, face=None):
    host = cfg["comfyui_host"].rstrip("/")
    llm = Ollama(cfg["ollama_host"])
    try:
        for m in llm.loaded():
            llm.unload(m)
    except requests.RequestException:
        pass
    seed = seed if seed is not None else random.randint(1, 2**48)
    r = requests.post(f"{host}/prompt", json={"prompt": workflow(prompt, seed, w, h, face)}, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"ComfyUI refused the workflow: {r.text[:500]}")
    pid, t0 = r.json()["prompt_id"], time.time()
    while time.time() - t0 < 600:
        hist = requests.get(f"{host}/history/{pid}", timeout=10).json()
        if pid in hist:
            entry = hist[pid]
            if entry.get("status", {}).get("status_str") == "error":
                raise RuntimeError(f"ComfyUI error: {str(entry['status'])[:500]}")
            for node in entry.get("outputs", {}).values():
                for img in node.get("images", []):
                    return requests.get(f"{host}/view", params=img, timeout=30).content, seed, round(time.time() - t0, 1)
        time.sleep(1)
    raise TimeoutError("image not ready in time")


def write_report(job, result, cfg):
    out_dir = NEXUS_ROOT / cfg["reports_dir"]
    out_dir.mkdir(parents=True, exist_ok=True)
    g, st = result["gate"], result["stats"]
    rel = lambda p: Path(p).relative_to(NEXUS_ROOT).as_posix()  # noqa: E731
    lines = [f"# Holo Officer report: {job['brief'][:80]}", "",
             "> **Status: needs NEXUS review.** Made by a local image model. Not checked yet.",
             f"> Gate: **{'PASSED' if g['passed'] else 'FAILED'}** - {len(result['images'])} image(s), "
             f"{result['size'][0]}x{result['size'][1]}, {len(g['problems'])} problems.",
             f"> Run: {st['model']}, {st['seconds']}s. Job `{job['id']}`.", "",
             "**Prompt:** " + job["brief"], ""]
    for i, im in enumerate(result["images"], 1):
        lines.append(f"{i}. `{rel(im['file'])}` (seed {im['seed']}, {im['seconds']}s)"
                     + (f" + animation `{rel(im['gif'])}`" if im.get("gif") else "")
                     + (f" + motion `{rel(im['motion_gif'])}`" if im.get("motion_gif") else "")
                     + (f" / `{rel(im['motion_mp4'])}`" if im.get("motion_mp4") else ""))
    if g["problems"]:
        lines += ["", "## Gate problems (for NEXUS)"] + [f"- {p}" for p in g["problems"]]
    path = out_dir / f"{datetime.now():%Y-%m-%d}-holo-{slugify(job.get('name') or job['brief'], 40)}.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("prompt")
    ap.add_argument("--name", default=None)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--animate", action="store_true")
    a = ap.parse_args()
    cfg = load_config()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ensure_comfy(cfg, print)
    try:
        data, seed, secs = generate(cfg, a.prompt, a.seed)
    finally:
        shutdown(cfg, print)
    stem = f"{datetime.now():%Y-%m-%d}-{a.name or slugify(a.prompt, 30)}"
    png = OUT_DIR / f"{stem}.png"
    png.write_bytes(data)
    print(f"image {png} (seed {seed}, {secs}s)")
    if a.animate:
        gif = OUT_DIR / f"{stem}-holo.gif"
        hologram_gif(data, gif)
        print(f"animation {gif} ({gif.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
