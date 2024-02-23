# Test script for repeatable psuedorandom number generation
#import md5
import hashlib
import random

r_random_index = 0

def repeatable_random_generator (seed):
    hash = str(seed).encode('utf-8')
    while True:
        hash = hashlib.md5(hash).digest()
        for c in hash:
            yield c
            #yield ord(c)

def get_r_random (high_val):
    global r_random_index
    #r_random_val = repeatable_random ('test')
    raw_random = 0
    for v in zip(range(10), repeatable_random_generator ('test'+str(r_random_index))):
        raw_random += v[1]
    r_random_index += 1
    return raw_random % high_val

def main ():
    for _ in range (40):
        print (f"{get_r_random (1584)}")
    
    #random.seed (0)
    #for i in range(10):
    #    rand_int = random.randint (0,1)
    #    print (f"Random integer: {rand_int}")
    


if __name__ == "__main__":
    main()