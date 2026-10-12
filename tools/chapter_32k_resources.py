"""Supplementary sampler for an already-running isolated local experiment."""
import ctypes, subprocess, time
from datetime import datetime, timezone
from pathlib import Path
from chapter_draft_benchmark import save
from local_benchmark_resources import Memory
OUT=Path(__file__).resolve().parents[1]/'output/chapter_32k_full'
rows=[]
while not (OUT/'resources.stop').exists():
    mem=Memory();mem.length=ctypes.sizeof(Memory)
    ok=ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem))
    row={'at':datetime.now(timezone.utc).isoformat(),'memory_query_ok':bool(ok),'host_available_mib':mem.available_physical/1048576}
    try:
        p=subprocess.run(['nvidia-smi','--query-gpu=memory.used,memory.total,utilization.gpu','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=4,creationflags=0x08000000)
        row['gpu']=p.stdout.strip()
    except Exception as exc:row['error']=str(exc)
    rows.append(row)
    save(OUT/'resources_valid.json',{'scope':'Supplementary samples from sampler start, not full-run peaks; integrated sampler initial version failed memory fields.','samples':rows})
    time.sleep(3)
