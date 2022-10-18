"""Module for managaing data for the Air Quality predictor.

Used for updating:
- Historical pollutant concentrations.
- Historical weather data.
- Weather forecast data.
"""

import os
import datetime
import pickle
import json
import time
import requests
import traceback
import pandas as pd
import numpy as np
import shutil
from io import StringIO
import air_quality.constants as C
import air_quality.logging as aqlogging
from meteostat import Stations
from meteostat import Hourly


class DataUpdater:

    LOG_DIR_PATH = os.path.join(C.WORK_DIR, 'logs')
    UPDATE_LOG_PATH = os.path.join(LOG_DIR_PATH, 'last-update.txt')

    CACHE_DIR_PATH = os.path.join(C.WORK_DIR, 'cache')
    KEY_TIMES_PATH = os.path.join(CACHE_DIR_PATH, 'key-times.pkl')

    TZ = 'Europe/Paris'

    def init_cache(self):
        if not os.path.exists(self.CACHE_DIR_PATH):
            os.makedirs(self.CACHE_DIR_PATH)

    def cache_key_times(self, key_times):
        self.init_cache()
        with open(self.KEY_TIMES_PATH, 'wb') as file:
            pickle.dump(key_times, file)


    def clear_key_times_cache(self):
        if os.path.exists(self.KEY_TIMES_PATH):
            os.remove(self.KEY_TIMES_PATH)


    def fetch_cached_key_times(self):
        if not os.path.exists(self.KEY_TIMES_PATH):
            return None

        with open(self.KEY_TIMES_PATH, 'rb') as file:
            return pickle.load(file)


    def create_temp_data(self):

        self.clear_temp_data()

        dm = DataManager()
        src_path = dm.EXISTING_DATA_PATH
        dest_path = os.path.join(src_path, 'temp')

        shutil.copytree(src_path, dest_path)


    def copy_temp_data_to_live(self):
        dm = DataManager()
        dest_path = dm.EXISTING_DATA_PATH
        src_path = os.path.join(dest_path, 'temp')
        files=os.listdir(src_path)
        for fname in files:
            filepath = os.path.join(src_path, fname)
            if not os.path.isdir(filepath):
                shutil.copy2(os.path.join(src_path, fname), dest_path)


    def clear_temp_data(self):
        dm = DataManager()
        src_path = dm.EXISTING_DATA_PATH
        dest_path = os.path.join(src_path, 'temp')
        if os.path.exists(dest_path):
            shutil.rmtree(dest_path)


    def hit_home_page(self):
        home_url = C.ENV_VARS['HOME_URL']
        print(home_url)
        response = requests.request("GET", home_url)
        return response.status_code


    def update_all(self):

        logger = aqlogging.setup_logger(
            name = 'General update',
            log_filepath = os.path.join(C.WORK_DIR, 'logs', 'general-data-update.log')
        )


        try:

            # Copy existing data files to temp folder for update
            self.create_temp_data()

            weather_forecast_dm = WeatherForecastDataManager()
            weather_forecast_dm.update_current_data()

            historical_weather_dm = HistoricalWeatherDataManager()
            historical_weather_dm.update_to_yesterday()

            air_quality_dm = AirQualityDataManager()
            air_quality_dm.update_to_yesterday()

            self.copy_temp_data_to_live()

            self.clear_temp_data()

        except Exception as e:

            tb_str = "".join(traceback.format_tb(e.__traceback__))

            message_str = f"Error: {str(e)}\nTraceback:\n{tb_str}"

            message_str = f"Error on data update\n{message_str}"

            logger.error(message_str)

            if C.ENV_VARS['DEBUG']:
                raise Exception(e) from e

    def refresh_metrics(self):
        url = f"{C.ENV_VARS['HOME_URL']}refresh-metrics"
        query_string = {
            'key' : C.ENV_VARS['CACHE_CLEAR_KEY']
        }
        print(url)
        response = requests.request("GET", url, params = query_string)
        return response.status_code, response.text

class DataManager:
    """Parent class for managaing data for the Air Quality predictor.
    """

    PREDICTION_EARLIEST_START = '2014-01-01'

    EXISTING_DATA_PATH = os.path.join(C.WORK_DIR, 'data', 'timeseries')
    EXISTING_DATA_FILENAME = '' # Will be set by subclass

    BASE_BACKUPS_PATH = os.path.join(C.WORK_DIR, 'data', 'backups')

    LOCATIONS_COORDS = {
        'Montpellier' : (43.6106, 3.8738),
        'Marseille' : (43.2965, 5.3698)
    }

    LOCATIONS = list(LOCATIONS_COORDS.keys())

    WEATHER_VARS = [
        'temperature_2m',
        'relativehumidity_2m',
        'dewpoint_2m',
        'surface_pressure',
        'cloudcover',
        'windspeed_10m',
        'winddirection_10m'
    ]

    TZ = 'Europe/Paris'


    def __init__(self):

        # Each subclass will create its own logger.
        self.logger = None

        self.existing_data = None

        self.temp_existing_data = None


    def handle_error(self, e : Exception, message : str = ''):

        tb_str = "".join(traceback.format_tb(e.__traceback__))

        message_str = f"Error: {str(e)}\nTraceback:\n{tb_str}"
        if message:
            message_str = f"{message}\n{message_str}"

        if self.logger is not None:
            self.logger.error(message_str)

        if C.ENV_VARS['DEBUG']:
            raise Exception(e)


    def get_existing_data_df(self, temp = False):

        if temp:

            if self.temp_existing_data is None:
                path = os.path.join(self.EXISTING_DATA_PATH, 'temp', self.EXISTING_DATA_FILENAME)
                with open(f"{path}.pkl", 'rb') as file:
                    self.temp_existing_data = pickle.load(file)

            return self.temp_existing_data.copy()

        else:

            if self.existing_data is None:
                path = os.path.join(self.EXISTING_DATA_PATH, self.EXISTING_DATA_FILENAME)
                with open(f"{path}.pkl", 'rb') as file:
                    self.existing_data = pickle.load(file)

            return self.existing_data.copy()


    def save_existing_data_df(self, df, temp = False):

        if temp:

            self.temp_existing_data = df.copy()
            path = os.path.join(self.EXISTING_DATA_PATH, 'temp', f"{self.EXISTING_DATA_FILENAME}.pkl")
            with open(path, 'wb') as file:
                pickle.dump(df, file)

        else:

            self.existing_data = df.copy()
            path = os.path.join(self.EXISTING_DATA_PATH, f"{self.EXISTING_DATA_FILENAME}.pkl")
            with open(path, 'wb') as file:
                pickle.dump(df, file)


    def get_existing_data_last_time(self, temp = False):
        existing_data_df = self.get_existing_data_df(temp)
        return existing_data_df['Datetime'].max()


    def get_next_day_to_fetch(self, temp = False):
        existing_data_last_time = self.get_existing_data_last_time(temp).date()
        return existing_data_last_time + pd.Timedelta(1, 'day')


    def previous_days_data_exists(self, date : str, temp : bool = False):
        existing_data_last_time = self.get_existing_data_last_time(temp)
        previous_day_last_datetime = pd.to_datetime(f"{date} 23:00:00") - pd.Timedelta(1, 'day')
        return previous_day_last_datetime <= existing_data_last_time


    def get_api_response(self, api_url : str, query_params : dict, headers : dict = None):
        return requests.request("GET", api_url, params = query_params, headers = headers)


    def get_api_json_reponse(self, api_url : str, query_params : dict, headers : dict = None):
        response = self.get_api_response(api_url, query_params, headers)
        return json.loads(response.text)


    def today(self):
        return pd.Timestamp.today(self.TZ).date()


    def fill_missing_values(self, dataframe : pd.DataFrame):

        # The first column is a category for the data - either 'location' or 'Polluant'.
        # So we divide our dataframe up by the category column before interpolating.
        category_col_name = dataframe.columns[0]

        df = dataframe.pivot_table(
            index = [category_col_name, 'Datetime'],
            dropna = False
        )

        category_dfs = []
        for category in df.index.get_level_values(0).unique():

            category_df = df.loc[category]

            if category_df.isna().values.any():

                # First use linear interpolation where possible.
                category_df.interpolate(inplace = True)

                # Then pad to fill any null values at the end if there are any.
                if category_df.isna().values.any():
                    category_df.interpolate(method = 'pad', inplace = True)

            # Add in the category column again and reset to original order.
            category_df.reset_index(inplace = True)
            category_df.insert(0, category_col_name, category)


            category_dfs.append(category_df)

        # Recombine all the categories dataframes together into a single df.
        filled_df = pd.concat(category_dfs).reset_index(drop = True)
        filled_df['Datetime'] = pd.to_datetime(filled_df['Datetime'])

        return filled_df

class WeatherForecastDataManager(DataManager):

    # Path to the current weather forecast data.
    EXISTING_DATA_FILENAME = 'Processed weather forecast data'

    LOGS_PATH = os.path.join(C.WORK_DIR, 'logs', 'weather-forecast-update.log')

    API_URL = 'https://api.open-meteo.com/v1/forecast'

    LOCATIONS = ['Montpellier', 'Marseille']

    DATA_COLUMNS = [
        'DewPointC',
        'cloudcover',
        'humidity',
        'pressure',
        'tempC',
        'winddirDegree',
        'windspeedKmph'
    ]

    def __init__(self):
        super().__init__()

        self.existing_data = None

        self.logger = aqlogging.setup_logger(
            name = 'Weather forecast data update', log_filepath = self.LOGS_PATH)


    def get_last_date_current_data(self, temp = False):

        current_data = self.get_existing_data_df(temp)

        last_dates = []
        for location in self.LOCATIONS:
            last_dates.append(
                current_data[current_data['location'] == location]['Datetime'].max()
            )

        return min(last_dates).date()


    def fetch_data(self, start : str, end : str):

        # We add the hourly weather variables because for some reason it does
        # not work as a param in requests.request.
        api_url = self.API_URL + '?hourly=' + ','.join(self.WEATHER_VARS)

        query_params = {
            'timezone' : self.TZ,
            'start_date' : start,
            'end_date' : end,
        }

        forecast_hourly_data_dfs = []

        for location, coordinates in self.LOCATIONS_COORDS.items():
            query_params['latitude'] = str(coordinates[0])
            query_params['longitude'] = str(coordinates[1])

            json_data = self.get_api_json_reponse(api_url, query_params)

            forecast_hourly_data_df = pd.DataFrame(json_data['hourly'])
            forecast_hourly_data_df['location'] = location
            forecast_hourly_data_dfs.append(forecast_hourly_data_df)

        forecast_hourly_data = pd.concat(forecast_hourly_data_dfs)

        # Rename columns to match the column names of the bulk historical
        # forecast data.
        col_names = {
            'time' : 'Datetime',
            'temperature_2m' : 'tempC',
            'relativehumidity_2m' : 'humidity',
            'dewpoint_2m' : 'DewPointC',
            'surface_pressure' : 'pressure',
            'windspeed_10m' : 'windspeedKmph',
            'winddirection_10m' : 'winddirDegree'
        }
        forecast_hourly_data.rename(columns = col_names, inplace = True)

        forecast_hourly_data['Datetime'] = pd.to_datetime(forecast_hourly_data['Datetime'])

        return forecast_hourly_data


    def merge_fetched_and_current_data(
        self,
        fetched_data : pd.DataFrame,
        current_data : pd.DataFrame
    ):

        merged_data = (
            pd.concat([current_data, fetched_data])

            # We will have duplicates as we are updating old forecasts.
            # Since we have added the new fetched_data to the end, we ensure
            # the new data is kept by setting `keep` to 'last'.
            .drop_duplicates(
                subset = ['location', 'Datetime'],
                keep = 'last'
            )

            .sort_values(by = ['location', 'Datetime'], ascending = [False, True])

            .reset_index(drop = True)
        )

        # Fill any null values.
        filled_data = self.fill_missing_values(merged_data)

        self.save_existing_data_df(filled_data, temp = True)


    def backup_fetched_data(self,
        fetched_data : pd.DataFrame,
        start : datetime.date
    ):

        date_fmt = '%Y-%m-%d'
        start = start.strftime(date_fmt)

        dirpath = os.path.join(self.BASE_BACKUPS_PATH, 'weather forecast')
        filename = f"{start}.gz"

        if not os.path.exists(dirpath):
            os.makedirs(dirpath)

        fetched_data.to_csv(os.path.join(dirpath, filename))


    def update_current_data(self):

        current_data = self.get_existing_data_df(temp = True)

        last_date_current_data = self.get_last_date_current_data(temp = True)

        # If the last data we have is on the 13th, say, then the last
        # forecast ran from the 7th to the 13th. So we will fetch from
        # the 8th to get new data.
        start = last_date_current_data - pd.Timedelta(5, 'D')

        # Max is a 7-day forecast including today, so end is 6 days
        # from today.
        end = self.today() + pd.Timedelta(6, 'D')

        # Don't run the update if we already have all the future data
        # we can get.
        if last_date_current_data >= end:
            self.logger.info(
                f"Not running the update for {start} to {end} as we already have this weather forecast data.")
            return False


        self.logger.info(
            f"Initiating update for {start} to {end}.")

        fetched_data = self.fetch_data(start, end)

        self.backup_fetched_data(fetched_data, start)

        self.merge_fetched_and_current_data(fetched_data, current_data)

        return True


class AirQualityDataManager(DataManager):

    EXISTING_DATA_FILENAME = 'Processed pollutants data'

    BACKUPS_PATH = os.path.join(DataManager.BASE_BACKUPS_PATH, 'pollutants')
    LOGS_PATH = os.path.join(C.WORK_DIR, 'logs', 'airquality-update.log')

    REQUEST_API_URL = 'https://www.geodair.fr/api-ext/MoyH/export'
    DOWNLOAD_API_URL = 'https://www.geodair.fr/api-ext/download'

    POLLUTANT_CODES = {
        'NO2' : '03',
        'O3' : '08',
        'PM10' : '24',
        'PM2.5' : '39',
        'SO2' : '01'
    }

    POLLUTANTS = list(POLLUTANT_CODES.keys())

    STATION_LOCATIONS = {
        'NO2' : [
            "Montpellier Chaptal",
            "Montpellier Prés d'Arènes",
            "Montpellier St Denis",
            "Pompignane"],
        'O3' : ["Montpellier Prés d'Arènes"],
        'PM10' : ["Montpellier Prés d'Arènes", "Pompignane"],
        'PM2.5' : ["Montpellier Prés d'Arènes", "Pompignane"],
        'SO2' : ["MARSEILLE 5 AVENUES"]
    }

    def __init__(self):

        super().__init__()

        self.api_key = C.ENV_VARS['GEODAIR_API_KEY']

        self.existing_data = None

        self.logger = aqlogging.setup_logger(
            name = 'Pollutants data update', log_filepath = self.LOGS_PATH)


    def fetch_download_id(self, date : str, pollutant : str):

        query_params = {
            'date' : date,
            'polluant' : self.POLLUTANT_CODES[pollutant]
        }

        headers = {
            'apikey' : self.api_key,
            'accept' : 'text/plain'
        }

        response = self.get_api_response(self.REQUEST_API_URL, query_params, headers = headers)

        error_message_info = (
            f"Date: {date}, Pollutant: {pollutant}, Pollutant code: {query_params['polluant']}")

        if response.status_code != 200:

            message = f"Unsuccessful Geod'Air request. Status code: {response.status_code}\n{error_message_info}"
            self.logger.error(message)

            return None

        if response.text[:7] != 'moyenne':

            message = f"Unexpected content from Geod'Air request: {response.text}\n{error_message_info}"
            self.logger.error(message)

            return None

        return response.text


    def download_file_stream(self, download_id : str):

        query_params = {'id' : download_id}

        headers = {
            'apikey' : self.api_key,
            'accept' : 'application/octet-stream'
        }

        response =  self.get_api_response(self.DOWNLOAD_API_URL, query_params, headers = headers)

        if response.status_code != 200:

            """
            TODO use errors and aqlogging
            raise ValueError(
                f"Unsuccessful Geod'Air download request. Status code: {response.status_code}." +
                f"Download id: {download_id}")
            """

            return None

        if response.text[:4] != 'Date':

            """
            TODO use errors and aqlogging
            raise ValueError(
                f"Unexpected content from Geod'Air download request: {response.text}\n" +
                f"Download id: {download_id}"
            )
            """

            return None

        return response.text

    def download_file_exists(self, date : str, pollutant : str):
        return os.path.exists(self.get_backup_path(date, pollutant))


    def get_backup_path(self, date : str, pollutant : str):
        return os.path.join(self.BACKUPS_PATH, f"{pollutant}_{date}.gz")


    def save_backup(self, content : str, date : str, pollutant : str):
        data_df = pd.read_csv(StringIO(content), sep = ';')
        path = self.get_backup_path(date, pollutant)
        data_df.to_csv(path)


    def get_pollutants_to_request(self, date : str):

        output = []

        # Check which pollutants we need to get.
        for pollutant in self.POLLUTANTS:
            if not self.download_file_exists(date, pollutant):
                output.append(pollutant)

        return output


    def fetch_pollutant_download_ids(self, date : str, pollutants : list[str]):

        download_ids = {}

        for pollutant in pollutants:
            response = self.fetch_download_id(date, pollutant)

            if response:
                download_ids[pollutant] = self.fetch_download_id(date, pollutant)
            time.sleep(0.5)

        return download_ids

    def fetch_required_pollutant_ids(self, date : str):

        pollutants_to_request = self.get_pollutants_to_request(date)
        return self.fetch_pollutant_download_ids(date, pollutants_to_request)


    def download_file_streams(self, date : str, download_ids : dict):
        for pollutant, download_id in download_ids.items():

            content = self.download_file_stream(download_id)

            if content:
                self.save_backup(content, date, pollutant)

            time.sleep(1)


    def single_fetch_data(self, date : str):

        download_ids = self.fetch_required_pollutant_ids(date)
        pollutants_str = ', '.join(download_ids.keys()) if download_ids else 'None'
        self.logger.info(f"Fetching data of {date} for pollutants: {pollutants_str}")

        # Allow a few seconds for the files to be generated.
        if download_ids:
            time.sleep(5)

        self.download_file_streams(date, download_ids)

        remaining_pollutant_ids = self.fetch_required_pollutant_ids(date)

        pollutants_str = ', '.join(remaining_pollutant_ids.keys()) if remaining_pollutant_ids else 'None'
        self.logger.info(f"Data fetched for {date}. Outstanding pollutants: {pollutants_str}")

        return remaining_pollutant_ids


    def get_merged_pollutants_data(self, date : str):

        pollutant_data_dfs = []
        for pollutant in self.POLLUTANTS:
            pollutant_data_path = self.get_backup_path(date, pollutant)
            pollutant_data_df = pd.read_csv(pollutant_data_path)

            # Select only the columns we need.
            pollutant_data_df = self.clean_columns_pollutants_data(pollutant_data_df)

            # Select the appropriate locations.
            pollutant_data_df = self.filter_pollutants_data_by_location(
                pollutant_data_df, pollutant
            ).copy()

            # If we have no data at all for this date and pollutant then we copy
            # from the day before.
            if len(pollutant_data_df) == 0:
                pollutant_data_df = self.get_filled_missing_day_data(date, pollutant)

            # Rename the valeur brute column.
            pollutant_data_df.rename(columns = {'valeur brute' : 'Concentration'}, inplace = True)

            pollutant_data_dfs.append(pollutant_data_df)

            merged_data = pd.concat(pollutant_data_dfs).reset_index(drop = True)

        return merged_data


    def get_previous_day_data(self, date : str, pollutant : str):

        previous_day = pd.to_datetime(date).date() - pd.Timedelta(1, 'day')

        existing_data = self.get_existing_data_df()

        previous_day_data = existing_data[
            (existing_data['Polluant'] == pollutant) &
            (existing_data['Datetime'].dt.date == previous_day)
        ]

        return previous_day_data


    def get_filled_missing_day_data(self, date : str, pollutant : str):

        filled_day_data = self.get_previous_day_data(date, pollutant).copy()

        # Shift the datetime forward by one day.
        filled_day_data['Datetime'] = filled_day_data['Datetime'] + pd.Timedelta(1, 'Day')

        # Modify columns so format matches fetched data.
        filled_day_data['nom site'] = 'Dummy site'
        filled_day_data.rename(columns = {'Concentration' : 'valeur brute'}, inplace = True)
        filled_day_data.columns.name = None

        return filled_day_data[['Datetime', 'Polluant', 'nom site', 'valeur brute']]



    def get_cleaned_fetched_pollutants_data(self, date : str):

        fetched_data = self.get_merged_pollutants_data(date)

        cleaned_df = self.get_non_positive_values_replaced_with_nan(fetched_data)

        averaged_data = self.get_data_averaged_across_sites(cleaned_df)

        return averaged_data


    def get_filled_data(self, data : pd.DataFrame):

        data_filled_with_whole_days = self.get_data_filled_with_whole_days(data)

        return data_filled_with_whole_days


    def get_data_filled_with_whole_days(self, data):

        pollutant_days_to_copy = self.get_days_needing_replacement(data)

        # If we have no days to copy, no changes needed!
        if pollutant_days_to_copy is None:
            return data

        fetched_data_excl_days_needing_replacement = self.get_data_without_days_to_replace(
            data, pollutant_days_to_copy
        )

        existing_data = self.get_existing_data_df()

        return self.replace_copied_days_data(
            existing_data,
            fetched_data_excl_days_needing_replacement,
            pollutant_days_to_copy
        )


    def get_data_averaged_across_sites(self, pollutants_data : pd.DataFrame):

        averaged_data = pollutants_data.pivot_table(
            index = ['Polluant', 'Datetime'],
            values = 'Concentration',
            aggfunc = 'mean',
            fill_value = np.nan,
            dropna = False
        )

        return averaged_data.reset_index()


    def clean_columns_pollutants_data(self, pollutant_data_df : pd.DataFrame):

        # Select only the columns we need.
        pollutant_data_df = pollutant_data_df[[
            'Date de début',
            'Polluant',
            'nom site',
            'valeur brute'
        ]].copy()

        # Rename the datetime column
        pollutant_data_df.rename(columns = {'Date de début' : 'Datetime'}, inplace = True)

        # Convert the datetime column type.
        pollutant_data_df['Datetime'] = pd.to_datetime(pollutant_data_df['Datetime'])

        return pollutant_data_df


    def filter_pollutants_data_by_location(self, df : pd.DataFrame, pollutant : str):

        # Correct known location misspellings.
        df.loc[df['nom site'] == 'Chaptal', 'nom site'] = 'Montpellier Chaptal'
        df.loc[df['nom site'] == 'Saint Denis', 'nom site'] = 'Montpellier St Denis'

        # Select
        df = df[df['nom site'].isin(self.STATION_LOCATIONS[pollutant])]

        return df


    def get_merged_fetched_and_existing_data(self, fetched_data_df : pd.DataFrame):
        existing_data_df = self.get_existing_data_df()
        merged_df = pd.concat([existing_data_df, fetched_data_df]).reset_index(drop = True)
        return merged_df.sort_values(
            by = ['Polluant', 'Datetime'],
        )


    def get_non_positive_values_replaced_with_nan(self, df: pd.DataFrame):
        output = df.copy()
        output.loc[output['Concentration'] <= 0, 'Concentration'] = np.nan
        return output


    def get_df_averaged_values_across_sites(self, data_df : pd.DataFrame):
        averaged_data = data_df.pivot_table(
            index = ['Polluant', 'Datetime'],
            values = 'Concentration',
            aggfunc = 'mean',
            fill_value = np.nan,
            dropna = False
        )

        return averaged_data


    def get_days_needing_replacement(self, fetched_data : pd.DataFrame):

        # Get a count of the null values by day.
        null_values = fetched_data[fetched_data['Concentration'].isna()].copy()

        if len(null_values) == 0:
            return None

        null_values['Null value'] = 1
        null_values['Date'] = null_values['Datetime'].dt.date

        count_null_values_by_day = null_values.pivot_table(
            index = ['Polluant', 'Date'],
            values = 'Null value',
            aggfunc = 'count'
        )

        # Select those days where more than 12 hours of data are null.
        pollutant_days_to_copy = (
            count_null_values_by_day[count_null_values_by_day['Null value'] >= 12]
            .index.to_frame(index = False)
        )

        if len(pollutant_days_to_copy) == 0:
            return None

        pollutant_days_to_copy['Polluant-Date'] = (
            pollutant_days_to_copy['Polluant'] + ' ' + pollutant_days_to_copy['Date'].astype('str')
        )

        return pollutant_days_to_copy


    def get_data_without_days_to_replace(
        self, fetched_data : pd.DataFrame, pollutant_days_to_copy : pd.DataFrame):

        fetched = fetched_data.copy()
        fetched['Polluant-Date'] = fetched['Polluant'] + ' ' + fetched['Datetime'].dt.strftime('%Y-%m-%d')

        fetched_data_merged_with_days_to_copy = (
            fetched.merge(
                pollutant_days_to_copy.drop(columns = ['Polluant']),
                how = 'left',
                on = 'Polluant-Date'
            )
        )

        fetched_data_merged_without_days_to_copy = fetched_data_merged_with_days_to_copy[
            fetched_data_merged_with_days_to_copy['Date'].isna()
        ].drop(columns = ['Date'])

        return fetched_data_merged_without_days_to_copy


    def same_day_last_year(self, polluant_date):

        polluant, date = polluant_date.split(' ')
        year = int(date[:4])

        # Set the month and day to fetch, handling leap years.
        month_day = date[4:]
        if month_day == '-02-29':
            month_day = '-02-28'

        return f"{polluant} {year - 1}{month_day}"


    def replace_copied_days_data(
        self,
        existing_data : pd.DataFrame,
        fetched_data_merged_without_days_to_copy : pd.DataFrame,
        pollutant_days_to_copy : pd.DataFrame
    ):

        existing_copy = existing_data.copy()
        data_to_concat = [fetched_data_merged_without_days_to_copy]

        existing_copy['Polluant-Date'] = (
            existing_copy['Polluant'] + ' ' + existing_data['Datetime'].dt.strftime('%Y-%m-%d'))

        for polluant_date in pollutant_days_to_copy['Polluant-Date']:
            data_to_copy = existing_copy[
                existing_copy['Polluant-Date'] == \
                    self.same_day_last_year(polluant_date)
            ]

            data_to_copy['Datetime'] = pd.to_datetime(
                polluant_date[-10:] + ' ' + data_to_copy['Datetime'].dt.strftime('%H:%M:%S')
            )

            data_to_copy['Polluant-Date'] = data_to_copy['Polluant-Date'].str[:-10] + polluant_date[-10:]
            data_to_concat.append(data_to_copy)

        return pd.concat(data_to_concat).sort_values(
            by = ['Polluant', 'Datetime']
        ).drop(columns = 'Polluant-Date')


    def add_processed_fetched_data_to_existing(self, processed_fetched_data):

        existing_data = self.get_existing_data_df(temp = True)

        update_existing_data = (
            pd.concat(
                [existing_data, processed_fetched_data]
            )

            # Shouldn't be duplicates, but just in case...
            .drop_duplicates(
                subset = ['Datetime', 'Polluant'],
                keep = 'first', # Prevent overwrite.
            )
        )

        return update_existing_data.sort_values(
            by = ['Polluant', 'Datetime']
        ).reset_index(drop = True)


    def run_update(self, date : str):

        # Log beginning of process.
        self.logger.info(f"Initiating air quality data update for {date}")

        # Fetch data.
        outstanding_download_ids = self.single_fetch_data(date)

        # Only update existing stored data if we have data for all pollutants.
        if len(outstanding_download_ids.keys()) == 0:

            # Get the stored update data and process it.
            cleaned_fetched_data = self.get_cleaned_fetched_pollutants_data(date)

            # Merge with existing data.
            updated_data = self.add_processed_fetched_data_to_existing(cleaned_fetched_data)

            # Fill any gaps.
            filled_data = self.fill_missing_values(updated_data)

            # Store new data.
            self.save_existing_data_df(filled_data, temp = True)

            # Log attempt to update saved data.
            self.logger.info(f"Air quality data updated for {date}")


    def update_next_day(self):

        try:

            # First check that the next day's data is available.
            today = self.today()
            yesterday = today - pd.Timedelta(1, 'day')

            next_day_to_fetch = self.get_next_day_to_fetch(temp = True)
            if next_day_to_fetch > yesterday:
                self.logger.warning(
                    f"Can't update next day's pollutants data ({next_day_to_fetch}) "
                    "as it is not available yet.")
                return False

            update_date_str = next_day_to_fetch.strftime('%Y-%m-%d')

            self.run_update(update_date_str)

            return True


        except Exception as e:

            self.handle_error(
                e, message = f"Error occured when updating air quality data for {next_day_to_fetch}")

            return False


    def update_to_yesterday(self):
        """We limit the number of attempts to ensure we can't be stuck in an
        infinite loop. This means we limit the max number of days that can be
        fetched as well.
        """

        max_attempts = 5

        attempt = 1

        no_fails = True

        while attempt <= max_attempts and no_fails:

            no_fails = self.update_next_day()

            # Don't bombard the API.
            if no_fails:
                time.sleep(1)

            attempt += 1


class HistoricalWeatherDataManager(DataManager):

    EXISTING_DATA_FILENAME = 'Processed historical weather data'

    BACKUPS_PATH = os.path.join(DataManager.BASE_BACKUPS_PATH, 'historical weather')
    LOGS_PATH = os.path.join(C.WORK_DIR, 'logs', 'historical-weather-update.log')

    LOCATION_COORDINATES = {
        'Montpellier' : (43.6106, 3.8738),
        'Marseille' : (43.2965, 5.3698)
    }

    LOCATIONS = list(LOCATION_COORDINATES.keys())

    DATA_COLUMNS = ['dwpt', 'pres', 'rhum', 'temp', 'wdir', 'wspd']

    CACHE_DIR = os.path.join(DataManager.BASE_BACKUPS_PATH, 'historical weather cache')
    CACHE_AGE = 60

    def __init__(self):

        super().__init__()

        self.logger = aqlogging.setup_logger(
            name = 'Historical weather data update', log_filepath = self.LOGS_PATH)
        self.station_ids = None
        self.existing_data = None

        Hourly.max_age = self.CACHE_AGE
        Hourly.cache_dir = self.CACHE_DIR


    def get_nearest_station_ids(self):

        # Return cached data if we have it.
        if self.station_ids is not None:
            return self.station_ids

        stations = Stations()
        nearest_station_ids = {}

        fetch_success = True
        for location, coords in self.LOCATION_COORDINATES.items():
            stations = stations.nearby(coords[0], coords[1])
            if isinstance(stations, Stations):
                nearest_station_ids[location] = stations.fetch(1).index[0]
            else:
                nearest_station_ids[location] = None
                self.logger.warning(f"No station found for {location}")
                fetch_success = False

        # Cache for next time.
        self.station_ids = nearest_station_ids if fetch_success else None

        return self.station_ids


    def fetch_hourly_data(self, start_date : str, end_date : str):

        station_ids = self.get_nearest_station_ids()

        if station_ids is None:
            self.logger.warning(
                f"No update attempted for {start_date} to {end_date} as station data is incomplete."
            )
            return None

        start = pd.to_datetime(f"{start_date} 00:00:00")
        end = pd.to_datetime(f"{end_date} 23:59:59")

        self.logger.info(f"Fetching hourly data for {start_date} to {end_date}")

        hourly_data_dfs = []
        fetch_success = True
        for location, station_id in station_ids.items():

            # Fetch hourly data and add location column.
            hourly_data = Hourly(station_id, start, end)

            if not isinstance(hourly_data, Hourly):
                self.logger.warning(f"Error fetching {location} data for {start_date} to {end_date}")
                fetch_success = False

            hourly_data_df = hourly_data.fetch()

            if not isinstance(hourly_data_df, pd.DataFrame) or len(hourly_data_df) == 0:
                self.logger.warning(f"Error creating {location} dataframefor {start_date} to {end_date}")
                fetch_success = False

            hourly_data_df['location'] = location

            hourly_data_df.sort_index(inplace = True)

            hourly_data_dfs.append(hourly_data_df)

        if not fetch_success:
            return None

        output = pd.concat(hourly_data_dfs)

        # Drop unused columns.
        required_columns = ['location']
        required_columns.extend(self.DATA_COLUMNS)

        return output[required_columns]


    def fetch_hourly_data_for_date(self, date : str):
        return self.fetch_hourly_data(date, date)


    def get_backup_path(self, date : str):
        return os.path.join(self.BACKUPS_PATH, f"{date}.gz")


    def backup_file_exists(self, date : str):
        return os.path.exists(self.get_backup_path(date))


    def save_backup(self, date : str, hourly_data : pd.DataFrame):
        hourly_data.to_csv(self.get_backup_path(date))
        self.logger.info(f"Attempted backup of fetched data for {date}")


    def get_previous_day(self, date : str):
        day = pd.to_datetime(f"{date} 00:00:00")
        day_before = day - pd.Timedelta(1, 'day')
        return day_before.strftime('%Y-%m-%d')


    def fetch_and_save_data_for_date(self, date : str, prevent_date_gaps = True):

        try:

            # Check we aren't missing the previous day.
            if prevent_date_gaps:
                if not self.previous_days_data_exists(date, temp = True):
                    self.logger.warning(
                        f"Data not fetched for {date} because previous day's data not found.")
                    return False

            # Check we haven't already got the data.
            if self.backup_file_exists(date):
                self.logger.info(f"Data not fetched for {date} because data already exists.")
                return True


            hourly_data = self.fetch_hourly_data_for_date(date)
            if hourly_data is not None:
                self.save_backup(date, hourly_data)
                self.logger.info(f"Backup saved for {date}")

                return True

        except Exception as e:

            self.handle_error(
                e, message = f"Error occured when fetching and saving historical weather data for {date}")

            return False


    def fetch_backedup_data(self, date : str) -> pd.DataFrame:

        if not self.backup_file_exists(date):
            return None

        data = pd.read_csv(self.get_backup_path(date))
        data.rename(columns = {'time' : 'Datetime'}, inplace = True)
        data['Datetime'] = pd.to_datetime(data['Datetime'])

        return data


    def get_merged_new_and_existing_data(self, date : str):

        existing_data_df = self.get_existing_data_df(temp = True)
        new_data = self.fetch_backedup_data(date)
        if new_data is None:
            self.logger.warning(
                f"Could not merge data of {date} with existing data as "
                f"{date} data has not been fetched.")
            return None

        # Check that the new data follows on from the existing data.
        existing_data_last_time = self.get_existing_data_last_time(temp = True)
        new_data_first_time = new_data['Datetime'].min()

        if new_data_first_time != existing_data_last_time + pd.Timedelta(1, 'hour'):
            self.logger.warning(
                f"Cannot merge data of {date} with existing data because the existing data"
                f" ends at {existing_data_last_time} and the new data begins at "
                f"{new_data_first_time}. There cannot be a gap between the two."
            )
            return None

        merged_data = (
            pd.concat([existing_data_df, new_data])
            .sort_values(by = ['location', 'Datetime'])
            .reset_index(drop = True)
        )

        return merged_data


    def fix_error_values(self, df):

        # Set any lowe dewpoint values to the mean.
        df.loc[df['dwpt'] < -10, 'dwpt'] = df['dwpt'].mean()

        # Set any high relative humidity values to 100.
        df.loc[df['rhum'] > 100, 'rhum'] = 100

        return df


    def merge_new_and_existing_data(self, date : str):

        try:

            merged_data = self.get_merged_new_and_existing_data(date)

            if merged_data is None:
                return False

            filled_data = self.fill_missing_values(merged_data)

            fixed_values = self.fix_error_values(filled_data)

            self.save_existing_data_df(fixed_values, temp = True)

            self.logger.info(f"Added {date} data and saved.")

            return True

        except Exception as e:

            self.handle_error(
                e, message = f"Error occured when adding and saving historical weather data for {date}")

            return False


    def update_next_day(self):

        # First check that the next day's data is available.
        today = self.today()
        yesterday = today - pd.Timedelta(1, 'day')

        next_day_to_fetch = self.get_next_day_to_fetch(temp = True)
        if next_day_to_fetch > yesterday:
            self.logger.warning(
                f"Can't update next day's data ({next_day_to_fetch}) as it is not available yet.")
            return False

        fetch_date_str = next_day_to_fetch.strftime('%Y-%m-%d')

        fetch_success = self.fetch_and_save_data_for_date(fetch_date_str)
        if not fetch_success:
            return False

        merge_success = self.merge_new_and_existing_data(fetch_date_str)

        return merge_success


    def update_to_yesterday(self):
        """We limit the number of attempts to ensure we can't be stuck in an
        infinite loop. This means we limit the max number of days that can be
        fetched as well.
        """

        max_attempts = 5

        attempt = 1

        no_fails = True

        while attempt <= max_attempts and no_fails:

            no_fails = self.update_next_day()

            # Don't bombard the API.
            if no_fails:
                time.sleep(1)

            attempt += 1
