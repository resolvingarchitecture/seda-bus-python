import threading
import time
import sys

print("Welcome...")
print("Is the GIL disabled:", not sys._is_gil_enabled())

def worker(name):
    start = time.time()
    while time.time() - start < 5:
        time.sleep(1)
        print(name)

threads = []

for i in range(4):
    t = threading.Thread(target=worker, args=str(i+1))
    threads.append(t)

for t in threads:
    print("Starting", t.name)
    t.start()
    time.sleep(1)

for t in threads:
    t.join()
    print("Complete", t.name)