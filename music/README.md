#   Music Library

Place your background music tracks here.

## Supported formats

- `.mp3` (recommended)
- `.m4a` / `.aac`
- `.wav`
- `.ogg`
- `.flac`

## Usage

1. Drop your `.mp3` files into this folder
2. When rendering a project, pass the music path:

```bash
curl -X POST http://localhost:8000/api/projects/1/render \
  -H 'Content-Type: application/json' \
  -d '{"music_path": "music/chill-lofi.mp3", "music_volume": 0.3}'
```

## Where to get free music

-   [Pixabay Music](https://pixabay.com/music/) — royalty-free
-   [Uppbeat](https://uppbeat.io/) — free with attribution
-   [YouTube Audio Library](https://www.youtube.com/audiolibrary) — free
-   [Mixkit](https://mixkit.co/free-stock-music/) — free

## Tips

- **Volume:** `0.2`–`0.4` is a good range for background music (30% = `0.3`)
- **Format:** MP3 192-320 kbps works best
- **Duration:** Short tracks (60-120s) loop automatically to match video length
- **Fade:** Music fades in over 1.5s and fades out over 2s
