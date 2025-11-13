# Audio Streamer Documentation

Complete guide for streaming audio to Daily Multi Translation rooms.

## Table of Contents

1. [Overview](#overview)
2. [Installation](#installation)
3. [Usage - Local Audio Streaming](#usage---local-audio-streaming)
4. [Testing Guide](#testing-guide)
5. [Troubleshooting](#troubleshooting)

---

## Overview

The `youtube_streamer.py` service allows you to stream local audio files to a Daily room, where they will be automatically translated by the existing translation bot.

### How It Works

1. **Audio Loading**: Loads audio file from local filesystem (`audios` folder)
2. **Audio Processing**: Converts to 16kHz mono format (Daily compatible)
3. **Daily Room Join**: Joins the specified Daily room using pipecat's `DailyTransport`
4. **Audio Streaming**: Streams audio chunks in real-time (20ms chunks) to the Daily room
5. **Translation**: The existing translation bot automatically detects the audio and translates it

### Workflow

```
Local Audio File
    ↓
[youtube_streamer.py]
    ↓
Daily Room (as participant)
    ↓
[bot.py - Translation Bot]
    ↓
Translated Audio Tracks
    ↓
[client/ - React Frontend]
```

This is a **separate service** that doesn't modify your existing workflow - it simply joins as another participant in the room.

---

## Installation

### Prerequisites

1. Python 3.8+ with virtual environment activated
2. All dependencies from `requirements.txt` installed
3. Daily API key set in environment (`DAILY_API_KEY`)
4. A Daily room URL (can be obtained from your FastAPI server)

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Install FFmpeg

`pydub` requires `ffmpeg` to be installed on your system:

- **Ubuntu/Debian**: `sudo apt-get install ffmpeg`
- **macOS**: `brew install ffmpeg`
- **Windows**: Download from [ffmpeg.org](https://ffmpeg.org/download.html)

### Environment Variables

Ensure your `.env` file has:

```bash
DAILY_API_KEY=your_daily_api_key
DEEPGRAM_API_KEY=your_deepgram_key
OPENAI_API_KEY=your_openai_key  # or LITELLM_API_KEY
AZURE_SPEECH_KEY=your_azure_key  # or CARTESIA_API_KEY
AZURE_SPEECH_REGION=your_azure_region
```

---

## Usage - Local Audio Streaming

The streamer now uses local audio files from the `audios` folder instead of downloading from YouTube.

### Quick Start

#### 1. List Available Audio Files

```bash
python youtube_streamer.py --list
```

This will show all audio files in the `audios` folder.

#### 2. Stream from Audios Folder (Auto-select first file)

```bash
python youtube_streamer.py \
  -u https://realtime-translation.daily.co/YOUR_ROOM_ID
```

This automatically uses the first audio file found in the `audios` folder.

#### 3. Stream Specific File

```bash
# From audios folder
python youtube_streamer.py \
  -u https://realtime-translation.daily.co/YOUR_ROOM_ID \
  -f audios/Talk\ Your\ Thesis\ \(TYT\)\ 2025\ _\ Tanisha\ _\ ISF\ 2025.mp3

# Or absolute path
python youtube_streamer.py \
  -u https://realtime-translation.daily.co/YOUR_ROOM_ID \
  -f /path/to/your/audio.mp3
```

#### 4. Use Custom Directory

```bash
python youtube_streamer.py \
  -u https://realtime-translation.daily.co/YOUR_ROOM_ID \
  -d /path/to/your/audio/folder
```

### Supported Audio Formats

- `.mp3` - MP3 audio
- `.wav` - WAV audio
- `.m4a` - M4A/AAC audio
- `.aac` - AAC audio
- `.ogg` - OGG audio
- `.flac` - FLAC audio
- `.opus` - Opus audio
- `.mp4` - MP4 audio

### Command Line Options

```
-u, --url          Daily room URL to join (required)
-f, --file         Path to specific audio file (optional)
-d, --directory    Directory containing audio files (default: audios)
-t, --token        Daily meeting token (optional, auto-generated if not provided)
--list             List available audio files and exit
```

### Examples

**Example 1: Stream first file from audios folder**
```bash
python youtube_streamer.py -u https://realtime-translation.daily.co/abc123
```

**Example 2: Stream specific file**
```bash
python youtube_streamer.py \
  -u https://realtime-translation.daily.co/abc123 \
  -f "audios/my_audio.mp3"
```

**Example 3: List files then stream**
```bash
# First, see what's available
python youtube_streamer.py --list

# Then stream a specific one
python youtube_streamer.py \
  -u https://realtime-translation.daily.co/abc123 \
  -f "audios/Talk Your Thesis (TYT) 2025 _ Tanisha _ ISF 2025.mp3"
```

### File Structure

```
daily-multi-translation/
├── audios/                          # Audio files folder
│   ├── Talk Your Thesis...mp3      # Your audio files here
│   └── other_audio.wav
├── youtube_streamer.py             # Streamer script
└── ...
```

### Notes

- Audio files are automatically converted to 16kHz mono for Daily compatibility
- The script maintains real-time playback speed
- If no file is specified, it uses the first file found in the `audios` folder
- Files are sorted alphabetically when auto-selecting
- The service will automatically leave the room when streaming completes or is interrupted

---

## Testing Guide

Complete step-by-step guide for testing the audio streaming → translation pipeline.

### Step 1: Start the FastAPI Server

Open **Terminal 1**:

```bash
cd /home/abhiunnam/ai-projects/daily-multi-translation
source venv/bin/activate
python server.py
```

**Expected Output:**
```
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:7860
```

**What happens:**
- Server creates a Daily room
- Spawns the translation bot automatically
- Returns a room URL (e.g., `https://realtime-translation.daily.co/abc123`)

**Note:** The bot process will be started automatically when you access the server endpoint.

### Step 2: Get the Room URL

**Option A: Via Browser**
- Open `http://localhost:7860` in your browser
- You'll be redirected to the Daily room URL
- Copy the URL from the address bar

**Option B: Via curl**
```bash
curl http://localhost:7860
# Follow the redirect or check the Location header
```

**Option C: Check Server Logs**
- Look for: `!!! Room URL: https://realtime-translation.daily.co/...`

### Step 3: Start the Audio Streamer

Open **Terminal 2**:

```bash
cd /home/abhiunnam/ai-projects/daily-multi-translation
source venv/bin/activate

# Stream from audios folder (auto-select first file)
python youtube_streamer.py \
  -u https://realtime-translation.daily.co/YOUR_ROOM_ID

# Or stream specific file
python youtube_streamer.py \
  -u https://realtime-translation.daily.co/YOUR_ROOM_ID \
  -f audios/your_audio.mp3
```

**Expected Output:**
```
INFO: Loading audio from: audios/your_audio.mp3
INFO: Original audio: 44100Hz, 2 channel(s), 300000ms duration
INFO: Audio loaded: 4800000 samples at 16000Hz (300.00 seconds)
INFO: Got Daily token for room: https://...
INFO: Starting audio stream to Daily room...
INFO: Starting audio stream loop...
```

**What happens:**
- Loads audio file from local filesystem
- Joins the Daily room
- Starts streaming audio chunks

### Step 4: Open the Client Frontend

Open **Terminal 3** (or use your existing client setup):

```bash
cd /home/abhiunnam/ai-projects/daily-multi-translation/client
npm install  # if not already done
npm start
```

**Or if using a static server:**
```bash
# Serve the index.html file
python -m http.server 3000
# Then open http://localhost:3000
```

### Step 5: Connect and Observe

1. **In the Browser:**
   - Paste the Daily room URL in the "Meeting URL" field
   - Click "Join"
   - Select a language (e.g., Hindi)

2. **What You Should See:**
   - **Left Panel:** Room joined, language selected
   - **Right Panel:**
     - "Currently listening to: Hindi" (or your selected language)
     - Audio visualizer showing activity
     - Live transcript appearing as the bot translates
     - "Play Audio" button becomes active

3. **Click "Play Audio":**
   - You should hear the translated audio
   - Transcripts should scroll in real-time
   - Waveform should show audio activity

### Verification Checklist

- [ ] Server starts without errors
- [ ] Bot process spawns automatically (check `bot_procs` in server logs)
- [ ] Audio streamer loads file successfully
- [ ] Audio streamer joins Daily room (check Daily dashboard)
- [ ] Client frontend connects to room
- [ ] Audio visualizer shows activity
- [ ] Transcripts appear in the UI
- [ ] Translated audio plays when clicking "Play Audio"
- [ ] No console errors in browser DevTools

### Expected Flow Timeline

```
0:00 - Server starts, creates room
0:01 - Bot joins room
0:02 - Audio streamer loads file
0:05 - Audio streamer joins room, starts streaming
0:06 - Client connects, sees audio activity
0:07 - First transcript appears
0:08 - Translated audio track available
0:10 - User clicks "Play Audio", hears translation
```

### Quick Test Script

Create a test script `test_integration.sh`:

```bash
#!/bin/bash

echo "=== Testing Audio Streaming Integration ==="

# Check dependencies
echo "1. Checking dependencies..."
python -c "import pydub, numpy" && echo "   ✓ Dependencies OK" || echo "   ✗ Missing dependencies"

# Check ffmpeg
command -v ffmpeg >/dev/null && echo "   ✓ ffmpeg installed" || echo "   ✗ ffmpeg not found"

# Check environment variables
echo "2. Checking environment variables..."
[ -z "$DAILY_API_KEY" ] && echo "   ✗ DAILY_API_KEY not set" || echo "   ✓ DAILY_API_KEY set"
[ -z "$DEEPGRAM_API_KEY" ] && echo "   ✗ DEEPGRAM_API_KEY not set" || echo "   ✓ DEEPGRAM_API_KEY set"

# Check audio files
echo "3. Checking audio files..."
if [ -d "audios" ] && [ "$(ls -A audios/*.mp3 audios/*.wav 2>/dev/null)" ]; then
    echo "   ✓ Audio files found"
else
    echo "   ✗ No audio files in audios folder"
fi

echo "4. Ready to test!"
echo "   Start server: python server.py"
echo "   Start streamer: python youtube_streamer.py -u <ROOM_URL>"
```

Make it executable:
```bash
chmod +x test_integration.sh
./test_integration.sh
```

### Monitoring

**Server Logs:**
- Watch for bot process creation
- Check for room creation messages

**Bot Logs:**
- Located in `logs/bot-*.log`
- Shows STT, translation, and TTS activity

**Audio Streamer:**
- Shows audio loading progress
- Shows streaming status

**Browser Console:**
- Check for JavaScript errors
- Monitor WebSocket connections
- Check audio context status

### Success Criteria

✅ Audio file successfully loaded and streamed  
✅ Bot detects audio and starts translation  
✅ Transcripts appear in real-time in the UI  
✅ Translated audio plays correctly  
✅ No errors in any component logs  
✅ Smooth audio playback without stuttering  

---

## Troubleshooting

### No audio files found

**Symptoms:**
```
ERROR: No audio files found in 'audios'
```

**Solutions:**
- Add audio files to the `audios` folder or specify a file with `-f`
- Check that the directory path is correct
- Verify file extensions are supported (mp3, wav, m4a, etc.)

### File not found

**Symptoms:**
```
ERROR: Audio file not found: /path/to/file.mp3
```

**Solutions:**
- Check the file path is correct
- Use absolute path or relative path from project root
- Verify file permissions allow reading

### Unsupported format

**Symptoms:**
```
ERROR: Unsupported audio format: .xyz
```

**Solutions:**
- Convert your audio file to a supported format (mp3, wav, m4a, etc.)
- Use ffmpeg to convert: `ffmpeg -i input.xyz output.mp3`

### FFmpeg not found

**Symptoms:**
```
FileNotFoundError: [Errno 2] No such file or directory: 'ffmpeg'
```

**Solutions:**
- Install ffmpeg (see Installation section)
- Verify ffmpeg is in PATH: `which ffmpeg` or `ffmpeg -version`
- On Windows, add ffmpeg to system PATH

### Bot not translating

**Symptoms:**
- Audio visualizer shows activity but no transcripts
- No translated audio tracks

**Solutions:**
- Check bot logs in `logs/` directory
- Verify API keys (Deepgram, OpenAI/LiteLLM, Azure/Cartesia)
- Check server logs for bot process errors
- Ensure bot process is running: `ps aux | grep bot`

### Client can't connect

**Symptoms:**
- "Unable to join the Daily room" error
- Button stays disabled

**Solutions:**
- Verify room URL is correct
- Check Daily API key is valid
- Check browser console for CORS errors
- Ensure Daily room exists and is accessible

### No audio playback

**Symptoms:**
- Button shows "Play Audio" but nothing happens
- Audio visualizer inactive

**Solutions:**
- Check browser console for audio context errors
- Verify browser allows autoplay (may need user interaction)
- Check that track is published (look for "Track ready" status)
- Try refreshing the page

### Audio streaming stops prematurely

**Symptoms:**
- Streaming starts but stops before file ends

**Solutions:**
- Check for errors in streamer logs
- Verify audio file is not corrupted
- Check network connection to Daily
- Ensure sufficient system resources

---

## Integration with Existing Workflow

This service is designed to work alongside your existing setup:

1. **No changes to bot.py**: The translation bot automatically detects and translates any audio in the room
2. **No changes to server.py**: The FastAPI server continues to work as before
3. **No changes to client**: The React frontend will automatically show translations from the audio

Simply run the audio streamer as a separate process, and it will integrate seamlessly with your existing translation pipeline.

---

## Next Steps

Once everything is working:

1. Add more audio files to the `audios` folder
2. Experiment with different audio formats and lengths
3. Consider adding progress indicators for long files
4. Add support for playlists or continuous streaming
5. Consider adding pause/resume functionality

