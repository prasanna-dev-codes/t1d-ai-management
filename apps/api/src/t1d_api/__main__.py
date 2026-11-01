"""Loopback-only local server; production startup is intentionally unsupported."""

import uvicorn

from t1d_api.config import Settings


def main() -> None:
    settings = Settings()
    uvicorn.run(
        "t1d_api.app:create_app",
        factory=True,
        host=settings.api_host,
        port=settings.api_port,
        access_log=False,
    )


if __name__ == "__main__":
    main()
