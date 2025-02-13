import sys
import random
from objects.sequence import DesignSeq

class Pool:

    def __init__(self, conf, desseq):
        self.size = conf.flags.pool_sizes[0]
        self.pool = [desseq]
        self.data = {str(desseq)}
        self.seqs_per_iteration = []
        if conf.flags.starting_seqs_file is not None:
            self._from_starting_seqs_file(desseq, conf.flags.starting_seqs_file)
        
        if len(self.pool) > self.size:
            print("Warning: pool size is smaller than starting sequences file. Truncating pool to size.", len(self.pool), self.size)
            self.pool = self.pool[:self.size]
        while len(self.pool) < self.size/2:
            newobj = desseq.mutate(self, conf, seq_pred_mode="random")
            self.add(newobj)
        
    def __str__(self):
        strings = []
        for seq in self.pool:
            strings.append(str(seq))
        strings.insert(0, "\nPool size: " + str(len(self.pool)) + "\n~~~~~~~~~~~~~~~~~~~~~~~~~")
        strings.append("~~~~~~~~~~~~~~~~~~~~~~~~~\n")
        return "\n".join(strings)
    
    def _from_starting_seqs_file(self, desseq, filename): 
        seqs = []
        pool = []
        with open(filename, "r") as inpf:
            for l in inpf:
                seqs.append(l.strip().split(","))
        for seq in seqs:
            newseq = ",".join(seq)
            newseqobj = DesignSeq(template_desseq=desseq, sequence=newseq)
            self.add(newseqobj)
                
    def add(self, newseq):
        if newseq and str(newseq) not in self.data:
            self.pool.append(newseq)
            self.data.add(str(newseq))

    def purge(self):
        purge_size = int(self.size/2)
        if len(self.pool) > purge_size:
            self.sort_by_score()
            self.pool = self.pool[:purge_size]
            self.data = {str(seq) for seq in self.pool}
    
    def refill(self, conf, seq_pred="mpnn"):
        while len(self.pool) < self.size:
            desseq = random.choice(self.pool)
            newobj = desseq.mutate(self, conf, seq_pred_mode=seq_pred)
            #check if duplicate with same sequence
            if str(newobj) not in self.data:
                self.add(newobj)
                self.data.add(str(newobj))
            
    def sort_by_score(self):
        seqs_and_scores = []
        for seq in self.pool:
            seqs_and_scores.append((seq, seq.get_average_score()))
        sorted_seqs_and_scores = sorted(seqs_and_scores, key=lambda x: x[1])
        
        new_pool = []
        for s in sorted_seqs_and_scores:
            new_pool.append(s[0])
        
        self.pool = new_pool
        self.seqs_per_iteration.append(sorted_seqs_and_scores)
        
    def log_scores(self, csv_file, iter):
        with open(csv_file, "a") as outf:
            outf.write("\nIteration " + str(iter) + "\n")
            for seq in self.pool:
                string = str(seq) + "," + str(seq.get_average_score()) 
                for s in seq.score:
                    for elem in s[0]:
                        if type(elem) == tuple:
                            string += "," + str(elem[0]) + "," + str(elem[0]*elem[1])
                outf.write(string + "\n")
        
# if __name__ == "__main__":
#     desseq = DesignSeq( jsonfile="residue_specs.json")
#     pool = Pool(10, desseq, starting_seqs_file="test_seqs.txt")
