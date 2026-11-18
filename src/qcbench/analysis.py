"""Analyze complete hardware datasets without conflating simulated and measured runs."""
from datetime import datetime,timezone
import math
import json
import platform
from importlib.metadata import version
from .plans import validate_plan,plan_digest
from .statistics import validate_counts,wilson,marginal_successes,fit_decay

KINDS=("hardware","simulator","synthetic")


def make_dataset(plan, counts, *, execution_kind, backend_name, job_id=None, metadata=None):
    """Bind externally collected counts to the exact plan. No execution is performed."""
    validate_plan(plan)
    if not isinstance(counts,dict): raise ValueError("counts must map circuit IDs to counts objects")
    records=[dict(circuit_id=cid,counts=value) for cid,value in counts.items()]
    data=dict(schema_version=1,plan_sha256=plan_digest(plan),execution_kind=execution_kind,
              backend_name=backend_name,job_id=job_id,metadata={} if metadata is None else metadata,records=records)
    validate_dataset(plan,data)
    return data


def validate_dataset(plan,data):
    validate_plan(plan)
    if not isinstance(data,dict) or data.get("schema_version")!=1 or data.get("plan_sha256")!=plan_digest(plan):
        raise ValueError("Dataset schema or plan fingerprint mismatch")
    if data.get("execution_kind") not in KINDS: raise ValueError("Declare hardware, simulator or synthetic execution_kind")
    if not isinstance(data.get("backend_name"),str) or not data["backend_name"].strip(): raise ValueError("backend_name is required")
    if data.get("job_id") is not None and (not isinstance(data["job_id"],str) or not data["job_id"].strip()):
        raise ValueError("job_id must be a nonempty string or null")
    if not isinstance(data.get("metadata",{}),dict): raise ValueError("metadata must be a JSON object")
    try: json.dumps(data.get("metadata",{}),allow_nan=False)
    except (TypeError,ValueError) as exc: raise ValueError("metadata must contain finite JSON values") from exc
    records=data.get("records")
    if not isinstance(records,list): raise ValueError("records must be a list")
    expected={c["id"]:c for c in plan["circuits"]}; seen=set()
    for row in records:
        if not isinstance(row,dict): raise ValueError("Every record must be an object")
        cid=row.get("circuit_id")
        if not isinstance(cid,str) or cid not in expected or cid in seen: raise ValueError("Unknown or duplicate circuit ID")
        seen.add(cid); validate_counts(row.get("counts"),expected[cid]["n_qubits"])
        if "effective_time_us" in row:
            t=row["effective_time_us"]
            if type(t) not in (int,float) or not math.isfinite(t) or t<0: raise ValueError("Invalid effective delay")
    if seen!=expected.keys(): raise ValueError("Dataset must contain exactly one record for every planned circuit")
    return data


def analyze(plan, data, confidence=.95):
    validate_dataset(plan,data)
    wilson(0,1,confidence)  # Validate before applying any confidence adjustment.
    rows={r["circuit_id"]:r for r in data["records"]}; metrics=[]
    ghz={}; decay={}
    for spec in plan["circuits"]:
        record=rows[spec["id"]]; counts=record["counts"]; shots=sum(counts.values())
        meta=spec["metadata"]; benchmark=spec["benchmark"]
        if benchmark=="readout":
            errors=marginal_successes(counts,meta["logical_qubit"],1-meta["prepared"])
            metrics.append(dict(benchmark=benchmark,metric="assignment_error",physical_qubit=meta["physical_qubit"],
                                prepared=meta["prepared"],**wilson(errors,shots,confidence)))
        elif benchmark=="mirror":
            success=counts.get("0"*spec["n_qubits"],0)
            metrics.append(dict(benchmark=benchmark,metric="all_zero_survival",depth=meta["depth"],sequence=meta["sequence"],
                                **wilson(success,shots,confidence)))
        elif benchmark=="ghz": ghz[spec["id"]]=(spec,counts,shots)
        else:
            success=marginal_successes(counts,meta["logical_qubit"],1)
            point=dict(time_us=record.get("effective_time_us",meta["time_us"]),requested_time_us=meta["time_us"],
                       successes=success,shots=shots,**{"probability_one":wilson(success,shots,confidence)})
            decay.setdefault((benchmark,meta["physical_qubit"]),[]).append(point)
    if ghz:
        n=len(plan["config"]["physical_qubits"])
        component_confidence=1-(1-confidence)/(n+1)
        _,counts,shots=ghz["ghz.z"]
        population=wilson(counts.get("0"*n,0)+counts.get("1"*n,0),shots,component_confidence)
        phases=[]
        for k in range(n):
            _,counts,shots=ghz[f"ghz.phase{k}"]
            good=sum(c for bits,c in counts.items() if bits.count("1")%2==k%2)
            phases.append(dict(phase_index=k,**wilson(good,shots,component_confidence)))
        fidelity=population["estimate"]/2+sum(p["estimate"] for p in phases)/n-.5
        interval=[population["interval"][i]/2+sum(p["interval"][i] for p in phases)/n-.5 for i in range(2)]
        interval=[min(1.,max(0.,v)) for v in interval]
        metrics.append(dict(benchmark="ghz",metric="ghz_fidelity",estimate=fidelity,interval=interval,confidence=confidence,
                            method="Population plus equatorial parity; Bonferroni-adjusted approximate Wilson component intervals",
                            population=population,phases=phases,measurement_settings=n+1))
    for (benchmark,qubit),points in decay.items():
        metrics.append(dict(benchmark=benchmark,metric="decay_time_us",physical_qubit=qubit,
                            **fit_decay(sorted(points,key=lambda p:p["time_us"]))))
    from . import __version__
    return dict(schema_version=1,qcbench_version=__version__,created_at=datetime.now(timezone.utc).isoformat(),
                suite=plan["suite"],plan_sha256=plan_digest(plan),execution_kind=data["execution_kind"],
                analysis_environment=dict(python=platform.python_version(),platform=platform.platform(),numpy=version("numpy"),scipy=version("scipy")),
                backend_name=data["backend_name"],job_id=data.get("job_id"),metadata=data.get("metadata",{}),
                config=plan["config"],total_circuits=len(rows),total_shots=sum(sum(r["counts"].values()) for r in rows.values()),
                metrics=metrics,limitations=["Provenance is caller-declared, not independently attested.",
                "Readout errors include state preparation and gate errors; no SPAM separation or mitigation.",
                "Confidence intervals assume independent shots and stable measurement settings.",
                "Mirror survival is not randomized benchmarking or a per-gate error estimate.",
                "Coherence fits assume a single exponential with free asymptote; inspect fit quality and time coverage."])
