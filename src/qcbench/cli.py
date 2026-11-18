import argparse
import json
import sys
from pathlib import Path
from . import __version__
from .plans import BENCHMARKS,DEFAULT_TIMES,make_plan,validate_plan,to_qasm3
from .analysis import analyze
from .demo import synthetic_dataset
from .reporting import write_json,write_csv


def main(argv=None):
    parser=argparse.ArgumentParser(description="Quantum computer experiment planning and shot-count analysis")
    parser.add_argument("--version",action="version",version=__version__)
    commands=parser.add_subparsers(dest="command",required=True)
    commands.add_parser("list",help="List hardware benchmark families")
    plan=commands.add_parser("plan",help="Generate a device-neutral experiment plan")
    plan.add_argument("--physical-qubits",type=int,nargs="+",default=[0,1])
    plan.add_argument("--benchmark",action="append",choices=BENCHMARKS)
    plan.add_argument("--times-us",type=float,nargs="+",default=DEFAULT_TIMES)
    plan.add_argument("--mirror-depths",type=int,nargs="+",default=[1,4,8])
    plan.add_argument("--mirror-sequences",type=int,default=3)
    plan.add_argument("--seed",type=int,default=0)
    plan.add_argument("--output",type=Path,required=True)
    export=commands.add_parser("export",help="Export logical-wire OpenQASM 3 circuits")
    export.add_argument("plan",type=Path); export.add_argument("--directory",type=Path,required=True)
    analysis=commands.add_parser("analyze",help="Analyze real or simulated shot records")
    analysis.add_argument("plan",type=Path); analysis.add_argument("data",type=Path)
    analysis.add_argument("--confidence",type=float,default=.95)
    analysis.add_argument("--output",type=Path); analysis.add_argument("--csv",type=Path)
    demo=commands.add_parser("demo",help="Generate explicitly synthetic example data and reports")
    demo.add_argument("--directory",type=Path,required=True)
    demo.add_argument("--shots",type=int,default=4096); demo.add_argument("--seed",type=int,default=123)
    args=parser.parse_args(argv)
    try:
        if args.command=="list": print("\n".join(BENCHMARKS)); return 0
        if args.command=="plan":
            value=make_plan(args.physical_qubits,args.benchmark or BENCHMARKS,args.times_us,
                            args.mirror_depths,args.mirror_sequences,args.seed)
            write_json(value,args.output)
            print(json.dumps({"circuits":len(value["circuits"]),"output":str(args.output),"submitted":False}))
        elif args.command=="export":
            value=validate_plan(json.loads(args.plan.read_text()))
            args.directory.mkdir(parents=True,exist_ok=True)
            for spec in value["circuits"]:
                (args.directory/(spec["id"]+".qasm")).write_text(to_qasm3(spec),encoding="utf-8")
            write_json(value,args.directory/"plan.json")
            print(json.dumps({"exported":len(value["circuits"]),"submitted":False}))
        elif args.command=="demo":
            args.directory.mkdir(parents=True,exist_ok=True)
            value=make_plan(); data=synthetic_dataset(value,args.shots,args.seed); report=analyze(value,data)
            for name,item in [("plan.json",value),("counts.json",data),("report.json",report)]: write_json(item,args.directory/name)
            write_csv(report,args.directory/"report.csv")
            print(json.dumps({"execution_kind":"synthetic","circuits":report["total_circuits"],"output":str(args.directory)}))
        else:
            report=analyze(json.loads(args.plan.read_text()),json.loads(args.data.read_text()),args.confidence)
            if args.csv: write_csv(report,args.csv)
            if args.output: write_json(report,args.output)
            else: print(json.dumps(report,indent=2,allow_nan=False))
        return 0
    except (ValueError,OSError,TypeError,KeyError) as exc:
        print("qcbench: "+str(exc),file=sys.stderr); return 2
