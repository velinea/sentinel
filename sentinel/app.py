from sentinel.config import load_config


def main():
    config = load_config()

    print("Sentinel starting...")
    print(f"HA: {config['homeassistant']['url']}")
    print(f"Cameras: {len(config['cameras'])}")
