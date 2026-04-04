"""Entry point for `python -m claude_chat`."""


def main():
    from claude_chat.app import ClaudeChatApp

    app = ClaudeChatApp()
    app.run()


if __name__ == "__main__":
    main()
