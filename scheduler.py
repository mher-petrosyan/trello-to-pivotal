import sched
import time

s = sched.scheduler(time.time, time.sleep)


def print_periodically(a='default'):
    s.enter(3, 1, print_periodically)
    print_time()


def periodically(func):
    def wrap(f):
        s.enter(3, 1, wrap, kwargs={'f': f})
        f()

    s.enter(1, 1, wrap, kwargs={'f': func})
    s.run()


def print_time(a='default'):
    print("From print_time", time.time(), a)


def print_some_times():
    print(time.time())
    s.enter(1, 1, print_periodically, kwargs={'a': 'keyword'})
    s.run()
    print(time.time())


# print_some_times()


def say_whee(*args):
    print("Whee!")


periodically(say_whee)
