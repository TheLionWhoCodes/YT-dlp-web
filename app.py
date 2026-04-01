import os
import shutil
import tempfile
import threading
from flask import Flask, render_template, request, jsonify, send_file, after_this_request
import yt_dlp

app = Flask(__name__)

QUALITY_OPTIONS = [
    {
        "id": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "label": "🏆 Mejor calidad",
        "desc": "Máxima resolución disponible"
    },
    {
        "id": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080]",
        "label": "🎬 1080p Full HD",
        "desc": "MP4 · Alta definición"
    },
    {
        "id": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]",
        "label": "📺 720p HD",
        "desc": "MP4 · Buena calidad"
    },
    {
        "id": "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480]",
        "label": "📱 480p",
        "desc": "MP4 · Tamaño moderado"
    },
    {
        "id": "bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/best[height<=360]",
        "label": "💾 360p",
        "desc": "MP4 · Archivo ligero"
    },
    {
        "id": "bestaudio[ext=m4a]/bestaudio",
        "label": "🎵 Solo Audio",
        "desc": "M4A · Sin video"
    },
]


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
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "socket_timeout": 15,
        }
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
        ydl_opts = {
            "format": format_id,
            "outtmpl": os.path.join(tmp_dir, "%(title)s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "merge_output_format": "mp4",
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            expected = ydl.prepare_filename(info)

        # Buscar el archivo generado (puede ser .mp4 tras el merge)
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
