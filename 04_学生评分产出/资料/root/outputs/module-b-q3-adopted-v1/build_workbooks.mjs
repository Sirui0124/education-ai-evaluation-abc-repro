import fs from 'node:fs/promises';
import crypto from 'node:crypto';
import {Workbook, SpreadsheetFile, FileBlob} from '@oai/artifact-tool';
const dir='/Users/sirui/Documents/ChatGPT/数学建模/outputs/module-b-q3-adopted-v1';
const key='/Users/sirui/Documents/ChatGPT/数学建模/outputs/01a0dced-dc37-7133-824b-3061277eee78/模块B问题3_学生领域认知层级明细.xlsx';
const backup="/Users/sirui/Documents/ChatGPT/\u6570\u5b66\u5efa\u6a21/outputs/01a0dd3d-c86d-7cd3-9841-588824672504/domain-unification/checkpoint/outputs/01a0dced-dc37-7133-824b-3061277eee78/\u6a21\u5757B\u95ee\u98983_\u5b66\u751f\u9886\u57df\u8ba4\u77e5\u5c42\u7ea7\u660e\u7ec6.xlsx";
const data=JSON.parse(await fs.readFile(dir+'/workbook-data.json','utf8'));
const hash=async p=>crypto.createHash('sha256').update(await fs.readFile(p)).digest('hex');
const oldHash=await hash(key);
if(oldHash!=="6c0e16132abc23b0d7ad49a09eac0dffab15d0072c69190119ba767f7400802c" && oldHash!==await hash(backup))throw Error('Key file changed since backup; do not overwrite');
const wb=await SpreadsheetFile.importXlsx(await FileBlob.load(key));
const s=wb.worksheets.getItem('学生领域');
const before=await wb.render({sheetName:'学生领域',range:'A1:H12',scale:1,format:'png'});
await fs.writeFile(dir+'/原表预览.png',new Uint8Array(await before.arrayBuffer()));
const headers=s.getRange('A5:H5').values[0];
if(JSON.stringify(headers)!==JSON.stringify(['学生','领域','ΔL','before L层级','after L层级','before证据回合','after证据回合','对话ID']))throw Error('Unexpected columns');
// Preserve exact row ordering in the important workbook.
const byKey=new Map(data.domains.map(r=>[r.student_key+'\0'+r.domain,r]));
const original=s.getRange('A6:H626').values;
const sorted=original.map(row=>{const r=byKey.get(row[0]+'\0'+(row[1]==='其他领域'?'其他与待判定':row[1]));if(!r)throw Error('Missing key');return r;});
s.getRange('A6:H626').values=sorted.map(r=>[r.student_key,r.domain,r.delta_l??'NA',r.before_l,r.after_l,JSON.stringify(r.before_evidence),JSON.stringify(r.after_evidence),JSON.stringify(r.dialogue_ids)]);
s.getRange('A1').values=[['模块B问题3：学生 × 领域认知层级（采纳版 v4）']];
s.getRange('A2').values=[['数学建模综合与数学基础保留直接六级；其余按原话题领域与学生隔离五折折算。折算分不是真实L级；模块不明或不可配对记NA。']];
s.getRange('A3').values=[[`708场对话，369位学生，621个学生×领域组合；${data.summary.computable_student_domain_pairs}组可计算、${data.summary.na_student_domain_pairs}组NA。Before为最早相关基线，After为可核对的已观测最高。`]];
wb.recalculate();
console.log((await wb.inspect({kind:'table',range:'学生领域!A5:E12',tableMaxRows:8,tableMaxCols:5,maxChars:2200})).ndjson);
console.log((await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!',options:{useRegex:true,maxResults:20}})).ndjson);
const pic=await wb.render({sheetName:'学生领域',range:'A1:H12',scale:1,format:'png'});
await fs.writeFile(dir+'/关键表采纳版预览.png',new Uint8Array(await pic.arrayBuffer()));
const staged=dir+'/关键表待写入.xlsx';await (await SpreadsheetFile.exportXlsx(wb)).save(staged);

const out=await SpreadsheetFile.importXlsx(await FileBlob.load(dir+'/逐对话采纳及学生指标.xlsx'));
function sheet(name,hs,rs,widths){
 const sh=out.worksheets.getItem(name);
 sh.getRangeByIndexes(0,0,1,hs.length).values=[hs];
 sh.getRangeByIndexes(1,0,rs.length,hs.length).values=rs;
 return sh;
}
const provenance=p=>JSON.stringify({turn_ids:p.turn_ids,module_id:p.module_id,module_name:p.module_name??null,heldout_fold:p.fold});
const cs=sheet('逐对话采纳',['对话ID','学生','主领域','采纳方式','Before采纳值','After采纳值','Δ采纳分','Before原始三级','After原始三级','Before原始六级','After原始六级','Before状态','After状态','配对状态/同任务','Before证据回合','After证据回合','原始会话索引'],data.conversations.map(r=>[r.id,r.student_key,r.domain??'NA',r.scale==='s6'?r.scale_status:'独立三级按原领域折算',r.before.display,r.after.display,r.delta??'NA',r.raw_s3_before??'NA',r.raw_s3_after??'NA',r.raw_s6_before??'NA',r.raw_s6_after??'NA',r.before.status,r.after.status,r.pair_status+' / '+(r.same_task?'是':'否'),provenance(r.before),provenance(r.after),r.session_id]),[12,19,25,24,29,29,15,19,19,19,19,24,24,12,22,22,85]);
cs.getRange('G2:G709').setNumberFormat('0.000');
const st=sheet('学生指标',['学生','总会话量','纳入会话量','Agent种类数','Agent覆盖率','AB3含Pro数','AB3占比','ABPro数','ABPro占比','采纳分≥3数','采纳分≥3/全部Pro','Pro可评分数','Pro的U数','Pro缺评分数','原阈值高组','原阈值低组','类别跨度高组','类别跨度低组','高跨度领域数','可计算领域数','NA领域数','Agent分布'],data.students.map(r=>[r.student_key,r.raw_session_count,r.included_session_count,r.observed_agent_category_count??'NA',r.agent_observation_coverage??'NA',r.ab3_inclusive_count,r.ab3_inclusive_share_all_included??'NA',r.abpro_count,r.abpro_share_all_included??'NA',r.ability_adopted_ge3_count,r.ability_adopted_ge3_share_all_abpro??'NA',r.ability_scorable_count,r.ability_u_count,r.ability_missing_count,r.high_literal?'是':'否',r.low_literal?'是':'否',r.high_category?'是':'否',r.low_category?'是':'否',r.high_domain_count_category,r.computable_domain_count,r.na_domain_count,JSON.stringify(r.observed_agent_distribution)]));
for(const col of ['E','G','I','K'])st.getRange(`${col}2:${col}370`).setNumberFormat('0.0%');
st.getRange('A1:A370').format.columnWidth=22;st.getRange('V1:V370').format.columnWidth=62;
const rs=sheet('规则说明',['项目','规则'],[
 ['范围','708场认知标注会话；学生指标包含369位学生全部已纳入会话。'],
 ['直接六级','数学建模综合与案例、数学基础，探索性采用；小样本与Before可靠性限制保留。'],
 ['三级折算','其余领域按证据任务定位原话题领域，使用学生隔离五折系数；目标约束代理分，不修改原始六级。'],
 ['配对','Before/After须归属同一领域，折算时还须同一原领域；U、缺失、领域或模块不明均为NA。'],
 ['原阈值分组','高：至少一可计算领域Δ≥3；低：所有可计算领域Δ≤1。折算差值不代表真实跨越L级。'],
 ['类别跨度分组','补充分析。三级低→高为大跨度、类别未变为低跨度；六级仍按≥3/≤1。'],
 ['意愿','AB3含ABPro/全部纳入会话；ABPro/全部纳入会话；Agent未知不是0。'],
 ['能力','采纳分≥3/全部ABPro；U与模块不明仍在分母。数值计算与科学计算领域的“高”折算低于3，不能等同。'],
 ['原始文件','原主表已备份；两套原始标签保留；详细规则见同目录采纳规则.md。'],
 ['风险','最高不是末次；校准标签不是金标准；采纳分及差值不是已证实的学习增益或因果效应。']],[19,118]);
rs.getRange('B2:B11').format.wrapText=true;rs.getRange('A2:B11').format.rowHeight=38;
out.recalculate();
for(const [name,range]of [['逐对话采纳','A1:G10'],['学生指标','A1:K10'],['规则说明','A1:B11']]){
 const preview=await out.render({sheetName:name,range,scale:1.1,format:'png'});
 await fs.writeFile(dir+`/${name}预览.png`,new Uint8Array(await preview.arrayBuffer()));
}
console.log((await out.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?',options:{useRegex:true,maxResults:20}})).ndjson);
await (await SpreadsheetFile.exportXlsx(out)).save(dir+'/逐对话采纳及学生指标.xlsx');
const detailRead=await SpreadsheetFile.importXlsx(await FileBlob.load(dir+'/逐对话采纳及学生指标.xlsx'));
for(const name of ['逐对话采纳','学生指标','规则说明']){
 const expected=out.worksheets.getItem(name).getUsedRange().values;
 const actual=detailRead.worksheets.getItem(name).getUsedRange().values;
 if(JSON.stringify(actual)!==JSON.stringify(expected))throw Error('Detail export mismatch: '+name);
}
// Validate all edited cells in the saved file before replacing the important workbook.
const reread=await SpreadsheetFile.importXlsx(await FileBlob.load(staged));
const actual=reread.worksheets.getItem('学生领域').getRange('A6:H626').values;
const expected=s.getRange('A6:H626').values;
if(JSON.stringify(actual)!==JSON.stringify(expected))throw Error('Export changed key data');
if(await hash(key)!==oldHash)throw Error('Concurrent key workbook change');
if(await hash(backup)!==oldHash)throw Error('Backup mismatch');
await fs.copyFile(staged,key);
await fs.writeFile(dir+'/workbook-validation.json',JSON.stringify({rows:621,fullCellReadback:true,backup_sha256:oldHash,new_sha256:await hash(key),outputs:[key,dir+'/逐对话采纳及学生指标.xlsx']},null,2));
console.log('Key workbook updated; original backup verified.');
