import yt_dlp


def get_video_title(url):
    options = {
        "quiet": True,
        "no_warnings": True,
    }

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(
                url,
                download=False
            )

            return info.get("title", "Unknown Title")

    except Exception as e:
        print("YouTube lookup failed:", e)
        return None