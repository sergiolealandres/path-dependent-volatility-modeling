import matplotlib.pyplot as plt
from collections.abc import Iterable
from collections import OrderedDict
from scipy.optimize import least_squares
from sklearn.metrics import r2_score, mean_squared_error
from scipy.optimize import minimize
from aux_files.utils import *


def deriv_alpha_shift_power_law(t, alpha, delta):
    """
    computes dR/d{alpha} for the time-shifted power-law kernel
    :param t: np.array
    :param alpha: float
    :param delta: float
    :return:
    """
    return - np.log(t + delta) * shifted_power_law(t, alpha, delta)


def deriv_delta_shift_power_law(t, alpha, delta):
    """
    compute dR/d{delta} for the time-shifted power-law kernel
    :param t: np.array
    :param alpha: float
    :param delta: float
    :return:
    """
    return - alpha / (t + delta) * shifted_power_law(t, alpha, delta)


def split_parameters(parameters, setting):
    n_alphas = len(setting)
    deltas = parameters[-n_alphas:]
    alphas = parameters[-2 * n_alphas:-n_alphas]
    betas = parameters[1:-2 * n_alphas]
    intercept = parameters[0]
    return intercept, betas, alphas, deltas


def compute_features_tspl(returns, setting, splitted_parameters):
    intercept, betas, alphas, others = splitted_parameters  # others is either deltas or kappas
    # assert len(splitted_parameters[0]) == len(setting) and len(splitted_parameters[1]) == len(setting)
    features = OrderedDict()
    for k, key in enumerate(setting):
        i, js = key
        features[i] = {j: compute_kernel_weighted_sum(x=returns, params=[alphas[k], others[k]],
                                                      func_power_law=shifted_power_law, transform=power_to(i),
                                                      result_transform=power_to(j)) for j in js}
    return features


def optimal_parameters_from_exponentials_tspl(X, y, p, setting, delta_value, plot=False, alpha=0):
    """
    Do a Lasso Regression on different EWMA's of the return, then find the kernel that best fits the resulting kernel
    :param X: pd.Dataframe, dataframe of returns
    :param y: np.array, target volatilties
    :param p: int. (see find_optimal_paramteters)
    :param setting: list. (see find_optimal_parameters)
    :param delta_value: None
    :param plot: if display the resulting sum of EWMA kernel and the fitted powerlaw
    :return:
    """
    x = X.iloc[:, 0]
    spans = np.array([10, 20, 120, 250])
    init_betas = []
    init_alphas = []
    init_others = []
    fixed_delta = delta_value is not None
    if fixed_delta:
        def power_law_with_coef(t, beta, alpha):
            return beta * shifted_power_law(t, alpha, delta_value)
    else:
        def power_law_with_coef(t, beta, alpha, other):
            return beta * shifted_power_law(t, alpha, other)
    for i, j0 in setting:
        j = min(j0)
        ewms = {span: pd.Series.ewm(power_to(i)(x), span=span).mean() for span in spans}
        X_ewm = pd.DataFrame.from_dict(ewms, orient='columns')
        reg = RidgeCV()
        reg.fit(X_ewm, power_to(p / j)(y))
        coef = reg.coef_
        alphas = 2 / (1 + spans)

        timestamps = np.arange(max(spans))
        exp_kernel = (coef * alphas * (1 - alphas) ** timestamps.reshape(-1, 1)).sum(axis=1)
        exp_kernel /= exp_kernel.sum()
        try:
            opt_coef, _ = curve_fit(power_law_with_coef, timestamps * dt, exp_kernel, maxfev=4000)
        except RuntimeError:
            opt_coef = np.array([1, 1, 10 * dt])
        if plot:
            pred_pl = power_law_with_coef(timestamps * dt, *opt_coef)
            plt.plot(timestamps * dt, pred_pl, label='best_fit', linestyle='--')
            plt.plot(timestamps * dt, exp_kernel, label='exp_kernel', alpha=0.5)
            plt.legend()
            plt.show()
        init_betas.extend([1] * len(j0))
        # init_betas.extend([power_to(l)(opt_coef[0]) for l in j0])
        init_alphas.append(opt_coef[1])
        if not fixed_delta:
            init_others.append(opt_coef[2])
        else:
            init_others.append(delta_value)
    parameters = np.concatenate(([0], init_betas, init_alphas, init_others))
    betas = fit_betas_tspl(parameters, X_train=X, y_train=y, setting=setting)
    return np.concatenate([betas, init_alphas, init_others])


def linear_of_kernels(returns, setting, parameters, return_features=False):
    """
    Do the prediction. Compute the linear function of the kernel weighted averages of transformed returns
    :param returns: np.array
    :param setting: list
    :param parameters: list of parameters (alpha, delta, betas)
    :param return_features: bool. If True, return the features along with the predictions
    :return: np.array of predictions
    """
    splitted_parameters = split_parameters(parameters=parameters, setting=setting)
    features = compute_features_tspl(returns=returns, setting=setting, splitted_parameters=splitted_parameters)
    ans = splitted_parameters[0]  # intercept
    iterator = 0  # iterates over betas
    for k in range(len(setting)):
        i, js = setting[k]
        for j in js:
            ans += splitted_parameters[1][iterator] * features[i][j]
            iterator += 1

    if return_features:
        return features, ans
    return ans

def ordered_dict_to_dataframe(train_features, test_features, setting):
    features = {}
    for (i, j_s) in setting:
        for j in j_s:
            if j == 1:
                var_name = f'R_{i}'
            else:
                var_name = f'R_{i}^{j}'
            features[var_name] = pd.concat([train_features[i][j], test_features[i][j]])
    return pd.DataFrame(features).sort_index()


def fit_betas_tspl(parameters, X_train, y_train, setting):
    reg = LinearRegression()
    train_features, _ = linear_of_kernels(returns=X_train, setting=setting, parameters=parameters, return_features=True)
    X_for_reg = []
    for key in train_features:
        X_for_reg.extend((list(train_features[key].values())))
    X_for_reg = np.array(X_for_reg).T
    reg.fit(X_for_reg, y_train)
    betas = np.concatenate([[reg.intercept_], reg.coef_])
    return betas


def find_optimal_parameters_tspl(vol, index, p=1, setting=((1, 1), (2, 1/2)), optimize_delta=True, delta_value=None,
                                 train_start_date=train_start_date, test_start_date=test_start_date,
                                 test_end_date=test_end_date, max_delta=1000, fixed_initial=False, use_jacob=True,
                                 init_parameters=None, lambda_reg=0):
    """
    Computes the optimal parameters to linearly estimate vol^p using the previous returns of index.
    :param vol: pd.Series of historical market prices of volatility index or realized vol
    :param index: pd.Series of historical market prices of index
    :param p: int (usually 1 or 2). Target of the prediction of vol^p
    :param setting: list of tuples. Each tuple is either a (i,j) or (i, (j1, dots, jk)).
    This means that each R_i^{j_l} is a feature of the regression, where R_i= \sum_t K(t) r_t^i
    :param optimize_delta: bool. Default True, If delta should be optimized or be fixed. It is better to optimize
    :param delta_value: float. Fixed value of delta
    :param train_start_date: datetime. Default May 15 2012. When to start the train dataset
    :param test_start_date: datetime. Default Jan 01 2019. When to start the test dataset
    :param test_end_date: datetime. Default May 15 2022. When to end the test dataset
    :param max_delta: int, default 1000. Number of days used to compute the past returns for each day
    :param fixed_initial: bool. If True, uses the initial parameters given in init_parameters
    :param use_jacob: bool If True, uses the analytical jacobian. Otherwise, it is estimated by the function.
    :param init_parameters: array. Initial parameters to provide if fixed initial is True
    :return: dictionary containing the solution from the scipy optimization, the optimal parameters, the features on the train and test set,
    the train and test r2 and RMSE, the prediction on the train and test set
    """
    if optimize_delta:
        delta_value = None
    setting = [(i, p if isinstance(p, Iterable) else (p,)) for i, p in setting]  # turn the single values into tuples

    df = dataframe_of_returns(index=index, vol=vol, max_delta=max_delta)
    # Remove NaNs on volatility (happens for vstoxx for some reason)

    train_data, test_data = split_data(df, train_start_date=train_start_date, test_start_date=test_start_date,
                                       test_end_date=test_end_date)
    train_data.dropna(inplace=True)
    test_data.dropna(inplace=True)

    cols = [f'r_(t-{lag})' for lag in range(max_delta)]
    X_train = train_data.loc[:, cols]
    X_test = test_data.loc[:, cols]
    vol_train = train_data['vol']
    vol_test = test_data['vol']
    target_transform = lambda x: power_to(p)(x)
    inv_target_transform = lambda x: power_to(1 / p)(x)

    y_train = target_transform(vol_train)
    y_train = y_train
    y_test = target_transform(vol_test)

    def residuals(parameters):
        # return - y_train + linear_of_kernels(returns=X_train, setting=setting, parameters=parameters,
        #                                      func_power_law=func_power_law)
        pred = linear_of_kernels(returns=X_train, setting=setting, parameters=parameters)
        return - y_train + pred

    def jacobian(parameters):
        train_features, pred_train = linear_of_kernels(returns=X_train, setting=setting, parameters=parameters,
                                                       return_features=True)
        # train_features containts the R_i^j
        splitted_parameters = split_parameters(parameters=parameters, setting=setting)
        intercept, betas, alphas, others = splitted_parameters  # others is either deltas or kappas

        jacob = np.zeros((len(parameters), len(y_train)))
        jacob[0] = 1  # For the intercept

        # df/dbeta
        iter = 1
        for i, ks in setting:
            for j in ks:
                jacob[iter] = train_features[i][j]
                iter += 1

        alpha_jac = np.zeros((n_alphas, len(y_train)))
        delta_jac = np.zeros((n_alphas, len(y_train)))
        sub_iter = 0  # iterates on the betas
        for iter, (i, ks) in enumerate(setting):
            R_i = power_to(1 / ks[0])(train_features[i][ks[0]])
            dR_i_dalpha = compute_kernel_weighted_sum(x=X_train, params=[alphas[iter], others[iter]],
                                                      func_power_law=deriv_alpha_shift_power_law, transform=power_to(i),
                                                      result_transform=identity)
            dR_i_ddelta = compute_kernel_weighted_sum(x=X_train, params=[alphas[iter], others[iter]],
                                                      func_power_law=deriv_delta_shift_power_law, transform=power_to(i),
                                                      result_transform=identity)
            coeff = np.full_like(y_train, 0)
            for j in ks:
                coeff += j * betas[sub_iter] * power_to(j - 1)(R_i)
                sub_iter += 1
            alpha_jac[iter] = coeff * dR_i_dalpha
            delta_jac[iter] = coeff * dR_i_ddelta

        jacob[-2 * n_alphas:-n_alphas] = alpha_jac
        jacob[-n_alphas:] = delta_jac
        # return (power_to(1/p - 1)(pred_train.values) / p * jacob).T
        return jacob.T

    size_parameters = 1 + np.sum([len(j_s) + 2 for i, j_s in setting])
    lower_bound = np.full(size_parameters, -np.inf)
    upper_bound = np.full(size_parameters, np.inf)
    n_alphas = len(setting)

    initial_parameters = np.full(size_parameters, 1.)
    if not fixed_initial:
        initial_parameters = optimal_parameters_from_exponentials_tspl(X=X_train, y=y_train, p=p, setting=setting,
                                                                       delta_value=delta_value, plot=False)

    lower_bound[-2 * n_alphas:-n_alphas] = 0  # force non-negative alphas
    upper_bound[-2 * n_alphas:-n_alphas] = 10

    # Non negative deltas
    lower_bound[-n_alphas:] = dt / 100  # force non-negative deltas
    eps = 1e-4
    if not optimize_delta:
        lower_bound[-n_alphas:] = np.clip(initial_parameters[-n_alphas:] * (1 - eps), dt, None)
        upper_bound[-n_alphas:] = np.clip(initial_parameters[-n_alphas:] * (1 + eps), dt * (1 + eps), None)

    if init_parameters is not None:
        initial_parameters = init_parameters

    initial_parameters = np.clip(initial_parameters, lower_bound, upper_bound)

    # print('initial parameters', initial_parameters)
    initial_pred_train = linear_of_kernels(returns=X_train, setting=setting, parameters=initial_parameters,
                                           return_features=False)
    initial_pred_test = linear_of_kernels(returns=X_test, setting=setting, parameters=initial_parameters,
                                          return_features=False)

    initial_pred_train = np.clip(initial_pred_train, 0, None)
    initial_pred_test = np.clip(initial_pred_test, 0, None)
    initial_vol_pred_train = inv_target_transform(initial_pred_train)
    initial_vol_pred_test = inv_target_transform(initial_pred_test)
    # else:
    #     initial_parameters = initial_parameters[:2*len(setting)+1]
    jacob = jacobian if use_jacob else '2-point'

    def objective(parameters):
        pred = linear_of_kernels(X_train, setting, parameters)
        residual_term = np.sum((y_train - pred)**2)
        _, _, alphas, deltas = split_parameters(parameters, setting)
        reg_term = lambda_reg * (np.sum(alphas**2) + np.sum(deltas**2))
        #print(reg_term, residual_term)
        return residual_term + reg_term
    if lambda_reg==0:
        sol = least_squares(residuals, initial_parameters, method='trf', bounds=(lower_bound, upper_bound), jac=jacob)
    else:
        sol = minimize(objective, initial_parameters, bounds=list(zip(lower_bound, upper_bound)), method='L-BFGS-B')
    #sol = least_squares(residuals, initial_parameters, method='trf', bounds=(lower_bound, upper_bound), jac=jacob)
    opt_params = sol['x']
    split_opt_params = split_parameters(parameters=opt_params, setting=setting)
    split_opt_params = list(split_opt_params)

    # Compute normalization constant of the kernels
    norm_constants = []
    norm_per_i = {}
    for iter, (i, js) in enumerate(setting):
        alpha = split_opt_params[2][iter]
        delta = split_opt_params[3][iter]
        #print("ddd")
        if iter==0:
            weights = shifted_power_law(np.arange(100) * dt, alpha=alpha, delta=delta)
        else:
            weights = shifted_power_law(np.arange(max_delta) * dt, alpha=alpha, delta=delta)
        #print(len(weights))
        norm_const = (np.sum(weights) * dt) ** np.array(js)
        norm_per_i[i] = norm_const
        norm_constants.extend(norm_const)

    train_features, pred_train = linear_of_kernels(returns=X_train, setting=setting, parameters=opt_params,
                                                   return_features=True)
    test_features, pred_test = linear_of_kernels(returns=X_test, setting=setting, parameters=opt_params,
                                                 return_features=True)

    split_opt_params[1] = split_opt_params[1] * np.array(norm_constants)  # add normalizer to the betas

    pred_train = np.clip(pred_train, 0, None)
    pred_test = np.clip(pred_test, 0, None)
    vol_pred_train = inv_target_transform(pred_train)
    vol_pred_test = inv_target_transform(pred_test)
    train_features = OrderedDict([(key, pd.DataFrame(train_features[key]) / norm_per_i[key]) for key in train_features])
    test_features = OrderedDict(
        [(key, pd.DataFrame(test_features[key]) / norm_per_i[key]) for key in test_features])
    features_df = ordered_dict_to_dataframe(train_features, test_features, setting)
    keys = ['beta_0']
    for i, j_s in setting:
        if len(j_s) == 1:
            keys.append(f'beta_{i}')
        else:
            keys.extend([f'beta_{i}{j}' for j in j_s])
    keys.extend([f'alpha_{i}' for i, j_s in setting] + [f'delta_{i}' for i, j_s in setting])

    opt_params[1:-2 * n_alphas] = split_opt_params[1]

    ans = {'sol': sol,  'opt_params': {keys[i]: opt_params[i] for i in range(len(keys))},
           'setting': setting, 'p': p,
           'train_pred': pd.Series(vol_pred_train, index=train_data.index),
           'test_pred': pd.Series(vol_pred_test, index=test_data.index),
           'train_rmse': mean_squared_error(y_true=vol_train, y_pred=vol_pred_train, squared=False),
           'test_rmse': mean_squared_error(y_true=vol_test, y_pred=vol_pred_test, squared=False),
           'train_r2': r2_score(y_true=vol_train, y_pred=vol_pred_train),
           'test_r2': r2_score(y_true=vol_test, y_pred=vol_pred_test),
           'features': features_df,
           'initial_parameters': {keys[i]: initial_parameters[i] for i in range(len(keys))},
           'initial_train_rmse': mean_squared_error(y_true=vol_train, y_pred=initial_vol_pred_train, squared=False),
           'initial_test_rmse': mean_squared_error(y_true=vol_test, y_pred=initial_vol_pred_test, squared=False),
           'initial_train_r2': r2_score(y_true=vol_train, y_pred=initial_vol_pred_train),
           'initial_test_r2': r2_score(y_true=vol_test, y_pred=initial_vol_pred_test),
           }
    return {key: ans[key] for key in ['train_r2', 'test_r2', 'train_rmse', 'test_rmse',
                                      'features', 'opt_params', 'train_pred', 'test_pred']}
