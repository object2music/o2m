import configparser
from pathlib import Path
from os import path

def get_config():
        config = configparser.ConfigParser()
        
        etc_path = '/etc/mopidy/mopidy.conf'
        home_path = str(Path.home()) + '/.config/mopidy/mopidy.conf'
        config_path = None

        if path.exists(etc_path):
            config_path = etc_path
        elif path.exists(home_path):
            config_path = home_path
        else:
            print('not found')
            return None
        
        config.read(config_path)
        return config
        
if __name__ == "__main__":
    config = get_config()
    print(config['spotify'])
