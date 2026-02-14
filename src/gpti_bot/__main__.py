from gpti_bot.cli import main
import time

if __name__ == "__main__":
    # Show CLI once
    main()

    # Keep container alive (daemon mode)
    print("\n[gpti] Bot idle — waiting for commands…")
    while True:
        time.sleep(3600)