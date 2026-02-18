from gpti_bot.cli import main
import os
import time

if __name__ == "__main__":
    # Show CLI once
    main()

    # Keep container alive only when explicitly enabled
    if os.getenv("GPTI_DAEMON", "0") in ("1", "true", "yes"):
        print("\n[gpti] Bot idle — waiting for commands…")
        while True:
            time.sleep(3600)