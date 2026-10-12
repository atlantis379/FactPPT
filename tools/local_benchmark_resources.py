"""Windows resource sampler for the isolated chapter experiment; no model calls."""
import ctypes
import json
from pathlib import Path
import subprocess
import time

OUT = Path(__file__).resolve().parents[1] / "output/chapter_draft_benchmark"


class Memory(ctypes.Structure):
    _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [(k, ctypes.c_ulonglong) for k in
        ("total_physical", "available_physical", "total_page_file", "available_page_file", "total_virtual", "available_virtual", "available_extended")]


def main():
    current = OUT / "resources.json"
    previous = json.loads(current.read_text(encoding="utf-8")) if current.exists() else {}
    records = previous.get("records", [])
    sessions = previous.get("sampling_sessions", []) + [{"started_epoch": time.time(), "resumed": bool(records)}]
    write_failures = previous.get("write_failures", 0)
    while not (OUT / "resources.stop").exists():
        memory = Memory(); memory.length = ctypes.sizeof(memory)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory))
        record = {"utc_epoch": time.time(), "ram_available_bytes": memory.available_physical, "memory_load_percent": memory.load}
        try:
            gpu = subprocess.check_output(["nvidia-smi", "--query-gpu=memory.used,utilization.gpu", "--format=csv,noheader,nounits"], text=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=10).strip()
            used, load = gpu.split(",")
            record.update(gpu_used_mib=int(used), gpu_utilization_percent=int(load))
        except Exception as exc:
            record["error"] = str(exc)
        records.append(record)
        temp = OUT / "resources.json.tmp"
        temp.write_text(json.dumps({"sampling_seconds": 5, "scope": "Late-start, interrupted and resumed samples; not full-run peaks or isolated model memory attribution", "sampling_sessions": sessions, "write_failures": write_failures, "records": records}, ensure_ascii=False), encoding="utf-8")
        # Windows readers can briefly lock the destination. Preserve the last
        # successful file and continue sampling rather than lose the whole run.
        for attempt in range(6):
            try:
                temp.replace(current)
                break
            except PermissionError:
                write_failures += 1
                time.sleep(.2)
        time.sleep(5)


if __name__ == "__main__": main()
