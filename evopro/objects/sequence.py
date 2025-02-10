import json, re, random, copy
import sys 
sys.path.append("/proj/kuhl_lab/evopro2/")
from objects.chemical import aa2num, num2aa, alphabet
from utils.wrappers import create_new_seq_mpnn
from utils.utils import merge_related_lists
from utils.parsing_utils import count_nonH_atoms

def sequencestring_to_sequence(seqstr):
    l = []
    for x in seqstr:
        if x == "X":
            print("HERE", aa2num[x])
        l.append(aa2num[x])
    return l
def sequence_to_sequencestring(seq):
    return "".join([num2aa[x] for x in seq])

class DesignSeq():
    
    def __init__(self, conf=None, template_desseq=None, sequence=None, jsonfile=None):
        self.scored = False
        self.score = []
        self.average_raw_score = 0
        
        if conf:
            if conf.flags.residue_specs_file is not None:
                self.chains = self._load_from_json(conf.flags.residue_specs_file)
        
        elif template_desseq is not None and sequence is not None:
            self.chains = copy.deepcopy(template_desseq.chains)
            self._update_sequence(sequence)
        
        elif jsonfile is not None:
            self.chains = self._load_from_json(jsonfile)
            
        else:
            raise ValueError("Cannot initialize DesignSeq object. Must provide either a json file or a template DesignSeq object+sequence string.")
            
    def __str__(self):
        strings = []
        for chain in self.chains:
            strings.append(self.chains[chain].get_sequence_string())
        
        return ','.join(strings)
    
    def get_lengths(self, chain):
        c = self.chains[chain]
        if c.type == "ligand":
            return count_nonH_atoms(c.sequence[0])
        else:
            return self.chains[chain].length
    
    def get_residue_lengths(self, chain):
        c = self.chains[chain]
        if c.type == "ligand":
            return len(c.sequence)
        else:
            return self.chains[chain].length
    
    def get_chain_sequence(self, chain):
        return self.chains[chain].get_sequence_string()
    
    def get_chain_type(self, chain):
        return self.chains[chain].type
    
    def get_average_score(self):
        if len(self.score)>0:
            self.average_raw_score = sum([x[0][0] for x in self.score])/len(self.score)
        return self.average_raw_score

    def _load_from_json(self, jsoninputsfile):
        chains = {}
        """load a DesignSeq object from a json file with specifications"""
        with open(jsoninputsfile, "r") as inpf:
            jdata = json.load(inpf)

        #TODO ensure jdata has all the necessary keys in generate json
        for chain_id in jdata["chains"]:
            chain = jdata["chains"][chain_id]
            chain_obj = Chain(type=chain["type"], sequence=chain["sequence"])
            chains[chain_id] = chain_obj
        
        for mod in jdata["modifications"]:
            chains[mod["chain"]].modifications.append(mod)
            
        #load mutable and symmetry information
        for mut in jdata["designable"]:
            ch = mut["chain"]
            chains[ch].mutable.append(mut)
            
        for sym in jdata["symmetric"]:
            symmetric = sym
            symmetric_ch_pos = []
            for s in symmetric:
                ch, pos = re.split('(\d+)',s)[:2]
                symmetric_ch_pos.append((ch, pos))
            
            for s in symmetric:
                ch_, pos_ = re.split('(\d+)',s)[:2]
                for ch, pos in symmetric_ch_pos:
                    if ch == ch_ and pos == pos_:
                        continue
                    else:
                        chains[ch].symmetric[int(pos)-1].append(ch_+pos_)
        
        return chains
    
    def _get_json(self):
        jdata = {"chains":{}}
        for chain in self.chains:
            jdata["chains"][chain] = {"sequence":self.chains[chain].get_sequence_string(), "type":self.chains[chain].type}
        
        jdata["designable"] = []
        jdata["symmetric"] = []
        jdata["modifications"] = []
        for chain in self.chains:
            for mut in self.chains[chain].mutable:
                new_mut = copy.deepcopy(mut)
                mut_to = new_mut["MutTo"]
                if "all" in mut_to:
                    if mut_to == "all":
                        include = alphabet
                        omit += new_mut['WTAA']
                    else:
                        omit = list(mut_to.split("-")[1])
                        if new_mut['WTAA'] not in omit:
                            omit += new_mut['WTAA']
                        
                    include = [x for x in alphabet if x not in omit]

                else:
                    include = list(mut_to)
                new_mut["MutTo"] = "".join(include)
                
                jdata["designable"].append(new_mut)
            symmetric = []
            for i, sym in enumerate(self.chains[chain].symmetric):
                for s in sym:
                    symmetric.append([chain+str(i+1),s])
            for mod in self.chains[chain].modifications:
                jdata["modifications"].append(mod)
                
            symmetric = merge_related_lists(symmetric)
            jdata["symmetric"].extend(symmetric)

        return jdata

    def _update_sequence(self, sequence):
        # print(sequence)
        for chain, newseq in zip(self.chains, sequence.split(",")):
            nseq = sequencestring_to_sequence(newseq)
            new_seq = []
            skip = False
            for i, s in enumerate(nseq):
                if s == 21:
                    #TODO: check why ligandmpnn adds an extra residue
                    new_seq.append(self.chains[chain].sequence[i])
                    skip = True
                else:
                    if not skip:
                        new_seq.append(s)
                    skip = False
            # print(len(nseq), len(new_seq), len(self.chains[chain].sequence))
            self.chains[chain].sequence = new_seq
            for mut in self.chains[chain].mutable:
                if aa2num[mut["WTAA"]] != self.chains[chain].sequence[mut["resid"]-1]:
                    mut["WTAA"] = num2aa[self.chains[chain].sequence[mut["resid"]-1]]

        self._update_symmetry()        
    
    def _update_symmetry(self):
        for chain in self.chains:
            #print(self.chains[chain].sequence)
            # print(self.chains[chain].symmetric, self.chains[chain].sequence)
            for i in range(len(self.chains[chain].sequence)):
                #print(i)
                for sym in self.chains[chain].symmetric[i]:
                    ch, pos = re.split('(\d+)',sym)[:2]
                    self.chains[ch].sequence[int(pos)-1] = self.chains[chain].sequence[i]
                    for mut in self.chains[ch].mutable:
                        if aa2num[mut["WTAA"]] != self.chains[chain].sequence[mut["resid"]-1]:
                            mut["WTAA"] = num2aa[self.chains[chain].sequence[mut["resid"]-1]]
        
    def _mutate_random(self, conf):
        all_dna_bases = ["a", "c", "g", "t"]
        all_rna_bases = ["b", "d", "h", "u"]
        new_desseq = copy.deepcopy(self)
        
        mutable = []
        for chain in self.chains:
            mutable.extend(self.chains[chain].mutable)
        num_mut = round(conf.flags.mutation_percents * len(mutable))
        
        if num_mut<1:
            num_mut=1
        if conf.flags.single_mut_only:
            num_mut = 1
            
        mut_set = random.sample(mutable, len(mutable))
        
        #TODO: load weights from mpnn bias file if provided
        
        weights = [1 for x in alphabet]
        
        num_mut_curr = 0
        while num_mut_curr < num_mut:
            mut_id = mut_set[num_mut_curr]
            mut_to = mut_id['MutTo']
            omit = ""
            if "all" in mut_to:
                if mut_to == "all":
                    include = alphabet
                    omit += mut_id['WTAA']
                else:
                    omit = list(mut_to.split("-")[1])
                    if mut_id['WTAA'] not in omit:
                        omit += mut_id['WTAA']
                    
                include = [x for x in alphabet if x not in omit]

            else:
                include = list(mut_to)
                
            weights = [1 if x in include else 0 for x in alphabet]
            #disabling "X" option from being selected for mutation
            weights[-1] = 0
                
            chain = mut_id['chain']
            id = mut_id['resid']
            
            if self.chains[chain].type == "protein":
                new_aa = random.choices(alphabet, weights)[0]
            # elif self.chains[chain].type == "rna":
            #     new_aa = random.choices(all_rna_bases, weights)[0]
            # elif self.chains[chain].type == "dna":
            #     new_aa = random.choices(all_dna_bases, weights)[0]
            else:
                print(self.chains[chain].type)
                raise ValueError("Invalid type of chain for mutation. Must be protein chain.")
            
            new_desseq._replace_residue(chain, id, new_aa)
            #print("after mutation", new_mut[mut_id])
            num_mut_curr+=1

        return new_desseq
    
    def _mutate_mpnn(self, conf, pool):
        new_seq = create_new_seq_mpnn(conf, pool)
        new_desseq = DesignSeq(template_desseq=self, sequence=new_seq)
        return new_desseq
        
    def _replace_residue(self, chain, id, new_aa):
        self.chains[chain].sequence[id-1] = aa2num[new_aa]
        for mut in self.chains[chain].mutable:
            if mut["resid"] == id and mut["chain"] == chain:
                mut["WTAA"] = new_aa
        self._update_symmetry()
    
    def mutate(self, pool, conf, seq_pred_mode="random"):
        # all_aas = ["A", "C", "D", "E", "F", "G", "H", "I", "K", "L", "M", "N", "P", "Q", "R", "S", "T", "V", "W", "Y"]
        # all_dna_bases = ["a", "c", "g", "t"]
        # all_rna_bases = ["b", "d", "h", "u"]
        
        if seq_pred_mode == "mpnn":
            return self._mutate_mpnn(conf, pool)
        
        elif seq_pred_mode == "random":
            while True:
                new_desseq = self._mutate_random(conf)
                #check if duplicate with same sequence
                if str(new_desseq) not in pool.data:
                    return new_desseq
                else:
                    continue
        
    def get_scores(self):  
        sorted_scores = sorted(self.score, key=lambda x: x[0])
        return sorted_scores
        
    
    def set_score(self, conf, score, pdbs, results):
        self.score.insert(0, (score, pdbs, results))
        if len(self.score) >= conf.flags.num_repeat_scoring:
            self.scored = True
        
        self.average_raw_score = sum([x[0][0] for x in self.score])/len(self.score)
    
class Chain:
    
    def __init__(self, type='protein', length=100, sequence=None):
        self.type = type
        self.length = length
        
        if sequence is not None:
            if self.type == "ligand":
                self.sequence = [sequence]
            else:
                self.sequence = [aa2num[x] for x in list(sequence)]
            self.length = len(self.sequence)
        else:
            self._init_empty_sequence()
        
        self.mutable = []
        self.symmetric = [[] for x in list(sequence)]
        self.modifications = []
        
    def __eq__(self, other):
        return self.get_sequence_string() == other.get_sequence_string()

    def __str__(self):
        return self.get_sequence_string()

    def __hash__(self):
        return hash(self.get_sequence_string())
    
    def get_sequence_string(self):
        #print(self.sequence)
        if self.type == "ligand":
            return "".join(self.sequence)
        else:
            return "".join([num2aa[x] for x in self.sequence])
    
    def sequencestring_to_sequence(self, seqstr):
        if self.type == "ligand":
            return seqstr
        else:
            return [aa2num[x] for x in seqstr]
    
    def sequence_to_sequencestring(self, seq):
        if self.type == "ligand":
            return "".join(seq)
        else:
            return "".join([num2aa[x] for x in seq])
    
    def _init_empty_sequence(self):
        self.sequence = [aa2num['?'] for _ in range(self.length)]
                

if __name__ == "__main__":
    desseq = DesignSeq( jsonfile="residue_specs.json")
    # desseq2 = DesignSeq(template_desseq=desseq, sequence="MRCVGVGNRDFVEGLSGATWVDVVLEHGGCVTTMAKNKPTLDIELQKTEATQEGGGGENLKYTVIITVHTGDQHQVGNETQGVTAEITPQASTTEAILPEYGTLGLECSPRTGLDFGGGGGGHLKCRLKM,MRCVGVGNRDFVEGLSGATWVDVVLEHGGCVTTMAKNKPTLDIELQKTEATQEGGGGENLKYTVIITVHTGDQHQVGNETQGVTAEITPQASTTEAILPEYGTLGLECSPRTGLDFGGGGGGHLKCRLKM,actgactg")
    print(desseq._get_json())