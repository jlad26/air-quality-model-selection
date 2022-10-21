# Air Quality Development and Model Selection

The outcome of this project can be seen at [airquality.sneezingtrees.com](http://airquality.sneezingtrees.com) -
an online tool for predicting air quality in Montpellier. I recommend you start there as most of the initial background and explanatory information is available there.

This is one of two repositories that go hand in hand:
- **Air Quality Development and Selection** (where you are now) - contains all work done to develop and select a machine learning model for predicting the concentrations of the five pollutants used to measure European Air Quality.
- [Air Quality Prediction Application](https://github.com/jlad26/air-quality-prediction) - the code for the web application at [airquality.sneezingtrees.com](http://airquality.sneezingtrees.com)

## Data
All the data required for this project that is not available in this repository (and its sibling) is available on [Google Drive](https://drive.google.com/drive/folders/1oyqjshm5qBBPRnwVxDH2NI_Q4hTdpFci?usp=sharing).

## Contents

Although the names of the notebooks are generally self-explanatory, here is the order in which I recommend you look at them:
- **Air Quality data collection**. Shows how the API works for downloading the pollutant concentration data and explains the initial data selections. The end result is a raw dataset for the period 2 January 2013 - 29 August 2022.
- **Weather data collection**. Shows how the APIs work for downloading a) historical weather data and b) weather forecast data. In each case the end result is a raw dataset covering the same period as the pollutants data (2 January 2013 - 29 August 2022).
- **Air Quality data processing**. Takes the raw dataset of pollutant data, cleans, averages across sites, and fills missing data. The resulting dataset is ready for model training.
- **Historical weather data processing**. Takes the raw dataset of historical weather data, conducts some initial feature analysis to select features, cleans, fills missing data, and corrects obvious errors.
- **Weather forecast data processing**. Takes the raw dataset of weather forecast data, conducts some initial feature analysis to select features, cleans, and fills missing data, and checks for obvious errors.
- **Feature analysis**. Selects historical weather and weather forecast features based on correlation with pollutant concentration. The resulting datasets for historical weather and weather forecast are the final versions ready for model training.
- **Model Testing - Example**. This is the noteboook I used for training the various models. It allows the training of one model at a time, so this is a single example - I used this notebook repeatedly to train each model.
- **Model comparison**. Analyses the relative performance of different groups of models by comparing MAE of predictions on the same data.