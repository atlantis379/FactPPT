import json, sys
from pathlib import Path
from .sources import load_sources, save
from . import facts as fx

def main(project: Path, sources_dir: Path):
    S, U = load_sources(sources_dir, project / "sources_manifest.json", project / "transcriptions")
    save(S, U, project / "sources.json")
    data = json.loads((project / "sources.json").read_text(encoding="utf-8"))
    F, D, R = fx.load(project / "facts.json")
    conflicts = fx.verify(F, D, data["units"], R)
    (project / "facts_report.md").write_text(fx.report(F, D, conflicts, data["sources"]), encoding="utf-8")
    fx.dump(F, D, conflicts, project / "facts_verified.json")
    return F, D, conflicts

if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
