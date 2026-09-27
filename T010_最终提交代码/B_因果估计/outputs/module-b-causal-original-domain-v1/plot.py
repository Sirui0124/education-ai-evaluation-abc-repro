from pathlib import Path
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
O=Path(__file__).parent;r=json.loads((O/'results.json').read_text());q=np.linspace(0,.8,161);base=r['scenarios'][0]['student_equal_mean'];slope=base/r['critical_q'];fig,ax=plt.subplots(figsize=(8,4.6));ax.plot(q,base-q*slope,color='#25455b',lw=2,label='Observed gain minus assumed baseline');ax.axhline(0,color='#777',lw=.8)
for x in [.23,.48]:
 y=base-x*slope;ax.scatter([x],[y],color='#c27737',zorder=3);ax.annotate(f'q={x:.0%}: {y:+.3f}',(x,y),xytext=(10,14),textcoords='offset points');ax.axvline(x,color='#aaa',ls=':',lw=.8)
ax.axvline(r['critical_q'],color='#9b3846',ls='--',lw=1,label=f"Zero crossing: {r['critical_q']:.2%}");ax.set(xlabel='Assumed conventional-learning fraction q (not observed)',ylabel='Remaining empirical-score change',title='Baseline sensitivity: 147 pairs / 139 students / 9 original domains');ax.legend(frameon=False,fontsize=9);ax.spines[['top','right']].set_visible(False);fig.text(.11,.01,'Descriptive sensitivity only; no untreated control and no identified AI causal effect.',fontsize=9);fig.tight_layout(rect=[0,.035,1,1]);fig.savefig(O/'baseline_sensitivity.png',dpi=180);fig.savefig(O/'baseline_sensitivity.pdf')
print('Saved scientific sensitivity figure')
