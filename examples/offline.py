"""Fully offline smoke test; every result is explicitly synthetic."""
from qcbench import make_plan,analyze,write_json,write_csv
from qcbench.demo import synthetic_dataset

plan=make_plan(physical_qubits=[0,1])
data=synthetic_dataset(plan,shots=4096,seed=123)
report=analyze(plan,data)
write_json(plan,'plan.json')
write_json(data,'counts.json')
write_json(report,'report.json')
write_csv(report,'report.csv')
print(report['execution_kind'],report['total_circuits'],report['total_shots'])
