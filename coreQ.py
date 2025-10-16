__module__ = "Silk QoL & Tiny"
__version__ = "0.0.1"

class Version:
    @staticmethod
    def parse_ver(v):
        return tuple(map(int, v.split(".")))

    @staticmethod
    def check_ver(Current_Version, Required_Version):
        if not Current_Version or not Required_Version:
            raise TypeError
        return Version.parse_ver(Current_Version) >= Version.parse_ver(Required_Version)
