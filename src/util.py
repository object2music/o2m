import configparser, sys
from pathlib import Path
from os import path

'''
    Get mopidy config file for mac or linux paths
'''
def get_config():
        config = configparser.ConfigParser()
        
        linux_path = '/etc/mopidy/mopidy.conf'
        mac_path = str(Path.home()) + '/.config/mopidy/mopidy.conf'
        config_path = None

        if path.exists(linux_path):
            config_path = linux_path
        elif path.exists(mac_path):
            config_path = mac_path
        else:
            print('not found')
            return None
        
        config.read(config_path)
        return config
        


if __name__ == "__main__":
    config = get_config()
    print(config['spotify'])
