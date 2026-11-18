"""Synthetic shot fixtures, clearly labelled and never reported as real QPU results."""
import math
import numpy as np
from .plans import validate_plan
from .analysis import make_dataset


def synthetic_dataset(plan,shots=4096,seed=123):
    validate_plan(plan)
    if type(shots) is not int or not 1<=shots<=1000000: raise ValueError("shots must be in 1..1000000")
    if type(seed) is not int or not 0<=seed<2**32: raise ValueError("seed must be in 0..2**32-1")
    rng=np.random.default_rng(seed); counts={}
    for spec in plan["circuits"]:
        n=spec["n_qubits"]; meta=spec["metadata"]; benchmark=spec["benchmark"]
        if benchmark=="ghz":
            if meta["basis"]=="z":
                bits=np.repeat(rng.integers(0,2,size=(shots,1)),n,axis=1)
            else:
                bits=rng.integers(0,2,size=(shots,n))
                bits[:,-1]=(np.sum(bits[:,:-1],axis=1)%2)^(meta["phase_index"]%2)
            bits^=(rng.random((shots,n))<.015).astype(int)
        elif benchmark=="mirror":
            bits=rng.integers(0,2,size=(shots,n)); bits[rng.random(shots)<math.exp(-.015*n*meta["depth"])]=0
        else:
            q=meta["logical_qubit"]
            if benchmark=="readout": probability=.025 if meta["prepared"]==0 else .965
            elif benchmark=="t1": probability=.025+.94*math.exp(-meta["time_us"]/75.)
            else: probability=.5+.47*math.exp(-meta["time_us"]/55.)
            bits=np.zeros((shots,n),dtype=int); bits[:,q]=(rng.random(shots)<probability).astype(int)
        result={}
        for sample in bits:
            key="".join(str(int(b)) for b in reversed(sample))
            result[key]=result.get(key,0)+1
        counts[spec["id"]]=result
    return make_dataset(plan,counts,execution_kind="synthetic",backend_name="synthetic-fixture",
                        metadata={"fixture_seed":seed,"fixture_model":"Family-specific shot distributions, not a gate-level noise simulator",
                                  "nominal_t1_us":75.,"nominal_t2_echo_us":55.})
