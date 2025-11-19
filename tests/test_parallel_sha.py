import hashlib
import threading
import time
import sys

print("Welcome...")
print("Is the GIL disabled:", getattr(sys,'_is_gil_enabled','No attribute'))

def worker(name, num_resources, algorithm):
    for n in range(num_resources):
        data = str(name+str(n)).encode('utf-8')
        alg = hashlib.new(algorithm, data, usedforsecurity=True)
        h = alg.hexdigest()
        # print(name+" Hash["+str(n)+"]: "+h)

def test(num_workers, num_resources, algorithm) :

    threads = []

    for i in range(num_workers):
        name = str("Worker-"+str(i+1))
        t = threading.Thread(target=worker, name=name, args=[name, num_resources, algorithm])
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

print("\n1 Worker : 1.2m hashes : SHA-1...")
one_worker_sha1 = str(test(1,1200000, 'sha1'))

print("\n4 Workers : 300k hashes each : SHA-1...")
four_workers_sha1 = str(test(4,300000, 'sha1'))

print("\n12 Workers : 100k hashes each : SHA-1...")
twelve_workers_sha1 = str(test(12,100000, 'sha1'))

print("\n1 Worker : 1.2m hashes : SHA-512...")
one_worker_sha512 = str(test(1,1200000, 'sha512'))

print("\n4 Workers : 300k hashes each : SHA-512...")
four_workers_sha512 = str(test(4,300000, 'sha512'))

print("\n12 Workers : 100k hashes each : SHA-512...")
twelve_workers_sha512 = str(test(12,100000, 'sha512'))

print("Elapsed Time 1 worker, 1.2m hashes, SHA-1: "+one_worker_sha1)
print("Elapsed Time 4 workers, 300k hashes each, SHA-1: "+four_workers_sha1)
print("Elapsed Time 12 workers, 100k hashes each, SHA-1: "+twelve_workers_sha1)

print("Elapsed Time 1 worker, 1.2m hashes, SHA-512: "+one_worker_sha512)
print("Elapsed Time 4 workers, 300k hashes each, SHA-512: "+four_workers_sha512)
print("Elapsed Time 12 workers, 100k hashes each, SHA-512: "+twelve_workers_sha512)