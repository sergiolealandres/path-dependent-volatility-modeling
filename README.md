# Path-Dependent Implied Volatility Surface Modeling

This folder contains all relevant files for the project focused on modeling and forecasting implied volatility surfaces using path-dependent techniques and SSVI parameterizations.

## Folder Structure

### aux_files/
Contains auxiliary functions used for calibration and optimization. Includes kernel definitions, objective functions, and helper tools for model fitting.

## Main Files

### part2
Implements and calibrates the path-dependent volatility model from Guyon and Lekeufack to predict ATM implied volatility using the historical path of the underlying asset.

### part3
Calibrates implied volatility surfaces using Heston-like SSVI and Parsimonious SSVI models. Includes arbitrage checks and model fit evaluation.

### part4
Forecasts the daily evolution of the Parsimonious SSVI parameters using Guyon’s model applied to each parameter separately.

### part4_ATM
Alternative version of `part4`, where the calibration is restricted to at-the-money options.

### requirements.txt
Specifies the required Python dependencies to run the code (e.g., numpy, scipy, pandas, matplotlib).

## Authors
Pablo Pastor Alcover  
Guillem Ribas Pescador  
Sergio Leal Andrés

Final project for the course MATH70128 – Selected Topics in Quantitative Finance
