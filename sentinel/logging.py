import logging


def setup_logging(level: str = "INFO"):
    logging.basicConfig(
        level=getattr(logging, level),
        format=(
            "%(asctime)s "
            "%(levelname)s "
            "%(message)s"
        ),
        datefmt="%Y-%m-%d %H:%M:%S",
    )