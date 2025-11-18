import threading
import time
import sys

print("Welcome...")
print("Is the GIL disabled:", getattr(sys,'_is_gil_enabled','No attribute'))

def worker(name):
    for n in range(100000):
        print(name+str(n))

threads = []

for i in range(4):
    t = threading.Thread(target=worker, args=str(i+1))
    threads.append(t)

begin = time.time()

for t in threads:
    print("Starting", t.name)
    t.start()
    # time.sleep(1)

for t in threads:
    t.join()
    print("Complete", t.name)

end = time.time()

elapsed = end-begin

print("Elapsed Time: "+str(elapsed))