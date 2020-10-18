import configparser, sys, time
from pathlib import Path
from os import path

'''
    Get mopidy config file for mac or linux paths
'''
def get_config2():
        config2 = configparser.ConfigParser()
        
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
        
        config2.read(config_path)
        return config2

def get_config():
        config = configparser.ConfigParser()
        
        linux_path = '/etc/mopidy/o2m.conf'
        mac_path = str(Path.home()) + '/.config/mopidy/o2m.conf'
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
        
        
def RateLimited(maxPerSecond):
    minInterval = 1.0 / float(maxPerSecond)
    def decorate(func):
        lastTimeCalled = [0.0]
        def rateLimitedFunction(*args,**kargs):
            elapsed = time.clock() - lastTimeCalled[0]
            leftToWait = minInterval - elapsed
            if leftToWait>0:
                time.sleep(leftToWait)
            ret = func(*args,**kargs)
            lastTimeCalled[0] = time.clock()
            return ret
        return rateLimitedFunction
    return decorate

if __name__ == "__main__":
    config = get_config()
    print(config['spotify'])
