import numpy as np 
import pandas as pd 
from .outflow import one_phase_pressure_profile, two_phase_pressure_profile, two_phase_outflow_curve, two_phase_upward_pressure
from .als import Als
from .inflow import OilInflow
from ...pvtpy.black_oil import Pvt,Oil,Gas,Water


def nozzle_flow(
    an:float,
    pn:float,
    pps:float,
    grad:float
) -> float :
    """nozzle_flow [Calculate Nozzle flow in bbl/d ]

    :param an: [Annular area -> in2]
    :type an: float
    :param pn: [Nozzle Pressure -> psi]
    :type pn: float
    :param pps: [Pump Intake Pressure -> psi]
    :type pps: float
    :param grad: [Power fluid Gradient -> psi/ft]
    :type grad: float
    :return: [Nozzle flow -> bbl/d]
    :rtype: float
    """

    qn = 832 * an * np.sqrt((pn - pps)/grad)

    return qn

def minimum_suction_area(
    qs:float,
    gs:float,
    pps:float,
    bsw:float,
    gor:float
) -> float:

    acm = qs * (((1/691)*np.sqrt(gs/pps)) + (((1 - bsw)*gor)/(24650*pps)))

    return acm

class JetPump(Als):
    def __init__(self,**kwargs):
        self.n = kwargs.pop('n',15)
        self.surf_to_pump_depth_md = kwargs.pop('surf_to_pump_depth_md',None)
        self.pump_to_perf_depth_md = kwargs.pop('pump_to_perf_depth_md',None) 
        self.surf_to_pump_depth_tvd = kwargs.pop('surf_to_pump_depth_tvd',None)
        self.pump_to_perf_depth_tvd = kwargs.pop('pump_to_perf_depth_tvd',None) 
        self.brand = kwargs.pop('brand',None)
        self.nozzle = kwargs.pop('nozzle',None)
        self.throat = kwargs.pop('throat', None)
        self.power_fluid_ge =kwargs.pop('power_fluid_ge',1)
        self.injection_di = kwargs.pop('injection_di',2.99)
        self.return_di = kwargs.pop('return_di',5)
        self.prod_di = kwargs.pop('prod_di',5)
        self.kn = kwargs.pop('kn',0.03)
        self.ktd = kwargs.pop('kn',0.2)

        super().__init__(**kwargs)

    @property 
    def surf_to_pump_depth_md(self):
        return self._surf_to_pump_depth_md

    @surf_to_pump_depth_md.setter 
    def surf_to_pump_depth_md(self,value):
        if value is not None:
            if isinstance(value,(int,float)):
                value = np.linspace(0,value,self.n)
            elif isinstance(value,(list,np.ndarray)):
                value = np.atleast_1d(value)
                assert value.ndim == 1 
                assert np.all(np.diff(value) > 0)
            else:
                raise ValueError('Type not allowed')
        self._surf_to_pump_depth_md = value

    @property 
    def pump_to_perf_depth_md(self):
        return self._pump_to_perf_depth_md

    @pump_to_perf_depth_md.setter 
    def pump_to_perf_depth_md(self,value):
        if value is not None:
            if isinstance(value,(int,float)):
                try:
                    value = np.linspace(self.surf_to_pump_depth_md[-1],value,self.n)
                except:
                    value = np.linspace(self.surf_to_pump_depth_tvd[-1],value,self.n)
            elif isinstance(value,(list,np.ndarray)):
                value = np.atleast_1d(value)
                assert value.ndim == 1 
                assert np.all(np.diff(value) > 0)
            else:
                raise ValueError('Type not allowed')
        self._pump_to_perf_depth_md = value

    @property 
    def surf_to_pump_depth_tvd(self):
        return self._surf_to_pump_depth_tvd

    @surf_to_pump_depth_tvd.setter 
    def surf_to_pump_depth_tvd(self,value):
        if value is not None:
            if isinstance(value,(int,float)):
                value = np.linspace(0,value,self.n)
            elif isinstance(value,(list,np.ndarray)):
                value = np.atleast_1d(value)
                assert value.ndim == 1 
                assert np.all(np.diff(value) > 0)
            else:
                raise ValueError('Type not allowed')
        else:
            assert self.surf_to_pump_depth_md is not None
        self._surf_to_pump_depth_tvd = value

    @property 
    def pump_to_perf_depth_tvd(self):
        return self._pump_to_perf_depth_tvd

    @pump_to_perf_depth_tvd.setter 
    def pump_to_perf_depth_tvd(self,value):
        if value is not None:
            if isinstance(value,(int,float)):
                try:
                    value = np.linspace(self.surf_to_pump_depth_md[-1],value,self.n)
                except:
                    value = np.linspace(self.surf_to_pump_depth_tvd[-1],value,self.n)
            elif isinstance(value,(list,np.ndarray)):
                value = np.atleast_1d(value)
                assert value.ndim == 1 
                assert np.all(np.diff(value) > 0)
            else:
                raise ValueError('Type not allowed')
        else:
            assert self.pump_to_perf_depth_md is not None
        self._pump_to_perf_depth_tvd = value

    @property
    def brand(self):
        return self._brand 

    @brand.setter 
    def brand(self, value):
        """brand [Ubh brand name]

        :param value: [Name of the UBH brand]
        :type value: [str]
        """
        if value is not None:
            assert isinstance(value,str)
        self._brand = value 

    @property
    def nozzle(self):
        return self._nozzle 

    @nozzle.setter 
    def nozzle(self,value):
        """nozzle [Nozzle Size mm]

        :param value: [nozzle size mm]
        :type value: [float]
        """

        assert isinstance(value,(int,float))
        assert value > 0
        self._nozzle = value

    @property
    def throat(self):
        return self._throat 

    @throat.setter 
    def throat(self,value):
        """throat [Throat size mm]

        :param value: [Throat size mm]
        :type value: [float]
        """
        assert isinstance(value,(int,float))
        assert value > 0
        self._throat = value

    @property
    def power_fluid_ge(self):
        return self._power_fluid_ge 

    @power_fluid_ge.setter 
    def power_fluid_ge(self,value):
        """power_fluid_ge [power_fluid_ge]

        :param value: [power_fluid_ge ]
        :type value: [float]
        """
        assert isinstance(value,(int,float))
        assert value > 0
        self._power_fluid_ge = value

    @property
    def injection_di(self):
        return self._injection_di 

    @injection_di.setter 
    def injection_di(self,value):
        """injection_di [injection_di]

        :param value: [injection_di ]
        :type value: [float]
        """
        if isinstance(value,(int,float)):
            try:
                value = np.full(self.surf_to_pump_depth_md.shape,value)
            except:
                value = np.full(self.surf_to_pump_depth_tvd.shape,value)
        elif isinstance(value,(list,np.ndarray)):
            value = np.atleast_1d(value)
            try:
                assert value.shape == self.surf_to_pump_depth_md.shape
            except:
                assert value.shape == self.surf_to_pump_depth_tvd.shape
        self._injection_di = value

    @property
    def return_di(self):
        return self._return_di 

    @return_di.setter 
    def return_di(self,value):
        """return_di [return_di]

        :param value: [return_di ]
        :type value: [float]
        """
        if isinstance(value,(int,float)):
            try:
                value = np.full(self.surf_to_pump_depth_md.shape,value)
            except:
                value = np.full(self.surf_to_pump_depth_tvd.shape,value)
        elif isinstance(value,(list,np.ndarray)):
            value = np.atleast_1d(value)
            try:
                assert value.shape == self.surf_to_pump_depth_md.shape
            except:
                assert value.shape == self.surf_to_pump_depth_tvd.shape
        self._return_di = value

    @property
    def prod_di(self):
        return self._prod_di 

    @prod_di.setter 
    def prod_di(self,value):
        """prod_di [prod_di]

        :param value: [prod_di ]
        :type value: [float]
        """
        if isinstance(value,(int,float)):
            try:
                value = np.full(self.pump_to_perf_depth_md.shape,value)
            except:
                value = np.full(self.pump_to_perf_depth_tvd.shape,value)
        elif isinstance(value,(list,np.ndarray)):
            value = np.atleast_1d(value)
            try:
                assert value.shape == self.pump_to_perf_depth_md.shape
            except:
                assert value.shape == self.pump_to_perf_depth_tvd.shape
        self._prod_di = value

    @property
    def kn(self):
        return self._kn 

    @kn.setter 
    def kn(self,value):
        """kn [kn Size mm]

        :param value: [kn size mm]
        :type value: [float]
        """

        assert isinstance(value,(int,float))
        assert value > 0
        self._kn = value

    @property
    def ktd(self):
        return self._ktd 

    @ktd.setter 
    def ktd(self,value):
        """ktd [ktd ]

        :param value: [ktd]
        :type value: [float]
        """

        assert isinstance(value,(int,float))
        assert value > 0
        self._ktd = value

    # Methods
    def get_area(self,value):
        assert isinstance(value,str) and value in ['nozzle', 'throat']

        size = self.nozzle if value == 'nozzle' else self.throat

        size_in = size / 25.4 
        area_in_sq = np.pi * np.power(size_in/2,2)

        return area_in_sq

    def fad(self):
        nozzle_area = self.get_area('nozzle')
        throat_area = self.get_area('throat')

        fad = nozzle_area / throat_area 

        return fad
    
    def annulus_area(self):
        nozzle_area = self.get_area('nozzle')
        throat_area = self.get_area('throat')

        annulus_area = throat_area - nozzle_area 

        return annulus_area

    def flow_match(
        self,
        injection_pressure=None,
        injection_rate = 0,
        mu_inj = 1,
        return_pressure = None,
        liquid_rate_guess = None,
        bsw = None,
        gas_rate = None,
        gor = None,
        glr = None,
        inflow = None,
        oil_obj=None,
        gas_obj=None,
        water_obj=None, 
        epsilon = 0.0006,
        surface_temperature=80, 
        temperature_gradient=1, 
        max_iter = 20,
        max_iter_profile = 20,
        max_iter_qn = 20,
        tol = 0.05,
        tol_profile = 0.05,
        tol_qn = 0.05,
        method_profile = 'hagedorn_brown'

    ):
        """flow_match [
            Estimate the production rate in a Jet pump Configuracion and 
            surface conditions.
            
            Calculation sequence taken from
            Petroleum Engineering Handbook., Bradley HB Chapter 6 page 6-44 

            ]

        :param injection_pressure: [description], defaults to None
        :type injection_pressure: [type], optional
        :param return_pressure: [description], defaults to None
        :type return_pressure: [type], optional
        :param flow_guess: [description], defaults to None
        :type flow_guess: [type], optional
        :param inflow: [description], defaults to None
        :type inflow: [type], optional
        :param oil_obj: [description], defaults to None
        :type oil_obj: [type], optional
        :param gas_obj: [description], defaults to None
        :type gas_obj: [type], optional
        :param water_obj: [description], defaults to None
        :type water_obj: [type], optional
        """
        #Assert Thp value
        assert isinstance(injection_pressure,(int,float,np.int64,np.float64))
        assert isinstance(return_pressure,(int,float,np.int64,np.float64))

        #Assert Inflow Curve is of type inflow
        assert isinstance(inflow,oil_inflow)

        #Assert Oil, water, Gas are pvtpy.black_oil type and have pvt attribute
        assert isinstance(oil_obj,oil) and oil_obj.pvt is not None
        assert isinstance(gas_obj,gas) and gas_obj.pvt is not None
        assert isinstance(water_obj,water) and water_obj.pvt is not None

        #Assert initial flow guess
        assert isinstance(liquid_rate_guess,(int,float,np.int64,np.float64))

        #assert max inter int
        assert isinstance(max_iter,int) and max_iter > 0

        #assert max inter int
        assert isinstance(bsw,(int,float)) and bsw >= 0 and bsw <= 1

        #Assert tvd depth
        assert self.surf_to_pump_depth_tvd is not None
        assert self.pump_to_perf_depth_tvd is not None
        ##### Create Arrays

        #Well production flow bbl/d
        qs = np.zeros(max_iter)
        qo = np.zeros(max_iter)
        qg = np.zeros(max_iter)
        _gor = np.zeros(max_iter)
        _glr = np.zeros(max_iter)
        qs[0] = liquid_rate_guess

        #Nozzle Flow and pressure
        qn = np.zeros(max_iter)
        qn[0] = injection_rate
        pn = np.zeros(max_iter)

        #Pwf and Pump intake pressure
        pwf = np.zeros(max_iter)
        pps = np.zeros(max_iter)

        # Return Flow
        qd = np.zeros(max_iter)

        #return gradient
        gd = np.zeros(max_iter)

        #Return Water Cut
        wcd = np.zeros(max_iter)

        #Liquid Gas Ratio

        fgl = np.zeros(max_iter)

        #Return viscosity
        mur = np.zeros(max_iter)

        #Discharge Pressure
        ppd = np.zeros(max_iter)

        #Pressure Ratio
        fpd = np.zeros(max_iter)

        #Mass Ratio
        fmfd1 = np.zeros(max_iter)
        fmfd2 = np.zeros(max_iter)

        #Minimum Suction Area
        acm = np.zeros(max_iter)
        cav = np.zeros(max_iter)

        #Suction gradient
        gs = np.zeros(max_iter)

        #Hydraulic Horse Power
        hp = np.zeros(max_iter)

        #Iterations
        it_qn = np.zeros(max_iter)
        er_it = np.zeros(max_iter)

        ##### Part A: Nozzle Pressure, Nozzle Flow

        err = tol + 0.01 
        i = 0

        if gas_rate is None:
            if gor is None:
                qg[0] = glr * qs[0] * 1e-3
            else:
                qg[0] = gor * qs[0] * (1 - bsw) * 1e-3
        else:
            qg[0] = gas_rate

        qo[0] = qs[0]*(1-bsw)

        _gor[0] = qg[0]*1e3 / qo[0]
        _glr[0] = qg[0]*1e3 / qs[0] 

        while err > tol and i < max_iter-1:
          
            #Estimate the pwf from flow rate
            pwf[i] = inflow.flow_to_pwf(qs[i])

            #Estimate pps - Pump intake pressure
            pps[i] = two_phase_upward_pressure(
                depth = self.pump_to_perf_depth_tvd,
                pwf = pwf[i],
                liquid_rate = qs[i],
                oil_rate = None,
                gas_rate = gas_rate,
                glr = glr,
                gor = gor,
                bsw = bsw,
                oil_obj = oil_obj,
                gas_obj = gas_obj,
                water_obj = water_obj, 
                epsilon=epsilon, 
                surface_temperature=surface_temperature, 
                temperature_gradient=temperature_gradient,  
                di=self.prod_di, 
                tol=tol_profile,
                max_iter = max_iter_profile,
                method = method_profile,
                guess=[pwf[i], pwf[i]*0.9]
            )
            # Suction Gradient
            gs[i] = (pwf[i] - pps[i]) / np.abs(self.pump_to_perf_depth_tvd[0] - self.pump_to_perf_depth_tvd[-1])
            #gor


            #Minimum Suction Area
            acm[i] = minimum_suction_area(
                qs[i],
                gs[i],
                pps[i],
                bsw,
                _gor[i]
            ) 

            #Evaluate if cavitate
            cav[i] = acm[i] > self.annulus_area()

            err_qn = tol_qn + 0.1
            qn_it = 0

            while err_qn > tol_qn and qn_it < max_iter_qn:
                #Nozzle pressure
                _,_pn = one_phase_pressure_profile(
                    p1=injection_pressure,
                    ge=self.power_fluid_ge,
                    epsilon=epsilon,
                    md=self.surf_to_pump_depth_tvd *-1,
                    tvd=self.surf_to_pump_depth_tvd *-1,
                    d = self.injection_di,
                    rate = qn[i],
                    mu = mu_inj
                    )

                #Nozzle flow
                _qn = nozzle_flow(
                    self.get_area('nozzle'),
                    _pn,
                    pps[i],
                    self.power_fluid_ge * 0.433
                )

                err_qn = np.abs(_qn - qn[i])/qn[i]

                qn_it += 1
                qn[i] = _qn
                pn[i] = _pn

            #Update Nozzle pressure
            pn[i] = _pn
            it_qn[i] = qn_it

            ##### Part B Production rate

            #Return Flow
            qd[i] = qs[i] + qn[i]

            #return gradiend
            gd[i] = (qn[i]*self.power_fluid_ge*0.433 + qs[i]*gs[i]) / qd[i]

            #Return water cut
            if self.power_fluid_ge ==1:
                wcd[i] = (qn[i] + bsw*qs[i]) / qd[i]
            else:
                wcd[i] = bsw*qs[i]/qd[i]

            #return gas/liquid ratio
            fgl[i] = qs[i] *(1 - bsw)*_gor[i] / qd[i]

            #return_viscosity
            muo = oil_obj.pvt.interpolate(return_pressure,property = 'muo').iloc[0,0]
            muw = water_obj.pvt.interpolate(return_pressure,property = 'muw').iloc[0,0]
            mur[i] = (1 - wcd[i]) * muo + wcd[i] * muw

            if fgl[i] > 10:
                _,ppd[i] = two_phase_pressure_profile(
                    depth = self.surf_to_pump_depth_tvd,
                    thp = return_pressure,
                    liquid_rate = qd[i],
                    oil_rate = None,
                    gas_rate = qg[i],
                    glr = fgl[i],
                    gor = None,
                    bsw = wcd[i],
                    oil_obj = oil_obj,
                    gas_obj = gas_obj,
                    water_obj = water_obj, 
                    epsilon=epsilon, 
                    surface_temperature=surface_temperature, 
                    temperature_gradient=temperature_gradient,  
                    di=self.return_di, 
                    tol=tol_profile,
                    max_iter = max_iter_profile,
                    method = method_profile,
                )

            else:
                _,ppd[i] = one_phase_pressure_profile(
                    p1=return_pressure,
                    ge=gd[i],
                    epsilon=epsilon,
                    md=self.surf_to_pump_depth_tvd *-1,
                    tvd=self.surf_to_pump_depth_tvd *-1,
                    d = self.injection_di,
                    rate = qn[i],
                    mu = mur,
                    backwards=-1
                    )

            #Pressure Ratio
            fpd[i] = (ppd[i] - pps[i])/(pn[i] - ppd[i])

            #Flow ratio
            #fmfd2_num = (qs[i] * gs[i] *((1 + 2.8 * np.power(gor/pps[i],1.2)) * (1-bsw) + bsw))
            #fmfd2_den = (qn[i] * self.power_fluid_ge*0.433)
            #fmfd2[i] = fmfd2_num / fmfd2_den

            rs_pps = oil_obj.pvt.interpolate(pps[i],property='rs').iloc[0,0]
            bg_pps = gas_obj.pvt.interpolate(pps[i],property='bg').iloc[0,0]
            free_gas_sc = qg[i] - (rs_pps*qo[i]*1e-3)

            free_gas_pps = free_gas_sc*1e3*bg_pps

            fmfd2[i] = ((qs[i] + free_gas_pps)/qn[i])

            #flow ratio from fig
            fad = self.fad()
            A2 = 2*fad 
            B2 = (1 - 2*fad)*(np.power(fad,2)/np.power(1 - fad,2))
            C2 = (1 + self.ktd)* np.power(fad,2)
            D2 = (1 + self.kn)

            fmfd1[i] = (2*C2 - np.sqrt(np.power(-2*C2,2) - 4*(B2-C2)*((A2-C2)-((fpd[i]*D2)/(fpd[i] + 1))))) / (2*(B2-C2))
            #Calculate new Qs
            qs[i+1] = qs[i] * fmfd1[i]/fmfd2[i]

            #Horse Power 
            hp[i] = 0.000017 * qn[i] * injection_pressure

            #Error
            err = np.abs(qs[i+1]-qs[i])/qs[i]
            er_it[i] = err

            #Calculate rates next iteration
            if gas_rate is None:
                if gor is None:
                    qg[i+1] = glr * qs[i+1] * 1e-3
                else:
                    qg[i+1] = gor * qs[i+1] * (1 - bsw) * 1e-3
            else:
                qg[i+1] = gas_rate

            qo[i+1] = qs[i+1]*(1-bsw)

            _gor[i+1] = qg[i+1]*1e3 / qo[i+1]
            _glr[i+1] = qg[i+1]*1e3 / qs[i+1] 

            print(f'\r Iteration {i}: -> Liquid Rate: {qs[i]:.0f} bbl -> pip: {pps[i]:.0f} psi -> error {er_it[i]*100:.0f}%', sep='',end='', flush=True)
            i += 1

        df_dict = {
        'qs':qs[:i+1],
        'qo':qo[:i+1],
        'qg':qg[:i+1],
        'gor':_gor[:i+1],
        'glr':_glr[:i+1],
        'qn':qn[:i+1],
        'pwf':pwf[:i+1],
        'pn':pn[:i+1],
        'pps':pps[:i+1],
        'qd':qd[:i+1],
        'gd':gd[:i+1],
        'wcd':wcd[:i+1],
        'fgl':fgl[:i+1],
        'mur':mur[:i+1],
        'ppd':ppd[:i+1],
        'fmfd1':fmfd1[:i+1],
        'fmfd2':fmfd2[:i+1],
        'fpd':fpd[:i+1], 
        'acm':acm[:i+1],
        'cav':cav[:i+1],
        'gs':gs[:i+1],
        'it_qn':it_qn[:i+1], 
        'error':er_it[:i+1],
        'hp':hp[:i+1]
        }

        df = pd.DataFrame(df_dict)

        qs_final = qs[i]

        return df, qs_final

