import sys
import torch
import torch.nn as nn

sys.path.append("/proj/kuhl_lab/evopro/")
from evopro.score_funcs.score_funcs import get_seq_indices, distance
from evopro.utils.pdb_parser import get_coordinates_pdb, get_ca_coordinates_pdb

def gather_edges(edges, neighbor_idx):
    # Features [B,N,N,C] at Neighbor indices [B,N,K] => Neighbor features [B,N,K,C]
    neighbors = neighbor_idx.unsqueeze(-1).expand(-1, -1, -1, edges.size(-1))
    edge_features = torch.gather(edges, 2, neighbors)
    return edge_features

def Intersection(lst1, lst2):
    return set(lst1).intersection(lst2)

class ProteinContacts(nn.Module):
    def __init__(self, pdb_str, top_k=30):
        
        """ Extract protein features """
        
        super(ProteinContacts, self).__init__()

        self.top_k = top_k
        self.X, self.mask = self._get_features(pdb_str)

    def _get_features(self, pdb_str):
        """ Extract protein features
        X: coordinates of Ca atoms
        mask: binary mask of Ca atoms"""
        
        # Get protein features
        X = get_ca_coordinates_pdb(pdb_str)
        mask = torch.ones(len(X))
        
        X = torch.tensor(X, dtype=torch.float32)
        #mask = torch.tensor(mask, dtype=torch.float32)
        
        X = X[None]
        mask = mask[None]
        
        return X, mask
    
    def _dist(self, eps=1E-6):
            """ Pairwise euclidean distances """
            # Convolutional network on NCHW
            #print(self.X.shape, self.mask.shape)
            mask_2D = torch.unsqueeze(self.mask,1) * torch.unsqueeze(self.mask,2)
            dX = torch.unsqueeze(self.X,1) - torch.unsqueeze(self.X,2)
            D = mask_2D * torch.sqrt(torch.sum(dX**2, 3) + eps)

            # Identify k nearest neighbors (including self)
            D_max, _ = torch.max(D, -1, keepdim=True)
            D_adjust = D + 2 * (1. - mask_2D) * D_max
            D_neighbors, E_idx = torch.topk(D_adjust, min(self.top_k, self.X.shape[-2]), dim=-1, largest=False)
            mask_neighbors = gather_edges(mask_2D.unsqueeze(-1), E_idx)

            return D_neighbors, E_idx, mask_neighbors

def score_contacts_pae_weighted_efficient(results, pdb, reslist1, reslist2, dist=4, contact_cap=36, dsobj=None, first_only=False):
    #start = time.time()
    if dsobj:
        reslist1 = get_seq_indices(dsobj, reslist1, first_only=first_only)
        reslist2 = get_seq_indices(dsobj, reslist2, first_only=first_only)

    chains, residues, resindices = get_coordinates_pdb(pdb)
    #print(residues, resindices)
    pae = results['pae_output'][0]
    
    prot = ProteinContacts(pdb, top_k=36)
    _, E_idx, _ = prot._dist()
    neighbors = E_idx.numpy()[0]
    #print(neighbors, neighbors.shape)
    
    reslist1_inds = [resindices[res] for res in reslist1]
    reslist2_inds = [resindices[res] for res in reslist2]
    #print(reslist1_inds, reslist2_inds)
    resindices_rev = dict((v, k) for k, v in resindices.items())

    score = 0
    pairs = []
    for res1_ind in reslist1_inds:
        neighbors_res1 = neighbors[res1_ind]
        #print(neighbors_res1, reslist2_inds)
        hits = list(Intersection(neighbors_res1, reslist2_inds))
        #print(hits)
        for res2_ind in hits:
            contact = 0
            weight = 0
            res1 = resindices_rev[res1_ind]
            res2 = resindices_rev[res2_ind]
            for atom1 in residues[res1]:
                for atom2 in residues[res2]:
                    if distance(atom1[2], atom2[2])<=dist:
                        pair = (res1, res2)
                        pair_rev = (res2, res1)
                        if pair not in pairs and pair_rev not in pairs:
                            if len(pairs)<contact_cap:
                                contact=1

                                pae_contact = pae[res1_ind][res2_ind] + pae[res2_ind][res1_ind]
                                weight = (70-pae_contact)/70
                                pairs.append(pair)

            score = score + contact*weight
    
    return pairs, score
