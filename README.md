<p align="center">
  <img src="https://raw.githubusercontent.com/qcbench-org/qcbench/main/assets/avatar.png" alt="QCBench logo" width="160" height="160">
</p>

# QCBench

[![PyPI](https://img.shields.io/pypi/v/qcbench)](https://pypi.org/project/qcbench/)
[![CI](https://github.com/qcbench-org/qcbench/actions/workflows/ci.yml/badge.svg)](https://github.com/qcbench-org/qcbench/actions/workflows/ci.yml)

**Reproducible quantum computer characterization from hardware experiments and shot counts.**

QCBench plans small QPU experiments, exports circuits, collects shot-count results and produces quantitative reports with uncertainty and provenance. Its first release measures **readout assignment error, GHZ state fidelity, mirror-circuit survival, T1 and spin-echo T2**. The focus is quantum-computer behavior under an actual experiment, rather than SDK operation speed.

Version 0.1.0 includes independently implemented circuit generators and analysis, an optional Qiskit device compiler, IBM Runtime submission and result collection, and a fully offline synthetic demonstration. It is an initial characterization toolkit, not a comprehensive hardware ranking, vendor-certified calibration suite or composite quantum-computer score. No real-device performance numbers are bundled or claimed.

## Install

Requires Python 3.11 or newer. Core dependencies are NumPy and SciPy; quantum SDKs are optional.

```bash
pip install qcbench
pip install 'qcbench[qiskit]'   # Native circuits and device-aware compilation
pip install 'qcbench[ibm]'      # Also IBM Runtime submission and collection
```

## Try it offline

```bash
qcbench list
qcbench demo --directory demo-results
qcbench analyze demo-results/plan.json demo-results/counts.json \
  --output report.json --csv report.csv
```

The demo writes a deterministic experiment plan, synthetic shot records, JSON analysis and CSV metrics. Every dataset and report carries `execution_kind="synthetic"`. The synthetic fixture uses family-specific outcome distributions; it is not a gate-level noise simulator or a hardware result.

## Prepare an experiment

```bash
qcbench plan --physical-qubits 0 1 --output plan.json
qcbench export plan.json --directory circuits

# Select only readout checks for one physical qubit.
qcbench plan --physical-qubits 7 --benchmark readout --output readout-plan.json

# Customize the time range and mirror circuits.
qcbench plan --physical-qubits 0 1 2 --times-us 0 10 25 50 100 200 \
  --mirror-depths 1 4 8 --mirror-sequences 3 --seed 42 --output plan.json
```

The default two-qubit plan contains **40 circuits**. Plan generation and OpenQASM export do not connect to a provider or submit jobs. OpenQASM 3 exports use logical wires; the accompanying plan contains the requested physical-qubit mapping. A provider must compile these programs for its device before execution. Delay and instruction support vary by hardware.

Selected physical indices must be unique nonnegative integers; up to 32 selected qubits are supported. GHZ needs at least two. Coherence experiments require at least five unique increasing delay times starting at zero. Times are in microseconds. Mirror depth counts forward layers; each forward circuit is followed by its inverse.

## Measurements

| Family | Experiment | Reported quantity |
| --- | --- | --- |
| `readout` | Prepare 0 and 1 on each selected qubit | P(measure 1 \| prepare 0) and P(measure 0 \| prepare 1), with Wilson intervals |
| `ghz` | Prepare a GHZ state and measure Z populations plus n equatorial parity settings | Estimated GHZ fidelity, component results and approximate combined interval |
| `mirror` | Seeded local rotations/CNOT layers followed by the inverse | All-zero return probability at each depth and sequence, with Wilson interval |
| `t1` | X preparation followed by a variable idle delay | Single-exponential probability-one decay time in microseconds |
| `t2_echo` | RY(pi/2), half delay, X, half delay, RY(pi/2) | Spin-echo probability-one decay time in microseconds |

GHZ fidelity uses **n+1 measurement settings** and includes coherence; all-zero/all-one population alone is not treated as fidelity. Readout results include preparation and gate errors. Mirror survival is not randomized benchmarking, and no per-gate error or quantum-volume value is inferred from it. There is no error mitigation in this release. See [METHODS.md](METHODS.md) for equations, assumptions and limitations.

## Import hardware shot counts

All counts use fixed-width binary strings, with the **most significant bit on the left**. Logical qubit 0 is the rightmost bit. Logical index i maps initially to `plan['config']['physical_qubits'][i]`. Counts must be nonnegative integers with a positive total, not quasi-probabilities, floating-point weights, hex strings or multiple-register strings.

For example, make and analyze a single-qubit readout dataset:

```python
from qcbench import make_plan, make_dataset, analyze, write_json

plan = make_plan(physical_qubits=[7], benchmarks=['readout'])
# Replace these illustrative counts with your measured results.
counts = {
    'readout.q0.p0': {'0': 980, '1': 20},
    'readout.q0.p1': {'0': 35, '1': 965},
}
data = make_dataset(
    plan, counts,
    execution_kind='synthetic',  # Use 'hardware' only for actual device counts.
    backend_name='illustrative-counts',
)
report = analyze(plan, data)
write_json(plan, 'plan.json')
write_json(data, 'counts.json')
write_json(report, 'report.json')
```

For real measurements, declare `execution_kind='hardware'`, supply the device name and job ID, and include relevant execution metadata. Use `simulator` for simulated circuits and `synthetic` for constructed data. Provenance is caller-declared, not independently authenticated. Merely setting the hardware label does not establish that data came from a QPU.

A dataset is bound to its exact plan by SHA-256. Analysis rejects missing, duplicate or unknown circuit IDs and mismatched plans. A complete dataset must contain one counts object for every planned circuit; partial jobs should be completed before analysis. Canonical version-1 plans are generated by `make_plan`; editing their circuit definitions or metadata is rejected. Custom experiment families require a new implementation and suite version.

## Qiskit preparation and sampler results

```python
from qcbench import make_plan, analyze
from qcbench.qiskit_adapter import prepare_qiskit, collect_sampler_result
from qiskit.primitives import StatevectorSampler

plan = make_plan(benchmarks=['readout', 'ghz', 'mirror'])
circuits, execution = prepare_qiskit(plan)
# Local simulator example; no cloud access or QPU submission.
result = StatevectorSampler(seed=7).run(circuits, shots=1024).result()
data = collect_sampler_result(
    plan, result, execution_kind='simulator',
    backend_name='StatevectorSampler', execution_metadata=execution,
)
report = analyze(plan, data)
```

For device compilation, call `prepare_qiskit(plan, backend)`. It uses optimization level 0, the requested initial layout and a fixed compiler seed. Barriers separate mirror layers, the inversion boundary, state preparation and final measurement so the intended mirror experiment is not trivially optimized into an empty circuit. Review the compiled gate counts and layout before submission; other provider optimizers may treat barriers differently.

When a backend exposes `dt`, idle delays are rounded to a multiple of its advertised granularity and pulse alignment. Effective idle times are recorded and used in decay analysis when the execution metadata is passed to the collector. These times exclude pulse durations. The requested physical list is an initial layout, not a promise that routing never uses other qubits. Compiled width, layout and gate counts are retained. Backend-specific timing and instruction constraints still require review.

## IBM QPU execution

The source repository includes [examples/ibm_hardware.py](https://github.com/qcbench-org/qcbench/blob/main/examples/ibm_hardware.py). By default, it writes a plan without connecting to IBM. It requires `--submit` and an explicit accessible backend to run a job:

```bash
# Plan only. No account lookup, cloud connection or job submission.
python examples/ibm_hardware.py --physical-qubits 0 1

# After reviewing the plan and configuring your IBM account locally:
python examples/ibm_hardware.py --backend YOUR_BACKEND_NAME \
  --physical-qubits 0 1 --shots 1024 --submit
```

The Python API `submit_ibm(plan, backend, shots=1024, allow_submit=True)` returns `(job, execution_metadata)`. Omitting the explicit opt-in raises an error before submission. A job can consume paid QPU time; review the backend, plan, circuit count, shot count and provider limits first. No cloud jobs run as part of installation, tests, demo, plan, export or analysis. Credentials use the provider SDK's existing account configuration and are never stored by QCBench.

The example records the submission/job ID, raw counts and report. It expects the ordered Sampler V2 result format and one classical register named `meas`. Retain the exact plan and publication order when retrieving a job later. Device submission is implemented but has not been validated on a paid QPU as part of this release; local compilation, local sampler collection and a stubbed submission protocol are tested.

## Reports and interpretation

Reports include package/suite versions, analysis timestamp and software environment, device/provenance labels, job ID, plan fingerprint, requested physical mapping, raw experiment configuration, total circuits/shots, per-metric statistics and fit diagnostics. Raw counts stay in the dataset for independent reanalysis. The report timestamp is analysis time, not a claim about when a device executed the experiment. Put execution timestamps, calibration identifiers and provider/compiler options in dataset metadata when available; keep credentials out of metadata.

Default confidence is 95%, adjustable with `qcbench analyze --confidence`. Wilson intervals are approximate frequentist intervals, not posterior probabilities. GHZ components use a Bonferroni adjustment with approximate Wilson intervals, so the combined result is not an exact-coverage or device-independent entanglement certificate. Shots must be independent and measurement settings stable for the statistical interpretation to apply.

Coherence fitting uses a bounded, weighted three-parameter exponential, with free initial probability and asymptote. It reports covariance-based standard error, chi-squared and degrees of freedom. Flat signals, too few effective times or poorly constrained parameters return `status='unidentifiable'` instead of a fabricated T value. A large reduced chi-squared is flagged as a model mismatch; a fitted value alone does not validate the model. Inspect time coverage, pulse calibration, residuals and drift before comparing devices. No bootstrap or calibration-systematic uncertainty is claimed.

Successful report production exits 0, including reports containing unidentifiable fits. Input, validation and file errors exit 2. Invalid performance should remain visible in reports, not be confused with an I/O failure.

## Development

```bash
python -m pip install -e '.[ibm,dev]'
python -m pytest -q
python -m build
python -m twine check --strict dist/*
```

Tests cover statistical boundaries, arbitrary-state GHZ fidelity, analytic decay recovery, provenance/count validation, ideal circuits, local sampler integration, device compilation and submission opt-in without cloud jobs. Core-only environments skip the optional adapter tests. See [CONTRIBUTING.md](CONTRIBUTING.md) and [RELEASING.md](RELEASING.md). Code and original experiment definitions are Apache-2.0 licensed.

## Roadmap

Additional QPU providers, richer job recovery, calibration snapshots, gate-set and randomized benchmarking protocols, application-level workloads, drift-aware repeats, systematic uncertainty, connectivity sweeps and cross-device result views. Each added protocol must define its experiment, statistical estimator and scope of valid interpretation.

## 中文说明

QCBench 面向量子计算真机的测评与表征，首版提供读出分配误差、GHZ 态保真度、镜像电路成功率、T1 和回波 T2 的电路生成与 counts 分析，支持 OpenQASM 3 导出、Qiskit 设备编译、IBM Runtime 显式提交/结果采集以及 JSON/CSV 报告。真机、模拟器和合成数据必须明确区分。默认离线演示不连接云平台，也不提交真机任务；首版尚未执行付费 QPU 验证，不包含真实设备排名或虚构真机分数。
