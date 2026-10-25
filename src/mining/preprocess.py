import numpy as np
from sklearn.base import BaseEstimator,TransformerMixin
from sklearn.preprocessing import StandardScaler
from sklearn.utils.validation import check_is_fitted


class RFMPreprocessor(TransformerMixin,BaseEstimator):
    def __init__(self,lower_quantile=.01,upper_quantile=.99):
        self.lower_quantile=lower_quantile;self.upper_quantile=upper_quantile
    def _array(self,X):
        data=np.asarray(X,dtype=np.float64)
        if data.ndim!=2 or data.shape[1]!=3 or not np.isfinite(data).all():raise ValueError('RFM must be a finite N by 3 matrix')
        if (data[:,0]<0).any() or (data[:,1]<1).any() or (data[:,2]<=0).any():raise ValueError('Invalid RFM feature domain')
        return data
    def fit(self,X,y=None):
        data=self._array(X)
        if not 0<=self.lower_quantile<self.upper_quantile<=1:raise ValueError('Invalid clipping quantiles')
        self.lower_=np.quantile(data,self.lower_quantile,axis=0)
        self.upper_=np.quantile(data,self.upper_quantile,axis=0)
        self.scaler_=StandardScaler().fit(np.log1p(np.clip(data,self.lower_,self.upper_)))
        self.n_features_in_=3;self.fit_rows_=len(data)
        return self
    def transform(self,X):
        check_is_fitted(self,['lower_','upper_','scaler_'])
        return self.scaler_.transform(np.log1p(np.clip(self._array(X),self.lower_,self.upper_)))
