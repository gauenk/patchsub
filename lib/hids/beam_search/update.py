"""

Update the next state using the proposed state values

"""


# -- python --
from easydict import EasyDict as edict

# -- linalg --
import torch as th
import numpy as np
from einops import rearrange,repeat

# -- this package --
from hids.l2_search import l2_search
from hids.utils import optional

# -- local --
from .inds import *
from .state_utils import get_ref_num,compute_ordering

def update_state(state,pstate,data,sigma,cnum,use_full=True):
    """
    Desc: Set the current state according to the
    best "nsearch" from the proposed states

    """

    # -- shapes --
    BS,bW = state.vals.shape
    BS,bW,sW = pstate.vals.shape
    B,bW,sW,sN,D = pstate.vecs.shape

    # -- flatten proposed state --
    vals = rearrange(pstate.vals,'b w s -> b (w s)')
    inds = rearrange(pstate.inds,'b w s n -> b (w s) n')
    vecs = rearrange(pstate.vecs,'b w s n d -> b (w s) n d')
    # order = rearrange(pstate.order,'b w s n -> b (w s) n')
    # print("order.shape: ",order.shape)

    # -- take topk --
    inds_topk = th.topk(vals,bW,1,False).indices
    aug1_inds = repeat(inds_topk,'b k -> b k n',n=sN)
    aug2_inds = repeat(aug1_inds,'b k n -> b k n d',d=D)
    # aug3_inds = repeat(inds_topk,'b k -> b k n',n=N)
    # print("aug3_inds.shape: ",aug3_inds.shape)

    # -- gather --
    state.vals[...] = th.gather(vals,1,inds_topk)
    state.inds[...] = th.gather(inds,1,aug1_inds)
    state.vecs[...] = th.gather(vecs,1,aug2_inds)
    # state.order[...] = th.gather(order,1,aug3_inds)

    # -- order inds in decreasing value --
    # sinds = th.argsort(state.inds[:,:,:cnum+1],2)
    # state.inds[...,:cnum+1] = th.gather(state.inds[:,:,:cnum+1],2,sinds)
    # print("state.inds.shape: ",state.inds.shape)
    # print(state.inds[0,0,:cnum+1])
    # print(state.inds[0,0,:cnum+2])
    # print(state.inds[0,1,:cnum+1])
    # print(state.inds[0,1,:cnum+2])

    # -- update mask from inds --
    state.imask[...] = 0
    state.imask[...].scatter_(2,state.inds[:,:,:cnum+1],1)

def select_final_state(state):

    # -- shapes --
    B,W,N,D = state.vecs.shape

    # -- take topk --
    top1_inds = th.topk(state.vals,1,1,False).indices
    top1_aug1_inds = repeat(top1_inds,'b w -> b w n',n=N)
    top1_aug2_inds = repeat(top1_aug1_inds,'b w n -> b w n d',d=D)

    # -- gather --
    vals = th.gather(state.vals,1,top1_inds)[:,0]
    inds = th.gather(state.inds,1,top1_aug1_inds)[:,0]
    vecs = th.gather(state.vecs,1,top1_aug2_inds)[:,0]

    return vals,inds,vecs

def terminate_early(state,data,sigma,snum,cnum,sv_fxn,sv_params):
    """
    Desc: Add all remaining indices from the original l2
    ordering and compare results across particles

    """
    # -- shapes --
    device = state.imask.device
    bsize,nparticles = state.imask.shape[:2]
    bsize,num,dim = data.shape

    # -- init vec --
    fnum = snum - cnum - 1

    # -- update state --
    for p in range(nparticles):

        # -- reference info --
        ref_num = get_ref_num(state,cnum,sv_params)
        ref = th.mean(state.vecs[:,p,:ref_num],1,keepdim=True)

        # -- compute order --
        ref_sigma = sigma / math.sqrt(ref_num)
        s_sigma = sigma**2 + ref_sigma**2
        compute_ordering(state,ref,data,s_sigma)
        # if p == 0: print(state.order[0,:])

        # -- order inds --
        rinds_ordered(state.inds[:,p,:cnum+1],state.order,
                      cnum+1,snum,state.remaining)

        # -- augment remaining inds --
        aug_remain = repeat(state.remaining,'b n -> b n d',d=dim)

        # -- append to current state --
        state.inds[:,p,cnum+1:] = state.remaining[:,:fnum]
        state.vecs[:,p,cnum+1:,:] = th.gather(data,1,aug_remain[:,:fnum])

    # -- update values --
    sv_fxn(state.vals[:,:,None],state.vecs[:,:,None],snum,sv_params)


