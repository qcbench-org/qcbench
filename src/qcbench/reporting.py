"""Portable reports, with provenance on every exported metric."""
import csv
import json
from pathlib import Path


def write_json(value,path):
    Path(path).write_text(json.dumps(value,indent=2,allow_nan=False)+"\n",encoding="utf-8")


def write_csv(report,path):
    fields=["execution_kind","backend_name","benchmark","metric","physical_qubit","prepared","depth","sequence",
            "estimate","interval_low","interval_high","confidence","shots","status","decay_time_us","decay_time_std_us","reason"]
    with Path(path).open("w",newline="",encoding="utf-8") as stream:
        writer=csv.DictWriter(stream,fieldnames=fields); writer.writeheader()
        for metric in report["metrics"]:
            row={k:metric[k] for k in fields if k in metric}
            row.update(execution_kind=report["execution_kind"],backend_name=report["backend_name"])
            if "interval" in metric: row.update(interval_low=metric["interval"][0],interval_high=metric["interval"][1])
            writer.writerow(row)
