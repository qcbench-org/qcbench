"""Deterministic hardware experiment plans and portable OpenQASM 3 export."""
import hashlib
import json
import math
import random

BENCHMARKS = ("readout", "ghz", "mirror", "t1", "t2_echo")
DEFAULT_TIMES = (0., 10., 25., 50., 100., 200.)


def _integers(values, name, minimum, maximum, unique=True):
    values = list(values)
    if not values or any(type(x) is not int or not minimum <= x <= maximum for x in values):
        raise ValueError(f"{name} must be nonempty integers in {minimum}..{maximum}")
    if unique and len(set(values)) != len(values):
        raise ValueError(f"{name} must not contain duplicates")
    return values


def make_plan(physical_qubits=(0, 1), benchmarks=BENCHMARKS, times_us=DEFAULT_TIMES,
              mirror_depths=(1, 4, 8), mirror_sequences=3, seed=0):
    """Build an SDK-neutral, deterministic plan; no device execution occurs."""
    physical = _integers(physical_qubits, "physical_qubits", 0, 100000)
    n = len(physical)
    if n > 32: raise ValueError("At most 32 selected qubits are supported")
    benchmarks = list(benchmarks)
    if not benchmarks or len(set(benchmarks)) != len(benchmarks) or any(x not in BENCHMARKS for x in benchmarks):
        raise ValueError("Select unique supported benchmarks")
    if "ghz" in benchmarks and n < 2: raise ValueError("GHZ requires at least two qubits")
    if type(seed) is not int or not 0 <= seed < 2**32: raise ValueError("seed must be in 0..2**32-1")
    if type(mirror_sequences) is not int or not 1 <= mirror_sequences <= 100:
        raise ValueError("mirror_sequences must be in 1..100")
    depths = _integers(mirror_depths, "mirror_depths", 1, 256)
    times = list(times_us)
    if not times or any(type(t) not in (int,float) or not math.isfinite(t) or t < 0 or t > 1e9 for t in times):
        raise ValueError("times_us must contain finite times in 0..1e9")
    if sorted(set(times)) != times: raise ValueError("times_us must be unique and increasing")
    if any(x in benchmarks for x in ("t1", "t2_echo")) and (len(times)<5 or times[0]!=0):
        raise ValueError("Coherence experiments need at least five times, starting at zero")
    times = [float(t) for t in times]
    config = dict(physical_qubits=physical, benchmarks=benchmarks, times_us=times,
                  mirror_depths=depths, mirror_sequences=mirror_sequences, seed=seed)
    circuits = []
    def gate(name, qubits, angle=None, duration_us=None):
        op = dict(name=name,qubits=list(qubits))
        if angle is not None: op["angle"] = angle
        if duration_us is not None: op["duration_us"] = duration_us
        return op
    def add(identifier, benchmark, operations, **metadata):
        circuits.append(dict(id=identifier,benchmark=benchmark,n_qubits=n,operations=operations,metadata=metadata))
    if "readout" in benchmarks:
        for q,p in enumerate(physical):
            for prepared in (0,1):
                add(f"readout.q{q}.p{prepared}","readout",[gate("x",[q])] if prepared else [],
                    logical_qubit=q,physical_qubit=p,prepared=prepared)
    if "ghz" in benchmarks:
        preparation = [gate("h",[0])] + [gate("cx",[q-1,q]) for q in range(1,n)]
        add("ghz.z","ghz",preparation,basis="z")
        for k in range(n):
            theta=k*math.pi/n
            ops=preparation+[gate("barrier",range(n))]
            for q in range(n): ops += [gate("rz",[q],-theta),gate("h",[q])]
            add(f"ghz.phase{k}","ghz",ops,basis="equatorial",phase_index=k,theta=theta)
    if "mirror" in benchmarks:
        rng=random.Random(seed)
        for depth in depths:
            for sequence in range(mirror_sequences):
                forward=[]
                for layer in range(depth):
                    for q in range(n):
                        forward += [gate("ry",[q],rng.uniform(-math.pi,math.pi)),gate("rz",[q],rng.uniform(-math.pi,math.pi))]
                    forward += [gate("cx",[q,q+1]) for q in range(layer%2,n-1,2)]
                    forward += [gate("barrier",range(n))]
                inverse=[]
                for op in reversed(forward):
                    inv=dict(op)
                    if "angle" in inv: inv["angle"]=-inv["angle"]
                    inverse.append(inv)
                add(f"mirror.d{depth}.s{sequence}","mirror",forward+inverse,depth=depth,sequence=sequence)
    for benchmark in ("t1","t2_echo"):
        if benchmark not in benchmarks: continue
        for q,p in enumerate(physical):
            for index,t in enumerate(times):
                if benchmark=="t1":
                    ops=[gate("x",[q]),gate("barrier",range(n)),gate("delay",[q],duration_us=t)]
                else:
                    ops=[gate("ry",[q],math.pi/2),gate("barrier",range(n)),
                         gate("delay",[q],duration_us=t/2),gate("x",[q]),
                         gate("delay",[q],duration_us=t/2),gate("barrier",range(n)),gate("ry",[q],math.pi/2)]
                add(f"{benchmark}.q{q}.t{index}",benchmark,ops,logical_qubit=q,physical_qubit=p,time_us=t)
    return dict(schema_version=1,suite="qpu-characterization-v1",config=config,circuits=circuits)


def validate_plan(plan):
    """Accept only this version's canonical plans; reject edited or ambiguous circuits."""
    if not isinstance(plan,dict) or plan.get("schema_version")!=1 or plan.get("suite")!="qpu-characterization-v1":
        raise ValueError("Unsupported plan schema or suite")
    config=plan.get("config")
    if not isinstance(config,dict): raise ValueError("Missing plan configuration")
    try: expected=make_plan(**config)
    except (TypeError,KeyError) as exc: raise ValueError("Invalid plan configuration") from exc
    if json.dumps(plan,sort_keys=True,allow_nan=False)!=json.dumps(expected,sort_keys=True,allow_nan=False): raise ValueError("Plan differs from its canonical configuration; regenerate it")
    return plan


def plan_digest(plan):
    validate_plan(plan)
    return hashlib.sha256(json.dumps(plan,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()


def to_qasm3(circuit):
    """Export logical wires; physical mapping is not encoded as a hardware promise."""
    n=circuit["n_qubits"]
    lines=["OPENQASM 3.0;",'include "stdgates.inc";',f"qubit[{n}] q;",f"bit[{n}] meas;"]
    for op in circuit["operations"]:
        args=", ".join(f"q[{q}]" for q in op["qubits"])
        name=op["name"]
        if name=="delay": lines.append(f"delay[{op['duration_us']:.17g}us] {args};")
        elif "angle" in op: lines.append(f"{name}({op['angle']:.17g}) {args};")
        else: lines.append(f"{name} {args};")
    lines.extend(f"meas[{q}] = measure q[{q}];" for q in range(n))
    return "\n".join(lines)+"\n"
