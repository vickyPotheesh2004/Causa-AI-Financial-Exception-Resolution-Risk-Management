from cause_ai.server import serve

if __name__ == "__main__":
    import os
    serve(os.environ.get("HOST", "127.0.0.1"), int(os.environ.get("PORT", "8000")))
