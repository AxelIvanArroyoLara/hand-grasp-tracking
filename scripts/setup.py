"""Registra el entorno y obtiene el modelo oficial con verificación SHA-256."""

import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
MODEL_URL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
MODEL_SHA = "fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1"


def command(*args):
    """Lee información diagnóstica sin ejecutar una shell."""
    try:
        return subprocess.check_output(args, stderr=subprocess.DEVNULL, text=True, timeout=5).strip()
    except (OSError, subprocess.SubprocessError):
        return None


def environment():
    """Guarda versiones y recursos visibles para planear el experimento."""
    tools = ("python3", "uv", "conda", "brew", "git", "gh", "ffmpeg", "tectonic", "pdflatex", "soffice")
    names = ("mediapipe", "opencv-contrib-python", "numpy", "scipy", "scikit-learn")
    versions = {}
    for name in names:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    memory = command("sysctl", "-n", "hw.memsize")
    env = {"architecture": platform.machine(), "system": platform.system(),
           "macos": platform.mac_ver()[0], "python": platform.python_version(),
           "python_system": command("/usr/bin/python3", "--version"),
           "model": command("sysctl", "-n", "hw.model"), "cpu_count": os.cpu_count(),
           "memory_bytes": int(memory) if memory and memory.isdecimal() else None,
           "disk_free_bytes": shutil.disk_usage(ROOT).free,
           "tools": {name: bool(shutil.which(name)) for name in tools}, "versions": versions}
    target = ROOT / "experiments/manifests/environment.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(env, indent=2) + "\n", encoding="utf-8")
    return env


def get_model():
    """Recupera el archivo de Google únicamente si falta o no coincide con el hash."""
    target = ROOT / "models/hand_landmarker.task"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == MODEL_SHA:
        return target
    staging = target.with_suffix(".task.part")
    try:
        with urlopen(MODEL_URL, timeout=45) as response, staging.open("wb") as output:
            shutil.copyfileobj(response, output)
        if hashlib.sha256(staging.read_bytes()).hexdigest() != MODEL_SHA:
            raise ValueError("El SHA-256 del modelo no corresponde a la versión fijada")
        staging.replace(target)
    finally:
        staging.unlink(missing_ok=True)
    return target


if __name__ == "__main__":
    environment()
    print(get_model())
