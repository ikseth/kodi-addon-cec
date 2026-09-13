import os
import sys

ADDON_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "addon", "script.cec.control")
sys.path.insert(0, os.path.join(ADDON_DIR, "resources", "lib"))
