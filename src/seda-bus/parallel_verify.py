import threading
import time
import sys

print("Welcome...")
print("Is the GIL disabled:", getattr(sys,'_is_gil_enabled','No attribute'))

def worker(name, amount_of_work):
    for n in range(amount_of_work):
        print(name+str(n))

def test(num_workers, amount_of_work) :

    threads = []

    work_per_worker = amount_of_work // num_workers
    for i in range(num_workers):
        t = threading.Thread(target=worker, args=[str(i+1),work_per_worker])
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

    return elapsed

one_worker = str(test(1,400000))
four_workers = str(test(4,400000))
twelve_workers = str(test(12,400000))

print("Elapsed Time 1,400k: "+one_worker)
print("Elapsed Time 4,400k: "+four_workers)
print("Elapsed Time 12,400k: "+twelve_workers)