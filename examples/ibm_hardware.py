"""Explicit opt-in IBM QPU execution. Default only writes a plan, without connecting."""
import argparse
from qcbench import make_plan,analyze,write_json,write_csv
from qcbench.qiskit_adapter import submit_ibm,collect_sampler_result


def main():
    parser=argparse.ArgumentParser(description='Review the plan before opting into potentially paid QPU execution')
    parser.add_argument('--backend',help='An accessible IBM QPU backend name')
    parser.add_argument('--physical-qubits',type=int,nargs='+',default=[0,1])
    parser.add_argument('--shots',type=int,default=1024)
    parser.add_argument('--submit',action='store_true',help='Explicitly authorize this example to submit a QPU job')
    args=parser.parse_args()
    if not 1<=args.shots<=10000000: parser.error('--shots must be in 1..10000000')
    plan=make_plan(physical_qubits=args.physical_qubits)
    write_json(plan,'plan.json')
    print('Circuit count:',len(plan['circuits']),'Requested total shots:',len(plan['circuits'])*args.shots)
    if not args.submit:
        print('Plan only: no cloud connection or job submission. Review plan.json before using --submit.')
        return
    if not args.backend: parser.error('--backend is required with --submit')
    from qiskit_ibm_runtime import QiskitRuntimeService
    backend=QiskitRuntimeService().backend(args.backend)
    job,metadata=submit_ibm(plan,backend,shots=args.shots,allow_submit=True)
    write_json({'job_id':job.job_id(),'backend_name':backend.name,'metadata':metadata},'submission.json')
    result=job.result()
    data=collect_sampler_result(plan,result,execution_kind='hardware',backend_name=backend.name,
                                job_id=job.job_id(),execution_metadata=metadata)
    write_json(data,'counts.json')
    report=analyze(plan,data)
    write_json(report,'report.json'); write_csv(report,'report.csv')
    print('Completed job:',job.job_id())


if __name__=='__main__': main()
