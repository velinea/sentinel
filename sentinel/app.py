from sentinel.config import load_config
from sentinel.ha.client import HomeAssistantClient
from sentinel.storage.snapshots import SnapshotStorage

def main():
    config = load_config()
    
    client = HomeAssistantClient(
        config.homeassistant.url,
        config.homeassistant.token,
    )
    
    storage = SnapshotStorage(config.storage.path)
    for camera in config.cameras:
        image = client.get_snapshot(camera.entity)
        storage.save(camera.name, image)
