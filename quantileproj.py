# -*- coding: utf-8 -*-
"""
Quantiles Local Projections Wrapper
rlafarguette@imf.org
Time-stamp: "2020-08-30 13:23:30 Romain"
"""

###############################################################################
#%% Import
###############################################################################
# Base
import pandas as pd                                     # Dataframes
import numpy as np                                      # Numeric tools

import statsmodels as sm                                # Statistical models
import statsmodels.formula.api as smf                   # Formulas

from collections import namedtuple                      # High perf container

# Plotting packages
import matplotlib.pyplot as plt
import seaborn as sns

# Warnings management
# With many quantile regressions, the convergence warnings are overwhelming
from  warnings import simplefilter                       # Filter warnings

from statsmodels.tools.sm_exceptions import (ConvergenceWarning,
                                             IterationLimitWarning)
simplefilter("ignore", category=ConvergenceWarning)
simplefilter("ignore", category=IterationLimitWarning)

# Specific warnings in quantile regressions 
np.seterr(divide='ignore', invalid='ignore')

###############################################################################
#%% Ancillary functions
###############################################################################
def zscore(series):
    """ Zscore a pandas series """
    return((series - series.mean())/series.std(ddof=0))

###############################################################################
#%% Parent class for the quantile projections
###############################################################################
class QuantileProj(object):
    """ 
    Specify a conditional quantile regression model

    Inputs
    ------
    depvar: string, 
       dependent variable 

    indvar_l: list
       list of independent variables. Intercept in included by default

    data: pd.DataFrame
       data to train the model on    

    """
    __description = "Quantile regressions wrapper"
    __author = "Romain Lafarguette, IMF, https://github.com/romainlafarguette"

    # Initializer
    def __init__(self, depvar, indvar_l, data,
                 horizon_l=[0], ):

        # Unit tests (defined at the bottom of the class)
        self.__quantilemod_unittest(depvar, indvar_l, data, horizon_l)
    
        # Attributes
        self.depvar = depvar # Dependent variable
        self.indvar_l = indvar_l
        self.horizon_l = sorted(horizon_l)

        # Data cleaning for the regression (no missing in dep and regressors)
        self.data = data[[self.depvar] + self.indvar_l].dropna().copy()
        
        # Print a warning in case of missing observations
        mn = data.shape[0] - self.data.shape[0]
        if mn > 0 : print(f'{mn:.0f} missing obs on depvar and indvar')
        
        # Create the forward variables based on the list of horizons
        self.depvar_l = list()
        for h in horizon_l:
            if h == 0:
                self.depvar_l.append(self.depvar)
            if h > 0:
                fname = f'{depvar}_fwd_{h}'
                self.depvar_l.append(fname)
                self.data[fname] = self.data[self.depvar].shift(-h)
                
        # Formula regressions for each dependent variable
        self.regform_d = {dv: self.__reg_formula(dv) for dv in self.depvar_l}
        
        # Run in parallel a zscore version of the data
        self.zdata = self.data.apply(zscore, axis=1).copy()

        
    # Class-methods (methods which returns a class defined below)    
    def fit(self, quantile_l=[0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95],
            alpha=0.1):
        """ Fit the quantile regressions for each quantile, horizon """
        return(QuantileFit(self, quantile_l, alpha))
                    
    # Methods
    def __reg_formula(self, ldepvar):
        """ Generate the specification for the quantile regressions """
        # NB: I prefer formulas as the sm output is clearer
        regressors_l = self.indvar_l[0]
        for v in self.indvar_l[1:]: regressors_l += f' + {v}'
        reg_f = f'{ldepvar} ~ {regressors_l}'
        return(reg_f)
    
    def __quantilemod_unittest(self, depvar, indvar_l, data, horizon_l):
        """ Unit testing on the inputs """
        # Test for types
        assert isinstance(depvar, str), 'depvar should be string'
        assert isinstance(indvar_l, list), 'indvars should be in list'
        assert isinstance(data, pd.DataFrame), 'data should be pandas frame'
        assert isinstance(horizon_l, list), 'horizons should be in list'

        # Types and boundaries
        for var in indvar_l:
            assert isinstance(var, str), 'each indvar should be string'
                    
        for horizon in horizon_l:
            assert isinstance(horizon, int), 'horizons should be integer'
            
        # Test for consistency
        mv_l = [x for x in [depvar] + indvar_l if x not in data.columns]
        assert len(mv_l)==0, 'f{mv_l} are not in data columns'


###############################################################################
#%% Class for the quantile fit
###############################################################################
class QuantileFit(object): # Fit class for the QuantileProj class

    """ 
    Fit a the quantile regressions

    Inputs
    ------
    quantile_l: list, default [0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95]
       List of quantiles to fit the regressions upon
    
    alpha: float, default 0.05
       Level of confidence for the asymptotic test
              
    """

    # Import from QuantileProj class
    def __init__(self, QuantileProj, quantile_l, alpha): 
        self.__dict__.update(QuantileProj.__dict__) # Pass all attributes 
        self.__quantilefit_unittest(quantile_l, alpha) # Unit tests input

        # Attributes
        self.quantile_l = sorted(quantile_l)
        self.alpha = alpha

        self.qfit_l = self.__qfit_l() # Return the fit of the qreg
        self.coeffs = self.__coeffs() # Very important: all the coefficients
                              
    def __qfit_l(self): 
        """ Fit a quantile regression at every quantile and horizon """

        # Prepare a container for each individual fit (convenient later)
        QFit =  namedtuple('Qfit', ['depvar', 'horizon', 'tau', 'qfit'])
        
        qfit_l = list() # Container
        
        for h, depvar in zip(self.horizon_l, self.depvar_l): 
            reg_f = self.regform_d[depvar] # Formula
                
            for tau in self.quantile_l: # For every tau

                # Estimate the quantile regression
                p = {'q':tau, 'maxiter':1000, 'p_tol':1e-05}
                qfit = smf.quantreg(formula=reg_f, data=self.data).fit(**p)

                # Package it into a container
                nt = {'depvar':depvar, 'horizon':h, 'tau':tau, 'qfit':qfit}
                qfit_l.append(QFit(**nt))
                
        print(f'{len(qfit_l)} quantile regressions estimated '
              f'for {len(self.horizon_l)} horizons '
              f'and {len(self.quantile_l)} quantiles')
        
        return(qfit_l)


    # Class-methods (methods which returns a class defined below)    
    def proj(self, cond_vector):
        """ Project quantiles based on a conditioning vector """
        return(QuantileProjection(self, cond_vector))

    
    def __coeffs(self):
        """ Create the frame of coefficients from all the quantile fit """

        depvar_frames_l = list() # Container        
        for qf in self.qfit_l:
            qfit = qf.qfit
            stats = [qfit.params, qfit.tvalues, qfit.pvalues,
                     qfit.conf_int(alpha=self.alpha)]
            
            stats_names = ['coeff', 'tval', 'pval', 'lower_ci', 'upper_ci']

            # Package it into a small dataframe
            dp = pd.concat(stats, axis=1); dp.columns = stats_names

            # Add information
            dp['pseudo_r2'] = qfit.prsquared
            dp.insert(0, 'tau', qf.tau)
            dp.insert(1, 'horizon', qf.horizon)

            # Store it
            depvar_frames_l.append(dp)

        # Concatenate all the frames to have a summary coefficients frame
        coeffs = pd.concat(depvar_frames_l)
        return(coeffs)


    # Unit tests
    def __quantilefit_unittest(self, quantile_l, alpha):
        """ Unit testing on the inputs """
        # Test for types
        assert isinstance(quantile_l, list), 'quantiles should be in list'

        # Test boundaries
        assert (0 < alpha < 1), 'level of confidence should be in (0,1)'
        for quantile in quantile_l:
            assert (0 < quantile < 1), 'quantile should be in (0,1)'

    

###############################################################################
#%% Projection class for the quantile fit class
###############################################################################
class QuantileProjection(object): # Projection class for the fit class

    """ 
    Project for a given conditioning vector

    Inputs
    ------
    cond_vector: Conditioning vector
                  
    """


    # Import from QuantileProj class
    def __init__(self, QuantileFit, cond_frame):
        self.__dict__.update(QuantileFit.__dict__) # Pass all attributes      
        self.__quantileproj_unittest(cond_frame) # Unit tests input
        
        # Attributes
        self.cond_frame = cond_frame

        self.proj_condquant = self.__proj_cond_quant()


    def __proj_cond_quant(self):
        """ Project the conditional quantiles """
        
        dc_l = list() # Container
        for qf in self.qfit_l:
            qfit = qf.qfit
            dc = qfit.get_prediction(exog=self.cond_frame).summary_frame()
            dc.columns = ['conditional_quantile_' + x for x in dc.columns]
            dc = dc.set_index(self.cond_frame.index)

            # Add extra information
            dc.insert(0, 'tau', qf.tau)
            dc.insert(1, 'horizon', qf.horizon)

            dc_l.append(dc) # Append to the container

        dcq = pd.concat(dc_l)
        return(dcq)
            

        

        
    # Unit tests
    def __quantileproj_unittest(self, cond_frame):
        """ Unit testing for the projection class """

        # Type testing
        c = isinstance(cond_frame, pd.DataFrame)
        assert c, 'cond_frame should be a pd.DataFrame with var in columns'

        # Test if the conditioning vector contains the independent variables
        mv_l = [x for x in self.indvar_l if x not in cond_frame.columns]
        assert len(mv_l)==0, f'{mv_l} not in conditioning frame columns'

        




    
###############################################################################
#%% Plot class for the quantile fit
###############################################################################


    
    #     # From class methods (see below)
    #     self.qfit_dict = self.__qfit_dict()
    #     self.mfit = self.__mfit()
    #     self.coeff = self.__coeff()
    #     self.mat_coeff = self.__mat_coeff()
        
    #     # Conditional quantiles: use as predictors the historical data
    #     # In-sample prediction, can be customized to fit counterfactual shocks
    #     self.cond_quant = self.cond_quantiles(predictors=self.pred_data)
        

    # def __qfit_dict(self): 
    #     """ Estimate the quantile fit for every quantile """
    #     qfit_dict = dict()
    #     for tau in self.quantile_list:
    #         reg_f = self.reg_formula
    #         qfit = smf.quantreg(formula=reg_f,data=self.data).fit(q=tau,
    #                                                               maxiter=2000,
    #                                                               p_tol=1e-05)
    #         qfit_dict[tau] = qfit
    #     return(qfit_dict)

    # def __mfit(self): 
    #     """ Estimate the OLS fit for every quantile """
    #     mfit = smf.ols(self.reg_formula, data=self.data).fit()
    #     return(mfit)
    
    # def __coeff(self):
    #     """ Extract the parameters and package them into pandas dataframe """
    #     params = pd.DataFrame()
    #     for tau in self.quantile_list:
    #         qfit = self.qfit_dict[tau]
    #         stats = [qfit.params, qfit.pvalues, qfit.conf_int(alpha=self.alpha)]
    #         stats_names = ['coeff', 'pval', 'lower', 'upper']
    #         dp = pd.concat(stats, axis=1); dp.columns = stats_names
    #         dp.insert(0, 'tau', qfit.q) # Insert as a first column
    #         dp['R2_in_sample'] = qfit.prsquared
            
    #         # Add the scaling information
    #         dp.loc[:,'normalized'] = self.scaling
    #         params = params.append(dp)
        
    #     # For information, coeffs from an OLS regression (conditional mean)
    #     mfit = self.mfit
    #     stats = [mfit.params, mfit.pvalues, mfit.conf_int(alpha=self.alpha)]
    #     stats_names = ['coeff', 'pval', 'lower', 'upper']
    #     dmp = pd.concat(stats, axis=1); dmp.columns = stats_names
    #     dmp.insert(0, 'tau', 'mean') # Insert as a first column
    #     dmp['R2_in_sample'] = mfit.rsquared
    #     #dmp = dmp.loc[dmp.index != 'Intercept',:].copy()
    #     ## Add the scaling information
    #     dmp.loc[:,'normalized'] = self.scaling
    #     coeff = pd.concat([params, dmp], axis='index')
        
    #     ## Return the full frame
    #     return(coeff)

    # def __mat_coeff(self):
    #     """ Return the matrix of coefficients, ready for projections  """
    #     vars_l = ['Intercept'] + self.regressors

    #     # Prepare the container
    #     mat_coeff = pd.DataFrame(index=self.quantile_list, columns=vars_l)
    #     mat_coeff.index.name = 'tau'

    #     # Sort it
    #     for q in mat_coeff.index:
    #         for v in mat_coeff.columns:
    #             cond = (self.coeff.index==v) & (self.coeff.tau==q)
    #             mat_coeff.loc[q,v] = float(self.coeff.loc[cond, 'coeff'])

    #     return(mat_coeff)
    
    # def cond_quantiles(self, predictors):
    #     """ 
    #     Estimate the conditional quantiles in sample 
    #     - Predictors have to be a pandas dataframe with regressors as columns
    #     """
    #     cond_quantiles = pd.DataFrame()

    #     # Clean the frame, to make sure the index will match
    #     df_pred = predictors.dropna(subset=self.regressors).copy() 
        
    #     for tau in self.quantile_list:
    #         qfit = self.qfit_dict[tau]
    #         # Run the prediction over a predictors frame     
    #         dc = qfit.get_prediction(exog=df_pred).summary_frame()
    #         dc.columns = ['conditional_quantile_' + x for x in dc.columns]
    #         dc = dc.set_index(df_pred.index)
            
    #         ## Insert extra information
    #         dc.insert(0, 'tau', tau)
    #         dc.insert(1, 'realized_value', df_pred.loc[:, self.depvar])    
    #         cond_quantiles = cond_quantiles.append(dc)
                        
    #     ## Add the conditional mean
    #     dm = self.mfit.get_prediction(exog=df_pred).summary_frame()
    #     dm.columns = ['conditional_quantile_' + x for x in dm.columns]
    #     dm = dm.set_index(df_pred.index)
        
    #     # Insert extra information in the frame
    #     dm.insert(0, 'tau', 'mean')
    #     dm.insert(1, 'realized_value', df_pred.loc[:, self.depvar])
        
    #     ## Concatenate both frames
    #     cq = pd.concat([cond_quantiles, dm])

    #     return(cq)

    
    # def plot_coeffs(self, title=None, num_cols=3, 
    #                 hspace=0.4, wspace=0.2,
    #                 label_d={},
    #                 fig_height=25, fig_width=15, **kwds):
    #     """ 
    #     Plot the coefficients with confidence interval and R2 

    #     Parameters
    #     -----------        
    #     title: str, default 'Quantile Coefficients and Pseudo R2' 
    #       Sup title of the plot

    #     num_cols: int, default 3
    #       Number of columns, number of rows adjusts automatically

    #     fontscale: float, default 2
    #       Increase the font in the chart (sns.style option)

    #     hspace, wspace: float between 0 and 1, default 0.4 and 0.2
    #       Increase or reduce space between subplots (horizontal, vertical)

    #     label_d: dict, default empty
    #       Label dictionary to replace the subplots caption selectively

    #     """        
    #     # List of regressors
    #     var_l = ['Intercept'] + self.regressors
    #     total_plots = len(var_l) + 1 # add R2 square 

    #     # Compute the number of rows required
    #     num_rows = total_plots // num_cols

    #     if total_plots % num_cols >0:
    #         num_rows += 1 # Add one row if residuals charts
                
    #     # Line plot
    #     dc = self.coeff.loc[self.coeff.tau != 'mean', :].copy()

    #     # Create the main figure
    #     fig, axs = plt.subplots(nrows=num_rows, ncols=num_cols)

    #     axs = axs.ravel() # Very helpful !!

    #     # In case, customize the labels for the plots
    #     label_l = [None] * len(var_l)
        
    #     # Replace the values in list with labels_d
    #     for idx, var in enumerate(var_l):
    #         if var in label_d.keys():
    #             label_l[idx] = label_d[var]
    #         else:
    #             label_l[idx] = var
                               
    #     # Add every single subplot to the figure with a for loop
    #     for i, var in enumerate(var_l):
            
    #       # Select the data 
    #       dcv = dc.loc[var, :].sort_values(by='tau')
    #       dcv['tau'] = 100*dcv['tau'].copy() # For readibility
          
    #       # Main frame
    #       axs[i].plot(dcv.tau, dcv.coeff, lw=3, color='navy')
    #       axs[i].plot(dcv.tau, dcv.upper, ls='--', color='blue')
    #       axs[i].plot(dcv.tau, dcv.lower, ls='--', color='blue')

    #       # Fill in-between
    #       x = [float(x) for x in dcv.tau.values]
    #       u = [float(x) for x in dcv.lower.values]
    #       l = [float(x) for x in dcv.upper.values]

    #       axs[i].fill_between(x, u, l, facecolor='blue', alpha=0.05)

    #       # Hline
    #       axs[i].axhline(y=0, color='black', lw=0.8)

    #       # Caption
    #       axs[i].set_title(f'{label_l[i]}', y=1.02)

    #     # R2 plot
    #     dr2 = dc.loc['Intercept', :].sort_values(by='tau').copy()
    #     axs[len(var_l)].plot(100*dr2['tau'], dr2['R2_in_sample'].values,
    #                          lw=3, color='firebrick')
    #     axs[len(var_l)].set_title('Pseudo R2', y=1.02)
          
    #     # Remove extra charts
    #     for i in range(len(var_l) + 1, len(axs)): 
    #         axs[i].set_visible(False) # to remove last plot

    #     if title: fig.suptitle(title, y=1.02)

    #     plt.subplots_adjust(hspace=hspace, wspace=wspace)

    #     # Layout
    #     fig.set_size_inches(fig_height, fig_width)
    #     fig.tight_layout()
        
    #     # Return both
    #     return(fig)
        
