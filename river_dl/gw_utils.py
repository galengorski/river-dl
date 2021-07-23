import pandas as pd
import numpy as np
import xarray as xr
import statsmodels.api as sm
from datetime import datetime
import math
from itertools import compress, product
import matplotlib.pyplot as plt
import seaborn as sns
from copy import deepcopy

from river_dl.preproc_utils import separate_trn_tst, read_multiple_obs, convert_batch_reshape
from river_dl.evaluate import calc_metrics

def amp_phi (Date, temp, isWater=False):
    """
    calculate the annual signal properties (phase and amplitude) for a temperature times series
    :param Date: vector of dates
    :param temp: vector of temperatures
    :param isWater: boolean indicator if the temp data is water temps (versus air)
    :returns: amplitude and phase
    """
    
    # Johnson, Z.C., Johnson, B.G., Briggs, M.A., Snyder, C.D., Hitt, N.P., and Devine, W.D., 2021, Heed the data gap: Guidelines for 
    #using incomplete datasets in annual stream temperature analyses: Ecological Indicators, v. 122, p. 107229, 
    #http://www.sciencedirect.com/science/article/pii/S1470160X20311687.
    # T(t) = T_mean + a*sin(wt) + b*cos(wt)
    
    #A = amplitude of the temp sinusoid (deg C)
    #A = sqrt (a^2 + b^2)
    
    #Phi = phase of the temp sinusoid (radians)
    #Phi = (3/2)* pi - atan (b/a) - in radians
    
    #convert the date to decimal years
    date_decimal = make_decimal_date(Date)
    
    #remove water temps below 1C or above 45C to avoid complex freeze-thaw dynamics near 0 C and because >45C is likely erroneous  
    if isWater:
        temp = [x if x >=1 and x<=45 else np.nan for x in temp]
    
    x = [[math.sin(2*math.pi*j),math.cos(2*math.pi*j)] for j in date_decimal]
# this solves the regression using scikit-learn (not on the current import list), which doesn't give confidence intervals
#     model = LinearRegression().fit(list(compress(x, np.isfinite(temp))),list(compress(temp, np.isfinite(temp))))
#     amp = math.sqrt(model.coef_[0]**2+model.coef_[1]**2)
#     phi = math.asin(model.coef_[1]/amp)

#this solves the regression using stats models, which provides confidence intervals on the coefficients
    X = sm.add_constant(x)
    try:
        model = sm.OLS(temp,X, missing='drop')
        results = model.fit()
    
        confInt = np.array(results.conf_int())
      
        amp = math.sqrt(results.params[1]**2+results.params[2]**2)
        amp_low = math.sqrt(np.min(abs(confInt[1]))**2+np.min(abs(confInt[2]))**2)
        amp_high = math.sqrt(np.max(abs(confInt[1]))**2+np.max(abs(confInt[2]))**2)
    
        phi = 3*math.pi/2-math.atan(results.params[2]/results.params[1])
        phiRange = [3*math.pi/2-math.atan(confInt[2][x]/confInt[1][y]) for x in range(2) for y in range(2)]
        phi_low = np.min(phiRange)
        phi_high = np.max(phiRange)
    except:
        amp=np.nan
        phi=np.nan
        amp_low=np.nan
        amp_high=np.nan
        phi_low=np.nan
        phi_high = np.nan
    
    return amp, phi, amp_low, amp_high, phi_low, phi_high


def annual_temp_stats(thisData, water_temp_pbm_col = 'seg_tave_water_pbm', water_temp_obs_col="seg_tave_water",air_temp_col = 'seg_tave_air'):
    """
    calculate the annual signal properties (phase and amplitude) for temperature times series
    :param thisData: [xr dataset] with time series data of air and water temp for each segment
    :param water_temp_pbm_col: str with the column name of the process-based model predicted water temperatures in degrees C
    :param water_temp_obs_col: str with the column name of the observed water temperatures in degrees C
    :param air_temp_col: str with the column name of the air temperatures in degrees C
    :returns: data frame with phase and amplitude of air and observed water temp, along with the
    phase shift and amplitude ratio for each segment, "low" and "high" values are the minimum and maximum 
    property values calculated with coefficient values within the 95th percent confidence interval
    """

    air_amp=[]
    air_amp_low=[]
    air_amp_high=[]
    air_phi=[]
    air_phi_low=[]
    air_phi_high=[]
    water_amp_obs = []
    water_amp_low_obs = []
    water_amp_high_obs = []
    water_phi_obs = []
    water_phi_low_obs = []
    water_phi_high_obs = []        
    water_amp_pbm = []
    water_amp_low_pbm = []
    water_amp_high_pbm = []
    water_phi_pbm = []
    water_phi_low_pbm = []
    water_phi_high_pbm = []
    
    #get the phase and amplitude for air and water temps for each segment
    for i in range(len(thisData['seg_id_nat'])):
        thisSeg = thisData['seg_id_nat'][i].data
        #get the air temp properties
        amp, phi, amp_low, amp_high, phi_low, phi_high = amp_phi(thisData['date'].values,thisData[air_temp_col][:,i].values,isWater=False)
        air_amp.append(amp)
        air_amp_low.append(amp_low)
        air_amp_high.append(amp_high)
        air_phi.append(phi)
        air_phi_low.append(phi_low)
        air_phi_high.append(phi_high)

        #get the process-based model (pbm) water temp properties
        amp, phi, amp_low, amp_high, phi_low, phi_high = amp_phi(thisData['date'].values,thisData[water_temp_pbm_col][:,i].values,isWater=True)
        water_amp_pbm.append(amp)
        water_amp_low_pbm.append(amp_low)
        water_amp_high_pbm.append(amp_high)
        water_phi_pbm.append(phi)
        water_phi_low_pbm.append(phi_low)
        water_phi_high_pbm.append(phi_high)
        
        #get the observed water temp properties
        #ensure sufficient data
        if np.sum(np.isfinite(thisData[water_temp_obs_col][:,i].values))>(365): #this requires at least 1 yr of data
            waterDF = pd.DataFrame({'date':thisData['date'].values,'tave_water':thisData[water_temp_obs_col][:,i].values})
            #require temps > 1 and <60 C for signal analysis
            waterDF.loc[(waterDF.tave_water<1)|(waterDF.tave_water>60),"tave_water"]=np.nan
            waterDF.dropna(inplace=True)
            
            if waterDF.shape[0]<(365):
                amp = np.nan
                phi = np.nan
                amp_low = np.nan
                amp_high = np.nan
                phi_low = np.nan
                phi_high = np.nan
            else:
                ### old code that may be used again for adding additional data requirements for the temp signal analysis
                #get the longest set of temp records with no gaps >49 days
                #dateDiff = [0]
                #dateDiff.extend([int((waterDF.date.iloc[x]-waterDF.date.iloc[x-1])/np.timedelta64(1, 'D')) for x in range(1,waterDF.shape[0])])
                #waterDF['dateDiff']=dateDiff
                #if max(dateDiff)>31:
                #    waterDF['bin']=pd.cut(waterDF.date,bins=waterDF.date.loc[(waterDF.date==np.nanmin(waterDF.date))|(waterDF.dateDiff>50) | (waterDF.dateDiff==0)|(waterDF.date==np.nanmax(waterDF.date))].values, include_lowest=True, labels=False)
                #    waterSum = waterDF[['date','bin']].groupby('bin',as_index=False).count()
                #    #keep the longest series
                #    maxBin = waterSum.bin[waterSum.date==np.max(waterSum.date)].values[0]
                #    waterDF = waterDF.loc[waterDF.bin==maxBin]
                
                if waterDF.shape[0]>=(365):
                    amp, phi, amp_low, amp_high, phi_low, phi_high = amp_phi(waterDF.date.values,waterDF.tave_water.values,isWater=True)
                else:
                    amp = np.nan
                    phi = np.nan
                    amp_low = np.nan
                    amp_high = np.nan
                    phi_low = np.nan
                    phi_high = np.nan
            
        else:
            amp = np.nan
            phi = np.nan
            amp_low = np.nan
            amp_high = np.nan
            phi_low = np.nan
            phi_high = np.nan
        water_amp_obs.append(amp)
        water_amp_low_obs.append(amp_low)
        water_amp_high_obs.append(amp_high)
        water_phi_obs.append(phi)
        water_phi_low_obs.append(phi_low)
        water_phi_high_obs.append(phi_high)

    Ar_obs = [water_amp_obs[x]/air_amp[x] for x in range(len(water_amp_obs))]
    delPhi_obs = [(water_phi_obs[x]-air_phi[x])*365/(2*math.pi) for x in range(len(water_amp_obs))]
    
    Ar_low_obs = [water_amp_low_obs[x]/air_amp_high[x] for x in range(len(water_amp_obs))]
    Ar_high_obs = [water_amp_high_obs[x]/air_amp_low[x] for x in range(len(water_amp_obs))]
    
    delPhi_low_obs = [(water_phi_low_obs[x]-air_phi_high[x])*365/(2*math.pi) for x in range(len(water_amp_obs))]
    delPhi_high_obs = [(water_phi_high_obs[x]-air_phi_low[x])*365/(2*math.pi) for x in range(len(water_amp_obs))]
    
    ########################################################
    #these thresholds were set based on analysis in Hare, D.K., Helton, A.M., Johnson, Z.C., Lane, J.W., and Briggs, M.A.,
    #2021, Continental-scale analysis of shallow and deep groundwater contributions to streams: Nature Communications, 
    #v. 12, no. 1, p. 1450, https://doi.org/10.1038/s41467-021-21651-0.

    #Ar is the ratio of the annual amplitude of the stream temp and the annual amplitude of the air temp. 
    #Ar > 1 indicates that the water temperature varies more widely than the air temperature, which would not be expected and suggests a data anomaly. 
    #Therefore Ar > 1.1 is set to NA (along with the corresponding delPhi)
    #remove Ar >1.1
    delPhi_obs=[delPhi_obs[i] if Ar_obs[i] <=1.1 else np.nan for i in range(len(delPhi_obs))]
    Ar_obs = [x if x <= 1.1 else np.nan for x in Ar_obs]
    
    #delPhi is the phase difference between the air temp and the water temp.
    #delPhi < 0 indicates the water warms / cools before the air, which is unexpected and suggests a data anomaly.
    # Therefore delPhi is set to NA when it is less than -10 and to 0 when it is between -10 and 0 (allowing a buffer for imprecision in estimating
    # the delPhi). Ar is also set to NA when delPhi is less than -10.
    #remove delPhi <-10
    Ar_obs = [Ar_obs[i] if delPhi_obs[i] >=-10 else np.nan for i in range(len(Ar_obs))]
    delPhi_obs = [x if x >=-10 else np.nan for x in delPhi_obs]
    
    #reset delPhi -10 to 0
    delPhi_obs = [x if x > 0 else 0 if np.isfinite(x) else np.nan for x in delPhi_obs]
    
    
    
    Ar_pbm = [water_amp_pbm[x]/air_amp[x] for x in range(len(water_amp_pbm))]
    delPhi_pbm = [(water_phi_pbm[x]-air_phi[x])*365/(2*math.pi) for x in range(len(water_amp_pbm))]
    
    tempDF = pd.DataFrame({'seg_id_nat':thisData['seg_id_nat'].values, 'air_amp':air_amp,'air_phi':air_phi,'water_amp_obs':water_amp_obs,'water_phi_obs':water_phi_obs,'Ar_obs':Ar_obs,'delPhi_obs':delPhi_obs,'Ar_low_obs':Ar_low_obs, 'Ar_high_obs':Ar_high_obs,'delPhi_low_obs':delPhi_low_obs,'delPhi_high_obs':delPhi_high_obs,'water_amp_pbm':water_amp_pbm,'water_phi_pbm':water_phi_pbm,'Ar_pbm':Ar_pbm,'delPhi_pbm':delPhi_pbm})
    return tempDF

def prep_annual_signal_data(
    obs_temper_file,
    pretrain_file,
    io_data_file,
    train_start_date,
    train_end_date,
    val_start_date,
    val_end_date,
    test_start_date,
    test_end_date,
    gwVarList,
    out_file=None,
    air_temp_col = 'seg_tave_air',
    water_temp_pbm_col = 'seg_tave_water',
    water_temp_obs_col = 'temp_c',
    segs = None,
):
    """
    add annual air and water temp signal properties (phase and amplitude to
    the prepped dataset and save a separate GW only dataset
    :param obs_temper_file: [str] temperature observations file (csv)
    :param pretrain_file: [str] the file with the pretraining data (SNTemp data)
    :param io_data_file: [str] the prepped data file
    :param train_start_date, train_end_date, val_start_date,val_end_date,test_start_date,test_end_date: [str]
    the start and end dates of the training, validation, and testing periods
    :param gwVarList: [str] list of groundwater-relevant variables
    :param out_file: [str] file to where the values will be written
    :param water_temp_pbm_col: str with the column name of the process-based model predicted water temperatures in degrees C
    :param water_temp_obs_col: str with the column name of the observed water temperatures in degrees C
    :param air_temp_col: str with the column name of the air temperatures in degrees C
    :returns: phase and amplitude of air and observed water temp, along with the
    phase shift and amplitude ratio
    """
    
    
    #read in the SNTemp data
    ds_pre = xr.open_zarr(pretrain_file)
    
    if segs:
        ds_pre = ds_pre.loc[dict(seg_id_nat=segs)]

    #read in the observed temperature data and join to the SNTemp data
    obs = [ds_pre.sortby(["seg_id_nat","date"])]
    obs.append(xr.open_zarr(obs_temper_file).transpose())
    obs=xr.merge(obs,join="left")
    obs=obs[[air_temp_col,water_temp_pbm_col,water_temp_obs_col]]
    obs = obs.rename({water_temp_pbm_col: "seg_tave_water_pbm"})
    obs = obs.rename({water_temp_obs_col: "seg_tave_water"})

    #split into testing and training
    obs_trn, obs_val, obs_tst = separate_trn_tst(obs, train_start_date,
        train_end_date,
        val_start_date,
        val_end_date,
        test_start_date,
        test_end_date)

    #get the annual signal properties for the training, validation, and testing data
    GW_trn = annual_temp_stats(obs_trn)
    GW_tst = annual_temp_stats(obs_tst)
    GW_val = annual_temp_stats(obs_val)

    
    #scale the Ar_obs & delPhi_obs
    GW_trn_scale = deepcopy(GW_trn)
    GW_trn_scale['Ar_obs'] = (GW_trn['Ar_obs']-np.nanmean(GW_trn['Ar_obs']))/np.nanstd(GW_trn['Ar_obs'])
    GW_trn_scale['delPhi_obs'] = (GW_trn['delPhi_obs']-np.nanmean(GW_trn['delPhi_obs']))/np.nanstd(GW_trn['delPhi_obs'])
    
    #add the GW data to the y dataset
    preppedData = np.load(io_data_file)
    data = {k:v for  k, v in preppedData.items() if not k.startswith("GW")}
    data['GW_trn_reshape']=make_GW_dataset(GW_trn_scale,obs_trn,gwVarList)
    data['GW_tst_reshape']=make_GW_dataset(GW_tst,obs_tst,gwVarList)
    data['GW_val_reshape']=make_GW_dataset(GW_val,obs_val,gwVarList)
    data['GW_tst']=GW_tst
    data['GW_trn']=GW_trn
    data['GW_val']=GW_val
    data['GW_cols']=GW_trn.columns.values.astype('str')
    data['GW_mean']=np.nanmean(GW_trn[['Ar_obs','delPhi_obs']],axis=0)
    data['GW_std']=np.nanstd(GW_trn[['Ar_obs','delPhi_obs']],axis=0)
    np.savez_compressed(out_file, **data)
    
    
    #save the GW-only dataset
    #data2 = {}
    #data2['GW_tst']=GW_tst
    #data2['GW_trn']=GW_trn
    #data2['GW_val']=GW_val
    #data2['GW_cols']=GW_trn.columns.values.astype('str')
    #np.savez_compressed(out_file2, **data2)

def calc_amp_phi(thisData, water_temp_pred_col = "seg_tave_water"):
    """
    compiles temperature signal properties for predicted temperatures
    :param thisData: [dataset] dataset of predicted temperatures
    :returns: dataframe with signal properties by segment
    """
    segList = np.unique(thisData['seg_id_nat'])
    water_amp_preds = []
    water_phi_preds = []
    for thisSeg in segList:
        amp, phi, amp_low, amp_high, phi_low, phi_high = amp_phi(thisData.loc[thisData.seg_id_nat==thisSeg,"date"].values,thisData.loc[thisData.seg_id_nat==thisSeg,water_temp_pred_col],isWater=True)
        water_amp_preds.append(amp)
        water_phi_preds.append(phi)
    return pd.DataFrame({'seg_id_nat':segList,'water_amp_pred':water_amp_preds,'water_phi_pred':water_phi_preds})

def make_decimal_date(date, ref_date = "1980-10-01"):
    """
    converts a list of dates to decimal years relative to a reference date
    :param date: array or list of dates
    :param ref_date: [str] reference date, see below for details before changing it
    :returns: list of decimal dates
    """
    
    #1980-10-01 is a reference date from which the decimal dates are calculated. Changing the time of year may require changing the calculation of phi. 
    # For details of if /how the phi calculation may need to change, see Appendix A in 
    # Johnson, Z.C., Johnson, B.G., Briggs, M.A., Snyder, C.D., Hitt, N.P., and Devine, W.D., 2021, 
    # Heed the data gap: Guidelines for using incomplete datasets in annual stream temperature analyses: 
    # Ecological Indicators, v. 122, p. 107229, http://www.sciencedirect.com/science/article/pii/S1470160X20311687.
    
    decimal_date = [float(x)/365 for x in ((date-np.datetime64(ref_date))/np.timedelta64(1, 'D'))]
    
    return decimal_date
    
def merge_pred_obs(gw_obs,obs_col,pred):
    """
    merges predicted and observed temperature signal properties into one dataframe
    :param gw_obs: [dataframe] dataframe of observed annual temperature signal properties by segment
    :param obs_col: [str] relevant column in the gw_obs dataframe
    :param pred: [dataframe] predicted values by segment
    :returns: dataframe with predictions and observations
    """
    obsDF = pd.DataFrame(gw_obs[obs_col],columns=gw_obs['GW_cols'])
    obsDF = obsDF.merge(pred)
    obsDF['Ar_pred']=obsDF['water_amp_pred']/obsDF['air_amp']
    obsDF['delPhi_pred'] = (obsDF['water_phi_pred']-obsDF['air_phi'])*365/(2*math.pi)
    return obsDF

def make_GW_dataset (GW_data,x_data,varList):
    """
    prepares a GW-relevant dataset for the GW loss function that can be combined with y_true
    :param GW_data: [dataframe] dataframe of annual temperature signal properties by segment
    :param x_data: [str] observation dataset
    :param varList: [str] variables to keep in the final dataset
    :returns: GW dataset that is reshaped to match the shape of the first 2 dimensions of the y_true dataset
    """
    #make a dataframe with all combinations of segment and date and then join the annual temperature signal properties dataframe to it
    prod = pd.DataFrame(product(np.unique(GW_data.seg_id_nat),x_data['date'].values),columns=['seg_id_nat','date'])

    prod = prod.merge(GW_data)
    
    #convert the date to decimal years 
    prod['dec_date']=make_decimal_date(prod.date)
    
    #precalculate sin(wt) and cos(wt) for the regression
    prod['sin_wt']=[math.sin(2*math.pi*x) for x in prod['dec_date']]
    prod['cos_wt']=[math.cos(2*math.pi*x) for x in prod['dec_date']]
    
    #reshape the resulting dataset
    obs2 = [x_data.sortby(["seg_id_nat", "date"])]
    obs2.append(prod.set_index(['date','seg_id_nat']).to_xarray())
    GW_ds = xr.merge(obs2, join="left")
    GW_ds = GW_ds[varList]
    GW_Arr = convert_batch_reshape(GW_ds)
    
    return GW_Arr
    
def calc_pred_ann_temp(GW_data,trn_data,tst_data, val_data,trn_output, tst_output,val_output):
    """
    calculates annual temperature signal properties using predicted temperatures
    :param GW_data: file of prepped GW only data
    :param trn_data, tst_data, val_data: [str] files with predicted temperatures from the training, testing, and validation partitions (feather)
    :param trn_output, tst_output, val_output: [str] output files for the calculated metrics for the training, testing, and validation partitions(csv)
    """
    gw_obs = np.load(GW_data)
    
    trn_preds = pd.read_feather(trn_data)
    tst_preds = pd.read_feather(tst_data)
    val_preds = pd.read_feather(val_data)
    
    gw_trn = calc_amp_phi(trn_preds)
    gw_tst = calc_amp_phi(tst_preds)
    gw_val = calc_amp_phi(val_preds)
    
    gw_stats_trn = merge_pred_obs(gw_obs,'GW_trn',gw_trn)
    gw_stats_tst = merge_pred_obs(gw_obs,'GW_tst',gw_tst)
    gw_stats_val = merge_pred_obs(gw_obs,'GW_val',gw_val)
                       
    gw_stats_trn.to_csv(trn_output)
    gw_stats_tst.to_csv(tst_output)
    gw_stats_val.to_csv(val_output)
    
def calc_gw_metrics(trnFile,tstFile,valFile,outFile,figFile1, figFile2, pbm_name = "SNTemp"):
    """
    summarizeds GW metrics across all data partitions and creates summary figures
    :param trnFile,tstFile,valFile: [str] input files for the calculated metrics for the training, testing, and validation partitions(csv)
    :param outFile: output file for the summarized metrics (csv)
    :param figFile1, figFile2: output files for the summary scatterplot and boxplot figures
    """
    trnDF = pd.read_csv(trnFile)
    tstDF = pd.read_csv(tstFile)
    valDF = pd.read_csv(valFile)
    
    resultsDF = 0
    for i in range(3):
        if i==0:
            thisData=trnDF
            partition="trn"
        elif i==1:
            thisData = tstDF
            partition="tst"
        elif i==2:
            thisData = valDF
            partition="val"
        for thisVar in ['Ar','delPhi']:
            print(thisVar)
            tempDF = pd.DataFrame(calc_metrics(thisData[["{}_obs".format(thisVar),"{}_pred".format(thisVar)]].rename(columns={"{}_obs".format(thisVar):"obs","{}_pred".format(thisVar):"pred"}))).T
            tempDF['variable']=thisVar
            tempDF['partition']=partition
            tempDF['model']='RGCN'

            if type(resultsDF)==int:
                resultsDF = tempDF
            else:
                resultsDF = resultsDF.append(tempDF,ignore_index=True)
                
            tempDF = pd.DataFrame(calc_metrics(thisData[["{}_obs".format(thisVar),"{}_pbm".format(thisVar)]].rename(columns={"{}_obs".format(thisVar):"obs","{}_pbm".format(thisVar):"pred"}))).T
            tempDF['variable']=thisVar
            tempDF['partition']=partition
            tempDF['model']=pbm_name
            resultsDF = resultsDF.append(tempDF,ignore_index=True)
                
    resultsDF.to_csv(outFile,header=True, index=False)
    
    fig = plt.figure(figsize=(15, 15))
    partDict = {'Training':trnDF,'Testing':tstDF,'Validation':valDF}
    metricLst = ['Ar','delPhi']
    thisFig = 0
    for thisPart in partDict.keys():
            thisData = partDict[thisPart]
            thisData['group']="Atmosphere"
            thisData.loc[thisData.delPhi_obs>=10,"group"]="Shallow"
            thisData.loc[(thisData.delPhi_obs<=10) & (thisData.Ar_obs<0.65),"group"]="Deep"

            for thisMetric in metricLst:
                thisFig = thisFig + 1
                ax = fig.add_subplot(len(partDict), len(metricLst), thisFig, aspect='equal')
                ax.set_title('{}, {}'.format(thisMetric, thisPart))
                ax.axline((np.nanmean(thisData['{}_pred'.format(thisMetric)]),np.nanmean(thisData['{}_pred'.format(thisMetric)])), slope=1.0,linewidth=1, color='black', label="1 to 1 line")
                colorDict = {"Atmosphere":"red","Shallow":"green","Deep":"blue"}
                for x in range(len(thisData['{}_obs'.format(thisMetric)])):
                    thisColor = colorDict[thisData.group[x]]
                    ax.plot([thisData['{}_obs'.format(thisMetric+"_low")][x],thisData['{}_obs'.format(thisMetric+"_high")][x]],[thisData['{}_pred'.format(thisMetric)][x],thisData['{}_pred'.format(thisMetric)][x]], color=thisColor)
#                ax.scatter(x=thisData['{}_obs'.format(thisMetric)],y=thisData['{}_pred'.format(thisMetric)],label="RGCN",color="blue")
                for thisGroup in np.unique(thisData['group']):
                    thisColor = colorDict[thisGroup]
                    ax.scatter(x=thisData.loc[thisData.group==thisGroup,'{}_obs'.format(thisMetric)],y=thisData.loc[thisData.group==thisGroup,'{}_pred'.format(thisMetric)],label="RGCN - %s"%thisGroup,color=thisColor)
                
#                ax.scatter(x=thisData['{}_obs'.format(thisMetric)],y=thisData['{}_sntemp'.format(thisMetric)],label="SNTEMP",color="red")
                for i, label in enumerate(thisData.seg_id_nat):
                    ax.annotate(int(label), (thisData['{}_obs'.format(thisMetric)][i],thisData['{}_pred'.format(thisMetric)][i]))
                if thisFig==1:
                          ax.legend()
                ax.set_xlabel("Observed")
                ax.set_ylabel("Predicted")

    plt.savefig(figFile1)
    
    fig = plt.figure(figsize=(15, 15))
    partDict = {'Training':trnDF,'Testing':tstDF,'Validation':valDF}
    metricLst = ['Ar','delPhi']
    thisFig = 0
    for thisPart in partDict.keys():
            thisData = partDict[thisPart]
            for thisMetric in metricLst:
                thisFig = thisFig + 1
                colsToPlot = ['{}_obs'.format(thisMetric),'{}_pbm'.format(thisMetric),'{}_pred'.format(thisMetric)]
                nObs =["n: " + str(np.sum(np.isfinite(thisData[thisCol].values))) for thisCol in colsToPlot]
                ax = fig.add_subplot(len(partDict), len(metricLst), thisFig)
                ax.set_title('{}, {}'.format(thisMetric, thisPart))
                ax=sns.boxplot(data=thisData[colsToPlot])
                # Add it to the plot
                pos = range(len(nObs))
                for tick,label in zip(pos,ax.get_xticklabels()):
                    ax.text(pos[tick],
                            np.nanmin(thisData[colsToPlot].values)-0.1*(np.nanmax(thisData[colsToPlot].values)-np.nanmin(thisData[colsToPlot].values)),
                            nObs[tick],
                            horizontalalignment='center',
                            weight='semibold')
                ax.set_ylim(np.nanmin(thisData[colsToPlot].values)-0.2*(np.nanmax(thisData[colsToPlot].values)-np.nanmin(thisData[colsToPlot].values)),np.nanmax(thisData[colsToPlot].values))

    plt.savefig(figFile2)
    