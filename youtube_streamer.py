#
# Local Audio Streamer for Daily Multi Translation
# This service joins a Daily room as a participant and streams local audio files
# The existing translation bot will automatically pick up and translate the audio
#

import argparse
import asyncio
import os
import sys
import threading
import time
from pathlib import Path
from typing import Optional

import numpy as np
from daily import Daily, CallClient
from dotenv import load_dotenv
from loguru import logger
from pipecat.transports.daily.utils import (
    DailyMeetingTokenParams,
    DailyMeetingTokenProperties,
    DailyRESTHelper,
)
import pydub

load_dotenv(override=True)

logger.remove(0)
logger.add(sys.stderr, level="INFO")

# Supported audio formats
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".opus", ".mp4"}

SAMPLE_RATE = 16000
NUM_CHANNELS = 1


class LocalAudioStreamer:
    """Streams local audio files to a Daily room using virtual microphone."""

    def __init__(self, room_url: str, token: Optional[str] = None):
        self.room_url = room_url
        self.token = token
        self.client: Optional[CallClient] = None
        self.virtual_mic = None
        self.audio_samples: Optional[np.ndarray] = None
        self.is_streaming = False
        self.keep_running = False
        self.stream_thread: Optional[threading.Thread] = None

    async def _get_token(self) -> str:
        """Get or generate a Daily meeting token."""
        if self.token:
            return self.token

        api_key = os.getenv("DAILY_API_KEY")
        if not api_key:
            raise RuntimeError(
                "DAILY_API_KEY not set. Required to generate meeting token."
            )

        import aiohttp
        async with aiohttp.ClientSession() as session:
            daily_rest_helper = DailyRESTHelper(
                daily_api_key=api_key,
                daily_api_url=os.getenv("DAILY_API_URL", "https://api.daily.co/v1"),
                aiohttp_session=session,
            )

            token = await daily_rest_helper.get_token(
                self.room_url,
                expiry_time=60 * 60,  # 1 hour
                params=DailyMeetingTokenParams(
                    properties=DailyMeetingTokenProperties(
                        start_video_off=True, start_audio_off=False
                    )
                ),
            )

            return token

    def _load_audio_file(self, audio_path: Path):
        """Load and process local audio file."""
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        if audio_path.suffix.lower() not in AUDIO_EXTENSIONS:
            raise ValueError(
                f"Unsupported audio format: {audio_path.suffix}. "
                f"Supported formats: {', '.join(AUDIO_EXTENSIONS)}"
            )

        logger.info(f"Loading audio from: {audio_path}")

        # Load audio file using pydub
        try:
            audio_segment = pydub.AudioSegment.from_file(str(audio_path))
            logger.info(
                f"Original audio: {audio_segment.frame_rate}Hz, "
                f"{audio_segment.channels} channel(s), "
                f"{len(audio_segment)}ms duration"
            )

            # Convert to 16kHz mono for Daily compatibility
            audio_segment = audio_segment.set_frame_rate(SAMPLE_RATE).set_channels(NUM_CHANNELS)

            # Convert to numpy array (int16 PCM)
            samples = np.array(audio_segment.get_array_of_samples(), dtype=np.int16)

            duration_seconds = len(samples) / SAMPLE_RATE
            logger.info(
                f"Audio loaded: {len(samples)} samples at {SAMPLE_RATE}Hz "
                f"({duration_seconds:.2f} seconds)"
            )

            return samples

        except Exception as e:
            logger.error(f"Failed to load audio file: {e}")
            raise RuntimeError(f"Error loading audio file: {e}") from e

    def _stream_audio_loop(self):
        """Stream audio chunks to virtual microphone (runs in thread)."""
        if self.audio_samples is None:
            logger.error("Audio samples not loaded")
            return

        logger.info("Starting audio stream loop...")
        chunk_size = int(SAMPLE_RATE * 0.02)  # 20ms chunks
        current_position = 0
        frames_sent = 0
        chunk_duration = chunk_size / SAMPLE_RATE  # Duration in seconds

        while self.is_streaming:
            # Loop audio if we've reached the end
            if current_position >= len(self.audio_samples):
                logger.info("Audio finished, looping...")
                current_position = 0

            end_pos = min(current_position + chunk_size, len(self.audio_samples))
            chunk = self.audio_samples[current_position:end_pos]

            # Convert to bytes (int16 PCM)
            chunk_bytes = chunk.tobytes()

            # Write to virtual microphone
            try:
                self.virtual_mic.write_frames(chunk_bytes)
                frames_sent += 1
                current_position = end_pos

                # Log progress every 50 frames (~1 second)
                if frames_sent % 50 == 0:
                    if len(self.audio_samples) > 0:
                        progress = (current_position % len(self.audio_samples)) / len(self.audio_samples) * 100
                        logger.info(f"Streaming progress: {progress:.1f}% ({frames_sent} frames sent)")

                # Sleep to maintain real-time playback rate (using time.sleep for thread)
                time.sleep(chunk_duration)

            except Exception as e:
                logger.error(f"Error writing audio frames: {e}")
                break

        logger.info(f"Finished streaming audio - total frames sent: {frames_sent}")

    def on_joined(self, data, error):
        """Callback when joined to meeting."""
        if error:
            logger.error(f"Unable to join meeting: {error}")
            self.is_streaming = False
            self.keep_running = False
            return

        logger.info("Successfully joined Daily room")
        # Start streaming audio in a separate thread
        self.is_streaming = True
        self.stream_thread = threading.Thread(target=self._stream_audio_loop, daemon=True)
        self.stream_thread.start()

    async def start_streaming(self, audio_path: str):
        """Start streaming local audio file to Daily room."""
        try:
            # Initialize Daily
            Daily.init()

            # Load audio file
            audio_file_path = Path(audio_path)
            self.audio_samples = self._load_audio_file(audio_file_path)

            # Get token
            token = await self._get_token()
            logger.info(f"Got Daily token for room: {self.room_url}")

            # Create virtual microphone device
            self.virtual_mic = Daily.create_microphone_device(
                "local-audio-mic",
                sample_rate=SAMPLE_RATE,
                channels=NUM_CHANNELS,
                non_blocking=True
            )
            logger.info("Virtual microphone created")

            # Create call client
            self.client = CallClient()

            # Update subscription profile
            self.client.update_subscription_profiles(
                {"base": {"camera": "unsubscribed", "microphone": "subscribed"}}
            )

            # Join the room
            # If token is provided, append it to the URL
            meeting_url = self.room_url
            if token:
                separator = "&" if "?" in meeting_url else "?"
                meeting_url = f"{meeting_url}{separator}t={token}"
            
            logger.info(f"Joining Daily room: {self.room_url}")
            self.keep_running = True
            self.client.join(
                meeting_url,
                client_settings={
                    "inputs": {
                        "camera": False,
                        "microphone": {
                            "isEnabled": True,
                            "settings": {
                                "deviceId": "local-audio-mic",
                                "customConstraints": {
                                    "autoGainControl": {"exact": False},
                                    "noiseSuppression": {"exact": False},
                                    "echoCancellation": {"exact": False},
                                },
                            },
                        },
                    },
                    "publishing": {
                        "microphone": {
                            "isPublishing": True,
                            "sendSettings": {
                                "channelConfig": "mono",
                            },
                        }
                    },
                },
                completion=self.on_joined,
            )

            # Keep running until interrupted
            logger.info("Streaming audio... Press Ctrl+C to stop")
            while self.keep_running:
                await asyncio.sleep(1)

        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        except Exception as e:
            logger.error(f"Error in streaming process: {e}")
            raise
        finally:
            await self.cleanup()

    async def cleanup(self):
        """Clean up resources."""
        self.is_streaming = False
        self.keep_running = False

        # Wait for stream thread to finish
        if self.stream_thread and self.stream_thread.is_alive():
            logger.info("Waiting for audio stream thread to finish...")
            self.stream_thread.join(timeout=2.0)

        if self.client:
            try:
                logger.info("Leaving Daily room...")
                self.client.leave()
                self.client.release()
            except Exception as e:
                logger.warning(f"Error leaving room: {e}")


def find_audio_files(audios_dir: Path) -> list[Path]:
    """Find all audio files in the audios directory."""
    if not audios_dir.exists():
        return []

    audio_files = []
    for ext in AUDIO_EXTENSIONS:
        audio_files.extend(audios_dir.glob(f"*{ext}"))
        audio_files.extend(audios_dir.glob(f"*{ext.upper()}"))

    return sorted(audio_files)


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Stream local audio files to Daily room for translation"
    )
    parser.add_argument(
        "-u",
        "--url",
        type=str,
        required=True,
        help="Daily room URL to join",
    )
    parser.add_argument(
        "-f",
        "--file",
        type=str,
        required=False,
        help="Path to audio file to stream (if not provided, will use first file from audios folder)",
    )
    parser.add_argument(
        "-d",
        "--directory",
        type=str,
        required=False,
        default="audios",
        help="Directory containing audio files (default: audios)",
    )
    parser.add_argument(
        "-t",
        "--token",
        type=str,
        required=False,
        help="Daily meeting token (optional, will be generated if not provided)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available audio files and exit",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Test audio loading and processing without connecting to Daily",
    )

    args = parser.parse_args()

    # List available files if requested
    if args.list:
        audios_dir = Path(args.directory)
        audio_files = find_audio_files(audios_dir)
        if audio_files:
            logger.info(f"Available audio files in '{audios_dir}':")
            for i, audio_file in enumerate(audio_files, 1):
                size_mb = audio_file.stat().st_size / (1024 * 1024)
                logger.info(f"  {i}. {audio_file.name} ({size_mb:.2f} MB)")
        else:
            logger.warning(f"No audio files found in '{audios_dir}'")
        return

    # Test mode - validate audio without connecting to Daily
    if args.test:
        # Determine audio file to test
        if args.file:
            audio_path = Path(args.file)
            if not audio_path.is_absolute():
                audio_path = Path.cwd() / audio_path
        else:
            audios_dir = Path(args.directory)
            audio_files = find_audio_files(audios_dir)
            if not audio_files:
                logger.error(f"No audio files found in '{audios_dir}'")
                sys.exit(1)
            audio_path = audio_files[0]
            logger.info(f"Testing first file from '{audios_dir}': {audio_path.name}")

        if not audio_path.exists():
            logger.error(f"Audio file not found: {audio_path}")
            sys.exit(1)

        logger.info("=" * 60)
        logger.info("Testing Audio Loading and Processing")
        logger.info("=" * 60)

        try:
            streamer = LocalAudioStreamer(room_url="", token=None)
            samples = streamer._load_audio_file(audio_path)
            logger.info(f"✓ Audio loaded successfully: {len(samples)} samples")
            logger.info(f"✓ All tests passed! Ready to stream.")
            sys.exit(0)
        except Exception as e:
            logger.error(f"✗ Test failed: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)

    # Determine audio file to use
    if args.file:
        audio_path = Path(args.file)
        if not audio_path.is_absolute():
            audio_path = Path.cwd() / audio_path
    else:
        # Use audios folder
        audios_dir = Path(args.directory)
        audio_files = find_audio_files(audios_dir)

        if not audio_files:
            logger.error(
                f"No audio files found in '{audios_dir}'. "
                "Please specify a file with -f/--file or add audio files to the audios folder."
            )
            sys.exit(1)

        audio_path = audio_files[0]
        logger.info(f"Using first audio file from '{audios_dir}': {audio_path.name}")

    if not audio_path.exists():
        logger.error(f"Audio file not found: {audio_path}")
        sys.exit(1)

    streamer = LocalAudioStreamer(room_url=args.url, token=args.token)
    try:
        await streamer.start_streaming(str(audio_path))
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
