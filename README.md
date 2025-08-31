# Discord Music Bot

This project contains a simple Discord bot written in Python using the `discord.py` library.  
The bot can join a voice channel and play music from YouTube based on a direct link or a search query.  
It also supports basic playback controls such as pause, resume, skip, previous, and queue listing.

## Features

- **Play songs from YouTube:** Provide a YouTube URL or type a search query and the bot will play the first matching video.  
- **Queue management:** Songs are queued in the order they are requested.  
- **Playback controls:** Commands are available to pause, resume, skip the current song, play the previous song, and view the queue.  
- **Voice channel handling:** The bot can join your current voice channel, switch between channels, and leave when finished.

## Requirements

This bot requires the following software and Python packages:

1. **Python 3.8+** – The bot uses asynchronous features in Python and the official `discord.py` library.  
2. **FFmpeg** – Used to transcode audio into a format playable by Discord.  
   The Python Land tutorial explains why FFmpeg is necessary and provides instructions on where to download it【562454067469386†L541-L543】.  
3. **yt‑dlp** – A fork of `youtube‑dl` for extracting audio streams from YouTube.  
4. **discord.py** – Official Discord API wrapper for Python.  
5. **python‑dotenv** (optional) – For loading the bot token from a `.env` file.

To install the required Python packages, run:

```bash
pip install -r requirements.txt
```

The `requirements.txt` file specifies the exact versions used by the bot.

## Setup

1. **Clone the project:**

   ```bash
   git clone https://github.com/<your-username>/discord_music_bot.git
   cd discord_music_bot
   ```

2. **Install FFmpeg:**  
   Download a prebuilt FFmpeg binary from the official site (see the Python Land tutorial for details【562454067469386†L541-L543】) and ensure that the `ffmpeg` executable is available in your `PATH`.  
   The bot uses `discord.FFmpegPCMAudio` internally to transcode audio for Discord.

3. **Configure your bot token:**  
   - Create a copy of `.env.example` named `.env` and paste your Discord bot token in place of the placeholder.  
   - Alternatively, set an environment variable named `DISCORD_TOKEN` in your shell or operating system.  
   Keep your token secret – **never commit it to source control**.

4. **Run the bot:**

   ```bash
   python bot.py
   ```

Once running, invite the bot to your server and use the commands described below.

## Commands

The bot uses a command prefix of `!`.  Commands must be issued in a text channel where the bot has access.

| Command          | Description                                                                           |
|------------------|---------------------------------------------------------------------------------------|
| `!join`          | Join the voice channel the invoking user is connected to.                             |
| `!leave`         | Disconnect from the voice channel and clear the queue.                                |
| `!play <query>`  | Play a song from YouTube. Provide a URL or search query.                              |
| `!pause`         | Pause the currently playing song.                                                     |
| `!resume`        | Resume playback if paused.                                                            |
| `!skip`          | Skip the current song and begin playing the next item in the queue.                    |
| `!prev`          | Play the previous song, if available.                                                  |
| `!queue`         | Display the current queue of songs.                                                   |

## How it works

### Downloading and streaming audio

The bot uses the `yt‑dlp` library to fetch audio data from YouTube.  
`yt‑dlp` is configured to download only the best available audio track and to run quietly to reduce log noise, similar to the `youtube_dl` configuration described in the Python Land tutorial【562454067469386†L183-L224】.  
FFmpeg is then used to convert that audio stream into an opus-encoded stream that Discord can play【562454067469386†L431-L480】.

### Queue and playback management

Songs are stored in an internal list and played sequentially.  When a user issues a `!play` command, the bot will search YouTube (if the argument is not already a URL) and add the resulting track to the queue.  If nothing is currently playing, the bot immediately begins playback.  Otherwise, the new song waits until the current song finishes.

Playback commands such as pause, resume and stop use the `discord.VoiceClient` interface provided by `discord.py` to control audio playback【562454067469386†L431-L480】.  Skipping triggers the next song in the queue, while the previous command rewinds the playback index to replay an earlier song.

## Notes

* This bot is for educational purposes.  Downloading audio from YouTube may be against their Terms of Service【562454067469386†L183-L190】.  Use responsibly.
* The GitHub connector in this environment does not support creating new repositories.  You will need to create a repository and push this project manually.  The files in this folder (`bot.py`, `README.md`, `requirements.txt` and `.env.example`) are ready to be committed.
