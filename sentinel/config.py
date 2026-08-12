from pathlib import Path
import yaml


def load_config(filename: str = "config.yaml") -> dict:
    path = Path(filename)

    if not path.exists():
        raise FileNotFoundError(
            f"Configuration file '{filename}' not found.\n"
            f"Copy config.example.yaml to {filename} and edit it."
        )

    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)
