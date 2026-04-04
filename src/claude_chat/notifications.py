"""Sound notification module for claude-chat.

Plays platform-specific chime sounds in a background thread so the UI
never blocks on audio playback.
"""

import sys
import threading


def play_chime(sound_type: str = "message") -> None:
    """Play a notification chime in a background thread.

    sound_type: "message" or "request"
    """
    thread = threading.Thread(target=_play_sound, args=(sound_type,), daemon=True)
    thread.start()


def _play_sound(sound_type: str) -> None:
    """Platform-specific sound playback."""
    try:
        if sys.platform == "win32":
            import winsound

            if sound_type == "message":
                winsound.PlaySound(
                    "SystemAsterisk", winsound.SND_ALIAS | winsound.SND_ASYNC
                )
            else:
                winsound.PlaySound(
                    "SystemExclamation", winsound.SND_ALIAS | winsound.SND_ASYNC
                )
        elif sys.platform == "darwin":
            import subprocess

            sound_file = (
                "/System/Library/Sounds/Ping.aiff"
                if sound_type == "message"
                else "/System/Library/Sounds/Purr.aiff"
            )
            subprocess.run(["afplay", sound_file], capture_output=True)
        else:
            # Linux: try paplay, fall back to terminal bell
            try:
                import subprocess

                subprocess.run(
                    [
                        "paplay",
                        "/usr/share/sounds/freedesktop/stereo/message-new-instant.oga",
                    ],
                    capture_output=True,
                    timeout=2,
                )
            except Exception:
                print("\a", end="", flush=True)
    except Exception:
        pass  # Never crash on sound playback failure
