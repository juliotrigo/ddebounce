from contextlib import contextmanager
import functools

import redis
import wrapt


class Lock:

    def __init__(self, client, default_ttl=None):
        self.client = client
        self.default_ttl = default_ttl or 30

    format_key = 'lock:{}'.format

    def acquire(self, key):
        key = self.format_key(key)
        pipe = self.client.pipeline()
        pipe.incr(key)
        pipe.expire(key, self.default_ttl)
        count, _ = pipe.execute()
        return count <= 1

    def release(self, key):
        key = self.format_key(key)
        pipe = self.client.pipeline()
        pipe.getset(key, 0)
        pipe.expire(key, self.default_ttl)
        count, _ = pipe.execute()
        count = int(count) if count else 0
        return count > 1

    def debounce(
        self, wrapped=None, key=None, repeat=False, callback=None
    ):

        if wrapped is None:
            return functools.partial(
                self.debounce, key=key, repeat=repeat, callback=callback)

        format_key = key or '{0}({{0}})'.format(wrapped.__name__).format

        @wrapt.decorator
        def wrapper(wrapped, instance, args, kwargs):
            key = format_key(*args, **kwargs)
            if self.acquire(key):
                try:
                    result = wrapped(*args, **kwargs)
                finally:
                    turns = self.release(key)
                if turns:
                    if callback:
                        callback(*args, **kwargs)
                    if repeat:
                        return wrapper(wrapped)(*args, **kwargs)
                return result

        return wrapper(wrapped)


def debounce(lock, wrapped=None, key=None, repeat=False, callback=None):
    return Lock(lock).debounce(wrapped, key, repeat, callback)


def debouncemethod(lock, wrapped=None, key=None, repeat=False, callback=None):

    @wrapt.decorator
    def wrapper(wrapped, instance, args, kwargs):
        decorated = Lock(lock(instance)).debounce(wrapped, key, repeat, callback)
        return decorated(*args, **kwargs)

    return wrapper
