import time

from player import Player


TEST_URL = "https://www.youtube.com/watch?v=x24ckW7vHj4"


def main():
    player = Player()

    print("Resolving YouTube stream...")
    player.play_youtube(TEST_URL)

    print("Playback requested. Press Ctrl+C to stop.")

    try:
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        player.stop()
        print("\nStopped.")


if __name__ == "__main__":
    main()