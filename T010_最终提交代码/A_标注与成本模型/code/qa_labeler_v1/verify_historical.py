"""Exact regression with externally supplied QA3 transcripts and QAPro labels."""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from qa_labeler.core import annotate_qapro, normalize, validate_qa3

def read(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--qa3',type=Path,required=True)
    p.add_argument('--qapro',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    sources=read(args.qa3); labels=read(args.qapro)
    source={r['id']:r for r in sources}
    if len(source)!=len(sources) or len({r['id'] for r in labels})!=len(labels):
        raise ValueError('Duplicate id')
    errors=[];counts=Counter();invalid=[]
    fields={'topic','turn_start','turn_end','label','reason','evidence','effective_student_turns',
            'deferred_student_turns','closure','agent_uptake','review_reason'}
    for r in labels:
        row=source[r['id']];record=normalize(row);computed=annotate_qapro(record)
        for key in ['label','primary_type']:
            if computed[key]!=r[key]:errors.append([r['id'],key])
        for key in ['r1','r2','r3']:
            if computed[key]!=r[key+'_hits']:errors.append([r['id'],key])
            counts[key]+=bool(computed[key])
        counts[computed['label']]+=1
        try:
            validate_qa3(record,{'id':record['id'],'session_id':record['session_id'],'qa_pro':'PENDING',
                'segments':[{k:v for k,v in s.items() if k in fields} for s in row['segments']]})
        except Exception as e:invalid.append([row['id'],str(e)])
    report={'regression_population':len(labels),'mismatches':errors,'counts':dict(counts),
            'qa3_contract_errors':invalid,
            'source_sha256':{'qa3':hashlib.sha256(args.qa3.read_bytes()).hexdigest(),
                             'qapro':hashlib.sha256(args.qapro.read_bytes()).hexdigest()},
            'scope':'从历史完整正文重新执行 QAPro v2.4。比较标签、主类型和全部命中；校验导入 QA3 的结构与证据。未调用远程模型重新判定 QA3。'}
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))
    return int(bool(errors or invalid))

if __name__=='__main__':raise SystemExit(main())
