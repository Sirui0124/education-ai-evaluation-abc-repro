import copy
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from qa_labeler.core import label_one, label_conversations, normalize, annotate_qapro
from qa_labeler.backend import APIAnnotator

ROOT = Path(__file__).resolve().parents[1]

def conversation(last='股价'):
    return {'id':'demo', 'messages':[{'role':'user','content':'什么是非平稳序列？'},
            {'role':'assistant','content':'统计性质随时间变化。请举一个非平稳序列？'},
            {'role':'user','content':last}]}

def annotation(record):
    return {'id':record['id'], 'session_id':record['session_id'], 'qa_pro':'PENDING', 'segments':[
        {'topic':'非平稳序列', 'turn_start':1, 'turn_end':3, 'label':'QA3', 'reason':'学生回答了同一任务中的问题',
         'evidence':[{'turn_index':3,'quote':record['turns'][2]['text']}], 'effective_student_turns':[3],
         'deferred_student_turns':[], 'closure':'UNKNOWN', 'agent_uptake':'未知', 'review_reason':''}]}

class LabelTests(unittest.TestCase):
    def test_r2_positive(self):
        r=label_one(conversation(), annotation)
        self.assertEqual((r['qa3'],r['qapro'],r['tier']),(True,True,'QA Pro'))
        self.assertEqual(r['qapro_details']['primary_type'],'R2_EFFECTIVE_ANSWER')
    def test_low_information(self):
        r=label_one(conversation('不知道'), annotation)
        self.assertTrue(r['qa3']); self.assertFalse(r['qapro'])
    def test_first_turn_never_r1(self):
        r=normalize(conversation());r['turns'][0]['text']='我想用线性回归'; r['turns'][2]['text']='继续'
        self.assertEqual(annotate_qapro(r)['r1'],[])
    def test_r1(self):
        r=annotate_qapro(normalize(conversation('我想用线性回归验证这个关系')))
        self.assertTrue(r['r1'])
    def test_r3(self):
        r=normalize(conversation('非平稳序列如何验证适用条件？'))
        self.assertTrue(annotate_qapro(r)['r3'])
    def test_teacher_priority(self):
        r=label_one({'id':'teacher','identity_role':'teacher'}, lambda _:self.fail('不应调用'))
        self.assertEqual(r['exclusion'],'疑似老师剔除'); self.assertIsNone(r['qa3'])
    def test_empty(self):
        self.assertEqual(label_one({'id':'empty','turns':[]},None)['exclusion'],'空对话')
    def test_missing_role(self):
        x=conversation(); x['messages'][0]['role']='unknown'
        self.assertEqual(label_one(x, annotation)['status'],'DATA_REVIEW')
    def test_missing_side(self):
        x=conversation();x['messages']=x['messages'][:1]
        self.assertEqual(label_one(x, annotation)['status'],'DATA_REVIEW')
    def test_duplicates(self):
        with self.assertRaises(ValueError):label_conversations([conversation(),conversation()],annotation)
    def test_hallucinated_evidence(self):
        def bad(record):
            x=annotation(record);x['segments'][0]['evidence'][0]['quote']='不存在的证据';return x
        r=label_one(conversation(),bad)
        self.assertEqual(r['status'],'ERROR');self.assertIsNone(r['qapro'])
    def test_agent_as_student_evidence(self):
        def bad(record):
            x=annotation(record);x['segments'][0]['effective_student_turns']=[2];return x
        self.assertEqual(label_one(conversation(),bad)['status'],'ERROR')
    def test_noncontiguous_turns(self):
        x=conversation();x['messages'][1]['turn_index']=10
        self.assertEqual(label_one(x, annotation)['status'],'DATA_REVIEW')
    def test_review_is_unknown(self):
        def review(record):
            x=annotation(record);s=x['segments'][0];s.update(label='REVIEW',effective_student_turns=[],review_reason='边界不清');return x
        r=label_one(conversation(),review)
        self.assertEqual(r['status'],'REVIEW');self.assertIsNone(r['qa3']);self.assertIsNone(r['qapro'])
    def test_no_qa3_skip_pro(self):
        def no(record):
            x=annotation(record);x['segments'][0].update(label='NO_FOLLOWUP_NEEDED',effective_student_turns=[]);return x
        r=label_one(conversation(),no)
        self.assertFalse(r['qa3']);self.assertIsNone(r['qapro']);self.assertEqual(r['tier'],'仅QA')
    def test_real_http_transport_with_local_fixture(self):
        record=normalize(conversation()); response=annotation(record)
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                self.server.seen=body
                self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers()
                self.wfile.write(json.dumps({'choices':[{'message':{'content':json.dumps({'results':[response]})}}]}).encode())
        server=HTTPServer(('127.0.0.1',0),Handler);worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        try:
            r=label_one(conversation(),APIAnnotator(f'http://127.0.0.1:{server.server_port}/v1','fake','test',retries=0))
            self.assertEqual(r['tier'],'QA Pro');self.assertEqual(server.seen['response_format']['type'],'json_schema')
        finally:server.shutdown();server.server_close();worker.join()
    def test_cli_resume_changed_input_and_import_mismatch(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp);record=normalize(conversation());ann={**record,'segments':annotation(record)['segments']}
            (p/'input.json').write_text(json.dumps([conversation()]))
            (p/'ann.json').write_text(json.dumps([ann]))
            cmd=[sys.executable,'-m','qa_labeler','--input',str(p/'input.json'),'--output',str(p/'out'),'--qa3-annotations',str(p/'ann.json')]
            for _ in range(2):self.assertEqual(subprocess.run(cmd,cwd=ROOT,capture_output=True).returncode,0)
            self.assertEqual(json.loads((p/'out/summary.json').read_text())['qapro_true'],1)
            (p/'input.json').write_text(json.dumps([conversation('改变正文')]))
            self.assertEqual(subprocess.run(cmd,cwd=ROOT,capture_output=True).returncode,1)
            cmd[cmd.index(str(p/'out'))]=str(p/'out2')
            self.assertEqual(subprocess.run(cmd,cwd=ROOT,capture_output=True).returncode,2)

if __name__=='__main__':unittest.main()
