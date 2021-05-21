import numpy as np
import math as m
import tensorflow as tf


@tf.function
def rmse(y_true, y_pred):
    y_true = tf.cast(y_true, tf.float32)
    y_pred = tf.cast(y_pred, tf.float32)
    num_y_true = tf.cast(
        tf.math.count_nonzero(~tf.math.is_nan(y_true)), tf.float32
    )
    if num_y_true > 0:
        zero_or_error = tf.where(
            tf.math.is_nan(y_true), tf.zeros_like(y_true), y_pred - y_true
        )
        sum_squared_errors = tf.reduce_sum(tf.square(zero_or_error))
        rmse_loss = tf.sqrt(sum_squared_errors / num_y_true)
    else:
        rmse_loss = 0.0
    return rmse_loss


def sample_avg_nse(y_true, y_pred):
    """
    calculate the sample averaged nse, i.e., it will calculate the nse across
    each of the samples (the 1st dimension of the arrays) and then average those
    """
    y_true = tf.cast(y_true, tf.float32)
    y_pred = tf.cast(y_pred, tf.float32)
    zero_or_error = tf.where(
        tf.math.is_nan(y_true), tf.zeros_like(y_true), y_pred - y_true
    )

    # add a small value to the deviation to prevent instability
    deviation = dev_masked(y_true) + 0.1

    numerator_samplewise = tf.reduce_sum(tf.square(zero_or_error), axis=1)
    denomin_samplewise = tf.reduce_sum(tf.square(deviation), axis=1)
    nse_samplewise = 1 - numerator_samplewise / denomin_samplewise
    nse_samplewise_avg = tf.reduce_sum(nse_samplewise) / tf.cast(
        tf.shape(y_true)[0], tf.float32
    )
    return nse_samplewise_avg


def nse(y_true, y_pred):
    y_true = tf.cast(y_true, tf.float32)
    y_pred = tf.cast(y_pred, tf.float32)
    zero_or_error = tf.where(
        tf.math.is_nan(y_true), tf.zeros_like(y_true), y_pred - y_true
    )

    deviation = dev_masked(y_true)
    numerator = tf.reduce_sum(tf.square(zero_or_error))
    denominator = tf.reduce_sum(tf.square(deviation))
    return 1 - numerator / denominator


def nnse(y_true, y_pred):
    return 1 / (2 - nse(y_true, y_pred))


def nnse_loss(y_true, y_pred):
    return 1 - nnse(y_true, y_pred)


def samplewise_nnse_loss(y_true, y_pred):
    nnse_val = 1 / (2 - sample_avg_nse(y_true, y_pred))
    return 1 - nnse_val


def nnse_masked_one_var(data, y_pred, var_idx):
    y_true, y_pred, weights = y_data_components(data, y_pred, var_idx)
    return nnse_loss(y_true, y_pred)


def nnse_one_var_samplewise(data, y_pred, var_idx):
    y_true, y_pred, weights = y_data_components(data, y_pred, var_idx)
    return samplewise_nnse_loss(y_true, y_pred)


def y_data_components(data, y_pred, var_idx):
    weights = data[:, :, -2:]
    y_true = data[:, :, :2]

    # ensure y_pred, weights, and y_true are all tensors the same data type
    y_true = tf.convert_to_tensor(y_true)
    weights = tf.convert_to_tensor(weights)
    y_true = tf.cast(y_true, y_pred.dtype)
    weights = tf.cast(weights, y_pred.dtype)

    # make all zero-weighted observations 'nan' so they don't get counted
    # at all in the loss calculation
    y_true = tf.where(weights == 0, np.nan, y_true)

    weights = weights[:, :, var_idx]
    y_true = y_true[:, :, var_idx]
    y_pred = y_pred[:, :, var_idx]
    return y_true, y_pred, weights


def rmse_masked_one_var(data, y_pred, var_idx):
    y_true, y_pred, weights = y_data_components(data, y_pred, var_idx)
    return rmse(y_true, y_pred)


def weighted_masked_rmse(lamb=0.5):
    """
    calculate a weighted, masked rmse.
    :param lamb: [float] (short for lambda). The factor that the auxiliary loss
    will be multiplied by before added to the main loss.
    """

    def rmse_masked_combined(data, y_pred):
        rmse_main = rmse_masked_one_var(data, y_pred, 0)
        rmse_aux = rmse_masked_one_var(data, y_pred, 1)
        rmse_loss = rmse_main + lamb * rmse_aux
        return rmse_loss

    return rmse_masked_combined


def mean_masked(y):
    num_vals = tf.cast(tf.math.count_nonzero(~tf.math.is_nan(y)), tf.float32)
    # get mean accounting for nans
    zero_or_val = tf.where(tf.math.is_nan(y), tf.zeros_like(y), y)
    mean = tf.reduce_sum(zero_or_val) / num_vals
    return mean


def dev_masked(y):
    mean = mean_masked(y)
    zero_or_dev = tf.where(tf.math.is_nan(y), tf.zeros_like(y), y - mean)
    return zero_or_dev


def std_masked(y):
    dev = dev_masked(y)
    num_vals = tf.cast(tf.math.count_nonzero(~tf.math.is_nan(y)), tf.float32)
    numerator = tf.reduce_sum(tf.square(dev))
    denominator = num_vals - 1
    return tf.sqrt(numerator / denominator)


def pearsons_r(y_true, y_pred):
    y_true_dev = dev_masked(y_true)
    y_pred_dev = dev_masked(y_pred)
    numerator = tf.reduce_sum(y_true_dev * y_pred_dev)
    ss_dev_true = tf.reduce_sum(tf.square(y_true_dev))
    ss_pred_true = tf.reduce_sum(tf.square(y_pred_dev))
    denominator = tf.sqrt(ss_dev_true * ss_pred_true)
    return numerator / denominator


def kge(y_true, y_pred):
    y_true = tf.cast(y_true, tf.float32)
    y_pred = tf.cast(y_pred, tf.float32)
    r = pearsons_r(y_true, y_pred)
    mean_true = mean_masked(y_true)
    mean_pred = mean_masked(y_pred)
    std_true = std_masked(y_true)
    std_pred = std_masked(y_pred)

    r_component = tf.square(r - 1)
    std_component = tf.square((std_pred / std_true) - 1)
    bias_component = tf.square((mean_pred / mean_true) - 1)
    return 1 - tf.sqrt(r_component + std_component + bias_component)


def norm_kge(y_true, y_pred):
    """
    normalized kge so it's scaled from 0 to 1
    """
    return 1 / (2 - kge(y_true, y_pred))


def kge_norm_loss(y_true, y_pred):
    """
    making it a loss, so low is good, high is bad
    """
    return 1 - norm_kge(y_true, y_pred)


def kge_loss_one_var(data, y_pred, var_idx):
    y_true, y_pred, weights = y_data_components(data, y_pred, var_idx)
    return kge_loss(y_true, y_pred)


def kge_loss(y_true, y_pred):
    return -1 * kge(y_true, y_pred)

def weighted_masked_rmse_gw(temp_index,temp_mean, temp_sd,lamb=0.5,lamb2=0, lamb3=0):
    """
    calculate a weighted, masked rmse.
    :param lamb: [float] (short for lambda). The factor that the auxiliary loss
    will be multiplied by before added to the main loss.
    """

    def rmse_masked_combined_gw(data, y_pred):
	print("data shape")
	print(data.shape)
	print("y_pred shape")
	print(y_pred.shape)
        rmse_main = rmse_masked_one_var(data, y_pred, 0)
        rmse_aux = rmse_masked_one_var(data, y_pred, 1)
        
        Ar_obs, Ar_pred, delPhi_obs, delPhi_pred = GW_loss_prep(temp_index,data, y_pred, temp_mean, temp_sd)
        rmse_Ar = rmse(Ar_obs,Ar_pred)
        rmse_delPhi = rmse(delPhi_obs,delPhi_pred)
        
      
        rmse_loss = rmse_main + lamb * rmse_aux + lamb2*rmse_Ar +lamb3*rmse_delPhi
        #return rmse_loss
        return rmse_loss
    return rmse_masked_combined_gw

def GW_loss_prep(temp_index, data, y_pred, temp_mean, temp_sd):
    #assumes that axis 0 of data and y_pred are the reaches and axis 1 are daily values
    y_true = data[:, :, 2:-2]
    y_pred_temp = y_pred[:,:,int(temp_index):(int(temp_index)+1)] #extract just the predicted temperature
    print("y_true shape")
    print(y_true.shape)
    print("y_pred_temp shape")
	print(y_pred_temp.shape)
    #unscale the predicted temps
    y_pred_temp = y_pred_temp*temp_sd+temp_mean
    
    x_lm = y_true[:,:,-2:] #extract the sin(wt) and cos(wt)
    
    #a tensor of the sin(wt) and cos(wt) for each reach x day, the 1's are for the intercept of the linear regression
    X_mat=tf.stack((tf.constant(1., shape=x_lm[:,:,0].shape), x_lm[:,:,0],x_lm[:,:,1]),axis=1)
    
    
    #getting the coefficients using a 3-d version of the normal equation:
    #https://cmdlinetips.com/2020/03/linear-regression-using-matrix-multiplication-in-python-using-numpy/
    #http://mlwiki.org/index.php/Normal_Equation
    X_mat_T = tf.transpose(X_mat,perm=(0,2,1))
    X_mat_T_dot = tf.einsum('bij,bjk->bik',X_mat_T,X_mat)#eigensums are used instead of dot products because we want the dot products of axis 1 and 2, not 0
    X_mat_inv = tf.linalg.pinv(X_mat_T_dot)
    X_mat_inv_dot = tf.einsum('bij,bjk->bik',X_mat_inv,X_mat_T)#eigensums are used instead of dot products because we want the dot products of axis 1 and 2, not 0
    a_b = tf.einsum('bij,bik->bjk',X_mat_inv_dot,y_pred_temp)#eigensums are used instead of dot products because we want the dot products of axis 1 and 2, not 0
    
    #the tensor a_b has the coefficients from the regression (reach x [[intercept],[a],[b]])
    #Aw = amplitude of the water temp sinusoid (deg C)
    Aw = tf.math.sqrt(a_b[:,1,0]**2+a_b[:,2,0]**2)
    #Phiw = phase of the water temp sinusoid (radians)
    Phiw = 3*m.pi/2-tf.math.atan(a_b[:,2,0]/a_b[:,1,0])
    
    #delPhi_pred = the difference in phase between the air and water temp sinusoids, in days
    delPhi_pred = (Phiw-y_true[:,0,2])*365/(2*m.pi)
    #Ar_pred = the ratio of the air temp and water temp amplitudes
    Ar_pred = Aw/y_true[:,0,3]
    
    return y_true[:,0,0], Ar_pred, y_true[:,0,1], delPhi_pred
