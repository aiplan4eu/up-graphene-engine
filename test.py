from queue import Queue
from time import sleep

def iterator():
    for i in range(10):
        yield i
        sleep(1)


def a():
    for i in iterator():
        yield i*i

q = Queue()
def b():
    q.put(a())

def c():
    r = q.get()
    return r

b()

for i in c():
    print(i, flush=True)
