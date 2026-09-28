"""Serialize expensive operations across every window in this process."""
import threading
import functools
import inspect

_lock=threading.RLock()


def serialized(function):
    signature=inspect.signature(function)
    @functools.wraps(function)
    def wrapped(*args,**kwargs):
        bound=signature.bind(*args,**kwargs);cancel=bound.arguments['cancel']
        from studio_engine import check
        check(cancel)
        while not _lock.acquire(timeout=.1):check(cancel)
        try:
            check(cancel)
            return function(*args,**kwargs)
        finally:_lock.release()
    return wrapped
