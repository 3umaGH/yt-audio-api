"""
main.py
Developed by Alperen Sümeroğlu - YouTube Audio Converter API
Clean, modular Flask-based backend for downloading and serving YouTube audio tracks.
Utilizes yt-dlp and FFmpeg for conversion and token-based access management.
"""

import secrets
import threading
import re
from flask import Flask, request, jsonify
from uuid import uuid4
from pathlib import Path
import yt_dlp
import access_manager
from constants import *
import os

# Initialize the Flask application
app = Flask(__name__)


@app.route("/", methods=["GET"])
def handle_audio_request():
    """
    Main endpoint to receive a YouTube video URL, download the audio in MP3 format,
    and return a unique token for accessing the file later.

    Query Parameters:
        - url (str): Full YouTube video URL.
        - recipient (num): 1 - own, 2 - friend

    Returns:
        - JSON: {"token": <download_token>}
    """
    video_url = request.args.get("url")
    if not video_url:
        return jsonify(error="Missing 'url' parameter in request."), BAD_REQUEST

    recipient = request.args.get("recipient")

    if recipient not in ["1", "2"]:
        return jsonify(error="Invalid 'recipient' parameter. Must be 1 (own) or 2 (friend)."), BAD_REQUEST

    folder = None

    api_key = request.args.get("key")

    if not api_key:
        return jsonify(error="Missing 'key' parameter in request."), BAD_REQUEST
    
    if not api_key == os.environ.get("API_KEY","123"):
        return jsonify(error="Invalid API key."), UNAUTHORIZED

    match recipient:
        case "1":
            folder = os.environ.get("RECIPIENT_1_FOLDER")
            pass
        case "2":
            folder = os.environ.get("RECIPIENT_2_FOLDER")
            pass

    # First, extract video info to get the title
    info_opts = {'quiet': True}
    try:
        with yt_dlp.YoutubeDL(info_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            video_title = info.get('title', 'unknown_video')
    except Exception as e:
        return jsonify(error="Failed to extract video information.", detail=str(e)), INTERNAL_SERVER_ERROR

    # Clean the title to make it filesystem-safe
    safe_title = re.sub(r'[^\w\s-]', '', video_title)  # Remove special characters
    safe_title = re.sub(r'[-\s]+', '-', safe_title)    # Replace spaces and multiple dashes with single dash
    safe_title = safe_title.strip('-')                 # Remove leading/trailing dashes
    
    # Limit filename length and add UUID suffix to ensure uniqueness
    if len(safe_title) > 50:
        safe_title = safe_title[:50]
    
    base_filename = f"{safe_title}_{str(uuid4())[:8]}"
    output_path = Path("/", folder, "yt") / base_filename
    print("Output path for download:", output_path)

    # yt-dlp configuration for downloading best audio and converting to mp3
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': str(output_path),
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192'
        }],
        'quiet': True
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])
    except Exception as e:
        return jsonify(error="Failed to download or convert audio.", detail=str(e)), INTERNAL_SERVER_ERROR

    # yt-dlp adds .mp3 extension during post-processing
    actual_filename = f"{base_filename}.mp3"
    return jsonify(result="success", file=actual_filename)

def _generate_token_response(filename: str):
    """
    Generates a secure download token for a given filename,
    registers it in the access manager, and returns the token as JSON.

    Args:
        filename (str): The name of the downloaded MP3 file

    Returns:
        JSON: {"token": <generated_token>}
    """
    token = secrets.token_urlsafe(TOKEN_LENGTH)
    access_manager.add_token(token, filename)
    return jsonify(token=token)


def main():
    """
    Starts the background thread for automatic token cleanup
    and launches the Flask development server.
    """
    token_cleaner_thread = threading.Thread(
        target=access_manager.manage_tokens,
        daemon=True
    )
    token_cleaner_thread.start()
    app.run(host=os.environ.get("FLASK_RUN_HOST", "127.0.0.1"), debug=True)


if __name__ == "__main__":
    main()
