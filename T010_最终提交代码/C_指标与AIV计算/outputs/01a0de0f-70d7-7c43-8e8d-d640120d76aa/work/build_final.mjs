import fs from 'node:fs/promises';
import path from 'node:path';
import {Workbook,SpreadsheetFile,FileBlob} from '@oai/artifact-tool';
const dir=path.resolve(import.meta.dirname,'..'),d=JSON.parse(await fs.readFile(path.join(import.meta.dirname,'analysis.json'),'utf8'));
const wb=Workbook.create();const names=['最终结论','学生评分','30项筛选','方案与稳健性','参数与定权','概念证据','覆盖与缺失'];
const sheets=Object.fromEntries(names.map(n=>[n,wb.worksheets.add(n)]));
const navy='#193B55',font='Arial';
function col(n){let x='';while(n){n--;x=String.fromCharCode(65+n%26)+x;n=Math.floor(n/26);}return x;}
function base(s,widths,rows){s.showGridLines=false;const end=col(widths.length);s.getRange(`A1:${end}${rows}`).format={font:{name:font,size:10,color:'#25374A'},verticalAlignment:'center',rowHeight:25};widths.forEach((v,i)=>s.getRange(`${col(i+1)}1:${col(i+1)}${rows}`).format.columnWidth=v);}
function put(s,a,v){s.getRange(a).values=[[v]];}
const queued=new Map();
function formula(s,a,v){if(!queued.has(s))queued.set(s,[]);queued.get(s).push([a,v]);}
function flush(){for(const[s,entries]of queued){const columns=new Map();for(const[a,v]of entries){const[,cc,rr]=a.match(/^([A-Z]+)(\d+)$/);if(!columns.has(cc))columns.set(cc,[]);columns.get(cc).push([Number(rr),v]);}for(const[cc,rs]of columns){rs.sort((a,b)=>a[0]-b[0]);let start=0;for(let i=1;i<=rs.length;i++){if(i<rs.length&&rs[i][0]===rs[i-1][0]+1)continue;s.getRange(`${cc}${rs[start][0]}:${cc}${rs[i-1][0]}`).formulas=rs.slice(start,i).map(r=>[r[1]]);start=i;}}}queued.clear();}
function title(s,v){put(s,'A2',v);s.getRange('A2').format.font={name:font,size:16,bold:true,color:navy};}
function line(s,row,v,last){s.getRange(`A${row}:${last}${row}`).merge();put(s,`A${row}`,v);s.getRange(`A${row}:${last}${row}`).format={wrapText:true,rowHeight:34};}
function table(s,r,h,rows,n,height=35){const last=col(h.length),end=r+rows.length;s.getRange(`A${r}:${last}${end}`).values=[h,...rows];s.tables.add(`A${r}:${last}${end}`,true,n).showBandedRows=false;s.getRange(`A${r}:${last}${end}`).format={wrapText:true,rowHeight:height};s.getRange(`A${r}:${last}${r}`).format={fill:navy,font:{name:font,size:10,bold:true,color:'#FFFFFF'},wrapText:true,rowHeight:34,horizontalAlignment:'center',verticalAlignment:'center'};}
const p=sheets['参数与定权'];base(p,[29,18,24,22,26,54],51);title(p,'参数与定权');line(p,3,'蓝字为参数；认知映射来自本次快照。权重拟合后固定，修改输入不自动重估熵权。','F');
p.getRange('A5:B9').values=[['自然完成率 q',.6],['认知组预算',.8],['组内熵权混合比例',.25],['全领域重要性之和',null],['熵权标定 s3 样本量',139]];
formula(p,'B8','=SUM(D20:D30)');p.getRange('B5:B7').setNumberFormat('0.0%');p.getRange('B5:B7').format.font.color='#2251FF';
put(p,'A10','参数状态');formula(p,'B10','=IF(AND(COUNT(B5:B7)=3,MIN(B5:B7)>=0,MAX(B5:B7)<=1,COUNT(B13:C15)=6,MIN(B13:C15)>=0,ABS(SUM(B13:B15)-1)<0.000000001,ABS(SUM(C13:C15)-1)<0.000000001,COUNT(C20:D30)=22,MIN(C20:C30)>=1,MAX(C20:C30)<=6,MIN(D20:D30)>0),"有效","参数缺失或越界")');
table(p,12,['指标','组内偏好','组内熵权（冻结）','正式权重','纯熵权（冻结）','含义'],['整体净CTQ','平均净CTQ','最高净CTQ','QAPro占比'].map((n,i)=>[n,i<3?d.prior[i]:null,i<3?d.cognition_entropy[i]:null,null,d.entropy_weights[i],i<3?'认知组预算×偏好与熵权混合':'固定过程质量预算']),'WeightParams',36);
for(let i=0;i<3;i++)formula(p,`D${13+i}`,`=IF($B$10="有效",$B$6*((1-$B$7)*B${13+i}+$B$7*C${13+i}),"参数待修正")`);
formula(p,'D16','=IF($B$10="有效",1-B6,"参数待修正")');p.getRange('B13:E16').setNumberFormat('0.00%');p.getRange('B13:B15').format.font.color='#2251FF';
table(p,19,['模块','概念领域','目标分','重要性','量尺','参数来源'],d.modules.map(m=>[m.module,m.domain,m.target,m.importance,['topic-09','topic-10'].includes(m.module)?'s6':'s3','目标来自新版映射；重要性本轮统一1']),'ModuleParams',40);p.getRange('C20:D30').format.font.color='#2251FF';
line(p,32,'自然完成率0.60及重要性是研究设定；没有未使用AI对照组，不能据此识别因果净效应。','F');
table(p,34,['来源','快照键','SHA256','版本','记录角色','原始位置'],Object.entries(d.manifest).map(([k,v])=>[k,k,v.sha256,d.version,'只读输入',v.source]),'Sources',55);p.getRange('C35:C39').format.font.size=9;
line(p,41,'标定权重与稳健性统计对应固定快照。更换数据需重新运行分析，不在Excel中默默重定权。','F');

const ce=sheets['概念证据'];base(ce,[23,12,9,26,14,14,13,12,15,15,15,16,16,16,28,13],d.components.length+8);title(ce,'概念级证据及净进展计算');line(ce,3,'CTQ取固定起点到最高有效终点；自然基线按个人起点扣除；原始证据未覆盖的概念不补零。','P');
table(ce,5,['学生学期','学期','量尺','概念领域','起点评分','最高评分','目标','重要性','实际CTQ','自然CTQ','净CTQ','加权净CTQ','加权实际','加权自然','对话证据ID','同任务'],d.components.map(r=>[r.student_key,r.term,r.scale,r.domain,r.before,r.after,null,null,null,null,null,null,null,null,r.evidence,r.same_task?'是':'否']),'ConceptEvidence',28);
const conceptRows=new Map();
d.components.forEach((r,i)=>{const row=6+i,mi=d.modules.findIndex(m=>m.domain===r.domain)+20;const key=r.student_key+'|'+r.scale;if(!conceptRows.has(key))conceptRows.set(key,[]);conceptRows.get(key).push(row);
 formula(ce,`G${row}`,`=IF(ISNUMBER('参数与定权'!C${mi}),'参数与定权'!C${mi},"缺目标")`);formula(ce,`H${row}`,`=IF(ISNUMBER('参数与定权'!D${mi}),'参数与定权'!D${mi},"缺重要性")`);
 formula(ce,`I${row}`,`=IF(AND(COUNT(E${row}:F${row})=2,MIN(E${row}:F${row})>=1,MAX(E${row}:F${row})<=6),MAX(0,(F${row}-E${row})/5),"前后值缺失或越界")`);
 formula(ce,`J${row}`,`=IF(AND(ISNUMBER('参数与定权'!$B$5),ISNUMBER(G${row}),ISNUMBER(E${row})),'参数与定权'!$B$5*MAX(G${row}-E${row},0)/5,"缺基线参数")`);
 formula(ce,`K${row}`,`=IF(COUNT(I${row}:J${row})=2,I${row}-J${row},"不可计算")`);
 for(const [out,input] of [['L','K'],['M','I'],['N','J']])formula(ce,`${out}${row}`,`=IF(AND(ISNUMBER(${input}${row}),ISNUMBER(H${row})),${input}${row}*H${row},"不可计算")`);
});ce.getRange(`E6:N${5+d.components.length}`).setNumberFormat('0.0000;(0.0000);0.0000');ce.freezePanes.freezeRows(5);ce.freezePanes.freezeColumns(4);

const st=sheets['学生评分'];base(st,[23,12,9,12,15,15,15,11,11,14,13,13,13,15,13,15,13,15,13,15,13,14,14,14,14,14,14,23,11,34],d.rows.length+8);title(st,'学生评分与同学期同量尺排名');line(st,3,'148条记录对应147名学生；s3、s6及春秋分别排名。筛选列可选学期/量尺，得分列可排序。并列采用平均名次。','AD');
const headers=['学生学期','学期','量尺','可评概念数','整体净CTQ','平均净CTQ','最高净CTQ','QAPro数','QA3含Pro','质量占比','总量标准分','均值标准分','峰值标准分','推荐AIV','组内名次','均衡AIV','均衡名次','突破AIV','突破名次','熵权AIV','熵权名次','总量贡献','均值贡献','峰值贡献','质量贡献','DHI＝平均实际CTQ','平均自然CTQ','净进展诊断','MAB','自主自述分类'];
table(st,5,headers,d.rows.map(r=>[r.student_key,r.term,r.scale,r.n,null,null,null,r.qapro,r.qa3,...Array(18).fill(null),null,r.mab,r.self]),'StudentScores',28);
const end=5+d.rows.length;
d.rows.forEach((r,i)=>{let row=6+i,cr=conceptRows.get(r.student_key+'|'+r.scale);const refs=c=>cr.map(n=>`'概念证据'!${c}${n}`).join(',');const gated=f=>`=IF(AND('参数与定权'!$B$10="有效",COUNT(${refs('K')})=${cr.length},COUNT(${refs('H')})=${cr.length}),${f},"参数或证据待修正")`;
 formula(st,`E${row}`,gated(`SUM(${refs('L')})`));formula(st,`F${row}`,gated(`E${row}/SUM(${refs('H')})`));formula(st,`G${row}`,gated(`MAX(${refs('K')})`));
 formula(st,`J${row}`,`=IF(AND(COUNT(H${row}:I${row})=2,I${row}>0,H${row}>=0,H${row}<=I${row}),H${row}/I${row},"缺有效分母")`);
 for(const [out,f] of [['K',`(1+E${row}/'参数与定权'!$B$8)/2`],['L',`(1+F${row})/2`],['M',`(1+G${row})/2`]])formula(st,`${out}${row}`,gated(f));
 const checks=`AND(COUNT(J${row}:M${row})=4,COUNT('参数与定权'!$D$13:$D$16)=4)`;
 formula(st,`N${row}`,`=IF(${checks},SUM(V${row}:Y${row}),"不可评分")`);
 for(const [cc,f] of [['P',`100*(0.3*K${row}+0.3*L${row}+0.2*M${row}+0.2*J${row})`],['R',`100*(0.2*K${row}+0.2*L${row}+0.4*M${row}+0.2*J${row})`],['T',`100*(K${row}*'参数与定权'!$E$13+L${row}*'参数与定权'!$E$14+M${row}*'参数与定权'!$E$15+J${row}*'参数与定权'!$E$16)`]])formula(st,`${cc}${row}`,`=IF(${checks},${f},"不可评分")`);
 for(const [out,sc] of [['O','N'],['Q','P'],['S','R'],['U','T']]){const rr=`$${sc}$6:$${sc}$${end}`;formula(st,`${out}${row}`,`=IF(ISNUMBER(${sc}${row}),1+COUNTIFS($B$6:$B$${end},B${row},$C$6:$C$${end},C${row},${rr},">"&${sc}${row})+(COUNTIFS($B$6:$B$${end},B${row},$C$6:$C$${end},C${row},${rr},${sc}${row})-1)/2,"不可排名")`);}
 for(const [out,src,param] of [['V','K',13],['W','L',14],['X','M',15],['Y','J',16]])formula(st,`${out}${row}`,`=IF(${checks},100*${src}${row}*'参数与定权'!$D$${param},"不可计算")`);
 formula(st,`Z${row}`,gated(`SUM(${refs('M')})/SUM(${refs('H')})`));formula(st,`AA${row}`,gated(`SUM(${refs('N')})/SUM(${refs('H')})`));formula(st,`AB${row}`,`=IF(ISNUMBER(F${row}),IF(F${row}>0.0000000001,"高于当前自然基线",IF(F${row}< -0.0000000001,"低于当前自然基线","等于当前自然基线")),"不可诊断")`);
});st.getRange(`E6:G${end}`).setNumberFormat('0.0000;(0.0000);0.0000');st.getRange(`J6:M${end}`).setNumberFormat('0.0%');st.getRange(`N6:AA${end}`).setNumberFormat('0.00');st.getRange(`Z1:Z${end}`).format.columnWidth=24;for(const cc of ['O','Q','S','U'])st.getRange(`${cc}6:${cc}${end}`).setNumberFormat('0.0');st.freezePanes.freezeRows(5);st.freezePanes.freezeColumns(3);

const s=sheets['最终结论'];base(s,[26,20,23,34,45],40);title(s,'AIV 最终指标与定权结果');line(s,3,'30项候选归结为8项字段：4项计分、1项自然基线、3项诊断。主方法为分层约束熵权＋偏好收缩。','E');
const core=[['整体加权净CTQ',null,'计分','已核验概念净进展之和','固定全课程锚点归一'],['平均净CTQ',null,'计分','有效概念的平均净进展','作为主要认知视角'],['最高知识点净CTQ',null,'计分','先扣各概念基线，再取最高','限制单次峰值的主导性'],['QAPro占比',null,'计分','QAPro÷QA3（含QAPro）','非QA3不进入分母'],['加权自然CTQ',null,'仅作基线','已在三个净CTQ中扣除','不再独立加分或扣分'],['DHI',0,'诊断','进展分布健康度','与平均CTQ结构性重复'],['MAB',0,'诊断','去重智能体数量','增量相关弱，存在机会混杂'],['学生自主评价',0,'诊断','保留讨论分类','未有独立行为核验，不转换能力分']];
table(s,5,['最终字段','正式权重','用途','定义','筛选结论'],core,'FinalCore',44);for(let i=0;i<4;i++)formula(s,`B${6+i}`,`='参数与定权'!D${13+i}`);s.getRange('B6:B13').setNumberFormat('0.00%');
table(s,16,['范围','数量','性质','处理','结果说明'],[['源学生学期',369,'全量','222人不评分','缺失不等于0分'],['可评学生学期',147,'有证据','输出148条量尺记录','1名学生有两种量尺'],['s3记录',139,'主要分析','按秋110、春29分别排名','合并仅用于方法敏感性'],['s6记录',9,'探索描述','按秋5、春4分别排名','不与s3混排']],'ScopeSummary',35);
line(s,22,'推荐权重针对当前快照冻结。q=0.60为研究情景，未取得自然教学对照组。AIV不能直接解释为AI因果净效应。','E');
line(s,24,'权重±10%：前列28人保持不变，但个别名次可变化25名。自然基线q=0.40—0.80：正净进展人数69人降至8人。','E');
line(s,26,'只在q=0.40—0.80均为正的s3学生有8人；70人均为负，61人的正负依赖基线。负值不等于AI造成伤害。','E');
line(s,28,'蓝字参数调整后，评分和组内名次重算；方案与稳健性为冻结分析表，状态提示会标记参数改变。','E');
formula(s,'A30',`=IF('参数与定权'!B10="有效","当前参数可计算","当前参数不完整，请查看参数表")`);

const pool=sheets['30项筛选'];base(pool,[7,15,30,35,15,28,32,23,42],39);title(pool,'30项候选指标的最终取舍');line(pool,3,'可得性指当前材料。初筛14项，核心复核10项，最终8字段；数值权重只对4个可评分项计算。','I');table(pool,5,['编号','大类','指标','意义','可得性','稳定性','相关性','最终定位','决定依据'],d.pool,'Candidate30',53);pool.freezePanes.freezeRows(5);pool.freezePanes.freezeColumns(3);

const ss=sheets['方案与稳健性'];base(ss,[33,22,22,22,22,22,43],87);title(ss,'方案对比与稳健性结果');
const unchanged=`AND(ABS('参数与定权'!B5-0.6)<0.000000001,ABS('参数与定权'!B6-0.8)<0.000000001,ABS('参数与定权'!B7-0.25)<0.000000001,${d.modules.flatMap((m,i)=>[`'参数与定权'!C${20+i}=${m.target}`,`'参数与定权'!D${20+i}=1`]).join(',')},${d.weights.map((x,i)=>`ABS('参数与定权'!D${13+i}-${x})<0.000000001`).join(',')})`;
formula(ss,'A3',`=IF('参数与定权'!B10<>"有效","参数无效，快照不适用",IF(${unchanged},"以下为当前冻结参数的已计算快照","参数已改变：以下快照需重跑分析；学生评分已按新参数计算"))`);ss.getRange('A3:G3').merge();ss.getRange('A3:G3').format={wrapText:true,rowHeight:34};
table(ss,5,['方案','总量权重','平均权重','峰值权重','质量权重','排名ρ','最大名次变化'],d.comparisons.map(x=>[x.name,...x.weights,x.rho,x.max_rank_change]),'Comparison',34);ss.getRange('B6:E9').setNumberFormat('0.00%');ss.getRange('F6:F9').setNumberFormat('0.0000');
line(ss,11,'139条s3记录合并作方法比较，前20%阈值为第28人得分，边界并列全部保留。四方案前列28人相同。','G');
table(ss,13,['检验','排名ρ','最大名次变化','前列交集人数','推荐前列人数','最大分差','备注'],d.sensitivity.map(x=>[x.name,x.rho,x.max_rank_change,x.top_intersection,x.top_base,x.max_score_change,x.n?`只在${x.n}条MAB完整记录比较`:(x.q?`正净进展${x.positive_net}人`:'同139条s3记录')]),'Sensitivity',36);ss.getRange('B14:B24').setNumberFormat('0.0000');ss.getRange('F14:F24').setNumberFormat('0.00');
table(ss,27,['权重联合角点','排名ρ','最大名次变化','前列交集人数','推荐前列人数','最大分差','扰动定义'],d.corners.map(x=>[x.factors.join(' / '),x.rho,x.max_rank_change,x.top_intersection,x.top_base,x.max_score_change,'各权重×0.9或1.1后归一']),'Corners16',29);ss.getRange('B28:B43').setNumberFormat('0.0000');ss.getRange('F28:F43').setNumberFormat('0.00');
table(ss,46,['Pearson相关','整体净CTQ','平均净CTQ','最高净CTQ','质量占比','含义','范围'],d.pearson.map((r,i)=>[['整体净CTQ','平均净CTQ','最高净CTQ','质量占比'][i],...r,'认知项高相关','139条s3记录']),'Correlation',32);ss.getRange('B47:E50').setNumberFormat('0.000');
const compactMethods=[['分层约束熵权＋偏好收缩','采用','认知80%、质量20%。组内以偏好为主，熵权为辅。','权重已计算，同批学生共用'],['AHP','不作主定权','缺真实专家成对判断矩阵','使用明示偏好，不虚构专家共识'],['熵权法','已计算对照','纯熵权使质量权重过大','仅采纳组内熵权信息'],['回归分析','不作主定权','缺独立效标，CTQ高度相关','不以同源结果循环验证'],['多目标优化','不作自动选优','缺外部准确性目标','比较多项表现，不宣称数学最优'],['贝叶斯方法','不作主定权','缺独立似然与误差模型','不把确定性收缩称作后验'],['线性加权和','采用','单调、有界、贡献可加','非线性仅作敏感性对照']];
table(ss,53,['方法','最终选择','决定依据','实施结果'],compactMethods,'Methods',66);
line(ss,63,'Bootstrap 500次只检验定权波动，不包含认知标注误差或因果不确定性。q敏感性才揭示本轮增量正负判断的主要风险。','G');
ss.freezePanes.freezeRows(5);

const cov=sheets['覆盖与缺失'];base(cov,[23,13,13,13,13,19,68,40],d.roster.length+8);title(cov,'全量覆盖及缺失原因');line(cov,3,'覆盖当前369名学生学期。无可评前后证据不赋0分；MAB与自述缺失也不补0。','H');table(cov,5,['学生学期','会话数','QA3含Pro','QAPro数','MAB','可评分量尺','未采纳领域状态与数量','自述分类'],d.roster,'CoverageAll',37);cov.freezePanes.freezeRows(5);cov.freezePanes.freezeColumns(1);

flush();wb.recalculate();
const near=(a,b)=>typeof a==='number'&&Math.abs(a-b)<1e-8;
for(let i=0;i<d.rows.length;i++){const r=d.rows[i],row=6+i;for(const [cell,num] of [[`N${row}`,r.scores['推荐']],[`P${row}`,r.scores['均衡发展']],[`R${row}`,r.scores['高阶突破']],[`T${row}`,r.scores['纯熵权']],[`O${row}`,r.ranks['推荐']]])if(!near(st.getRange(cell).values[0][0],num))throw Error(`独立复算不一致 ${cell}: ${JSON.stringify(st.getRange(cell).values)} != ${num}`);}
const initial=st.getRange('N6').values[0][0];p.getRange('B5').values=[[.7]];wb.recalculate();if(near(initial,st.getRange('N6').values[0][0]))throw Error('q输入未传递');if(!ss.getRange('A3').values[0][0].includes('参数已改变'))throw Error('快照过期未提示');
p.getRange('B5').clear({applyTo:'contents'});wb.recalculate();if(typeof st.getRange('N6').values[0][0]==='number')throw Error('缺q仍出分');p.getRange('B5').values=[[.6]];
const oldnum=st.getRange('H6').values[0][0],oldrank=st.getRange('O6').values[0][0];st.getRange('H6').values=[[0]];wb.recalculate();if(near(oldrank,st.getRange('O6').values[0][0]))throw Error('改比例名次未更新');st.getRange('H6').values=[[oldnum]];
p.getRange('B6').values=[[-.1]];wb.recalculate();if(typeof st.getRange('N6').values[0][0]==='number')throw Error('负权重未拒绝');p.getRange('B6').values=[[.8]];wb.recalculate();
const savedBefore=ce.getRange('E6').values[0][0];ce.getRange('E6').clear({applyTo:'contents'});wb.recalculate();if(typeof st.getRange('N6').values[0][0]==='number')throw Error('缺证据仍出分');ce.getRange('E6').values=[[7]];wb.recalculate();if(typeof st.getRange('N6').values[0][0]==='number')throw Error('越界证据仍出分');ce.getRange('E6').values=[[savedBefore]];wb.recalculate();
const errors=await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!',options:{useRegex:true,maxResults:30}});await fs.writeFile(path.join(import.meta.dirname,'formula-error-scan.json'),JSON.stringify(errors));
const output=path.join(dir,'AIV最终指标定权与学生评分.xlsx');await(await SpreadsheetFile.exportXlsx(wb)).save(output);
const re=await SpreadsheetFile.importXlsx(await FileBlob.load(output));if(!near(re.worksheets.getItem('学生评分').getRange('N6').values[0][0],initial))throw Error('保存重读不一致');
const views=[['最终结论','A1:E30','conclusion'],['学生评分','A1:O15','scores'],['学生评分','V5:AD15','contributions'],['30项筛选','A1:I15','pool1'],['30项筛选','A16:I35','pool2'],['方案与稳健性','A1:G24','schemes'],['方案与稳健性','A27:G43','corners'],['方案与稳健性','A46:G61','methods'],['参数与定权','A1:F30','params'],['概念证据','A1:P14','evidence'],['覆盖与缺失','A1:H14','coverage']];
for(const [name,range,file] of views){if(!['contributions','methods'].includes(file))continue;const b=await wb.render({sheetName:name,range,scale:1.3,format:'png'});await fs.writeFile(path.join(import.meta.dirname,file+'.png'),new Uint8Array(await b.arrayBuffer()));}
await fs.writeFile(path.join(import.meta.dirname,'validation.json'),JSON.stringify({students:d.rows.length,concepts:d.components.length,independent_numeric_checks:d.rows.length*5,input_tests:['q changes score','blank q suppresses score','quality edit changes rank','negative group weight rejected','snapshot stale warning','missing concept evidence suppresses score','out of range evidence suppresses score'],export_reimport:true,native_excel_tested:false,output},null,2));console.log(output);
