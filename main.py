"""
main.py
Developed by Alperen Sümeroğlu - YouTube Audio Converter API
Clean, modular Flask-based backend for downloading and serving YouTube audio tracks.
Utilizes yt-dlp and FFmpeg for conversion and token-based access management.
"""

import secrets
import threading
import re
import os
from flask import Flask, request, jsonify
from uuid import uuid4
from pathlib import Path
import yt_dlp
import access_manager
from constants import *
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TDRC, TCON, TPE2, TRCK, TPOS, COMM
from mutagen.mp3 import MP3

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

    # First, extract video info to get the title and metadata
    info_opts = {'quiet': True}
    try:
        with yt_dlp.YoutubeDL(info_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            video_title = info.get('title', 'unknown_video')
            uploader = info.get('uploader', '')
            upload_date = info.get('upload_date', '')
            duration = info.get('duration', 0)
            description = info.get('description', '')
            
            # Try to parse artist and track from title if it follows common patterns
            artist = None
            track = video_title
            
            # Common patterns: "Artist - Track", "Artist: Track", "Track by Artist"
            if ' - ' in video_title:
                parts = video_title.split(' - ', 1)
                if len(parts) == 2:
                    artist, track = parts[0].strip(), parts[1].strip()
            elif ': ' in video_title:
                parts = video_title.split(': ', 1)
                if len(parts) == 2:
                    artist, track = parts[0].strip(), parts[1].strip()
            elif ' by ' in video_title.lower():
                parts = video_title.lower().split(' by ')
                if len(parts) == 2:
                    track, artist = parts[0].strip(), parts[1].strip()
                    
            # If we couldn't parse artist from title, use uploader as artist
            if not artist:
                artist = uploader
                
            print(f"Extracted metadata - Artist: {artist}, Track: {track}, Uploader: {uploader}")
            
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
        }, {
            'key': 'FFmpegMetadata',
            'add_metadata': True,
        }, {
            'key': 'EmbedThumbnail',
            'already_have_thumbnail': False,
        }],
        'writeinfojson': False,
        'writethumbnail': True,
        'embedthumbnail': True,
        'addmetadata': True,
        'quiet': True
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])
    except Exception as e:
        return jsonify(error="Failed to download or convert audio.", detail=str(e)), INTERNAL_SERVER_ERROR

    # yt-dlp adds .mp3 extension during post-processing
    actual_filename = f"{base_filename}.mp3"
    actual_file_path = Path("/", folder, "yt") / actual_filename
    
    # Add additional metadata using mutagen
    try:
        
        # Load the MP3 file
        audio_file = MP3(str(actual_file_path))
        
        # Add ID3 tags if they don't exist
        if audio_file.tags is None:
            audio_file.add_tags()
        
        # Set metadata optimized for Navidrome single track management
        if track:
            audio_file.tags.add(TIT2(encoding=3, text=track))  # Title
        if artist:
            audio_file.tags.add(TPE1(encoding=3, text=artist))  # Artist
            audio_file.tags.add(TPE2(encoding=3, text=artist))  # Album Artist
        
        # For single track management, use the track name as album or leave empty
        # This prevents grouping all YouTube tracks under one album
        if track and artist:
            # Use "Artist - Track" format for album to keep tracks separate
            audio_file.tags.add(TALB(encoding=3, text=f"{artist} - {track}"))
        elif track:
            # Use just the track name as album
            audio_file.tags.add(TALB(encoding=3, text=track))
        else:
            # Fallback to video title
            audio_file.tags.add(TALB(encoding=3, text=video_title))
        
        # Add year from upload date if available
        if upload_date and len(upload_date) >= 4:
            audio_file.tags.add(TDRC(encoding=3, text=upload_date[:4]))  # Year
        
        # Set a more specific genre if we can infer it from the title/artist
        genre = "Music"  # Default genre instead of "YouTube"
        if any(word in video_title.lower() for word in ['remix', 'mix', 'dj']):
            genre = "Electronic"
        elif any(word in video_title.lower() for word in ['live', 'concert', 'performance']):
            genre = "Live"
        elif any(word in video_title.lower() for word in ['cover', 'acoustic']):
            genre = "Cover"
        elif 'official' in video_title.lower():
            genre = "Pop"  # Assume official releases are pop-ish
        
        audio_file.tags.add(TCON(encoding=3, text=genre))  # Genre
        
        # Add track number as 1 for single tracks
        audio_file.tags.add(TRCK(encoding=3, text="1"))  # Track number
        
        # Add disc number as 1 for single tracks  
        audio_file.tags.add(TPOS(encoding=3, text="1"))  # Disc number
        
        # Add comment with video URL for reference
        comment_text = f"Source: {video_url}"
        if uploader:
            comment_text += f" | Uploader: {uploader}"
        if duration:
            mins, secs = divmod(duration, 60)
            comment_text += f" | Duration: {mins}:{secs:02d}"
            
        audio_file.tags.add(COMM(encoding=3, lang='eng', desc='', text=comment_text))
        
        # Save the tags
        audio_file.save()
        print(f"Successfully added metadata to {actual_filename}")
        
    except ImportError:
        print("Warning: mutagen not available, skipping additional metadata")
    except Exception as e:
        print(f"Warning: Failed to add additional metadata: {e}")

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
