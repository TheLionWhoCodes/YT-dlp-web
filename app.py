import os
import shutil
import tempfile
import threading
import base64
from flask import Flask, render_template, request, jsonify, send_file, after_this_request
import yt_dlp

app = Flask(__name__)

QUALITY_OPTIONS = [
    {"id": "best",           "label": "🏆 Mejor calidad", "desc": "Máxima resolución disponible"},
    {"id": "best[height<=1080]", "label": "🎬 1080p Full HD",  "desc": "MP4 · Alta definición"},
    {"id": "best[height<=720]",  "label": "📺 720p HD",        "desc": "MP4 · Buena calidad"},
    {"id": "best[height<=480]",  "label": "📱 480p",           "desc": "MP4 · Tamaño moderado"},
    {"id": "best[height<=360]",  "label": "💾 360p",           "desc": "MP4 · Archivo ligero"},
    {"id": "bestaudio/best",     "label": "🎵 Solo Audio",     "desc": "M4A · Sin video"},
]


def get_cookies_file():
    b64 = os.environ.get("YT_COOKIES_B64")
    if not b64:
        return None
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode="wb")
    tmp.write(base64.b64decode(b64))
    tmp.close()
    return tmp.name


def build_ydl_opts(extra=None):
    opts = {
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 15,
    }
    cookies_file = get_cookies_file()
    if cookies_file:
        opts["cookiefile"] = cookies_file
    if extra:
        opts.update(extra)
    return opts


@app.route("/")
def index():
    return render_template("index.html", qualities=QUALITY_OPTIONS)


@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.get_json()
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify({"error": "URL vacía"}), 400

    try:
        ydl_opts = build_ydl_opts()
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        duration = info.get("duration", 0) or 0
        minutes = int(duration) // 60
        seconds = int(duration) % 60

        return jsonify({
            "title": info.get("title", "Sin título"),
            "thumbnail": info.get("thumbnail", ""),
            "channel": info.get("uploader", ""),
            "duration": f"{minutes}:{seconds:02d}" if duration else "—",
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/download", methods=["POST"])
def download():
    data = request.get_json()
    url = (data.get("url") or "").strip()
    format_id = data.get("format_id") or "best"

    if not url:
        return jsonify({"error": "URL vacía"}), 400

    tmp_dir = tempfile.mkdtemp()

    try:
        # Intenta con el formato pedido, si falla usa "best"
        for fmt in [format_id, "best"]:
            try:
                ydl_opts = build_ydl_opts({
                    "format": fmt,
                    "outtmpl": os.path.join(tmp_dir, "%(title)s.%(ext)s"),
                    "merge_output_format": "mp4",
                })
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    expected = ydl.prepare_filename(info)
                break
            except Exception:
                shutil.rmtree(tmp_dir, ignore_errors=True)
                tmp_dir = tempfile.mkdtemp()
                if fmt == "best":
                    raise

        filename = expected
        if not os.path.exists(filename):
            base = os.path.splitext(expected)[0]
            filename = base + ".mp4"

        if not os.path.exists(filename):
            archivos = os.listdir(tmp_dir)
            if not archivos:
                return jsonify({"error": "No se generó ningún archivo"}), 500
            filename = os.path.join(tmp_dir, archivos[0])

        @after_this_request
        def cleanup(response):
            def remove():
                try:
                    shutil.rmtree(tmp_dir)
                except Exception:
                    pass
            threading.Thread(target=remove, daemon=True).start()
            return response

        return send_file(
            filename,
            as_attachment=True,
            download_name=os.path.basename(filename),
        )

    except Exception as e:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
