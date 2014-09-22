import os
import errno

from itertools import chain


def is_str(s):
    try:
        return isinstance(s, basestring)
    except NameError:
        return isinstance(s, str)


def ensure_dir(path):
    if not os.path.exists(path):
        os.mkdir(path)
    elif not os.path.isdir(path):
        raise OSError(errno.ENOTDIR,
                      "Path already exists and is not a directory")


def flatten(list_):
    """Flatten one level of nesting"""
    return list(chain.from_iterable(list_))


class TeeWriter(object):
    def __init__(self, *files, **kwargs):
        self.should_close = bool(kwargs.get('close', False))
        self.files = files

    def close(self):
        if self.should_close:
            for f in self.files:
                f.close()

    def __del__(self):
        self.close()

    def write(self, data):
        for f in self.files:
            f.write(data)

    def flush(self):
        for f in self.files:
            f.flush()
