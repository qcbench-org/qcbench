import copy
import csv
import json
import math
import numpy as np
import pytest
from qcbench import make_plan,plan_digest,validate_plan,to_qasm3,make_dataset,analyze,write_json,write_csv
from qcbench.demo import synthetic_dataset
from qcbench.statistics import wilson,validate_counts,fit_decay
from qcbench.cli import main


def test_deterministic_plan_and_qasm():
    a=make_plan(); b=make_plan()
    assert a==b and plan_digest(a)==plan_digest(b)
    assert len(a['circuits'])==40
    assert len({c['id'] for c in a['circuits']})==40
    assert make_plan(seed=4)!=a
    text=to_qasm3(a['circuits'][0])
    assert 'OPENQASM 3.0;' in text and 'meas[0] = measure q[0];' in text
    t1=next(c for c in a['circuits'] if c['id']=='t1.q0.t1')
    assert 'delay[10us] q[0];' in to_qasm3(t1)


@pytest.mark.parametrize('kwargs',[
 {'physical_qubits':[]},{'physical_qubits':[0,0]},{'physical_qubits':[-1]},
 {'physical_qubits':[True,1]},{'physical_qubits':[0]}, {'physical_qubits':list(range(33))},
 {'benchmarks':['bad']},{'benchmarks':[]},{'times_us':[0,1,2]},
 {'times_us':[0,1,2,3,3]},{'times_us':[0,1,2,3,float('nan')]},
 {'mirror_depths':[0]},{'mirror_sequences':0},{'seed':-1},
])
def test_invalid_plans(kwargs):
    with pytest.raises(ValueError): make_plan(**kwargs)


def test_plan_edits_rejected():
    a=make_plan(); a['circuits'][0]['id']='wrong'
    with pytest.raises(ValueError,match='canonical'): validate_plan(a)
    with pytest.raises(ValueError): validate_plan({})
    assert make_plan(physical_qubits=[7],benchmarks=['t1'])['config']['physical_qubits']==[7]


def test_wilson_known_values_and_boundaries():
    r=wilson(50,100)
    assert r['interval']==pytest.approx([.4038315303659956,.5961684696340044])
    assert wilson(0,100)['interval'][1]>0
    assert wilson(100,100)['interval'][0]<1
    for a,b in [(1,0),(-1,5),(6,5),(True,2)]:
        with pytest.raises(ValueError): wilson(a,b)
    with pytest.raises(ValueError): wilson(0,10,1)


@pytest.mark.parametrize('counts',[{}, {'0':0},{'0':1},{'00':-1},{'00':.5},{'00':True},{'0x0':1},{'0 0':1},{'02':1}])
def test_counts_validation(counts):
    with pytest.raises(ValueError): validate_counts(counts,2)


def test_synthetic_run_and_decay_recovery():
    p=make_plan(); d=synthetic_dataset(p,shots=20000,seed=12); r=analyze(p,d)
    assert r['execution_kind']=='synthetic' and r['total_shots']==40*20000
    assert synthetic_dataset(p,shots=100,seed=4)==synthetic_dataset(p,shots=100,seed=4)
    fits=[m for m in r['metrics'] if m['metric']=='decay_time_us']
    assert len(fits)==4
    for m in fits:
        assert m['status']=='fitted',m
        expected=75 if m['benchmark']=='t1' else 55
        assert m['decay_time_us']==pytest.approx(expected,rel=.12)
        assert math.isfinite(m['decay_time_std_us'])
    g=next(m for m in r['metrics'] if m['benchmark']=='ghz')
    assert 0<=g['interval'][0]<=g['estimate']<=g['interval'][1]<=1


@pytest.mark.parametrize('n',[2,3,4])
def test_ghz_fidelity_for_arbitrary_states(n):
    # Direct Born probabilities for an arbitrary state, independently of circuit generation.
    p=make_plan(physical_qubits=range(n),benchmarks=['ghz'])
    rng=np.random.default_rng(n)
    psi=rng.normal(size=2**n)+1j*rng.normal(size=2**n); psi/=np.linalg.norm(psi)
    h=np.array([[1,1],[1,-1]])/np.sqrt(2)
    records={}
    for spec in p['circuits']:
        state=psi
        if spec['metadata']['basis']!='z':
            theta=spec['metadata']['theta']
            single=h@np.diag([np.exp(.5j*theta),np.exp(-.5j*theta)])
            unitary=np.array([[1.]])
            for _ in range(n): unitary=np.kron(unitary,single)
            state=unitary@psi
        records[spec['id']]={f'{i:0{n}b}':int(round(float(abs(v)**2)*100000000)) for i,v in enumerate(state)}
    data=make_dataset(p,records,execution_kind='simulator',backend_name='Born-rule calculation')
    metric=analyze(p,data)['metrics'][0]
    expected=float(abs((psi[0]+psi[-1])/np.sqrt(2))**2)
    assert metric['estimate']==pytest.approx(expected,abs=1e-7)


def test_population_alone_does_not_establish_ghz_coherence():
    p=make_plan(benchmarks=['ghz'])
    counts={'ghz.z':{'00':500,'11':500},'ghz.phase0':{'00':250,'01':250,'10':250,'11':250},
            'ghz.phase1':{'00':250,'01':250,'10':250,'11':250}}
    metric=analyze(p,make_dataset(p,counts,execution_kind='simulator',backend_name='incoherent mixture'))['metrics'][0]
    assert metric['population']['estimate']==1
    assert metric['estimate']==.5


@pytest.mark.parametrize('mutation',['hash','missing','duplicate','unknown','kind','counts','delay','metadata','job_id'])
def test_invalid_datasets(mutation):
    p=make_plan(benchmarks=['readout']); d=synthetic_dataset(p,100)
    if mutation=='hash': d['plan_sha256']='bad'
    if mutation=='missing': d['records'].pop()
    if mutation=='duplicate': d['records'].append(d['records'][0])
    if mutation=='unknown': d['records'][0]['circuit_id']='bad'
    if mutation=='kind': d['execution_kind']='unspecified'
    if mutation=='counts': d['records'][0]['counts']={'00':1.3}
    if mutation=='delay': d['records'][0]['effective_time_us']=float('inf')
    if mutation=='metadata': d['metadata']={'bad':float('nan')}
    if mutation=='job_id': d['job_id']=[]
    with pytest.raises(ValueError): analyze(p,d)


def test_decay_model_and_unidentifiability():
    points=[]
    for t in [0,10,25,50,100,200]:
        points.append(dict(time_us=t,successes=int(round((.05+.9*math.exp(-t/80))*1000000)),shots=1000000))
    r=fit_decay(points)
    assert r['status']=='fitted' and r['decay_time_us']==pytest.approx(80,rel=1e-3)
    flat=[dict(time_us=t,successes=1000,shots=1000) for t in [0,1,2,3,4]]
    assert fit_decay(flat)['status']=='unidentifiable'
    assert fit_decay(points[:3])['status']=='unidentifiable'


def test_little_endian_marginals_and_export(tmp_path):
    p=make_plan(physical_qubits=[4,9],benchmarks=['readout'])
    counts={'readout.q0.p0':{'00':90,'01':10},'readout.q0.p1':{'00':20,'01':80},
            'readout.q1.p0':{'00':70,'10':30},'readout.q1.p1':{'00':40,'10':60}}
    r=analyze(p,make_dataset(p,counts,execution_kind='hardware',backend_name='user-declared-fixture'))
    assert [m['estimate'] for m in r['metrics']]==[.1,.2,.3,.4]
    assert [m['physical_qubit'] for m in r['metrics']]==[4,4,9,9]
    write_json(r,tmp_path/'r.json'); write_csv(r,tmp_path/'r.csv')
    assert json.loads((tmp_path/'r.json').read_text())==r
    with (tmp_path/'r.csv').open() as stream: rows=list(csv.DictReader(stream))
    assert len(rows)==4 and rows[0]['execution_kind']=='hardware'


def test_cli_offline_pipeline(tmp_path,capsys):
    assert main(['list'])==0
    assert 't2_echo' in capsys.readouterr().out
    assert main(['plan','--output',str(tmp_path/'plan.json')])==0
    assert main(['export',str(tmp_path/'plan.json'),'--directory',str(tmp_path/'qasm')])==0
    assert len(list((tmp_path/'qasm').glob('*.qasm')))==40
    assert main(['demo','--directory',str(tmp_path/'demo'),'--shots','1000'])==0
    assert main(['analyze',str(tmp_path/'demo/plan.json'),str(tmp_path/'demo/counts.json'),
                 '--output',str(tmp_path/'report.json'),'--csv',str(tmp_path/'report.csv')])==0
    assert main(['analyze',str(tmp_path/'absent'),str(tmp_path/'absent')])==2
    assert main(['plan','--physical-qubits','0','0','--output',str(tmp_path/'bad.json')])==2
