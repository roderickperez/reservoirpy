import pandas as pd 
import numpy as np
import geopandas as gpd
from shapely.geometry import Point
from .mincurve import min_curve_method
from .mincurve import survey
from .interpolate import interpolate_deviation, interpolate_position
from .projection import unit_vector, projection_1d
from scipy.interpolate import interp1d
from scipy.spatial import distance_matrix
from pyproj import Proj, transform
import folium
from folium.plugins import MarkerCluster, MeasureControl,MousePosition#,LocateControl
import matplotlib.pyplot as plt
import seaborn as sns
import pyvista as pv 
from ...welllogspy.log import log
from ...wellproductivitypy import pi
from ...wellproductivitypy.decline import declination, wor_declination, bsw_to_wor
from ...volumetricspy import surface_group
from ...cashflows.timeseries import cash
from ...cashflows.taxing import after_tax_cashflow
from ...cashflows.analysis import timevalue
from ...cashflows.rate import perrate
from sqlalchemy import create_engine
from ...wellschematicspy import well_schema
import pickle
from datetime import date, timedelta
import pyDOE2 as ed
from lasio import LASFile
import time

def input_to_list(input):
    assert isinstance(input,(str,list)), f'input must be either string or list'
    
    input_list = []
    if isinstance(input,str):
        input_list.append(input)
    else:
        input_list.extend(input)
    return input_list


class perforations(gpd.GeoDataFrame):

    def __init__(self, *args, **kwargs):
        kh = kwargs.pop("kh", None)
        productivity_index = kwargs.pop("productivity_index", None)
        is_open = kwargs.pop('is_open',None)  
        fluid = kwargs.pop('fluid',None)                                                                                                                               
        super(perforations, self).__init__(*args, **kwargs)

        if kh is not None:
            assert isinstance(kh,list) 
            assert all(isinstance(i,(int,float)) for i in kh)
            self['kh'] = kh
        elif 'kh' in self.columns:
            assert all(isinstance(i,(int,float)) for i in self['kh'].tolist())

        if productivity_index is not None:
            assert isinstance(productivity_index,list) 
            assert all(isinstance(i,(int,float)) for i in productivity_index)
            self['productivity_index'] = productivity_index
        elif 'productivity_index' in self.columns:
            assert all(isinstance(i,(int,float)) for i in self['productivity_index'].tolist())

        if is_open is not None:
            assert isinstance(is_open,list)
            assert all(isinstance(i,bool) for i in is_open)
            self['is_open'] = is_open
        elif 'is_open' in self.columns:
            assert all(isinstance(i,bool) for i in self['is_open'].tolist())

        if fluid is not None:
            assert isinstance(fluid,list)
            assert all(i in ['oil','gas','water'] for i in fluid)
            self['fluid'] = fluid
        elif 'fluid' in self.columns:
            assert all(isinstance(i,bool) for i in self['is_open'].tolist())
            assert all(i in ['oil','gas','water'] for i in self['fluid'].tolist())


    def open_perf(self):
        return self[self['is_open']==True]

    def get_tick(self):
        try:
            self['md_tick'] = self['md_bottom'] - self['md_top']
        except:
            pass

        try:
            self['tvd_tick'] = self['tvd_bottom'] - self['tvd_top']
        except:
            pass
        
        return self
    
    def get_mid_point(self):
        try:
            self['md_mid_point'] = (self['md_bottom'] + self['md_top'])*0.5
        except:
            pass

        try:
            self['tvd_mid_point'] = (self['tvd_bottom'] + self['tvd_top'])*0.5
        except:
            pass
    
        try:
            self['tvdss_mid_point'] = (self['tvdss_bottom'] + self['tvdss_top'])*0.5
        except:
            pass
        return self
        
    
    @property
    def _constructor(self):
        return perforations
    
class tops(gpd.GeoDataFrame):

    def __init__(self, *args, **kwargs):    
        formation = kwargs.pop("formation", None)            
        unit = kwargs.pop("unit", None)                                                                                                                     
        super(tops, self).__init__(*args, **kwargs)  

        if formation is not None:
            formation = np.atleast_1d(formation)
            self['formation'] = formation
            self.set_index('formation',inplace=True)
        elif 'formation' in self.columns:
            self.set_index('formation',inplace=True)

        if unit is not None:
            unit = np.atleast_1d(unit)
            self['unit'] = unit
            self.set_index('unit',inplace=True)
        elif 'unit' in self.columns:
            self.set_index('unit',inplace=True)

    def get_tick(self):
        try:
            self['md_tick'] = self['md_bottom'] - self['md_top']
        except:
            pass

        try:
            self['tvd_tick'] = self['tvd_bottom'] - self['tvd_top']
        except:
            pass
        
        return self
    
    def get_mid_point(self):
        try:
            self['md_mid_point'] = (self['md_bottom'] + self['md_top'])*0.5
        except:
            pass

        try:
            self['tvd_mid_point'] = (self['tvd_bottom'] + self['tvd_top'])*0.5
        except:
            pass
    
        try:
            self['tvdss_mid_point'] = (self['tvdss_bottom'] + self['tvdss_top'])*0.5
        except:
            pass
        return self 
    
    @property
    def _constructor(self):
        return tops

def vtk_survey(points):
    """Given an array of points, make a line set"""
    poly = pv.PolyData()
    poly.points = points
    cells = np.full((len(points)-1, 3), 2, dtype=np.int)
    cells[:, 1] = np.arange(0, len(points)-1, dtype=np.int)
    cells[:, 2] = np.arange(1, len(points), dtype=np.int)
    poly.lines = cells
    return poly
   
freq_format={
    'M':'%Y-%m',
    'D':'%Y-%m-%d',
    'A':'%Y'
}

class well:
    def __init__(self, **kwargs):

        self.name = kwargs.pop('name', None)
        self.rte = kwargs.pop('rte', 0)
        self.surf_coord = kwargs.pop('surf_coord', None)
        self.crs = kwargs.pop('crs', None)
        self.perforations = kwargs.pop('perforations', None)
        self.tops = kwargs.pop('tops', None)
        self.units = kwargs.pop('units',None)
        self.openlog = kwargs.pop('openlog', None)
        self.masterlog = kwargs.pop('masterlog', None) 
        self.caselog = kwargs.pop('caselog', None)
        self.td = kwargs.pop('td',None)  # First set td before survey
        self.survey = kwargs.pop('survey', None)
        self.declination = kwargs.pop('declination',None)
        self.kh = kwargs.pop('kh',None)
        self.productivity_index = kwargs.pop('productivity_index',None)
        self.constrains = kwargs.pop('constrains',None)
        self.als = kwargs.pop('als',None)
        self.schema = kwargs.pop('schema',None)
        self.schedule = kwargs.pop('schedule',None)
        self.fq  = kwargs.pop('fq','M')
        self.cashflow = kwargs.pop('cashflow',None)


#####################################################
############## Properties ###########################

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self,value):
        assert isinstance(value,(str,type(None))), f'{type(value)} not accepted. Name must be str'
        self._name = value

    @property
    def rte(self):
        return self._rte

    @rte.setter
    def rte(self,value):
        if value is not None:
            assert isinstance(value,(int,float)), f'{type(value)} not accepted. Name must be number'
        self._rte = value

    @property
    def surf_coord(self):
        return self._surf_coord

    @surf_coord.setter
    def surf_coord(self,value):
        if value is not None:
            assert isinstance(value,(list,Point)), f'{type(value)} not accepted. Name must be shapely.geometry.Point or list [x,y,z]'
            if isinstance(value,Point):
                self._surf_coord = value
            elif isinstance(value,list):
                assert len(value) <= 3 and len(value) >= 2
                if len(value)==3:
                    self._surf_coord = Point(value[0],value[1],value[2])
                elif len(value)==2:
                    self._surf_coord = Point(value[0],value[1])
        else:
            self._surf_coord = value


    @property
    def crs(self):
        return self._crs

    @crs.setter
    def crs(self,value):
        if value is not None:
            if isinstance(value,str):
                assert value.startswith('EPSG:'), 'if crs is string must starts with EPSG:. If integer must be the Coordinate system reference number EPSG http://epsg.io/'
            else:
                try:
                    value = f'EPSG:{int(value)}'
                except:
                    value = None
        self._crs = value

    @property
    def fq(self):
        return self._fq

    @fq.setter
    def fq(self,value):
        assert isinstance(value,str), f"{type(value)} not accepted. Name must be str"
        assert value in ['A', 'BA', 'Q', 'BQ', 'M', 'BM', 'CBM', 'SM', '6M', '6BM', '6CMB']      
        self._fq = value

    @property
    def perforations(self):
        return self._perforations

    @perforations.setter
    def perforations(self,value):
        if value is not None:
            assert isinstance(value,perforations), f'{type(value)} not accepted. Name must be reservoirpy.wellpy.path.perforations'
            if self.crs is not None and value is not None:
                value.crs = self.crs
        self._perforations = value

    @property
    def tops(self):
        return self._tops

    @tops.setter
    def tops(self,value):
        if value is not None:
            assert isinstance(value,tops), f'{type(value)} not accepted. Name must be reservoirpy.wellpy.path.tops'
            if self.crs is not None and value is not None:
                value.crs = self.crs
        self._tops = value    

    @property
    def units(self):
        return self._units

    @units.setter
    def units(self,value):
        if value is not None:
            assert isinstance(value,tops), f'{type(value)} not accepted. Name must be reservoirpy.wellpy.path.tops'
            if self.crs is not None and value is not None:
                value.crs = self.crs
        self._units = value    

    @property
    def openlog(self):
        return self._openlog

    @openlog.setter
    def openlog(self,value):
        if value is not None:
            assert isinstance(value,dict)
            for i in value:
                assert isinstance(value[i],(log,LASFile))         
        self._openlog = value

    @property
    def masterlog(self):
        return self._masterlog

    @masterlog.setter
    def masterlog(self,value):
        if value is not None:
            assert isinstance(value,dict)
            for i in value:
                assert isinstance(value[i],(log,LASFile))         
        self._masterlog = value

    @property
    def caselog(self):
        return self._caselog

    @caselog.setter
    def caselog(self,value):
        if value is not None:
            assert isinstance(value,dict)
            for i in value:
                assert isinstance(value[i],(log,LASFile))       
        self._caselog = value

    @property
    def survey(self):
        return self._survey

    @survey.setter
    def survey(self,value):
        if value is not None:
            if isinstance(value,survey):
                self._survey = value
            elif isinstance(value,pd.DataFrame):
                assert all(i in value.columns for i in ['md','inc','azi'])
                _survey = min_curve_method(
                    value['md'],
                    value['inc'],
                    value['azi'],
                    surface_easting=self._surf_coord.x, 
                    surface_northing=self._surf_coord.y, 
                    kbe=self._rte,
                    crs=self._crs)
                self._survey = _survey
        elif self.td is not None:
            _survey = min_curve_method(
                np.array([0,self.td]),
                np.zeros(2),
                np.zeros(2),
                surface_easting=self._surf_coord.x, 
                surface_northing=self._surf_coord.y, 
                kbe=self._rte,
                crs=self._crs)
            self._survey = _survey
        else:
            self._survey = value

    @property
    def td(self):
        return self._td

    @td.setter
    def td(self,value):
        if value is None:
            self._td = value
        else:
            assert isinstance(value,(int,float))
            self._td = value

    @property
    def declination(self):
        return self._declination
    
    @declination.setter
    def declination(self,value):
        assert isinstance(value, (declination,type(None))), "must be declination type"
        self._declination = value

    @property
    def kh(self):
        return self._kh 

    @kh.setter 
    def kh(self,value):
        assert isinstance(value,(type(None),dict)), "kh must be a dictionary indexed by formation (Key)"
        if isinstance(value,dict):
            assert all(isinstance(value[i],(int,float)) for i in value)
        self._kh = value    

    @property
    def constrains(self):
        return self._constrains

    @constrains.setter
    def constrains(self,value):
        if value is not None:
            #Assert is a dictionary
            assert isinstance(value,dict)
            keys = list(value.keys())
            
            #assert 'date','constrain','value' are in the dict
            assert all(i in keys for i in ['date','constrain','value'])

            #assert items are list or numpy ndarray
            for i in value:
                assert isinstance(value[i],(list,np.ndarray))

        self._constrains = value

    @property
    def als(self):
        return self._als

    @als.setter 
    def als(self, value):
        if value is not None:
            assert issubclass(type(value),pi.als)
            if value.surf_to_pump_depth_tvd is None:
                value.surf_to_pump_depth_tvd = self.to_tvd(value.surf_to_pump_depth_md)
            if value.pump_to_perf_depth_tvd is None:
                value.pump_to_perf_depth_tvd = self.to_tvd(value.pump_to_perf_depth_md)
        self._als = value

    @property
    def schema(self):
        return self._schema

    @schema.setter 
    def schema(self, value):
        if value is not None:
            assert isinstance(value,dict)
            for i in value:
                assert isinstance(value[i],well_schema)       
        self._schema = value

    @property
    def cashflow(self):
        return self._cashflow

    @cashflow.setter 
    def cashflow(self, value):
        if value is not None:
            assert isinstance(value,dict)
            for i in value:
                assert isinstance(value[i],dict)   
                for j in value[i]:
                    assert isinstance(value[i][j],cash)       
        self._cashflow = value

    @property
    def schedule(self):
        return self._schedule

    @schedule.setter 
    def schedule(self, value):
        if value is not None:
            assert isinstance(value,dict)
            for i in value:
                assert isinstance(value[i],dict)
                for j in value[i]:
                    assert isinstance(value[i][j]['declination'],(declination,wor_declination))     
        self._schedule = value


#####################################################
############## methods ###########################

    def add_schema(self,schema):
        assert isinstance(schema,dict)
        for i in schema:
            assert isinstance(schema[i],well_schema) 

        if self.schema is None:
            self.schema = schema
        else:
            self._schema.update(schema)

    def add_schedule(self,schedule):
        assert isinstance(schedule,dict)
        for i in schedule:
            assert isinstance(schedule[i],dict) 

        if self.schedule is None:
            self.schedule = schedule
        else:
            self._schedule.update(schedule)

    def add_cashflow(self,cashflows,case=None):
        assert isinstance(cashflows,dict)
        assert case is not None
        for cashflow in cashflows:
            assert isinstance(cashflows[cashflow],cash) 

        if self.cashflow is None:
            self.cashflow = {case:cashflows}
        elif case not in self.cashflow.keys():
            self._cashflow[case] = cashflows
        else:
            self._cashflow[case].update(cashflows)

    def add_logs(self,logs_dict, which='openlog'):

        assert isinstance(logs_dict,dict)
        for i in logs_dict:
            assert isinstance(logs_dict[i],log)     
        
        if which=='openlog':
            if self.openlog is None:
                self.openlog = logs_dict
            else:
                self._openlog.update(logs_dict)
        elif which == 'masterlog':
            if self.masterlog is None:
                self.masterlog = logs_dict
            else:
                self._masterlog.update(logs_dict)
        elif which == 'caselog':
            if self.caselog is None:
                self.caselog = logs_dict
            else:
                self._caselog.update(logs_dict)
        else:
            raise ValueError('No attribute target defined')

    def sample_deviation(self,step=100):
        if self._survey is not None:
            _survey = self.survey
            new_dev = interpolate_deviation(_survey.index, 
                                            _survey['inc'], 
                                            _survey['azi'], md_step=step)
        else:
            raise ValueError("No survey has been set")
        return new_dev

    def sample_position(self,step=100):
        if self._survey is not None:
            _survey = self.survey
            new_pos = interpolate_position(_survey['tvd'], 
                                            _survey['easting'], 
                                            _survey['northing'], 
                                            tvd_step=step)
            new_pos_gpd = gpd.GeoDataFrame(new_pos,geometry=gpd.points_from_xy(new_pos.new_easting,new_pos.new_northing),crs=self._crs)
        else:
            raise ValueError("No survey has been set")
        return new_pos_gpd

    """
            #Set the depth interpolators
            self._tvd_int = interp1d(self.survey.index,self.survey['tvd'])
            self._tvdss_int = interp1d(self.survey.index,self.survey['tvdss'])
            self._northing_int = interp1d(self.survey['tvd'],self.survey.geometry.y)
            self._easting_int = interp1d(self.survey['tvd'],self.survey.geometry.x)
        else:
            self.survey=None
"""

    def to_tvd(self,md:(int,float)=None,which:list=None, ss:bool=False,tick=True):
        if self._survey is not None:
            r = None
            _survey=self.survey
            _tvd_int = interp1d(_survey.index,_survey['tvd'],fill_value='extrapolate')
            _tvdss_int = interp1d(_survey.index,_survey['tvdss'],fill_value='extrapolate')

            if md is not None:
                if ss==True:
                    _tvdss = _tvdss_int(md)
                    r = _tvdss
                else:
                    _tvd = _tvd_int(md)
                    r = _tvd
                
            if which is not None:
                if 'perforations' in which:
                    if self._perforations is not None:
                        if ss==True:
                            if 'md_top' in self._perforations.columns:
                                self._perforations['tvdss_top']=self._perforations['md_top'].apply(_tvdss_int)
                            if 'md_bottom' in self._perforations.columns:
                                self._perforations['tvdss_bottom']=self._perforations['md_bottom'].apply(_tvdss_int)
                        else:
                            if 'md_top' in self._perforations.columns:
                                self._perforations['tvd_top']=self._perforations['md_top'].apply(_tvd_int)
                            if 'md_bottom' in self._perforations.columns:
                                self._perforations['tvd_bottom']=self._perforations['md_bottom'].apply(_tvd_int)
                            if 'tvd_bottom' in self._perforations.columns and 'tvd_bottom' in self._perforations.columns and tick==True:
                                self._perforations['tvd_tick'] = self._perforations['tvd_bottom'] - self._perforations['tvd_top']
                    else:
                        print(f" {self.name} No perforations have been set")


                if 'tops' in which:
                    if self._tops is not None:
                        if ss==True:
                            if 'md_top' in self._tops.columns:
                                self._tops['tvdss_top']=self._tops['md_top'].apply(_tvdss_int)
                            if 'md_bottom' in self._tops.columns:
                                self._tops['tvdss_bottom']=self._tops['md_bottom'].apply(_tvdss_int)
                        else:
                            if 'md_top' in self._tops.columns:
                                self._tops['tvd_top']=self._tops['md_top'].apply(_tvd_int)
                            if 'md_bottom' in self._tops.columns:
                                self._tops['tvd_bottom']=self._tops['md_bottom'].apply(_tvd_int)
                            if 'tvd_bottom' in self._tops.columns and 'tvd_bottom' in self._tops.columns and tick==True:
                                self._tops['tvd_tick'] = self._tops['tvd_bottom'] - self._tops['tvd_top']
                    else:
                        print(f" {self.name} No tops have been set")

                if 'units' in which:
                    if self._units is not None:
                        if ss==True:
                            if 'md_top' in self._units.columns:
                                self._units['tvdss_top']=self._units['md_top'].apply(_tvdss_int)
                            if 'md_bottom' in self._units.columns:
                                self._units['tvdss_bottom']=self._units['md_bottom'].apply(_tvdss_int)
                        else:
                            if 'md_top' in self._units.columns:
                                self._units['tvd_top']=self._units['md_top'].apply(_tvd_int)
                            if 'md_bottom' in self._units.columns:
                                self._units['tvd_bottom']=self._units['md_bottom'].apply(_tvd_int)
                            if 'tvd_bottom' in self._units.columns and 'tvd_bottom' in self._units.columns and tick==True:
                                self._units['tvd_tick'] = self._units['tvd_bottom'] - self._units['tvd_top']
                    else:
                        print(f" {self.name} No units have been set")
                
                if 'openlog' in which:
                    if self._openlog is not None:
                        for i in self._openlog:
                            try:
                                _d = self._openlog[i].df().index.values
                                _tvd = _tvd_int(_d)
                                _tvdss = _tvdss_int(_d)
                                self._openlog[i].add_curve('tvd',_tvd,descr='tvd')
                                self._openlog[i].add_curve('tvdss',_tvdss,descr='tvdss')
                            except:
                                print(f"{i} not calculated")
                                pass
                    else:
                        print(f" {self.name} No openlog have been set")

                if 'masterlog' in which:
                    if self._masterlog is not None:
                       for i in self._masterlog:
                            try:
                                _d = self._masterlog[i].df().index.values
                                _tvd = _tvd_int(_d)
                                _tvdss = _tvdss_int(_d)
                                self._masterlog[i].add_curve('tvd',_tvd,descr='tvd')
                                self._masterlog[i].add_curve('tvdss',_tvdss,descr='tvdss')
                            except:
                                print(f"{i} not calculated")
                                pass
                    else:
                        print(f" {self.name} No masterlog have been set")

                if 'caselog' in which:
                    if self._caselog is not None:
                       for i in self._caselog:
                            try:
                                _d = self._caselog[i].df().index.values
                                _tvd = _tvd_int(_d)
                                _tvdss = _tvdss_int(_d)
                                self._caselog[i].add_curve('tvd',_tvd,descr='tvd')
                                self._caselog[i].add_curve('tvdss',_tvdss,descr='tvdss')
                            except:
                                print(f"{i} not calculated")
                                pass
                    else:
                        print(f" {self.name} No caselog have been set")

        else:
            raise ValueError("No survey has been set")
        return r
  

    
    def to_coord(self,md:(int,float)=None,which:list=None):
        if self._survey is not None:
            r=None
            _survey=self.survey
            _northing_int = interp1d(_survey['tvd'],_survey.geometry.y,fill_value='extrapolate')
            _easting_int = interp1d(_survey['tvd'],_survey.geometry.x,fill_value='extrapolate')
            _tvd_int = interp1d(_survey.index,_survey['tvd'],fill_value='extrapolate')
            if md is not None:
                _tvd = _tvd_int(md)
                _northing = _northing_int(_tvd)
                _easting = _easting_int(_tvd)
                coord = Point(_easting,_northing)
                r = coord
                
            if which is not None:
                if 'perforations' in which:
                    if self._perforations is not None:
                        try:
                            self._perforations['northing'] = self._perforations['tvd_top'].apply(_northing_int)
                            self._perforations['easting'] = self._perforations['tvd_top'].apply(_easting_int)
                            self._perforations['geometry'] = self._perforations[['northing', 'easting']].apply(lambda x: Point(x['easting'],x['northing']),axis=1)
                        except:
                            ValueError("No tvd has been set")
                    else:
                        print(f" {self.name} No perforations have been set")
                        
                if 'tops' in which:
                    if self._tops is not None:
                        try:
                            self._tops['northing'] = self._tops['tvd_top'].apply(_northing_int)
                            self._tops['easting'] = self._tops['tvd_top'].apply(_easting_int)
                            self._tops['geometry'] = self._tops[['northing', 'easting']].apply(lambda x: Point(x['easting'],x['northing']),axis=1)
                        except:
                            ValueError("No tvd has been set")
                    else:
                        print(f" {self.name} No tops have been set")

                if 'units' in which:
                    if self._units is not None:
                        try:
                            self._units['northing'] = self._units['tvd_top'].apply(_northing_int)
                            self._units['easting'] = self._units['tvd_top'].apply(_easting_int)
                            self._units['geometry'] = self._units[['northing', 'easting']].apply(lambda x: Point(x['easting'],x['northing']),axis=1)
                        except:
                            ValueError("No tvd has been set")
                    else:
                        print(f" {self.name} No units have been set")
        else:
            raise ValueError("No survey has been set")
        return r

    def tops_to_logs(self,which:list=None, units=False):
        df = self._tops if units==False else self._units
        _item = 'formation' if units==False else 'unit'
        if df is None:
            raise ValueError("No tops have been set")
        else:
            if which is None:
                raise ValueError("No log specification")
            else:
                if ('masterlog' in which) & (self._masterlog is not None):
                    for j in self._masterlog:
                        _d = self._masterlog[j].df().index
                        _m = pd.DataFrame(index=_d)
                        for i in df.iterrows():
                            _m.loc[(_m.index>=i[1]['md_top'])&(_m.index<=i[1]['md_bottom']),_item] = i[0]
                        self._masterlog[j].add_curve(_item,_m[_item].values,descr=_item)
                if ('openlog' in which) & (self._openlog is not None):
                    for j in self._openlog:
                        _d = self._openlog[j].df().index
                        _m = pd.DataFrame(index=_d)
                        for i in df.iterrows():
                            _m.loc[(_m.index>=i[1]['md_top'])&(_m.index<=i[1]['md_bottom']),_item] = i[0]
                        self._openlog[j].add_curve(_item,_m[_item].values,descr=_item)
                if ('caselog' in which) & (self._caselog is not None):
                    for j in self._caselog:
                        _d = self._caselog[j].df().index
                        _m = pd.DataFrame(index=_d)
                        for i in df.iterrows():
                            _m.loc[(_m.index>=i[1]['md_top'])&(_m.index<=i[1]['md_bottom']),_item] = i[1][_item]
                        self._caselog[j].add_curve(_item,_m[_item].values,descr=_item)

    def add_to_logs(self,df,key,which='openlog'):

        if which =='openlog':
            col_add = df.columns[~df.columns.isin(np.intersect1d(df.columns, self._openlog[key].df().columns))]
            df_merge = self._openlog[key].df().merge(df[col_add], how='left', left_index=True,right_index=True)
            assert df_merge.shape[0] == self._openlog[key].df().shape[0]
            for i in df_merge[col_add].iteritems():
                self._openlog[key].add_curve(i[0],i[1])         

        if which =='masterlog':
            col_add = df.columns[~df.columns.isin(np.intersect1d(df.columns, self._masterlog[key].df().columns))]
            df_merge = self._masterlog[key].df().merge(df[col_add], how='left', left_index=True,right_index=True)
            assert df_merge.shape[0] == self._masterlog[key].df().shape[0]
            for i in df_merge[col_add].iteritems():
                self._masterlog[key].add_curve(i[0],i[1])   

        if which =='caselog':
            col_add = df.columns[~df.columns.isin(np.intersect1d(df.columns, self._caselog[key].df().columns))]
            df_merge = self._caselog[key].df().merge(df[col_add], how='left', left_index=True,right_index=True)
            assert df_merge.shape[0] == self._caselog[key].df().shape[0]
            for i in df_merge[col_add].iteritems():
                self._caselog[key].add_curve(i[0],i[1])   

    def interval_attributes(self,perforations:bool=False, 
                            intervals:perforations=None, 
                            curves:list = None, which = 'openlog',key=None,
                            aggfunc = ['min','max','mean']):
        if perforations == True :
            p = self._perforations
        else:
            p = intervals 
          
        curves.append('inter')
        log_appended = pd.DataFrame()
        #add column to identify the interval
        for i,c in p.iterrows():
            if which == 'openlog': 
                logdf = self._openlog[key].df().copy()
            elif which == 'masterlog':
                logdf = self._masterlog[key].df().copy()
            elif which == 'caselog':
                logdf = self._caselog[key].df().copy()
            else:
                raise ValueError('No logs selected')

            logdf.loc[(logdf.index >= c['md_top'])&(logdf.index<=c['md_bottom']),'inter']=i
            
            #filter all the intervals
            logdf = logdf[~logdf['inter'].isnull()]

            #Group and aggregate functions
            log_grp = logdf[curves].groupby('inter').agg(aggfunc)
            log_appended = log_appended.append(log_grp)

        p_result = pd.concat([p,log_appended],axis=1)
        if perforations ==True:
            self._perforations = p_result 
            
        return p_result

    def get_vtk(self):
        """
        Get the vtk object in PyVista for the well survey
        """
    
        if self.survey is None:
            raise ValueError('The survey has not been set')
        else:
            _survey = self.survey.reset_index()
            _survey = _survey.loc[:,_survey.columns != 'geometry']
            
            surv_vtk = vtk_survey(_survey[['easting','northing','tvdss']].values)
            
            for col in _survey.iteritems():
                surv_vtk.point_arrays[col[0]] = col[1].values

        return surv_vtk

    def well_map(self,zoom=10, map_style = 'OpenStreetMap',z_unit='ft', to_crs='EPSG:4326', tooltip=False,popup=True, ax=None):
        """
        Make a Foluim map with the selected well

        Input:
            zoom -> (int, float) Initial zoom for folium map
            map_stule -> (str) Type of map folium
        Return:
            w_map -> (folium.Map) Folium map object
        """
        _coord = gpd.GeoDataFrame()

        z_coef = 0.3048 if z_unit=='ft' else 1

        x_coord = self.surf_coord.x
        y_coord = self.surf_coord.y
        z_coord = self.surf_coord.z*z_coef if self.surf_coord.has_z==True else self.rte*z_coef
        shape = self.surf_coord
        crs = self.crs
        _w = gpd.GeoDataFrame({'x':[x_coord],'y':[y_coord],'z':[z_coord],'geometry':[shape]}, index=[self.name])
        _w.crs = crs
        _w = _w.to_crs(to_crs)
        _w['lon'] = _w['geometry'].x
        _w['lat'] = _w['geometry'].y
        _coord = _coord.append(_w)
        center = _coord[['lat','lon']].mean(axis=0)

        #make the map
        if ax is None:
            map_folium = folium.Map(
                location=(center['lat'],center['lon']),
                zoom_start=zoom,
                tiles = map_style)
        else:
            assert isinstance(ax,folium.folium.Map)
            map_folium = ax

        for i, r in _coord.iterrows():
            folium.Marker(
                [r['lat'],r['lon']],
                tooltip=f"{i}" if tooltip else None,
                popup = folium.Popup(html=f"{i}",show=True) if popup else None,
                icon=folium.Icon(icon='tint', color='green')
                ).add_to(map_folium)

        folium.LayerControl().add_to(map_folium)
        #LocateControl().add_to(map_folium)
        MeasureControl().add_to(map_folium)
        MousePosition().add_to(map_folium)

        return map_folium


    def get_kh_from_perforations(self,is_open=False, inplace=True):
    # ! Do not use.. Not fully implemented
        """
        Estimate the Productivity Index by formation with the self.perforations attribute.
        The self.perforations attribute must have a column 'kh' with the Productivity Index for 
        the interval. If the column 'is_open' is present and the keyword 'is_open' is true the 
        productivity Index is calculated for the Open Formations.
        Productivity index is grouped by formation and sum.
        If the column 'formation' is not present a single item dictionary is calculated
        Input:
            is_open -> (bool, False).
        Return:
            kh -> (dict) Dictionary with the productivity index by formation
        """
        assert self.perforations is not None, 'To estimate kh from Perf, perf must be defined'
        _perf = self.perforations
        _keys = ['formation','kh','fluid']
        assert all(i in _perf.columns for i in _keys)

        # If is_open only take the open.reset_index().set_index('fm')d intervals
        if is_open and 'is_open' in _perf.columns:
            _perf = _perf[_perf['is_open']==True]

        #Group by and sum aggregate
        _kh_df_gr = _perf.groupby(['formation','fluid']).agg({'kh':'sum'})
        _kh_dict = _kh_df_gr.groupby(level=0).apply(lambda x: x.reset_index().set_index('fluid')[['kh']].to_dict(orient='index')).to_dict()

        if inplace:
            self._kh = _kh_dict

        return _kh_dict

    def get_productivity_index_from_perforations(self,is_open=False, inplace=True):
        # ! Do not use.. Not fully implemented
        """
        Estimate the Productivity Index by formation with the self.perforations attribute.
        The self.perforations attribute must have a column 'productivity_index' with the Productivity Index for 
        the interval. If the column 'is_open' is present and the keyword 'is_open' is true the 
        productivity Index is calculated for the Open Formations.
        Productivity index is grouped by formation and sum.
        If the column 'formation' is not present a single item dictionary is calculated
        Input:
            is_open -> (bool, False).
        Return:
            productivity_index -> (dict) Dictionary with the productivity index by formation
        """
        assert self.perforations is not None, 'To estimate productivity_index from Perf, perf must be defined'
        _perf = self.perforations
        _keys = ['formation','productivity_index','fluid']
        assert all(i in _perf.columns for i in _keys)

        # If is_open only take the open.reset_index().set_index('fm')d intervals
        if is_open and 'is_open' in _perf.columns:
            _perf = _perf[_perf['is_open']==True]

        #Group by and sum aggregate
        _productivity_index_df_gr = _perf.groupby(['formation','fluid']).agg({'productivity_index':'sum'})
        _productivity_index_dict = _productivity_index_df_gr.groupby(level=0).apply(lambda x: x.reset_index().set_index('fluid')[['productivity_index']].to_dict(orient='index')).to_dict()

        if inplace:
            self._productivity_index = _productivity_index_dict

        return _productivity_index_dict

    def add_perforations(self,value, to_tvd=True, to_coord=True):
        """
        Add perforations to the existing ones
        """
        assert isinstance(value,perforations)

        if self.perforations is None:
            self._perforations = value
        else:
            _df = self.perforations.copy()
            _df = _df.append(value)
            self._perforations = _df
        
        if to_tvd:
            self.to_tvd(which=['perforations'])
            self.to_tvd(which=['perforations'],ss=True)

        if to_coord:
            self.to_coord(which=['perforations'])


    def schedule_forecast(self,
        cases = None,
        start_date:date=None,
        end_date:date=None,
        show=['oil','water','wc','total'],
        cash_name = {'capex':'capex','income':'income','var_opex':'var_opex','fix_opex':'fix_opex'},
        fq_estimate = 'D',
        fq_output = None
    ):
        if fq_output is None:
            fq_output = self.fq
        
        _case_list = []
        if cases is None:

            for key in self.schedule.keys():
                _case_list.append(key)
                
        elif isinstance(cases,str):
            _case_list.append(cases)
            
        elif isinstance(cases,list):
            _case_list.extend(cases)          
 
        cases_forecast_list = []

        # Iterate over all cases
        for case in _case_list:

            assert self.schedule is not None
            if case not in self.schedule.keys():
                continue
            sched = self.schedule[case]

            if cash_name is not None:
                assert isinstance(cash_name,dict)

            _forecast_list = []
            capex_sched ={}
            var_opex_list = []
            fix_opex_list = []
            income_list = []
            
            #dictionary to store the numerated keys. It is used to get get dependent start forecast
            num_dict = {} 

            #Iterate over the periods
            for i,v in enumerate(sched):
                
                #Update dictionary to enumerate the key to find the forecast dependant start
                num_dict[v]=i

                
                start_date_case = sched[v].get('start_date', None)
                end_date_case = sched[v].get('end_date', None)  
                
                #show water default True if wor_declination; if declination default is false
                show_water = sched[v].get('show_water', False if isinstance(sched[v]['declination'],declination) else True)
                # Start of declination is the end of prevous
                depend_start = sched[v].get('depend_start', None) 

                #days delay
                time_delay = sched[v].get('time_delay', timedelta(days=30)) 
                assert isinstance(time_delay,timedelta)

                # for declination object change ti the depend start
                change_ti = sched[v].get('change_ti', True)
                change_flow = sched[v].get('change_flow', False)

                # for wor_declination 
                depend_bsw = sched[v].get('depend_bsw', True)
                discount_bsw = sched[v].get('discount_bsw', 0.95)

                fix_end = sched[v].get('fix_end', False)

                #Capex 
                capex = sched[v].get('capex', None)
                abandonment = sched[v].get('abandonment', None)

                #Opex
                var_oil_opex = sched[v].get('var_oil_opex', None)
                var_gas_opex = sched[v].get('var_gas_opex', None)
                fix_opex = sched[v].get('fix_opex', None)

                #Price
                oil_price = sched[v].get('oil_price', None)
                gas_price = sched[v].get('gas_price', None)

                #royalty
                oil_royalty = sched[v].get('oil_royalty',0)
                gas_royalty = sched[v].get('gas_royalty',0)
                
                #limit
                econ_limit = sched[v].get('econ_limit',None)
                np_limit = sched[v].get('np_limit',None)
                
                #Initial npi
                npi = sched[v].get('npi',0)
                
                #Move Ti
                move_ti = sched[v].get('move_ti',None)
                
                #fluid rate
                fluid_rate = sched[v].get('fluid_rate',None)
                
                #gor
                gor = sched[v].get('gor',None) 
                    
                if depend_start in list(num_dict.keys()) and i>0:
                    
                    depend_number = num_dict[depend_start]
                    start_date_case = _forecast_list[depend_number].index[-1] + time_delay

                    if change_ti and isinstance(sched[v]['declination'],declination):
                        sched[v]['declination'].ti = _forecast_list[depend_number].index[-1].date()

                    if change_flow and isinstance(sched[v]['declination'],declination):
                        if sched[v]['declination'].gas:
                            sched[v]['declination'].qi = _forecast_list[depend_number]['qg'].iloc[-1]
                        else:
                            sched[v]['declination'].qi = _forecast_list[depend_number]['qo'].iloc[-1]                        
                    
                    if depend_bsw and isinstance(sched[v]['declination'],wor_declination):
                        sched[v]['declination'].bsw_i = _forecast_list[depend_number]['bsw'].iloc[-1] * discount_bsw

                if move_ti is not None:
                    assert isinstance(move_ti,date), f'move_ti must be date'
                    sched[v]['declination'].ti = move_ti
                
                _f,_ = sched[v]['declination'].forecast(
                    show_water=show_water, 
                    fq=fq_estimate, 
                    start_date=start_date_case,
                    end_date=end_date_case,
                    econ_limit = econ_limit,
                    np_limit = np_limit,
                    npi = npi,
                    fluid_rate = fluid_rate,
                    gor=gor
                )

                if start_date is not None:
                    _f = _f[_f.index>=pd.Timestamp(start_date)]

                if end_date is not None:
                    _f = _f[_f.index<=pd.Timestamp(end_date)]

                if var_oil_opex is not None:
                    if isinstance(var_oil_opex, (int,float,list,np.ndarray)):
                        var_oil_opex = np.atleast_1d(var_oil_opex)
                        assert var_oil_opex.ndim==1
                    var_opex_o = _f[['vo']].to_period(fq_output).reset_index().groupby('time').sum().multiply(var_oil_opex)
                    var_opex_list.append(var_opex_o.fillna(0))

                if var_gas_opex is not None:
                    if isinstance(var_gas_opex, (int,float,list,np.ndarray)):
                        var_gas_opex = np.atleast_1d(var_gas_opex)
                        assert var_gas_opex.ndim==1
                    var_opex_g = _f[['vg']].to_period(fq_output).reset_index().groupby('time').sum().multiply(var_gas_opex,axis='index')
                    var_opex_list.append(var_opex_g.fillna(0))

                if fix_opex is not None:
                    if isinstance(fix_opex,(int,float,list)):
                        fix_opex_s = pd.Series(np.full(_f.index.shape, fix_opex), index=_f.index)
                    elif isinstance(fix_opex,pd.Series):
                        fix_opex_list.append(fix_opex)

                if oil_price is not None:
                    # Oil price must be a scalar or a pd Series indexed by Period
                    income_o = _f['vo'].to_period(fq_output).reset_index().groupby('time').sum().multiply(oil_price,axis='index').multiply((1-oil_royalty),axis='index').dropna()
                    income_list.append(income_o)

                if gas_price is not None:
                    # Oil price must be a scalar or a pd Series indexed by Period
                    income_g = _f['vg'].to_period(fq_output).reset_index().groupby('time').sum().multiply(oil_price,axis='index').multiply((1-oil_royalty),axis='index').dropna()
                    income_list.append(income_g)                    
                    

                if abandonment is not None:
                    if isinstance(abandonment,dict):
                        capex_sched.update(abandonment)
                    else:
                        fmt = freq_format[fq_output]
                        abandonment_date = _f.index[-1].strftime(fmt)
                        capex_sched.update({abandonment_date:abandonment})

                if all([cash_name is not None,capex is not None]):
                    if isinstance(capex,dict):
                        capex_sched.update(capex)
                    else:
                        fmt = freq_format[fq_output]
                        capex_date = start_date_case.strftime(fmt)
                        capex_sched.update({capex_date:capex})

                _f['period'] = v
                _forecast_list.append(_f)

            # Add to case forecast list
            _forecast = pd.concat(_forecast_list,axis=0)
            _forecast['case'] = case
            
            if start_date is not None:
                _forecast = _forecast[_forecast.index>=pd.Timestamp(start_date)]

            if end_date is not None:
                _forecast = _forecast[_forecast.index<=pd.Timestamp(end_date)]

            #Add to general forecast
            cases_forecast_list.append(_forecast)
            
            #Cash flow generate
            if bool(capex_sched):
                cash_objt = cash(const_value=0, start=_forecast.index.min(), chgpts=capex_sched,
                    end=_forecast.index.max(), freq=fq_output, name=cash_name['capex'] +'_'+ self.name)
                
                self.add_cashflow({cash_name['capex']:cash_objt},case=case)

            if len(income_list)>0:
                income_df = pd.concat(income_list, axis=1)
                income_df['total'] = income_df.sum(axis=1)
                inc_cash_objt = cash(const_value=income_df['total'].to_list(),
                    start=income_df.index.min().to_timestamp(),
                    freq=fq_output, name=cash_name['income'] +'_'+ self.name)
                
                self.add_cashflow({cash_name['income']:inc_cash_objt},case=case)

            if len(var_opex_list)>0:
                var_opex_df = pd.concat(var_opex_list, axis=1)
                var_opex_df['total'] = var_opex_df.sum(axis=1)
                varopex_cash_objt = cash(const_value=var_opex_df['total'].to_list(),
                    start=var_opex_df.index.min().to_timestamp(),
                    freq=fq_output, name=cash_name['var_opex'] +'_'+ self.name)
                
                self.add_cashflow({cash_name['var_opex']:varopex_cash_objt},case=case)

            if len(fix_opex_list)>0:
                fix_opex_df = pd.concat(fix_opex_list, axis=1)
                fix_opex_df['total'] = fix_opex_df.sum(axis=1)
                fixopex_cash_objt = cash(const_value=fix_opex_df['total'].to_list(),
                    start=fix_opex_df.index.min().to_timestamp(),
                    freq=fq_output, name=cash_name['fix_opex'] +'_'+ self.name)
                
                self.add_cashflow({cash_name['fix_opex']:fixopex_cash_objt},case=case)

            # Add to case forecast list
        if len(cases_forecast_list)>0:
            _cases_forecast = pd.concat(cases_forecast_list,axis=0)       

            #Aggregation dict for output dataframe
            output_agg = {
                'qo':'mean',
                'vo':'sum',
                'np':'max',
            }
            
            if 'qw' in _cases_forecast.columns:
                output_agg.update({
                    'qw':'mean',
                    'vw':'sum',
                    'wp':'max',
                    'bsw':'mean'
                })
                
            if 'qg' in _cases_forecast.columns:
                output_agg.update({
                    'qg':'mean',
                    'vg':'sum',
                    'gp':'max',
                })
            
            
            output_forecast = _cases_forecast.to_period(fq_output).reset_index().groupby(['case','period','time']).agg(output_agg).reset_index()
            output_forecast['datetime'] = output_forecast['time'].apply(lambda x: x.to_timestamp())
            output_forecast['well'] = self.name
            return output_forecast
        else:
            return None

    def get_fcf(
        self,
        cases:str=None,
        income:list=['income'],
        opex:list=['var_opex','fix_opex'],
        capex:list=['capex'],
        prate=0,
        pyr=12
    ):
        _case_list = []
        if cases is None:
            for key in self.cashflow.keys():
                _case_list.append(key)
                
        elif isinstance(cases,str):
            _case_list.append(cases)
            
        elif isinstance(cases,list):
            _case_list.extend(cases)       
            
        spreadsheet_cases = []
        npv_cases = {}
        for case in _case_list:
            
            spreadsheet_list = []
            
            if income is not None:
                income_list = []
                for i in income:
                    try:
                        income_list.append(self.cashflow[case][i].cashflow())
                    except KeyError:
                        pass

                if len(income_list)>0:
                    income_df = pd.concat(income_list, axis=1)
                    income_df['total_income'] = income_df.sum(axis=1)
                    spreadsheet_list.append(income_df['total_income'])

            if opex is not None:
                opex_list = []
                for i in opex:
                    try:
                        opex_list.append(self.cashflow[case][i].cashflow())
                    except KeyError:
                        pass

                if len(opex_list)>0:
                    opex_df = pd.concat(opex_list, axis=1)
                    opex_df['total_opex'] = opex_df.sum(axis=1)
                    spreadsheet_list.append(opex_df['total_opex'])

            if capex is not None:
                capex_list = []
                for i in capex:
                    try:
                        capex_list.append(self.cashflow[case][i].cashflow())
                    except KeyError:
                        pass

                if len(capex_list)>0:
                    capex_df = pd.concat(capex_list, axis=1)
                    capex_df['total_capex'] = capex_df.sum(axis=1)
                    spreadsheet_list.append(capex_df['total_capex'])

            # Estimate financial data
            if len(spreadsheet_list)>0:
                spreadsheet = pd.concat(spreadsheet_list, axis=1).fillna(0)

                col_list = ['total_income','total_opex','total_capex']

                for c in col_list:
                    if c not in spreadsheet.columns:
                        spreadsheet[c] = np.zeros(spreadsheet.shape[0])        

                #EBIT
                spreadsheet['net_income'] = spreadsheet['total_income'] + spreadsheet['total_opex']

                #Tax
                #tax_rate = pd.Series(np.full(spreadsheet.shape[0],tax*100), index=spreadsheet.index)
                #spreadsheet['tax'] = after_tax_cashflow(cflo=spreadsheet['ebit'], tax_rate=tax_rate) 

                #Net Income
                #spreadsheet['net_income'] = spreadsheet['ebit'] - spreadsheet['tax']
                
                #Freecashflow
                spreadsheet['free_cash_flow'] = spreadsheet['net_income'] + spreadsheet['total_capex']
                spreadsheet['cum_free_cash_flow'] = spreadsheet['free_cash_flow'].cumsum()
                spreadsheet['case'] = case
                spreadsheet['well'] = self.name
                #NPV         
                prate = np.atleast_1d(prate)
                
                npv = {}
                for pr in prate:
                    prn = perrate(pr,pyr=pyr)
                    
                    prate_series = pd.Series(np.full(spreadsheet.shape[0],prn), index=spreadsheet.index)
                    _npv = timevalue(spreadsheet['free_cash_flow'], prate_series)
                    npv.update({pr:_npv})

                #Append to general spreadsheet
                spreadsheet_cases.append(spreadsheet)
                
                #Append to dict of general npv
                npv_cases.update({case:npv})
                
        return pd.concat(spreadsheet_cases,axis=0), npv_cases

class wells_group:
    def __init__(self,*args,**kwargs):
        _well_list = []

        if args is not None:
            for i in args:
                _well_list.append(i)
        
        self.wells = _well_list 
        self.crs = kwargs.pop('crs', None)
        self.surfaces = kwargs.pop('surfaces', None)

    @property
    def wells(self):
        return self._wells

    @wells.setter 
    def wells(self,value):
        assert isinstance(value,list)
        if not value:
            self._wells = {}
        else:
            assert all(isinstance(i,well) for i in value)
            w_dict={}
            for i in value:
                w_dict[i.name] = i
            self._wells = w_dict

    @property
    def crs(self):
        return self._crs

    @crs.setter
    def crs(self,value):
        assert isinstance(value,(int,str,type(None))), f"{type(value)} not accepted. Name must be str. Example 'EPSG:3117'"
        
        if isinstance(value,int):
            value = f'EPSG:{value}'
        elif isinstance(value,str):
            assert value.startswith('EPSG:'), 'if crs is string must starts with EPSG:. If integer must be the Coordinate system reference number EPSG http://epsg.io/'
        self._crs = value

    @property
    def surfaces(self):
        return self._surfaces
    
    @surfaces.setter
    def surfaces(self, value):
        if value is not None:
            assert isinstance(value, surface_group)
        self._surfaces = value

    def add_well(self,*args):
        _add_well = []

        if args is not None:
            for i in args:
                _add_well.append(i)

        assert all(isinstance(i,well) for i in _add_well)

        _wells_dict = self.wells.copy()

        for i in _add_well:
            _wells_dict[i.name] = i
        self._wells = _wells_dict

    # Methods

    def describe(self):
        """
        Get a dataframe describing the attributes of each well

        Return:
            df -> (gpd.GeoDataFrame) 
        """
        gdf = gpd.GeoDataFrame()

        for well in self.wells:
            dict_attr = {
                'schema':[False if self.wells[well].schema is None else True],
                'rte':[self.wells[well].rte],
                'surf_coord':[self.wells[well].surf_coord],
                'crs':[self.wells[well].crs],
                'survey': [False if self.wells[well].survey is None else True],
                'perforations': [False if self.wells[well].perforations is None else True],
                'tops': [False if self.wells[well].tops is None else True],
                'units': [False if self.wells[well].units is None else True],                
                'openlog': [False if self.wells[well].openlog is None else True],
                'masterlog': [False if self.wells[well].masterlog is None else True],
                'caselog': [False if self.wells[well].caselog is None else True],
                'schedule':[False if self.wells[well].schedule is None else True]
                }
            _well_gpd = gpd.GeoDataFrame(dict_attr, index=[well])
            gdf = gdf.append(_well_gpd)

        gdf = gdf.set_geometry('surf_coord')

        return gdf

    def wells_tops(self, wells:list=None, horizons:list=None, projection1d = False, azi=90, center=None, units=False):
        """
        Get a DataFrame with the wells formations tops
        Input:
            wells ->  (list, None) List of wells in the Group to show
                    If None, all wells in the group will be selected
            horizons ->  (list, None) List of formation in the Group to show 
                    If None, all formations in the group will be selected
            projection1d ->  (bool, default False) If true it adds a column with a 1d projection of coordinates 
            azi -> (int, float, np.ndarray, default 90) Azimuth direction for projection
            center -> (list, np.nd.ndarray)  Center for the projection

        Return:
            tops -> (gpd.GeoDataFrame) GeoDataFrame with tops indexed by well
        """        
        assert isinstance(wells,(list,type(None)))
        assert isinstance(horizons,(list,type(None)))
        assert isinstance(center,(list,np.ndarray, type(None)))
        assert isinstance(azi,(int,float,np.ndarray))
        # Define which wells for the distance matrix will be shown    
        if wells is None:
            _well_list = []
            for key in self.wells:
                _well_list.append(key)
        else:
            _well_list = wells

        _wells_tops = gpd.GeoDataFrame()

        for well in _well_list:
            if units==False:
                if self.wells[well].tops is None:
                    continue
            else:
                if self.wells[well].units is None:
                    continue
    
            if self.wells[well].survey is not None:
                self.wells[well].to_tvd(which=['units' if units else 'tops'])
                self.wells[well].to_tvd(which=['units' if units else 'tops'],ss=True)
                self.wells[well].to_coord(which=['units' if units else 'tops'])
            else:
                assert projection1d == False, 'If projection1d is True surveys must be set'
            _tops = self.wells[well].units.copy() if units else self.wells[well].tops.copy()
            _tops['well'] = well
            _wells_tops = _wells_tops.append(_tops, ignore_index=False)
        
        if horizons is not None:
            _wells_tops = _wells_tops.loc[horizons]

        #_wells_tops = _wells_tops.reset_index()
        
        if projection1d == True:
            _pr,c = projection_1d(_wells_tops[['easting','northing']].values, azi, center=center)
            _wells_tops['projection'] = _pr
            r=[_wells_tops,c]
        else:
            r=_wells_tops

        return r

    def wells_surveys(self, wells:list=None, projection1d = False, azi=90, center=None):
        """
        Get a DataFrame with the wells surveys
        Input:
            wells ->  (list, None) List of wells in the Group to show
                    If None, all wells in the group will be selected
            formations ->  (list, None) List of formation in the Group to show 
                    If None, all formations in the group will be selected
        Return:
            tops -> (gpd.GeoDataFrame) GeoDataFrame with tops indexed by well
        """    
        assert isinstance(wells,(list,type(None)))
        assert isinstance(center,(list,np.ndarray, type(None)))
        assert isinstance(azi,(int,float,np.ndarray))
        # Define which wells for the distance matrix will be shown    
        if wells is None:
            _well_list = []
            for key in self.wells:
                _well_list.append(key)
        else:
            _well_list = wells

        _wells_survey = gpd.GeoDataFrame()
        for well in _well_list:
            if self.wells[well].survey is None:
                continue
            else:
                _s = self.wells[well].survey.copy()
                _s['well'] = well 
                _s = _s.reset_index()
                _wells_survey = _wells_survey.append(gpd.GeoDataFrame(_s))

        _wells_survey.crs = self.crs
        if projection1d == True:
            _pr,c = projection_1d(_wells_survey[['easting','northing']].values, azi, center=center)
            _wells_survey['projection'] = _pr
            r=[_wells_survey,c]
        else:
            r=_wells_survey

        return r
    
    def wells_surveys_ascii(self, 
        wells:list=None, 
        factor=None, 
        cols=['easting','northing','tvdss','md'],
        float_format='{:.2f}'.format
        ):
        
        assert isinstance(wells,(list,type(None)))
        
        wells_surveys_df = self.wells_surveys(wells=wells)
             
        string = ""

        if factor is None:
            factor = np.ones(len(cols))
        else:
            factor = np.atleast_1d(factor)
            assert (factor.ndim==1) & (factor.shape[0]==len(cols))
        
        for w in wells_surveys_df['well'].unique():

            _df = wells_surveys_df.loc[wells_surveys_df['well']==w,cols] * factor
            string += f"WELLNAME: {w}\n"
            string += _df.to_string(header=False,index=False,float_format=float_format) + '\n'
        return string
        

    def wells_perforations(self, wells:list=None, horizons=None):
        """
        Get a DataFrame with the wells perforations
        Input:
            wells ->  (list, None) List of wells in the Group to show
                    If None, all wells in the group will be selected
            formations ->  (list, None) List of formation in the Group to show 
                    If None, all formations in the group will be selected
        Return:
            tops -> (gpd.GeoDataFrame) GeoDataFrame with tops indexed by well
        """    
        if wells is not None:
            assert isinstance(wells,(list,str))
            wells = input_to_list(wells)
            
        if horizons is not None:
            assert isinstance(wells,(list,str))
            horizons = input_to_list(horizons)
            
        # Define which wells for the distance matrix will be shown    
        if wells is None:
            _well_list = []
            for key in self.wells:
                _well_list.append(key)
        else:
            _well_list = wells

        _wells_survey = gpd.GeoDataFrame()
      
        for well in _well_list:
            if self.wells[well].perforations is None:
                continue
            else:
                if horizons is None:
                    _s = self.wells[well].perforations.copy()
                else:
                    _s = self.wells[well].perforations.copy()
                    _s = _s[_s['formation'].isin(horizons)]
                if _s.empty:
                    continue
                else:
                    _s['well'] = well 
                    _s = _s.reset_index()
                    _wells_survey = _wells_survey.append(gpd.GeoDataFrame(_s))

        return _wells_survey
    
    def wells_perforations_ascii(self,
        wells:list=None, 
        horizons:list=None,
        factor=None, 
        cols=['md_top','md_bottom'],
        float_format='{:.2f}'.format
    ):
        assert isinstance(wells,(list,type(None)))
        
        wells_perforations_df = self.wells_perforations(wells=wells, horizons=horizons).reset_index()
             
        string = ""

        if factor is None:
            factor = np.ones(len(cols))
        else:
            factor = np.atleast_1d(factor)
            assert (factor.ndim==1) & (factor.shape[0]==len(cols))
            
        wells_perforations_df['completion'] = 'perforation'
        
        if 'date' not in wells_perforations_df.columns:
            wells_perforations_df['date'] = '"SOH"'
        else:
            wells_perforations_df['date'] = wells_perforations_df['date'].apply(lambda x: x.strftime('%Y-%m-%d').upper())
        
        if 'skin' not in wells_perforations_df.columns:
            wells_perforations_df['skin'] = 0

        if 'OH' not in wells_perforations_df.columns:
            wells_perforations_df['oh'] = 0.354           
        
        for w in wells_perforations_df['well'].unique():
            #_df = wells_perforations_df.loc[wells_perforations_df['well']==w,:]
            wells_perforations_df.loc[wells_perforations_df['well']==w,cols] = wells_perforations_df.loc[wells_perforations_df['well']==w,cols] * factor        
            
            string += f"WELLNAME {w}\n"
            cols_order = ['date','completion','md_top','md_bottom','oh','skin']
            string += wells_perforations_df.loc[wells_perforations_df['well']==w,cols_order].to_string(header=False,index=False,float_format=float_format) + '\n'
        return string
        
    def wells_coordinates(self, wells:list=None, z_unit='ft', to_crs='EPSG:4326'):
        """
        Get a DataFrame with the wells surface coordinates
        Input:
            wells ->  (list, None) List of wells in the Group to show the matrix. 
                    If None, all wells in the group will be selected
        Return:
            wells_coord -> (gpd.GeoDataFrame) GeoDataFrame with wells coords
        """
        assert isinstance(wells,(list,type(None)))

        # Define which wells for the distance matrix will be shown    
        if wells is None:
            _well_list = []
            for key in self.wells:
                _well_list.append(key)
        else:
            _well_list = wells

        #Create coordinates dataframe
        _coord = gpd.GeoDataFrame()

        z_coef = 0.3048 if z_unit=='ft' else 1

        for well in _well_list:
            x_coord = self.wells[well].surf_coord.x
            y_coord = self.wells[well].surf_coord.y
            z_coord = self.wells[well].surf_coord.z*z_coef if self.wells[well].surf_coord.has_z==True else self.wells[well].rte*z_coef
            shape = self.wells[well].surf_coord
            crs = self.wells[well].crs
            _w = gpd.GeoDataFrame({'x':[x_coord],'y':[y_coord],'z':[z_coord],'geometry':[shape]}, index=[well])
            _w.crs = crs
            _w = _w.to_crs(to_crs)
            _w['lon'] = _w['geometry'].x
            _w['lat'] = _w['geometry'].y
            _coord = _coord.append(_w)

        return _coord


    def wells_distance(self,wells:list=None, dims:list=['x','y','z'], z_unit:str='ft'):
        """
        Calculate a distance matrix for the surface coordinates of the wells

        Input:
            wells ->  (list, None) List of wells in the Group to show the matrix. 
                    If None, all wells in the group will be selected
            z ->  (Bool, default False). Take into account the z component. Z must be in the same
                    units of x, y coord
            z_unit -> (str, default 'ft') Indicate the units of the z coord. 
                    If 'ft' the z is multiplied by 0.3028 otherwise by 1

        Return:
            dist_matrix -> (pd.DataFrame) Distance matrix with index and column of wells
        """
        
        assert isinstance(wells,(list,type(None)))

        _coord = self.wells_coordinates(wells=wells, z_unit=z_unit)

        dist_array = distance_matrix(_coord[dims].values,_coord[dims].values)
        dist_matrix = pd.DataFrame(dist_array,index=_coord.index, columns=_coord.index)

        return dist_matrix

    def wells_map(self, wells:list=None,zoom=10, map_style = 'OpenStreetMap',tooltip=True,popup=False,ax=None):
        """
        Make a Foluim map with the selected wells

        Input:
            wells ->  (list, None) List of wells in the Group to show the matrix. 
                    If None, all wells in the group will be selected
            zoom -> (int, float) Initial zoom for folium map
        Return:
            w_map -> (folium.Map) Folium map object
        """
        assert isinstance(wells,(list,type(None)))

        _coord = self.wells_coordinates(wells=wells)

        center = _coord[['lat','lon']].mean(axis=0)

        #make the map
        if ax is None:
            map_folium = folium.Map(
                location=(center['lat'],center['lon']),
                zoom_start=zoom,
                tiles = map_style)
        else:
            assert isinstance(ax,folium.folium.Map)
            map_folium = ax

        for i, r in _coord.iterrows():
            folium.Marker(
                [r['lat'],r['lon']],
                tooltip=f"{i}" if tooltip else None,
                popup = folium.Popup(html=f"{i}",show=True,max_width='50%') if popup else None,
                icon=folium.Icon(icon='tint', color='green')
                ).add_to(map_folium)

        folium.LayerControl().add_to(map_folium)
        #LocateControl().add_to(map_folium)
        MeasureControl().add_to(map_folium)
        MousePosition().add_to(map_folium)

        return map_folium

    def wells_tops_map(self, wells:list=None,horizons:list=None,zoom:int=10, map_style:str = 'OpenStreetMap',tooltip:bool=True,popup:bool=False,ax=None, units:bool=False):
        """
        Make a Foluim map with the selected wells

        Input:
            wells ->  (list, None) List of wells in the Group to show the matrix. 
                    If None, all wells in the group will be selected
            zoom -> (int, float) Initial zoom for folium map
        Return:
            w_map -> (folium.Map) Folium map object
        """
        assert isinstance(wells,(list,type(None)))

        _coord = self.wells_tops(wells=wells, horizons=horizons, units=units)
        _coord = _coord.to_crs('EPSG:4326')
        _coord['lon'] = _coord['geometry'].x
        _coord['lat'] = _coord['geometry'].y
        center = _coord[['lat','lon']].mean(axis=0)

        #make the map
        if ax is None:
            map_folium = folium.Map(
                location=(center['lat'],center['lon']),
                zoom_start=zoom,
                tiles = map_style)
        else:
            assert isinstance(ax,folium.folium.Map)
            map_folium = ax

        for i, r in _coord.iterrows():
            folium.Marker(
                [r['lat'],r['lon']],
                tooltip=f"{r['well']} {i}" if tooltip else None,
                popup = folium.Popup(html=f"{r['well']} {i}",show=True,max_width='50%') if popup else None,
                icon=folium.Icon(icon='tint', color='green')
                ).add_to(map_folium)

        folium.LayerControl().add_to(map_folium)
        #LocateControl().add_to(map_folium)
        MeasureControl().add_to(map_folium)
        MousePosition().add_to(map_folium)

        return map_folium

    def wells_surveys_map(self, wells:list=None,zoom:int=10, map_style:str = 'OpenStreetMap',tooltip:bool=True,popup:bool=False,ax=None,radius=10):
        """
        Make a Foluim map with the selected wells

        Input:
            wells ->  (list, None) List of wells in the Group to show the matrix. 
                    If None, all wells in the group will be selected
            zoom -> (int, float) Initial zoom for folium map
        Return:
            w_map -> (folium.Map) Folium map object
        """
        assert isinstance(wells,(list,type(None)))

        _coord = self.wells_surveys(wells=wells)
        _coord = _coord.to_crs('EPSG:4326')
        _coord['lon'] = _coord['geometry'].x
        _coord['lat'] = _coord['geometry'].y
        center = _coord[['lat','lon']].mean(axis=0)

        #make the map
        if ax is None:
            map_folium = folium.Map(
                location=(center['lat'],center['lon']),
                zoom_start=zoom,
                tiles = map_style)
        else:
            assert isinstance(ax,folium.folium.Map)
            map_folium = ax

        for i, r in _coord.iterrows():
            folium.Circle(
                [r['lat'],r['lon']],
                tooltip=f"{r['well']} <br>md:{r['md']} <br>tvd:{r['tvd']} <br>tvdss:{r['tvdss']} <br>inc:{r['inc']} " if tooltip else None,
                popup = folium.Popup(html=f"{r['well']} <br>md:{r['md']} <br>tvd:{r['tvd']} <br>tvdss:{r['tvdss']} <br>inc:{r['inc']} ",show=True,max_width='50%') if popup else None,
                #icon=folium.Icon(icon='circle',prefix='fa', color='green'),
                radius=radius
                ).add_to(map_folium)

        folium.LayerControl().add_to(map_folium)
        #LocateControl().add_to(map_folium)
        MeasureControl().add_to(map_folium)
        MousePosition().add_to(map_folium)

        return map_folium

    def formation_distance(self, wells:list=None, horizon:str=None, dims:list=['easting','northing','tvdss_top'], z_unit='ft',units=False):
        """
        Calculate a distance matrix for the formation of interest

        Input:
            wells ->  (list, None) List of wells in the Group to show the matrix. 
                    If None, all wells in the group will be selected
            formation -> (str) Formation of interest. The attributes tops and survey must be set on each well
        Return:
            dist_matrix -> (pd.DataFrame) Distance matrix with index and column of wells
        """
        assert isinstance(wells,(list,type(None)))

        # Define which wells for the distance matrix will be shown    
        if wells is None:
            _well_list = []
            for key in self.wells:
                _well_list.append(key)
        else:
            _well_list = wells

        z_coef = 0.3048 if z_unit=='ft' else 1

        _fm_df = gpd.GeoDataFrame()

        for key in _well_list:
            has_survey = self.wells[key].survey is not None
            has_tops = self.wells[key].units is not None if units else self.wells[key].tops is not None
            if all([has_tops,has_survey]):
                if units:
                    assert horizon in self.wells[key].units.index.tolist() 
                    if 'tvdss_top' not in self.wells[key].units.columns:
                        self.wells[key].to_tvd(which=['units'])
                        self.wells[key].to_tvd(which=['units'],ss=True)
                    if 'geometry' not in self.wells[key].units.columns:
                        self.wells[key].to_coord(which=['units'])
                    _df = self.wells[key].units.loc[[horizon],['easting','northing','tvdss_top']].reset_index()
                    _df['well'] = key
                    _df['tvdss_top'] = _df['tvdss_top']*z_coef
                    #print(_df)
                    _fm_df = _fm_df.append(_df, ignore_index=True) 
                else:  
                    assert horizon in self.wells[key].tops.index.tolist()
                    if 'tvdss_top' not in self.wells[key].tops.columns:
                        self.wells[key].to_tvd(which=['tops'])
                        self.wells[key].to_tvd(which=['tops'],ss=True)
                    if 'geometry' not in self.wells[key].tops.columns:
                        self.wells[key].to_coord(which=['tops'])
                    _df = self.wells[key].tops.loc[[horizon],['easting','northing','tvdss_top']].reset_index()
                    _df['well'] = key
                    _df['tvdss_top'] = _df['tvdss_top']*z_coef
                    #print(_df)
                    _fm_df = _fm_df.append(_df, ignore_index=True)
                
        
        dist_array = distance_matrix(_fm_df[dims].values,_fm_df[dims].values)
        dist_matrix = pd.DataFrame(dist_array,index=_fm_df['well'], columns=_fm_df['well'])

        return dist_matrix

    def structural_view(self,
        wells:list=None, 
        horizons:list=None, 
        show_surveys=True, 
        show_horizons=True, 
        azi=0, 
        center=None,
        ax=None,
        margin=500,
        units=False, 
        **kwargs):
        """
        plot a structural view of the tops and wells in a 2D representation

        Input:
            wells ->  (list, None) List of wells in the Group to show. 
                    If None, all wells in the group will be selected
            horizons -> (list) Formations of interest. The attributes tops and survey must be set on each well
                    If None all the formations available are selected 
            surveys -> (bool, default True) If the surveys are plotted 
            formations -> (bool, default True) If the tops are plotted 
            azi -> (int,float, default 0) The azimuth direction being azimuth 0 direction North-South
            center -> (list, np.ndarray) The center for the prejection. Lits or numpy array with shape (2,)
            ax -> (ax, default None) axis for plottling Matplotlib
        Return:
            dist_matrix -> (pd.DataFrame) Distance matrix with index and column of wells
        """
        assert isinstance(wells,(list,type(None))), f'{type(wells)}'
        assert isinstance(horizons,(list,type(None)))
        assert isinstance(show_surveys, bool)
        assert isinstance(show_horizons, bool)
        assert isinstance(azi, (int,float)) and azi >=0 and azi<=360 
        assert isinstance(center,(list,np.ndarray,type(None)))

        #Create the Axex
        stax= ax or plt.gca()

        #set center
        if center is not None:
            center = np.atleast_1d(center)
            assert center.shape == (2,)     
   
        # Plot

        # Color pallete
        fm_color = kwargs.pop('formation_cmap','Set1')
        well_color = kwargs.pop('well_cmap','GnBu_d')
        legend = kwargs.pop('legend','brief')
        horizon_scatter = kwargs.pop('scatter',False)
        ann = kwargs.pop('ann',True)
        ann_fontsize = kwargs.pop('ann_fontsize',11)

        if show_horizons:
            tops, center_tops = self.wells_tops(wells=wells, horizons=horizons, projection1d=True, azi=azi,center=center, units=units)
            tops.reset_index(inplace=True)
            if horizon_scatter:
                sns.scatterplot(
                    x='projection',
                    y='tvdss_top', 
                    data=tops, 
                    hue='unit' if units else 'formation',
                    markers=True, 
                    ax=stax, 
                    palette=fm_color, 
                    legend=legend)
            else:
                sns.lineplot(
                    x='projection',
                    y='tvdss_top', 
                    data=tops, 
                    hue='unit' if units else 'formation',
                    markers=True, 
                    ax=stax, 
                    palette=fm_color, 
                    legend=legend)
            
        if ann:
            for i,v in tops.iterrows():
                stax.annotate(
                    f"{v['well']}",
                    xy=(v['projection'],v['tvdss_top']),
                    xycoords='data',
                    horizontalalignment='right', 
                    fontsize=ann_fontsize,
                    bbox={'boxstyle':'round', 'fc':'0.8'},
                    xytext=(0, 20),
                    textcoords='offset points'
                    )
                

        if show_surveys:
            surv,_ = self.wells_surveys(
                wells=wells,
                projection1d=True, 
                azi=azi, 
                center=center_tops if show_horizons==True else None
            )
            sns.lineplot(
                x='projection',
                y='tvdss', 
                data=surv, 
                hue='well', 
                ax=stax, 
                palette=well_color, 
                legend=False
            )

        ## y lims
        ylims = kwargs.pop('ylims',None)
        if ylims==None: #Depth Limits
            if show_surveys and show_horizons:
                ylims=[surv['tvdss'].max()-margin,surv['tvdss'].min()+margin]
            elif show_surveys:
                ylims=[surv['tvdss'].max()-margin,surv['tvdss'].min()+margin]
            elif show_horizons:
                ylims=[tops['tvdss_top'].max()-margin,surv['tvdss_top'].min()+margin]

        stax.set_ylim([ylims[1],ylims[0]])

        xlims = kwargs.pop('xlims',None)
        if xlims is not None:
            stax.set_xlim([xlims[0],xlims[1]])

    def wells_surveys_vtk(self, wells:list=None):
        """
        Get the vtk object in PyVista for the wells survey selected
        Input:
            wells ->  (list, None) List of wells in the Group to show. 
                    If None, all wells in the group will be selected
        Return:
            surveys -> (pv.MultiBlock) pyvista.MultiBlock object with vtk surveys
        """
        if wells is None:
            _well_list = []
            for key in self.wells:
                if self.wells[key].survey is not None:
                    _well_list.append(key)
        else:
            _well_list = wells

        data = {}
        for well in _well_list:
            data[well] = self.wells[well].get_vtk()

        survey_blocks = pv.MultiBlock(data)

        return survey_blocks

    def tops_vtk(self,wells:list=None, horizons:list=None,units=False):
        """
        Get the vtk object in PyVista for the well tops
        Input:
            wells ->  (list, None) List of wells in the Group to show. 
                    If None, all wells in the group will be selected
            formation -> (list, None) List of formations in the Group to show. 
                    If None, all formatiions in the group will be selected
        Return:
            tops -> (pv.MultiBlock) pyvista.MultiBlock object with vtk tops
        """

        assert isinstance(wells,(list,type(None))), f'{type(wells)}'
        assert isinstance(horizons,(list,type(None)))

        tops = self.wells_tops(wells=wells, horizons=horizons, projection1d=False, units=units)
        tops.reset_index(inplace=True)
        data = {}
        _item = 'unit' if units else 'formation'
        for fm in tops[_item].unique():
            _df = tops.loc[tops[_item]==fm,['easting','northing','tvdss_top']].values
            _surf = pv.PolyData(_df).delaunay_2d()
            data[fm] = _surf 

        fm_blocks = pv.MultiBlock(data)

        return fm_blocks

    def structural_view_vtk(self,wells:list=None, horizons:list=None, units=False):
        """
        Get the vtk object in PyVista for the well tops and surveys
        Input:
            wells ->  (list, None) List of wells in the Group to show. 
                    If None, all wells in the group will be selected
            formation -> (list, None) List of formations in the Group to show. 
                    If None, all formatiions in the group will be selected
        Return:
            surv_tops -> (pv.MultiBlock) pyvista.MultiBlock object with vtk surveys and tops
        """
        assert isinstance(wells,(list,type(None))), f'{type(wells)}'
        assert isinstance(horizons,(list,type(None)))

        s_vtk = self.wells_surveys_vtk(wells=wells)
        t_vtk = self.tops_vtk(wells=wells, horizons=horizons, units=units)

        blocks = pv.MultiBlock()

        for t in t_vtk.keys():
            blocks.append(t_vtk[t])

        for s in s_vtk.keys():
            blocks.append(s_vtk[s])

        return blocks

    def get_from_oilbase(self,engine, wells:list=None, fields:list=None):
        """
        Add wells information from the Postgres Database scuervo91/oilbase
        It uses the structure and the sintaxis implemented specifically in that database
        """
                 
        
        well_heads_query= """
            select w.well, w.surface_x, w.surface_y, w.epsg, w.kbe
            from list.wells w
            join list.fields f on w.field_id = f.id
        """

        well_surveys_query= """
            select w.well, s.md, s.inc, s.azi
            from list.surveys s
            join list.wells w on s.well_id = w.id
            join list.fields f on w.field_id = f.id
        """

        well_perforations_query= """
            select w.well, p.md_top, p.md_bottom, fm.formation
            from list.perforations p
            join list.wells w on p.well_id = w.id
            join list.fields f on w.field_id = f.id
            join list.formations fm on p.formation_id = fm.id
        """

        well_formations_tops_query= """
            select w.well, ft.md_top, ft.md_bottom, fm.formation
            from list.formations_tops ft
            join list.wells w on ft.well_id = w.id
            join list.fields f on w.field_id = f.id
            join list.formations fm on ft.formation_id = fm.id
        """

        well_units_tops_query = """
            select w.well, ut.md_top, ut.md_bottom, u.unit, fm.formation
            from list.units_tops ut
            join list.units u on ut.unit_id = u.id 
            join list.formations fm on u.formation_id = fm.id
            join list.wells w on ut.well_id = w.id
            join list.fields f on w.field_id = f.id
        """

        #Custom the query
        query_list = {
            'well_heads':well_heads_query,
            'well_surveys': well_surveys_query,
            'well_perforations':well_perforations_query,
            'well_formations_tops':well_formations_tops_query,
            'well_units_tops':well_units_tops_query
        }

        if wells is not None:
            assert isinstance(wells,(str,list))

            for i in query_list:
                query_list[i] = query_list[i] + f" where w.well in {tuple(wells)}".replace(',)',')')


        if fields is not None:
            assert isinstance(fields,(str,list))

            if wells is None:
                for i in query_list:
                    query_list[i] = query_list[i] + f" where f.field in {tuple(fields)}".replace(',)',')')
            else:
                for i in query_list:
                    query_list[i] = query_list[i] + f" and f.field in {tuple(fields)}".replace(',)',')')


        # query from oilbase
        df_dict = {}
        for i in query_list:
            try:
                _df = pd.read_sql(query_list[i], con=engine)
                df_dict[i] = _df
            except:
                df_dict[i] = None
     
        #List of wells
        wells_list = df_dict['well_heads']['well'].tolist()

        #Create wells object
        for i in wells_list:
            #Perforations
            _p = df_dict['well_perforations']
            try:
                _perf = perforations(_p.loc[_p['well']==i,['md_top','md_bottom','formation']])
                if _perf.empty:
                    _perf = None
            except:
                _perf = None 
            
            #Tops
            _t = df_dict['well_formations_tops']

            try:
                _tops = tops(_t.loc[_t['well']==i,:])
                if _tops.empty:
                    _tops = None
            except:
                _tops = None

            #units
            _u = df_dict['well_units_tops']

            try:
                _units = tops(_u.loc[_u['well']==i,:])
                if _units.empty:
                    _units = None
            except:
                _units = None

            #surveys
            _s = df_dict['well_surveys']

            try:
                _survey = _s.loc[_s['well']==i,['md','inc','azi']].sort_values(by='md', ascending=True)

                if _survey.empty:
                    _survey = None
            except:
                _survey = None
            
            _wh = df_dict['well_heads']
            _rte = _wh.loc[_wh['well']==i,'kbe'].iloc[0]
            _crs = _wh.loc[_wh['well']==i,'epsg'].iloc[0]
            _surf_coord = _wh.loc[_wh['well']==i,['surface_x','surface_y']].squeeze().tolist()
            
            _surf_coord =  None if any([i is None for i in _surf_coord]) else _surf_coord
            _well = well(
                name = i,
                rte = _rte,
                crs = _crs,
                surf_coord = _surf_coord, 
                survey = _survey,
                perforations = _perf,
                tops = _tops,
                units = _units
            )

            try:
                _well.to_tvd(which=['tops','perforations','units'])
                _well.to_tvd(which=['tops','perforations','units'],ss=True)
                _well.to_coord(which=['tops','perforations','units'])
            except:
                pass

            self.add_well(_well)

    def schedule_forecast(self,
        cases=None,
        wells:list=None,
        start_date=None, 
        end_date=None,
        cash_name = {'capex':'capex','income':'income','var_opex':'var_opex','fix_opex':'fix_opex'},
        fq_estimate = 'D',
        fq_output = None,
        **kwargs):

        if wells is None:
            _well_list = []
            for key in self.wells:
                _well_list.append(key)
        else:
            _well_list = wells
            
        

        forecast_df = pd.DataFrame()
        for well in _well_list:
            if self.wells[well].schedule is None:
                continue
            if isinstance(cases,(str,list)):
                well_cases = cases
            elif isinstance(cases,dict):
                try:
                    assert isinstance(cases[well],(str,list))
                    well_cases = cases[well]
                except KeyError:
                    print(f'{well} was not found in dict cases')
                    continue
                except Exception as e:
                    print(f'None value passed to well case. Error found {e}')
                    continue
            else:
                well_cases=None
            _f= self.wells[well].schedule_forecast(
                cases=well_cases,
                start_date=start_date, 
                end_date=end_date,
                cash_name=cash_name, 
                fq_estimate = fq_estimate,
                fq_output = fq_output,
                **kwargs
            )
            if _f is not None:
                forecast_df = pd.concat([forecast_df,_f],axis=0, ignore_index=False).fillna(0)

        return forecast_df

    def scenarios_maker(self,cases=None, wells=None, reduce=1):
        
        assert isinstance(reduce,int) and reduce >= 1
        
        if wells is None:
            _well_list = []
            for key in self.wells:
                _well_list.append(key)
        else:
            _well_list = wells
                   
        _cases_list = []
        
        levels = []
        
        for well in _well_list:
            _well_cases = []
            if self.wells[well].schedule is None:
                continue
            
            if cases is None:
                _well_cases = list(self.wells[well].schedule.keys())
            elif isinstance(cases,str):
                _well_cases.append(cases)
            elif isinstance(cases,list):
                _well_cases.extend(cases)
            elif isinstance(cases,dict):
                assert isinstance(cases[well],(str,list))
                if isinstance(cases,str):
                    _well_cases.append(cases)
                elif isinstance(cases,list):
                    _well_cases.extend(cases)
            
            _well_cases = [i for i in _well_cases if i in self.wells[well].schedule.keys()]
            _cases_list.append(_well_cases)
            levels.append(len(_well_cases))
        
        # Escenarios Array
        escenarios_array = ed.fullfact(levels) if reduce==1 else ed.gsd(levels,reduce)

        scenarios_list = []
        for escenario in escenarios_array:
            esc = {_well_list[i]:_cases_list[i][int(v)] for i,v in enumerate(escenario)}

            scenarios_list.append(esc)
        
        return scenarios_list
    
    def scenarios_forecast(
        self,
        scenarios=None,
        wells:list=None,
        start_date=None, 
        end_date=None,
        cash_name = {'capex':'capex','income':'income','var_opex':'var_opex','fix_opex':'fix_opex'},
        fq_estimate = 'D',
        fq_output = None,
        **kwargs
        ):
        assert isinstance(scenarios,list)
        
        scenarios_list = []
        for i,scenario in enumerate(scenarios):
            scenario_df = self.schedule_forecast(
                cases = scenario,
                wells = wells,
                start_date = start_date,
                end_date = end_date,
                cash_name = cash_name,
                fq_estimate = fq_estimate,
                fq_output = fq_output
            )
            scenario_df['scenario'] = i 
            scenarios_list.append(scenario_df)
        
        return pd.concat(scenarios_list,axis=0)
            
            
    def get_cashflow(self, wells:list=None, cases:str=None, cash_name:str=None):
        if wells is None:
            _well_list = []
            for key in self.wells:
                _well_list.append(key)
        else:
            _well_list = wells
        
        _cases_list = []
        _cash_name_list = []
        cashflow_list = []
        
        #Iterate over wells
        for well in _well_list:
            
            if self.wells[well].cashflow is None:
                continue
            if isinstance(cases,(str,list)):
                _cases_list.extend(input_to_list(cases))
            elif isinstance(cases,dict):
                try:
                    assert isinstance(cases[well],(str,list))
                    _cases_list.extend(input_to_list(cases[well]))
                except KeyError:
                    print(f'{well} was not found in dict cases')
                    continue
                except Exception as e:
                    print(f'None value passed to well case. Error found {e}')
                    continue
            else:
                _cases_list.extend(list(self.wells[well].cashflow.keys()))

            _cases_list = [i for i in _cases_list if i in self.wells[well].cashflow.keys()]
            
            if len(_cases_list) == 0:
                print(f'No cases found in {well}')
                continue
            
            #Iterate over cases
            for case in _cases_list:
                if isinstance(cash_name,(str,list)):
                    _cash_name_list.extend(input_to_list(cash_name))
                elif isinstance(cash_name,dict):
                    try:
                        assert isinstance(cash_name[well],(str,list))
                        _cash_name_list.extend(input_to_list(cash_name[well]))
                    except KeyError:
                        print(f'{well} was not found in dict cash name')
                        continue
                    except Exception as e:
                        print(f'None value passed to well case. Error found {e}')
                        continue
                else:
                    _cash_name_list.extend(list(self.wells[well].cashflow[case].keys()))
                                           
                _cash_name_list = [i for i in _cash_name_list if i in self.wells[well].cashflow[case].keys()]

                if len(_cash_name_list) == 0:
                    print(f'No cash name found in case {case} on well {well}')
                    continue
                
                for cash_name in _cash_name_list:
                    cash_series = self.wells[well].cashflow[case][cash_name].cashflow()
                    cash_df = pd.DataFrame(cash_series.values, columns=['cashflow'], index=cash_series.index)
                    cash_df['well'] = well 
                    cash_df['case'] = case 
                    cash_df['cash_name'] = cash_name
                    cashflow_list.append(cash_df)

        if len(cashflow_list)>0:
            cashflow_df = pd.concat(cashflow_list, axis=0)
            return cashflow_df
        
    def get_fcf(self, 
        cases:str=None,
        wells:list=None, 
        income:list=['income'],
        opex:list=['var_opex','fix_opex'],
        capex:list=['capex'],
        prate=0,
        pyr=12
    ):
        assert cases is not None

        if wells is None:
            _well_list = []
            for well in self.wells:
                _well_list.append(well)
        else:
            _well_list = wells

        fcf_list =[]

        for w in _well_list:
            if self.wells[w].cashflow is None or cases not in self.wells[w].cashflow.keys():
                continue
            fcf,_ = self.wells[w].get_fcf(
                cases=cases,
                income=income, 
                opex=opex,
                capex=capex, 
            )
            fcf['well'] = w
            fcf_list.append(fcf)


        if len(fcf_list)>0:
            fcf_df = pd.concat(fcf_list,axis=0, ignore_index=False)

            spreadsheet=fcf_df.reset_index().groupby('index')[['total_income','total_opex','total_capex']].sum()

            #EBIT
            spreadsheet['net_income'] = spreadsheet['total_income'] + spreadsheet['total_opex']
          
            #Freecashflow
            spreadsheet['free_cash_flow'] = spreadsheet['net_income'] + spreadsheet['total_capex']
            spreadsheet['cum_free_cash_flow'] = spreadsheet['free_cash_flow'].cumsum()
            
            #NPV         
            prate = np.atleast_1d(prate)
            npv = {}
            for pr in prate:
                prn = perrate(pr,pyr=pyr)
                
                prate_series = pd.Series(np.full(spreadsheet.shape[0],prn), index=spreadsheet.index)
                _npv = timevalue(spreadsheet['free_cash_flow'], prate_series)
                npv.update({pr:_npv})
                
            return spreadsheet, npv

        else:
            print('No FCF Found')


    def save(self,file):
        with open(file, 'wb') as f:
            pickle.dump(self, f)
