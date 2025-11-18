import hashcash
import threading
import time
import sys

from tests.hashcash import hashcash_mint

print("Welcome...")
print("Is the GIL disabled:", getattr(sys,'_is_gil_enabled','No attribute'))

def worker(name, num_resources, difficulty):
    for n in range(num_resources):
        hashcash_stamp = hashcash_mint(name, difficulty)
        print(name+" Stamp["+str(n)+"]: "+hashcash_stamp)

def test(num_workers, num_resources, difficulty) :

    threads = []

    for i in range(num_workers):
        name = str("Worker-"+str(i+1))
        t = threading.Thread(target=worker, name=name, args=[name, num_resources, difficulty])
        threads.append(t)

    begin = time.time()

    for t in threads:
        print("Starting", t.name)
        t.start()

    for t in threads:
        t.join()
        print("Complete", t.name)

    end = time.time()

    elapsed = end-begin

    return elapsed

print("\n1 Worker : 12 resources : 18 difficulty...")
one_worker_18 = str(test(1,12, 18))

print("\n4 Workers : 3 resources each : 18 difficulty...")
four_workers_18 = str(test(4,3, 18))

print("\n12 Workers : 1 resource each : 18 difficulty...")
twelve_workers_18 = str(test(12,1, 18))

print("\n1 Worker : 12 resources : 20 difficulty...")
one_worker_20 = str(test(1,12, 20))

print("\n4 Workers : 3 resources each : 20 difficulty...")
four_workers_20 = str(test(4,3, 20))

print("\n12 Workers : 1 resource each : 20 difficulty...")
twelve_workers_20 = str(test(12,1, 20))

print("Elapsed Time 1 worker, 12 resources, 18 difficulty: "+one_worker_18)
print("Elapsed Time 4 workers, 3 resources each, 18 difficulty: "+four_workers_18)
print("Elapsed Time 12 workers, 1 resource each, 18 difficulty: "+twelve_workers_18)

print("Elapsed Time 1 worker, 12 resources, 18 difficulty: "+one_worker_20)
print("Elapsed Time 4 workers, 3 resources each, 18 difficulty: "+four_workers_20)
print("Elapsed Time 12 workers, 1 resource each, 18 difficulty: "+twelve_workers_20)