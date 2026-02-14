"""
access_manager.py

Token management system for YouTube Audio Converter API.
Handles token-based authentication, expiration, and cleanup of downloaded audio files.

Crafted with precision by Alperen Sümeroğlu — bringing clean code and clean audio together.
"""

import time
import os
from datetime import datetime, timedelta
from pathlib import Path
from constants import EXPIRY_TIME_MINUTES, DOWNLOADS_DIRECTORY

# Stores active tokens with their expiration timestamps
allowed_tokens = {}

# Maps tokens to their respective audio file names
audio_files = {}

def add_token(token: str, filename: str) -> None:
    """
    Registers a new token with an expiration time and links it to an audio file.

    Args:
        token (str): The generated access token.
        filename (str): The name of the associated audio file.
    """
    expiry = datetime.now() + timedelta(minutes=EXPIRY_TIME_MINUTES)
    allowed_tokens[token] = expiry
    audio_files[token] = filename

def has_access(token: str) -> bool:
    """
    Checks if a given token exists in the allowed tokens.

    Args:
        token (str): The access token.

    Returns:
        bool: True if the token is known, False otherwise.
    """
    return token in allowed_tokens

def is_valid(token: str) -> bool:
    """
    Determines whether a token is still valid based on expiration.

    Args:
        token (str): The access token.

    Returns:
        bool: True if the token is still valid, False if expired.
    """
    return allowed_tokens[token] >= datetime.now()

def get_audio_file(token: str) -> str:
    """
    Retrieves the audio file name associated with a token.

    Args:
        token (str): The access token.

    Returns:
        str: The filename of the audio file.
    """
    print(audio_files[token])
    print(audio_files)
    return audio_files[token]

def remove_expired_tokens() -> list:
    """
    Identifies expired access tokens, removes them from storage,
    and collects filenames of associated audio files for deletion.

    Returns:
        list: List of filenames to delete.
    """
    expired = []
    files_to_remove = []

    for token in list(allowed_tokens.keys()):
        if not is_valid(token):
            expired.append(token)
            files_to_remove.append(audio_files.pop(token, None))

    for token in expired:
        allowed_tokens.pop(token, None)

    return [f for f in files_to_remove if f]

def delete_expired_files(files: list) -> None:
    """
    Deletes expired audio files from the filesystem.

    Args:
        files (list): List of filenames to delete.
    """
    for file in files:
        try:
            full_path = Path(DOWNLOADS_DIRECTORY) / file
            full_path.unlink(missing_ok=True)
        except Exception as e:
            print(f"Failed to delete file '{file}': {e}")

def manage_tokens() -> None:
    """
    Background task that runs indefinitely to remove expired tokens
    and delete associated audio files every second.
    """
    while True:
        expired_files = remove_expired_tokens()
        delete_expired_files(expired_files)
        time.sleep(1)
