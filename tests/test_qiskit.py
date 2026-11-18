import importlib.util
import sys
import types
import numpy as np
import pytest
from qcbench import make_plan,analyze
from qcbench.qiskit_adapter import to_qiskit,prepare_qiskit,collect_sampler_result,submit_ibm

HAS_QISKIT=importlib.util.find_spec('qiskit') is not None


def test_no_submission_without_explicit_opt_in():
    with pytest.raises(ValueError,match='Submission disabled'): submit_ibm(make_plan(),object())


@pytest.mark.skipif(not HAS_QISKIT,reason='optional Qiskit not installed')
def test_all_ideal_circuits_and_sampler_collection():
    from qiskit.primitives import StatevectorSampler
    plan=make_plan(benchmarks=['readout','ghz','mirror'])
    circuits,metadata=prepare_qiskit(plan)
    result=StatevectorSampler(seed=7).run(circuits,shots=2048).result()
    data=collect_sampler_result(plan,result,execution_kind='simulator',backend_name='StatevectorSampler',execution_metadata=metadata)
    report=analyze(plan,data)
    for metric in report['metrics']:
        if metric['benchmark']=='readout': assert metric['estimate']==0
        else: assert metric['estimate']==1
    assert len(result)==len(plan['circuits'])
    with pytest.raises(ValueError): collect_sampler_result(plan,list(result)[:-1],execution_kind='simulator',backend_name='bad')


@pytest.mark.skipif(not HAS_QISKIT,reason='optional Qiskit not installed')
def test_mirror_identity_and_coherence_ideal_states():
    from qiskit.quantum_info import Statevector
    plan=make_plan(physical_qubits=[0,1,2],benchmarks=['mirror','t1','t2_echo'],mirror_sequences=2)
    for spec in plan['circuits']:
        native=to_qiskit(spec).remove_final_measurements(inplace=False)
        # Remove delays for ideal unitary analysis, retaining intended gates/barriers.
        cleaned=native.copy_empty_like()
        for inst in native.data:
            if inst.operation.name!='delay': cleaned.append(inst.operation,inst.qubits)
        state=Statevector.from_instruction(cleaned)
        expected=0 if spec['benchmark']=='mirror' else 1<<spec['metadata']['logical_qubit']
        assert abs(state.data[expected])**2==pytest.approx(1)


@pytest.mark.skipif(not HAS_QISKIT,reason='optional Qiskit not installed')
def test_backend_compilation_layout_and_effective_delays():
    from qiskit.providers.fake_provider import GenericBackendV2
    backend=GenericBackendV2(5,seed=7,noise_info=False)
    plan=make_plan(physical_qubits=[1,3],benchmarks=['t1','t2_echo'])
    circuits,metadata=prepare_qiskit(plan,backend)
    assert len(circuits)==24 and metadata['requested_initial_layout']==[1,3]
    assert metadata['compiled_for_backend'] and metadata['optimization_level']==0
    for spec,record in zip(plan['circuits'],metadata['circuits']):
        assert record['effective_time_us']==pytest.approx(spec['metadata']['time_us'],abs=backend.dt*1e6*2)
    spec=next(c for c in plan['circuits'] if c['id']=='t1.q0.t1')
    native=to_qiskit(spec,dt=3e-6,alignment=2)
    assert native.metadata['effective_time_us']==12


@pytest.mark.skipif(not HAS_QISKIT,reason='optional Qiskit not installed')
def test_submission_protocol_with_stub_no_network(monkeypatch):
    from qiskit.providers.fake_provider import GenericBackendV2
    calls={}; sentinel=object()
    class StubSampler:
        def __init__(self,mode): calls['backend']=mode
        def run(self,circuits,shots): calls.update(circuits=circuits,shots=shots); return sentinel
    monkeypatch.setitem(sys.modules,'qiskit_ibm_runtime',types.SimpleNamespace(SamplerV2=StubSampler))
    plan=make_plan(benchmarks=['readout']); backend=GenericBackendV2(2,seed=3,noise_info=False)
    job,metadata=submit_ibm(plan,backend,shots=100,allow_submit=True)
    assert job is sentinel and calls['backend'] is backend and calls['shots']==100
    assert metadata['requested_shots_per_circuit']==100
    with pytest.raises(ValueError): submit_ibm(plan,backend,shots=0,allow_submit=True)
