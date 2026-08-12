from sentinel.config import load_config
from sentinel.ha.client import HomeAssistantClient

def main():
    config = load_config()
    
    client = HomeAssistantClient(
        config.homeassistant.url,
        config.homeassistant.token,
    )
    
    image = client.get_snapshot(
        config.cameras[0].entity
    )
    
    with open("snapshot.jpg", "wb") as f:
        f.write(image)
