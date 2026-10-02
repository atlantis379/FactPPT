"""Replay cached six-page A assets through the production native compiler.

No model calls, receipts, workflow confirmations or medical approvals are created.
"""
from __future__ import annotations
import copy
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from factdeck.visual_render import render


def main():
    src=ROOT/"output/visual_ab_test"; out=ROOT/"output/visual_pipeline_smoke"
    models=json.loads((src/"A/measured_layout.json").read_text(encoding="utf8"))
    lock=json.loads((src/"content_lock.json").read_text(encoding="utf8"))["pages"]
    generation={"font":"Microsoft YaHei","pages":[]}
    for i,(m,p) in enumerate(zip(models,lock),1):
        m=copy.deepcopy(m); m["rasters"]=[]
        generation["pages"].append({"id":p["id"],"lock":{"notes":p["notes"],"design":{}},
            "layout":{"model":m,"components":[{"name":"主体插画","x":0,"y":0,"w":1280,"h":630},{"name":"底部装饰","x":0,"y":630,"w":1280,"h":90}]},
            "assets":{"vector":{"path":str(src/f"A_vector/source{i:02d}.svg")}}})
    result=render(generation,out,Path,"A 主线导出路径 · 存档资产验证")
    result["test_scope"]="六页真实存档 SVG/内容锁经主线转换与 Office 渲染；没有新增模型/Adobe调用，不是生产医学或风格审核。未复用实验额外遮罩。"
    (out/"smoke_report.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf8")
    print(json.dumps({"output":str(out),"summary":result["summary"],"office":result["office"]},ensure_ascii=False))


if __name__=="__main__": main()
