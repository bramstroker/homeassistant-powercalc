import glob
from os.path import basename, dirname, isfile

modules = glob.glob(dirname(__file__) + "/*.py")

__all__ = [basename(f)[:-3] for f in modules if isfile(f)]
