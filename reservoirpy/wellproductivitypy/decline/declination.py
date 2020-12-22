import pandas as pd
import numpy as np
from scipy.optimize import curve_fit
from datetime import date, timedelta
import matplotlib.pyplot as plt
from .dca import DCA

############################################################################################
# Forecast Function
def forecast_curve(range_time,qi,di,ti,b,npi=0, gas=False, fluid_rate=None, gor=None, bsw=None):
  """forecast_curve [Estimate a Forecast curve given Decline curve parameters]

  Parameters
  ----------
  range_time : [type]
      [Time range ]
  qi : [type]
      [Initial flow]
  di : [type]
      [Anual declination rate]
  ti : [type]
      [Date of the initial flow]
  b : [type]
      [Arp's parameter]
  npi : int, optional
      [Initial cumulative production], by default 0
  gas : bool, optional
      [If True the colunm names change], by default False

  Returns
  -------
  [type]
      [description]
  """
  ##Convert dates to number for apply regression methods

  days_number = range_time.apply(lambda x: x.toordinal()) 
  ti_day = ti.toordinal()

  #Estimate the difference in days between the dates to forecast and Initial Ti
     
  day_diff = days_number-ti_day                          

  if b == 0:
    q = qi*np.exp(-(di/365)*day_diff) 
  elif (b>0)&(b<=1):
    q = qi/np.power(1+b*(di/365)*day_diff,1/b)

  #diff_period = np.append(np.array([0]),np.diff(days_number))
  diff_period = np.diff(days_number,append=0)
  diff_q = diff_period * q 
  cum = diff_q.cumsum()
  cum = cum + npi
  
  if gas:
    df_dict = {
      'time':range_time[:-1],
      'qg':q[:-1],
      'vg':diff_q[:-1],
      'gp':cum[:-1],
    }
  else:
    df_dict = {
          'time':range_time[:-1],
          'qo':q[:-1],
          'vo':diff_q[:-1],
          'np':cum[:-1],
    }
  
  #Caculate water rate by providing either fluid rate or bsw. 
  if any([fluid_rate is not None,bsw is not None]):
    
    #If fluid rate and Bsw are provided the 'fluid_rate' parameters has priority
    if fluid_rate is not None:
      qw = fluid_rate - q 
    elif bsw is not None:
      qw = (bsw*q)/(1-bsw) 
      
    diff_qw = diff_period * qw
    cumw = diff_qw.cumsum()
    df_dict.update({
        'qw':qw[:-1],
        'vw':diff_qw[:-1],
        'wp':cumw[:-1],      
    })
     
  if gor is not None:
    qg = (gor/1000) * q
    diff_qg = diff_period * qg
    cumg = diff_qg.cumsum()
    df_dict.update({
        'qg':qg[:-1],
        'vg':diff_qg[:-1],
        'gp':cumg[:-1],      
    })
  forecast = pd.DataFrame(df_dict)
  forecast = forecast.set_index('time')
  forecast = forecast.round(2)
  total_cum = forecast['gp'].iloc[-1]  if gas else forecast['np'].iloc[-1] 
  
  return forecast, total_cum

def forecast_econlimit(t,qt,qi,di,ti,b, fr, end_date=None,npi=0,gas=False, fluid_rate=None, gor=None, bsw=None):
  """
  Estimate a Forecast curve until a given Economic limit rate and Decline curve parameters

  Attributes:
    t:         Initial date to start forecast
    qt:        Economic limit rate -> Number
    qi:        Initial flow rate -> Number
    di:        Decline rate in fraction and positive-> Number
    ti:        Date of the initial flow Rate-> Timestamp
    b:         Arp's Coefficient. 0<=b<=1  -> Number 

  Return -> Three-Column DataFrame: 
            -Column 'time' Timestamp Series 
            -Column 'curve' Forecast values Series
            -Column 'cum' cummulative flow rate
  """
  # Estimate the time at economic limit
  if b == 0:
    date_until = pd.Timestamp.fromordinal(int(np.log(qi / qt) * (1/(di/365))) + ti.toordinal())
  elif (b > 0) & (b <= 1):
    date_until = pd.Timestamp.fromordinal(int((np.power(qi / qt, b) - 1)/(b * (di/365))) + ti.toordinal())
  else:
    raise ValueError('b must be between 0 and 1')

  if end_date is not None and date_until > pd.Timestamp(end_date):
    date_until = end_date

  if date_until < t:
    f = pd.DataFrame({'time':[t],'rate':[0], 'cum':[npi]})
    f = f.set_index('time')
    Np = npi
    print('Rate has already reached economic limit established')
  else:
    TimeRange = pd.Series(pd.date_range(start=t, end=date_until, freq=fr))

    f, Np = forecast_curve(TimeRange,qi,di,ti,b, npi=npi, gas=gas, fluid_rate=fluid_rate,gor=gor, bsw=bsw)

  return f, Np

######################################################################
#Create Declination Object 

class Declination(DCA):
  """
  Decline curve object for Oil and Gas Forecasting
  
  Attributes:
    Qi: Initial Flow Rate in bbl/d: Number
    Di: Decline rate. Number must be positive and written in fraction: Number
    Ti: Date if Initial flow Rate (Qi): Timestamp
    b:  Arps Coefficient: 0<=b<=1  
  
   """
  def __init__(self, **kwargs):
    self.qi = kwargs.pop('qi',None)
    self.di = kwargs.pop('di',None)
    self.b = kwargs.pop('b',0)
    self.ti = kwargs.pop('ti',None)
    self.start_date = kwargs.pop('start_date',None)
    self.end_date = kwargs.pop('end_date',None)
    self.econ_limit = kwargs.pop('econ_limit', None)
    self.np_limit = kwargs.pop('np_limit', None)
    self.fluid_rate = kwargs.pop('fluid_rate',None)
    self.anomaly_points = kwargs.pop('anomaly_points',None)
    self.fq = kwargs.pop('fq','M')
    self.gas = kwargs.pop('gas',False)


#####################################################
############## Properties ###########################

  @property
  def qi(self):
    return self._qi

  @qi.setter
  def qi(self,value):
    if value is not None:
      assert isinstance(value,(int,float,np.ndarray)), f'{type(value)} not accepted. Name must be number'
    self._qi = value

  @property
  def di(self):
    return self._di

  @di.setter
  def di(self,value):
    if value is not None:
      assert isinstance(value,(int,float,np.ndarray)), f'{type(value)} not accepted. Name must be number'
    self._di = value

  @property
  def b(self):
    return self._b

  @b.setter
  def b(self,value):
    assert isinstance(value,(int,float,np.ndarray)), f'{type(value)} not accepted. Name must be number'
    assert value >= 0 and value <= 1
    if value <= 1.0e-2:
      value = 0
    elif value >= 0.99:
      value = 1
   
    self._b = value

  @property
  def ti(self):
    return self._ti

  @ti.setter
  def ti(self,value):
    if value is not None:
      assert isinstance(value,date), f'{type(value)} not accepted. Name must be date'
    self._ti = value

  @property
  def kind(self):
    if self._b == 0:
      self._kind='Exponential'
    elif self._b == 1:
      self._kind = 'Harmonic'
    elif (self._b<1)&(self._b>0):
      self._kind = 'Hyperbolic'
    return self._kind

  @property
  def start_date(self):
    return self._start_date
  
  @start_date.setter
  def start_date(self,value):
    if value is not None:
      assert isinstance(value,date), f'{type(value)} not accepted. It must be date'
    self._start_date = value

  @property
  def end_date(self):
    return self._end_date

  @end_date.setter
  def end_date(self,value):
    if value is not None:
      assert isinstance(value,date), f'{type(value)} not accepted. It must be date'
    self._end_date = value

  @property
  def anomaly_points(self):
    return self._anomaly_points

  @anomaly_points.setter
  def anomaly_points(self,value):
    if value is not None:
      assert isinstance(value,pd.DataFrame), f'{type(value)} not accepted. It must be pd.DataFrame'
    self._anomaly_points = value
  
  @property
  def econ_limit(self):
    return self._econ_limit

  @econ_limit.setter
  def econ_limit(self,value):
    if value is not None:
      assert isinstance(value,(int,float,np.ndarray)), f'{type(value)} not accepted. Name must be number'
    self._econ_limit = value

  @property
  def np_limit(self):
    return self._np_limit

  @np_limit.setter
  def np_limit(self,value):
    if value is not None:
      assert isinstance(value,(int,float,np.ndarray)), f'{type(value)} not accepted. Name must be number'
    self._np_limit = value

  @property
  def fluid_rate(self):
      return self._fluid_rate

  @fluid_rate.setter
  def fluid_rate(self,value):
      if value is not None:
          assert isinstance(value,(int,float,np.ndarray)), f'{type(value)} not accepted. Name must be number'
      self._fluid_rate = value

  @property
  def fq(self):
      return self._fq

  @fq.setter
  def fq(self,value):
      assert isinstance(value,str), f"{type(value)} not accepted. Name must be str"     
      self._fq = value

  @property
  def gas(self):
    return self._gas

  @gas.setter
  def gas(self,value):
    assert isinstance(value,bool), f'{type(value)} not accepted.  must be bool'
    self._gas = value

  def __str__(self):
    return '{self.kind} Declination \n Ti: {self.ti} \n Qi: {self.qi} bbl/d \n Rate: {self.di} Annually \n b: {self.b}'.format(self=self)
  
  def __repr__(self):
    return '{self.kind} Declination \n Ti: {self.ti} \n Qi: {self.qi} bbl/d \n Rate: {self.di} Annually \n b: {self.b}'.format(self=self)

  def forecast(self,
    start_date:date=None, 
    end_date:date=None, 
    fq:str=None,
    econ_limit:float=None,
    np_limit:float=None,
    npi:float=0, 
    fluid_rate:float=None,
    show_water:bool = False,
    gor = None,
    bsw=None,
    **kwargs
    ):
    """
    Forecast curve from the declination object. 
 
    Input: 
        start_date ->  (datetime.date) Initial date Forecast
        end_date ->  (datetime.date) end date Forecast
        fq -> (str) frequecy for the time table. 
              Use https://pandas.pydata.org/pandas-docs/stable/user_guide/timeseries.html#timeseries-offset-aliases
        econ_limit -> (int,float,np.dnarray) Economic limit Rate. If end_date 

    Return: 
      f: DataFrame with t column and curve column
      np: Cummulative production

    """
    if econ_limit is None:
      econ_limit = self.econ_limit
    else:
      assert isinstance(econ_limit,(int,float,np.ndarray)), 'econ_limit must be a number'

    if fq is None:
      fq = self.fq
    else:
      assert isinstance(fq,str), 'fq must be str'

    if start_date is None: 
      if self.start_date is None:
        start_date = self.ti
      else:
        start_date = self.start_date
    else:
      assert isinstance(start_date,date), 'start_date must be date'

    if end_date is None: 
      if self.end_date is None:
        end_date = self.ti + timedelta(days=365) if econ_limit is None else None
      else:
        end_date = self.end_date
    else:
      assert isinstance(end_date,date), 'end_date must be date'

    if np_limit is None:
      np_limit = self.np_limit
    else:
      assert isinstance(np_limit,(int,float,np.ndarray)), 'econ_limit must be a number'

    if fluid_rate is None:
      fluid_rate = self.fluid_rate

    if econ_limit is None:
      time_range = pd.Series(pd.date_range(start=start_date, end=end_date, freq=fq, **kwargs))
      f, Np = forecast_curve(time_range,self.qi,self.di,self.ti,self.b,npi=npi, gas=self.gas,fluid_rate=fluid_rate, gor=gor, bsw=bsw)
    else:
      f, Np = forecast_econlimit(start_date,econ_limit,self.qi,self.di,self.ti,self.b, fr=fq,end_date=end_date,npi=npi,gas=self.gas,fluid_rate=fluid_rate,gor=gor, bsw=bsw)

    if np_limit is not None:
      if Np > np_limit:
        f = f.loc[f['np']<np_limit,:]
        Np = f.iloc[-1,-1]

    if show_water and any([fluid_rate is not None, bsw is not None]):
      f['bsw'] = f['qw'] / (f['qw'] + f['qo'])
      f['wor'] = f['qw'] / f['qo']
      f['wor_1'] = f['wor'] + 1

    return f, Np

  ################################################################################
  #Decline Fit
  def fit(self,df:pd.DataFrame,time:str='time',rate:str='rate',b=None, ad=True,xstd=2, adjust_last_prod=False):
    """
    Estimate the declination parameters of a time series of production daily rate
    as a Decline Curve defined by Arps

      Attributes:
      df: (pd.DataFrame)  DataFrame with with time and rate columns
      time: (str, default 'time') column name of the datetime
      rate: (str, default 'rate') column name of the rate
      b:         Arp's Coefficient. 0<=b<=1  -> If None b parameter is also fitted
                                            -> if  (b>=0)&(b<=1) b is not fitted but fixed
                                            -> Default: None
      ad:        apply anomally detection    ->  Bool, Default: True
                

      Return -> q -> 1D Numpy array with the Flow rate
    """
    r=None # Return
    df = df.dropna()
    df = df[df[rate]>0]
    print("Shape of input dataframe ",df.shape[0])
    range_time = df[time]
    flow_rate = df[rate]
    if ad == True:
      #Convert date to ordinal
      tnum = range_time.apply(lambda x: x.toordinal()) 

      #logaritmit to flow rate
      lnq = np.log(flow_rate)

      # Derivative of the ln(flow_rate) with respect to time
      slp = -np.diff(lnq) / np.diff(tnum)
      slp = np.append(slp[0],slp)

      #Mean and std of derivative
      mu = slp.mean()
      sig=slp.std()

      #Extract the anomalies points
      range_time_a = range_time[np.abs(slp)>mu+xstd*sig]
      flow_rate_a = flow_rate[np.abs(slp)>mu+xstd*sig]
      if not range_time_a.empty and not flow_rate_a.empty:  
        r = pd.concat([range_time_a,flow_rate_a],axis=1)
        r.rename(columns={time: "date", rate: "rate"}, inplace=True)
        print(f"Revome {r.shape[0]} rows by anomalies")
      else:
        print("No row removed")

      #delete anomalies points to make the regression 
      range_time = range_time[np.abs(slp)<mu+xstd*sig]
      flow_rate = flow_rate[np.abs(slp)<mu+xstd*sig]
  
      #anomaly = pd.DataFrame({'time':range_time[np.abs(slp)>=mu+xstd*sig].values,'flow':flow_rate[np.abs(slp)>=mu+xstd*sig].values})
      #r.append(anomaly)
      print(f'new shape {range_time.shape[0]}')
    if b is None:
      
      def decline_function(range_time,qi,di,b):
        """
        Estimate the flow rate given the decline curve parameters assuming the Ti 
        to the first value on range_time. 
        
        This function is intended to be used with scipy.optimize.curve_fit function to
        create the cost function to fit the decline curve parameters to a given 
        production data. 

        Attributes:
          range_time: Range of dates to estimate the Forecast Curve-> Timestamp Series
          qi:        Initial flow rate -> Number
          di:        Decline rate in fraction and positive-> Number
          b:         Arp's Coefficient. 0<=b<=1  -> Number 

          Return -> q -> 1D Numpy array with the Flow rate: 
        """
        days_number = range_time.apply(lambda x: x.toordinal())
        ti_day = range_time.iloc[0].toordinal() 
        day_diff = days_number-ti_day 

        if b == 0:
          q = qi*np.exp(-(di/365)*day_diff) 
        elif (b>0) & (b<=1):
          q = qi/np.power(1+b*(di/365)*day_diff,1/b)
        
        return q
      
      popt, pcov = curve_fit(decline_function, range_time, flow_rate, bounds=(0, [np.inf, np.inf, 1]))
      #dec = declination(qi=popt[0], di=popt[1], ti=range_time[0], b=popt[2])
      self.qi = flow_rate.iloc[-1] if adjust_last_prod else popt[0]
      self.di = popt[1]
      self.ti = range_time.iloc[-1] if adjust_last_prod else range_time.iloc[0]
      self.b = popt[2]
      self.start_date = range_time.iloc[-1] if adjust_last_prod else range_time.iloc[0]
      self.end_date = range_time.iloc[-1] + timedelta(days=365) if adjust_last_prod else range_time.iloc[-1]
      self.anomaly_points = r

    elif (b >= 0) & (b <= 1):
      
      def decline_function(range_time,qi,di):
        """
        Estimate the flow rate given the decline curve parameters assuming the Ti 
        to the first value on range_time. 
        
        This function is intended to be used with scipy.optimize.curve_fit function to
        create the cost function to fit the decline curve parameters to a given 
        production data. 

        Attributes:
          range_time: Range of dates to estimate the Forecast Curve-> Timestamp Series
          qi:        Initial flow rate -> Number
          di:        Decline rate in fraction and positive-> Number
          b:         Arp's Coefficient. 0<=b<=1  -> Number 

          Return -> declination object
        """
        days_number = range_time.apply(lambda x: x.toordinal())
        ti_day  = range_time.iloc[0].toordinal() 
        day_diff = days_number-ti_day 
        b
        if b == 0:
          q = qi*np.exp(-(di/365)*day_diff) 
        elif (b>0)&(b<=1):
          q = qi/np.power(1+b*(di/365)*day_diff,1/b)
        
        return q 
      
      popt, pcov = curve_fit(decline_function, range_time, flow_rate, bounds=(0, [np.inf, np.inf]))
      #dec = declination(qi=popt[0], di=popt[1], ti=range_time.iloc[0], b=b)
      self.qi = flow_rate.iloc[-1] if adjust_last_prod else popt[0]
      self.di = popt[1]
      self.ti = range_time.iloc[-1] if adjust_last_prod else range_time.iloc[0]
      self.b = b
      self.start_date = range_time.iloc[0]
      self.end_date = range_time.iloc[-1]
      self.anomaly_points = r

  def plot(self, start_date=None, end_date=None, fq='M',econ_limit=None,ax=None,
    rate_kw={},cum_kw={},ad_kw={},cum=False,npi=0,anomaly=False, **kwargs):
    if start_date is None: 
      if self.start_date is None:
        start_date = self.ti
      else:
        start_date = self.start_date

    if end_date is None: 
      if self.end_date is None:
        end_date = self.ti + timedelta(days=365)
      else:
        end_date = self.end_date

    f,n = self.forecast(start_date=start_date, end_date=end_date, fq=fq ,econ_limit=econ_limit,npi=npi, **kwargs)
    #Create the Axex
    dax= ax or plt.gca()

    # Default kwargs for rate
    def_rate_kw = {
    'color': 'darkgreen',
    'linestyle':'--',
    'linewidth': 2
    }
    for (k,v) in def_rate_kw.items():
        if k not in rate_kw:
            rate_kw[k]=v

    # Default kwargs for cum
    def_cum_kw = {
    'color': 'darkgreen',
    'linestyle':'dotted',
    'linewidth': 2
    }
    for (k,v) in def_cum_kw.items():
        if k not in cum_kw:
            cum_kw[k]=v

    # Default kwargs for anomaly detection
    def_ad_kw = {
    'c': 'red',
    's':40,
    'marker': 'o'
    }
    for (k,v) in def_ad_kw.items():
        if k not in ad_kw:
            ad_kw[k]=v

    #Plotting
    dax.plot(f.index,f['qo'],**rate_kw)   

    if cum:
      cumax=dax.twinx()
      cumax.plot(f.index,f['np'],**cum_kw)  

    if anomaly and self.anomaly_points is not None:
      ad_df = self.anomaly_points
      dax.scatter(ad_df['date'],ad_df['qo'],**ad_kw)

#Hybrid declinations

## aux functions
def flow_limit(qi,dlim,di,b):
    ql = qi*np.power((dlim/di),1/b)
    return ql

def time_limit(qi,qlim,b,di):
    tl = ((np.power(qi/qlim,b)-1)/(b*di))*365
    return tl

class HybridDeclination(DCA):
  def __init__(self,dec_hyp, dlim):
    self.dec_hyp = dec_hyp
    self.dlim = dlim 
    self.qlim = flow_limit(dec_hyp.qi,dlim,dec_hyp.di,dec_hyp.b)
    self.tlim = dec_hyp.ti + timedelta(days=time_limit(dec_hyp.qi,self.qlim,dec_hyp.b,dec_hyp.di))
    self.dec_exp = declination(
        qi = self.qlim,
        di = dlim,
        b = 0,
        ti = self.tlim
    )

  @property
  def dec_hyp(self):
    return self._dec_hyp

  @dec_hyp.setter 
  def dec_hyp(self,value):
    assert isinstance(value,declination), "dec_hyp must be of type declination"
    assert value.b > 0, "b value must be greater than 0"
    self._dec_hyp = value 

  @property
  def dlim(self):
    return self._dlim 

  @dlim.setter
  def dlim(self,value):
    assert isinstance(value,(int,float))
    self._dlim = value 

  def forecast(self, start_date=None, end_date=None, fq='M'):
    if start_date is None:
      start_date = self.dec_hyp.ti
    
    if end_date is None:
      end_date = self.tlim + timedelta(days=365)

    if start_date < self.tlim and end_date > self.tlim:
      _forecast_1,_np_1 = self.dec_hyp.forecast(start_date=start_date, end_date=self.tlim, fq=fq)
      _forecast_2,_np_2 = self.dec_exp.forecast(start_date=self.tlim, end_date=end_date, fq=fq)
      _forecast_2['cum'] = _forecast_2['cum'] + _forecast_1['cum'].iloc[-1]
      _forecast = _forecast_1.append(_forecast_2)
      _np = _np_1 + _np_2
    
    elif start_date < self.tlim and end_date < self.tlim:
      _forecast,_np = self.dec_hyp.forecast(start_date=start_date, end_date=end_date, fq=fq)

    elif start_date > self.tlim and end_date > self.tlim:
      _forecast,_np = self.dec_exp.forecast(start_date=start_date, end_date=end_date, fq=fq)

    return _forecast,_np



