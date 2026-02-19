import argparse
import sys


def main():
    parser = argparse.ArgumentParser(
        prog="accommodation-buddy",
        description="Accommodation Buddy — MLL lesson accommodation tool",
    )
    subparsers = parser.add_subparsers(dest="command")

    # serve command
    serve_parser = subparsers.add_parser("serve", help="Start the web server")
    serve_parser.add_argument(
        "--scaffolding-model", default="llama3",
        help="Ollama model name for accommodation generation (default: llama3)",
    )
    serve_parser.add_argument(
        "--ocr-model", default="deepseek-r1",
        help="Ollama model name for OCR/text extraction (default: deepseek-r1)",
    )
    serve_parser.add_argument("--port", type=int, default=8000, help="Web server port")
    serve_parser.add_argument("--host", default="0.0.0.0", help="Web server bind address")
    serve_parser.add_argument("--workers", type=int, default=1, help="Uvicorn worker count")
    serve_parser.add_argument("--db-url", default=None, help="Database connection string")
    serve_parser.add_argument("--redis-url", default=None, help="Redis connection string")
    serve_parser.add_argument("--ollama-url", default=None, help="Ollama server URL")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    if args.command == "serve":
        # Override settings from CLI args
        from accommodation_buddy.config import settings

        settings.scaffolding_model = args.scaffolding_model
        settings.ocr_model = args.ocr_model
        settings.app_port = args.port
        settings.app_host = args.host
        settings.workers = args.workers

        if args.db_url:
            settings.database_url = args.db_url
        if args.redis_url:
            settings.redis_url = args.redis_url
        if args.ollama_url:
            settings.ollama_url = args.ollama_url

        import uvicorn

        uvicorn.run(
            "accommodation_buddy.main:app",
            host=args.host,
            port=args.port,
            workers=args.workers,
            reload=False,
        )


if __name__ == "__main__":
    main()
