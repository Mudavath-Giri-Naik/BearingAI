import io
import numpy as np
import pandas as pd
from scipy.stats import skew, kurtosis
from scipy.signal import find_peaks
GRID=np.linspace(0,561.25,450)
BANDS=[(0,25),(25,50),(50,100),(100,200),(200,350),(350,561.26)]
class InvalidSignal(ValueError):pass
def parse(raw):
 if len(raw)>2_000_000:raise InvalidSignal('CSV exceeds 2 MB')
 try:
  d=pd.read_csv(io.BytesIO(raw),encoding='utf-8-sig')
  x=pd.to_numeric(d.iloc[:,0],errors='raise').to_numpy(float)
  y=pd.to_numeric(d.iloc[:,1],errors='raise').to_numpy(float)
 except Exception as e:raise InvalidSignal('Invalid CSV frequency/magnitude columns') from e
 if len(x)!=450 or not np.isfinite(x).all() or not np.isfinite(y).all() or np.any(np.diff(x)<=0) or abs(x[0])>.02 or x[-1]<561.15 or x[-1]>1122.6 or (y<0).any():
  raise InvalidSignal('Expected 450 finite, nonnegative magnitude rows with increasing frequency from 0 to at least 561.25 Hz')
 return x,y
def features(raw):
 x,y=parse(raw); a=np.interp(GRID,x,y); log=np.log10(np.maximum(a,1e-8));eps=1e-12
 d={}
 for name,z in [('mag',a),('logmag',log)]:
  d.update({name+'_mean':float(z.mean()),name+'_std':float(z.std()),name+'_median':float(np.median(z)),name+'_max':float(z.max()),name+'_min':float(z.min()),name+'_p05':float(np.percentile(z,5)),name+'_p95':float(np.percentile(z,95)),name+'_skew':float(skew(z)),name+'_kurtosis':float(kurtosis(z))})
 energy=a*a;total=energy.sum()+eps;p=energy/total;peaks,props=find_peaks(a,prominence=max(a.max()*.1,1e-8))
 d.update(rms=float(np.sqrt(np.mean(energy))),crest_factor=float(a.max()/(np.sqrt(np.mean(energy))+eps)),peak_count=float(len(peaks)),prominence_sum=float(props['prominences'].sum()),spectral_centroid=float((GRID*a).sum()/(a.sum()+eps)),spectral_entropy=float(-(p*np.log(p+eps)).sum()))
 for i,j in enumerate(np.argsort(a)[-5:][::-1]):d[f'top{i+1}_frequency']=float(GRID[j]);d[f'top{i+1}_magnitude']=float(a[j])
 for lo,hi in BANDS:
  z=a[(GRID>=lo)&(GRID<hi)]; name=f'band_{int(lo)}_{int(hi)}';d[name+'_energy_fraction']=float((z*z).sum()/total);d[name+'_max']=float(z.max());d[name+'_mean']=float(z.mean())
 # v3 multiscale patterns: summarize local signal shape, normalized shape, and peak geometry.
 sm=np.maximum(a,1e-10);la=np.log10(sm);diff=np.diff(la)
 d['log_gradient_std']=float(diff.std());d['log_gradient_p95']=float(np.percentile(np.abs(diff),95));d['log_gradient_total']=float(np.abs(diff).mean())
 for i in range(12):
  lo=int(i*450/12); hi=int((i+1)*450/12);b=sm[lo:hi]; lb=la[lo:hi]
  d[f'seg{i}_logmean']=float(lb.mean()); d[f'seg{i}_logstd']=float(lb.std())
  d[f'seg{i}_logmax']=float(lb.max());d[f'seg{i}_relative_energy']=float((b*b).sum()/total)
 for j,pct in enumerate([.025,.05,.10,.20]):
  pk,_=find_peaks(sm,prominence=max(sm.max()*pct,1e-10))
  d[f'peak_count_pct_{j}']=float(len(pk))
 for k in [3,5,10,20,40]:
  d[f'top{k}_energy_frac']=float(np.sort(energy)[-k:].sum()/total)
 for lag in [1,2,4,8,16,32]:
  d[f'log_autocorr_{lag}']=float(np.corrcoef(la[:-lag],la[lag:])[0,1]) if la.std()>1e-9 else 0.
 if not np.isfinite(list(d.values())).all():raise InvalidSignal('Non-finite features')
 return d
