# ClipNest Server

A small backend-powered video downloader for **publicly accessible videos that the user owns or has permission to download**.

## What it does
- Accepts a video URL in the ClipNest page.
- Uses yt-dlp on the server to fetch a supported public video.
- Shows download status and serves the resulting file to the browser.
- Uses FFmpeg to merge compatible video/audio streams when available.

## Important limits
- This is not a guarantee that every social-media URL will work. Platform support and access rules change.
- It does not use login cookies, account credentials, private links, DRM removal, or access-control bypasses.
- Download only content you own or have permission to save, and follow the source platform's terms and copyright rules.
- Server storage is temporary. Jobs are removed after about one hour, and files may disappear when the host restarts.
- This demo keeps job state in memory and is intended for personal testing, not public high-traffic use.
- The 500 MB cap is per downloaded file.

## Deploy with a Docker-capable host
1. Upload this folder to a private GitHub repository.
2. Create a new web service on a Docker-capable host (for example, Render).
3. Connect the repository and select the included `Dockerfile`.
4. Deploy. The host will provide a public HTTPS address.
5. Open that address on your phone.

Do not publish this as an unrestricted public service. Add authentication, rate limits, persistent job storage, and abuse monitoring before making it public.

## Run locally
Requires Python 3.10+ and FFmpeg installed.

```bash
pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000`.

## Project files
- `app.py` — Flask API and download worker
- `static/index.html` — mobile-friendly website
- `requirements.txt` — Python packages
- `Dockerfile` — deployment image with FFmpeg
