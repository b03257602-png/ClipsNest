import os
import re
import time
import uuid
import socket
import shutil
import threading
import ipaddress
from pathlib import Path
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor

from flask import Flask, jsonify, request, send_file, send_from_directory
import yt_dlp

APP_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = APP_DIR / "downloads"
DOWNLOAD_DIR.mkdir(exist_ok=True)

app = Flask(__name__, static_folder="static")
executor = ThreadPoolExecutor(max_workers=2)
jobs = {}
jobs_lock = threading.Lock()
MAX_FILE_BYTES = 500 * 1024 * 1024
JOB_TTL_SECONDS = 3600

def valid_public_url(raw):
    if not isinstance(raw, str) or len(raw) > 2048:
        return False, "Please enter a valid video URL."
    parsed = urlparse(raw.strip())
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return False, "Use a complete http:// or https:// video link."
    if parsed.username or parsed.password:
        return False, "URLs containing embedded login details are not supported."
    host = parsed.hostname.lower()
    if host in ("localhost", "localhost.localdomain"):
        return False, "That address is not allowed."
    try:
        # Reject literal private/local IP addresses and hostnames resolving to them.
        addresses = socket.getaddrinfo(host, None)
        for item in addresses:
            ip = ipaddress.ip_address(item[4][0])
            if not ip.is_global:
                return False, "That address is not publicly accessible."
    except Exception:
        return False, "The link's host could not be verified."
    return True, parsed

def cleanup_old_jobs():
    now = time.time()
    with jobs_lock:
        expired = [jid for jid, job in jobs.items()
                   if now - job.get("created", now) > JOB_TTL_SECONDS]
        for jid in expired:
            job = jobs.pop(jid, None)
            if job:
                shutil.rmtree(job["folder"], ignore_errors=True)

def run_download(job_id, url):
    folder = DOWNLOAD_DIR / job_id
    folder.mkdir(parents=True, exist_ok=True)
    with jobs_lock:
        jobs[job_id]["status"] = "working"
        jobs[job_id]["message"] = "Checking the video link…"

    def progress_hook(data):
        if data.get("status") == "downloading":
            total = data.get("total_bytes") or data.get("total_bytes_estimate")
            downloaded = data.get("downloaded_bytes", 0)
            percent = int(downloaded * 100 / total) if total else None
            with jobs_lock:
                if job_id in jobs:
                    jobs[job_id]["progress"] = percent
                    jobs[job_id]["message"] = "Downloading video…"
        elif data.get("status") == "finished":
            with jobs_lock:
                if job_id in jobs:
                    jobs[job_id]["progress"] = 100
                    jobs[job_id]["message"] = "Preparing your video…"

    options = {
        "outtmpl": str(folder / "%(title).100B-%(id)s.%(ext)s"),
        "format": "best[ext=mp4]/best",
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "restrictfilenames": True,
        "max_filesize": MAX_FILE_BYTES,
        "socket_timeout": 20,
        "retries": 2,
        "fragment_retries": 2,
        "progress_hooks": [progress_hook],
        # No cookies, credentials, DRM removal, or private-content access.
    }

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get("title") or "video"
        files = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in
                 (".mp4", ".mkv", ".webm", ".mov", ".m4v")]
        if not files:
            raise RuntimeError("No downloadable video file was produced for this link.")
        chosen = max(files, key=lambda p: p.stat().st_size)
        if chosen.stat().st_size > MAX_FILE_BYTES:
            raise RuntimeError("This video is larger than the 500 MB limit.")
        with jobs_lock:
            jobs[job_id].update({
                "status": "done",
                "message": "Your video is ready.",
                "progress": 100,
                "filename": chosen.name,
                "title": title[:120]
            })
    except Exception as exc:
        msg = str(exc).replace("\n", " ").strip()
        if len(msg) > 240:
            msg = msg[:237] + "..."
        with jobs_lock:
            if job_id in jobs:
                jobs[job_id].update({
                    "status": "error",
                    "message": msg or "This link could not be downloaded."
                })

@app.get("/")
def home():
    return send_from_directory("static", "index.html")

@app.post("/api/download")
def start_download():
    cleanup_old_jobs()
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    ok, result = valid_public_url(url)
    if not ok:
        return jsonify(error=result), 400
    job_id = uuid.uuid4().hex
    folder = DOWNLOAD_DIR / job_id
    with jobs_lock:
        jobs[job_id] = {
            "status": "queued",
            "message": "Added to download queue…",
            "progress": 0,
            "created": time.time(),
            "folder": str(folder)
        }
    executor.submit(run_download, job_id, url)
    return jsonify(job_id=job_id), 202

@app.get("/api/status/<job_id>")
def job_status(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            return jsonify(error="Download not found. It may have expired."), 404
        return jsonify(
            status=job["status"],
            message=job["message"],
            progress=job.get("progress"),
            title=job.get("title"),
            download_url=f"/api/file/{job_id}" if job["status"] == "done" else None
        )

@app.get("/api/file/<job_id>")
def get_file(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
        if not job or job.get("status") != "done":
            return jsonify(error="This download is not ready."), 404
        folder = Path(job["folder"])
        filename = job["filename"]
    path = folder / filename
    if not path.is_file():
        return jsonify(error="The downloaded file is no longer available."), 404
    return send_file(path, as_attachment=True, download_name=filename)

@app.get("/health")
def health():
    return jsonify(status="ok")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")))
