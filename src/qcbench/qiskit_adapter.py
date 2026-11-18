"""Optional circuit preparation and IBM Runtime submission. No saved credentials."""
import math
from .plans import validate_plan,plan_digest
from .analysis import make_dataset


def to_qiskit(spec, *, dt=None, alignment=1):
    from qiskit import QuantumCircuit,QuantumRegister,ClassicalRegister
    if dt is not None and (not math.isfinite(dt) or dt<=0): raise ValueError("dt must be positive seconds")
    if type(alignment) is not int or alignment<1: raise ValueError("alignment must be a positive integer")
    n=spec["n_qubits"]
    circuit=QuantumCircuit(QuantumRegister(n,"q"),ClassicalRegister(n,"meas"),name=spec["id"])
    effective=0.
    for op in spec["operations"]:
        name=op["name"]; q=op["qubits"]
        if name=="delay":
            duration=op["duration_us"]
            if dt is None:
                circuit.delay(duration,q[0],unit="us"); effective+=duration
            else:
                ticks=int(math.floor(duration*1e-6/dt/alignment+.5))*alignment
                circuit.delay(ticks,q[0],unit="dt"); effective+=ticks*dt*1e6
        elif name=="barrier": circuit.barrier(*q)
        elif name in ("ry","rz"): getattr(circuit,name)(op["angle"],*q)
        else: getattr(circuit,name)(*q)
    # Prevent state preparation / measurement simplification across the final boundary.
    circuit.barrier(*range(n))
    circuit.measure(range(n),range(n))
    circuit.metadata={"qcbench_circuit_id":spec["id"]}
    if spec["benchmark"] in ("t1","t2_echo"): circuit.metadata["effective_time_us"]=effective
    return circuit


def prepare_qiskit(plan,backend=None):
    """Prepare circuits, optionally compile against a device without submitting jobs."""
    validate_plan(plan)
    from importlib.metadata import version
    dt=getattr(backend,"dt",None) if backend is not None else None
    target=getattr(backend,"target",None) if backend is not None else None
    alignment=math.lcm(int(getattr(target,"granularity",1)),int(getattr(target,"pulse_alignment",1))) if target else 1
    circuits=[to_qiskit(c,dt=dt,alignment=alignment) for c in plan["circuits"]]
    if backend is not None:
        from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager
        manager=generate_preset_pass_manager(backend=backend,optimization_level=0,
                    initial_layout=plan["config"]["physical_qubits"],seed_transpiler=plan["config"]["seed"])
        circuits=manager.run(circuits)
    execution=dict(plan_sha256=plan_digest(plan),qiskit_version=version("qiskit"),optimization_level=0,
                   requested_initial_layout=plan["config"]["physical_qubits"],device_dt_seconds=dt,
                   delay_alignment_dt=alignment,compiled_for_backend=backend is not None,circuits=[])
    for native,spec in zip(circuits,plan["circuits"]):
        record=dict(circuit_id=spec["id"],depth=native.depth(),num_qubits=native.num_qubits,
                    gate_counts={str(k):int(v) for k,v in native.count_ops().items()},layout=str(native.layout))
        if "effective_time_us" in (native.metadata or {}): record["effective_time_us"]=native.metadata["effective_time_us"]
        execution["circuits"].append(record)
    return circuits,execution


def collect_sampler_result(plan,result,*,execution_kind,backend_name,job_id=None,execution_metadata=None):
    """Collect ordered Sampler V2 publications, each with the single 'meas' register."""
    validate_plan(plan)
    results=list(result)
    if len(results)!=len(plan["circuits"]): raise ValueError("Sampler result count does not match plan")
    counts={}
    for spec,pub in zip(plan["circuits"],results):
        try: counts[spec["id"]]=pub.data.meas.get_counts()
        except AttributeError as exc: raise ValueError("Expected Sampler V2 data.meas.get_counts()") from exc
    metadata=execution_metadata or {}
    if metadata and metadata.get("plan_sha256")!=plan_digest(plan): raise ValueError("Execution metadata fingerprint mismatch")
    data=make_dataset(plan,counts,execution_kind=execution_kind,backend_name=backend_name,job_id=job_id,metadata=metadata)
    if metadata:
        compiled={row["circuit_id"]:row for row in metadata["circuits"]}
        if compiled.keys()!={c["id"] for c in plan["circuits"]}: raise ValueError("Incomplete compiled-circuit metadata")
        for row in data["records"]:
            if "effective_time_us" in compiled[row["circuit_id"]]:
                row["effective_time_us"]=compiled[row["circuit_id"]]["effective_time_us"]
    from .analysis import validate_dataset
    validate_dataset(plan,data)
    return data


def submit_ibm(plan,backend,*,shots=1024,allow_submit=False):
    """Explicit opt-in cloud submission; may consume paid QPU time. Returns (job, metadata)."""
    if allow_submit is not True:
        raise ValueError("Submission disabled: explicitly set allow_submit=True after reviewing QPU cost and plan")
    if type(shots) is not int or not 1<=shots<=10000000: raise ValueError("shots must be in 1..10000000")
    circuits,metadata=prepare_qiskit(plan,backend)
    from qiskit_ibm_runtime import SamplerV2
    job=SamplerV2(mode=backend).run(circuits,shots=shots)
    metadata["requested_shots_per_circuit"]=shots
    return job,metadata
