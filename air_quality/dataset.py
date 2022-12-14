"""Module for the Dataset class.
"""

from enum import Enum
import numpy as np
from darts.dataprocessing.transformers import Scaler
from darts.utils.timeseries_generation import datetime_attribute_timeseries


class TrainingType(Enum):
    """An Enum to specify which components of dataset to use depending on
    purpose.

    The elements of dataset to use change depending on whether we are in
    'VAL' mode (validation i.e., using the valdation set to select model and
    model parameters), 'TEST' (testing i.e., using the test set to evaluate
    performance of the chosen model), or 'PROD' (production i.e., using the
    entire dataset to predict.)

    The value of each mode is a dictionary. The keys of the dictionary represent
    the parameters required by the model and the values of the dictionary represent
    the components of the dataset.

    So for example when in VAL mode we use the train component to train on, the
    val component to validate and the train_val component for covariates or historical
    forecasts. (Note that we can use train_val for past covariates as the darts model
    automatically slices the provided past covariates timeseries to match the training
    timeseries.)

    In contrast when in TEST mode we use both the training and validation components for
    training, test set for validation, and the entire dataset for historical forecasts
    and covariates.
    """
    VAL = {'train' : 'train', 'val' : 'val', 'train_val' : 'train_val'}
    TEST = {'train' : 'train_val', 'val' : 'test', 'train_val' : 'train_val_test'}
    PROD = {'train' : 'train_val_test', 'val' : 'none', 'train_val' : 'entire'}


class Dataset:
    """Converts saved data into a form suitable for training by a model.

    Slices and prepares the data according to the dictionary of dataset choices. In this class
    we use the following terminology:
        dataset type: to refer to the use of a particular timeseries - either 'train', 'val' or
            'train_val'. Corresponds to the keys of the dictionaries of the TrainingType Enum.
        timeseries type: to refer to a slice of data, e.g., 'train', 'val', 'train_val',
            'test', 'train_val_test', etc. Corresponds to the the values of the dictionaries of
            the TrainingType Enum.

    Attributes:
        training_type: TrainingType for this dataset.
        target_ts_set: air_quality.TimeSeriesSet instance of the target series.
        covariates_ts_set: Dictionary with two keys 'past' and 'future' with the value in each
            case being the corresponding air_quality.TimeSeriesSet of the covariates series.
        dataset_choices: Dictionary of settings that define the dataset:
            training_type: can be one of 'VAL' or 'TEST. This specifies whether we are in
                'validation' or 'test' mode. In 'validation' mode - (used for selecting and tuning
                a model) we train on the 'train' data and validate on the 'validation' data, while
                the 'test' data remains unseen. In 'test' mode we train on 'train' and 'validation'
                data combined, and we validate (for early stopping) on the 'test' data.
            forecast_pollutants: a list of which pollutant(s) to train on.
            covariates_types: which combination of 'past' and 'future' covariates (i.e., weather
                data and/or seasonal time data) to train with. Different models can use different
                types of covariates so this choice is automatically overridden where necessary later
                on. (Forexample, Transformers cannot use future covariates, so a selection of
                'future' would be ignored. This is useful for evaluating which types of covariates
                improve prediction.
            feature_covariates: which combination of covariates types to train on. 'data' means the
                weather data (forecast and historical) while time means seasonal time information
                of hour, day of week, and month. This is useful for evaluating which types of
                covariates improve prediction.
            forecast_pollutants: List of strings of pollutants to be forecasted.
            forecast_locations: List of strings of locations ordered to correspond with the list
                of pollutants in forecast_pollutants.
            ts_target_unscaled: A dictionary with keys of dataset type and values containing lists
                of Darts Timeseries, one for each pollutant being forecasted. The Darts timeseries
                represent the unscaled target series, one for each pollutant being forecasted.
            target_scalers: A list of Scaler instances corresponding to the list of pollutants
                being forecasted. Each Scaler was used to scale the timeseries of the corresponding
                pollutant.
            ts_target_scaled: Equivalent to ts_target_unscaled except that the timeseries have been
                scaled.
            covariates_scalers: A dictionary with two keys 'past' and 'future'. Each value is a
                list of Scaler instances that were used to scale the corresponding timeseries
                for each pollutant being forecasted.
            ts_covariates_unscaled: A dictionary with two keys 'past' and 'future'. Each value is a
                list of Darts Timeseries, one for each pollutant being forecasted. The Darts
                timeseries represent the unscaled covariates data.
            ts_covariates_scaled: Equivalent to ts_covariates_unscaled except that the timeseries
                have been scaled.
            start_time: Pandas timestamp of the start time of all the series.
    """

    def __init__(
        self,
        target_ts_set,
        past_covariates_ts_set,
        future_covariates_ts_set,
        dataset_choices
    ):

        self.training_type = TrainingType[dataset_choices['training_type'].upper()]

        self.target_ts_set = target_ts_set
        self.covariates_ts_set = {
            'past' : past_covariates_ts_set,
            'future' : future_covariates_ts_set
        }
        self.dataset_choices = dataset_choices

        # Set the forecast location according to which pollutant is being analysed
        self.forecast_pollutants = dataset_choices['forecast_pollutants']
        self.forecast_locations = [
            'Marseille' if pollutant == 'SO2' \
                else 'Montpellier' for pollutant in self.forecast_pollutants
        ]

        self.ts_target_unscaled = self._get_unscaled_target_series()
        self.target_scalers = self._get_target_scalers()
        self.ts_target_scaled = self._get_scaled_target_series()

        self.covariates_scalers = {
            'past' : [],
            'future' : []
        }
        self.ts_covariates_unscaled = self._get_unscaled_covariates_series()
        self.ts_covariates_scaled = self._get_scaled_covariates_series()

        # Set start times.
        self.start_time = self._get_start_time()


    def _get_start_time(self):

        start_time = self.ts_target_unscaled['train'][0].start_time()

        start_time_error_msg = 'Start times are not the same.'
        if (
            'past' in self.ts_covariates_unscaled and
            self.ts_covariates_unscaled['past']
        ):
            if self.ts_covariates_unscaled['past'][0].start_time() != start_time:
                raise ValueError(start_time_error_msg)

        if (
            'future' in self.ts_covariates_unscaled and
            self.ts_covariates_unscaled['future']
        ):
            if self.ts_covariates_unscaled['future'][0].start_time() != start_time:
                raise ValueError(start_time_error_msg)

        return start_time


    def _get_unscaled_target_series(self):
        series = {}
        for ds_type, ds_slice in self.training_type.value.items():

            # If type is not being provided, then set to None.
            if ds_slice == 'none':
                series[ds_type] = None
            else:
                series[ds_type] = self.target_ts_set.get_ts_sequence(
                    ds_slice, subset = self.forecast_pollutants
                )
        return series


    def _get_target_scalers(self):

        scalers = []

        # We always fit our scaler to the training data only.
        for ts in self.ts_target_unscaled['train']:
            s = Scaler()
            s.fit(ts)
            scalers.append(s)

        return scalers


    def _get_scaled_target_series(self):

        ts_target_scaled = {}
        for ds_component, ts_sequence_unscaled in self.ts_target_unscaled.items():

            # If this type of unscaled sequence has not been provided, then set
            # scaled to None as well.
            if ts_sequence_unscaled is None:
                ts_target_scaled[ds_component] = None
                continue

            ts_sequence_scaled = []
            scaler_index = 0
            for ts in ts_sequence_unscaled:

                # Get the scaler corresponding to this pollutant.
                s = self.target_scalers[scaler_index]

                # Transform the timeseries and add to the sequence.
                ts_sequence_scaled.append(
                    s.transform(ts)
                )

                scaler_index += 1

            ts_target_scaled[ds_component] = ts_sequence_scaled

        return ts_target_scaled


    def _get_unscaled_time_features_series(self):
        ts_type = self.training_type.value['train_val']
        return self._get_unscaled_time_features_series_by_ts_type(ts_type)


    def _get_unscaled_time_features_series_by_ts_type(self, ts_type):

        target_ts_sequence = self.target_ts_set.get_ts_sequence(ts_type)

        time_index = target_ts_sequence[0].time_index
        ts_time_features = datetime_attribute_timeseries(
            time_index, attribute="hour", one_hot=False)
        ts_time_features = ts_time_features.stack(
            datetime_attribute_timeseries(time_index, attribute="day_of_week", one_hot=False))
        ts_time_features = ts_time_features.stack(
            datetime_attribute_timeseries(time_index, attribute="month", one_hot=False))
        ts_time_features = [ts_time_features.astype(np.float32)] * len(self.forecast_locations)
        return ts_time_features


    def _get_unscaled_data_covariates_series(self):

        ts_type = self.training_type.value['train_val']
        return self._get_unscaled_data_covariates_series_by_ts_type(ts_type)


    def _get_unscaled_data_covariates_series_by_ts_type(self, ts_type):

        covariates_ts_unscaled = {}

        # Fix the end time to be no longer than the end of the equivalent target series.
        # Otherwise our time features series won't match the length of the covariates.
        # TODO Don't rely on NO2 key.
        end_time = self.target_ts_set.ts[ts_type]['NO2'].end_time()

        for cov_type in self.dataset_choices['covariates_types']:

            cov_ts_set = self.covariates_ts_set[cov_type]

            covariates_ts_unscaled[cov_type] = cov_ts_set.get_ts_sequence(
                ts_type, subset = self.forecast_locations, end_time = end_time
            )

        return covariates_ts_unscaled


    def _get_selected_covariates_series(self, data_covariates_series, time_features_series):

        feature_covariates = self.dataset_choices['feature_covariates']
        covariates_types = self.dataset_choices['covariates_types']

        ts_covariates = {
                'past' : None,
                'future' : None
            }

        if feature_covariates == ['data']:
            ts_covariates = data_covariates_series

        elif feature_covariates == ['time']:
            for cov_type in covariates_types:
                ts_covariates[cov_type] = time_features_series

        elif 'time' in feature_covariates and 'data' in feature_covariates:

            for cov_type in covariates_types:
                ts_covariates[cov_type] = self.concatenate_ts_sequences(
                    data_covariates_series[cov_type],
                    time_features_series,
                    axis = 1
                )

        return ts_covariates


    def _get_unscaled_covariates_series(self):
        return self._get_selected_covariates_series(
            self._get_unscaled_data_covariates_series(),
            self._get_unscaled_time_features_series()
        )


    def _get_scaled_covariates_series(self):

        # We must fit the scalers using only the training set.
        # Get the unscaled covariates for the training set.
        unscaled_data_covariates_series_train = \
            self._get_unscaled_data_covariates_series_by_ts_type('train')
        unscaled_time_features_series_train = \
            self._get_unscaled_time_features_series_by_ts_type('train')

        unscaled_ts_covariates_train = self._get_selected_covariates_series(
            unscaled_data_covariates_series_train,
            unscaled_time_features_series_train
        )

        covariates_types = self.dataset_choices['covariates_types']

        ts_covariates_scaled = {
            'past' : None,
            'future' : None
        }


        # For the selected 'past' and/or 'future' covariates...
        for cov_type in covariates_types:

            # Get the unscaled timeseries sequence for the training set - this
            # is what we use to fit the scaler.
            unscaled_ts_sequence_train = unscaled_ts_covariates_train[cov_type]

            # Get the unscaled timeseries sequence for the training and validation set -
            # this is what we want to transform with the scaler..
            unscaled_ts_sequence_train_val = self.ts_covariates_unscaled[cov_type]

            scaled_ts_sequence = []
            ts_sequence_index = 0

            for ts_train in unscaled_ts_sequence_train:

                # Fit the scaler on the training set and store it.
                s = Scaler()
                s.fit(ts_train)
                self.covariates_scalers[cov_type].append(s)

                # Transform the combined training and validation set.
                ts_train_val = unscaled_ts_sequence_train_val[ts_sequence_index]
                scaled_ts_sequence.append(s.transform(ts_train_val))

                ts_sequence_index += 1

            ts_covariates_scaled[cov_type] = scaled_ts_sequence

        return ts_covariates_scaled


    def get_ts_first_last(self, ts, caption = ''):
        """Gets the first and last row of a timeseries dataframe.

        Args:
            ts: TimeSeries instance.
            caption: A string to be used as the caption for the dataframe.

        Returns:
            Pandas dataframe.
        """

        if caption:
            return ts.pd_dataframe().iloc[[0, -1]].style.set_caption(caption)
        else:
            return ts.pd_dataframe().iloc[[0, -1]]


    def get_first_last_covariates(self, scaled = False):
        """Gets the first and last row of the timeseries dataframe for
        each combination of covariate type and pollutant.

        Args:
            scaled: Boolean indicating whether to apply to the scaled timeseries.

        Returns:
            List of Pandas dataframes.
        """

        if scaled:
            ts_covariates = self.ts_covariates_scaled
        else:
            ts_covariates = self.ts_covariates_unscaled

        output_dfs = []

        for covariate_type in self.dataset_choices['covariates_types']:

            ts_sequence = ts_covariates[covariate_type]

            # Convert to list if needed.
            ts_sequence = self.maybe_convert_ts_sequence_to_list(ts_sequence)

            for i in range(len(ts_sequence)):
                output_dfs.append(
                    self.get_ts_first_last(
                        ts_sequence[i],
                        caption = f"{covariate_type}: {self.forecast_pollutants[i]}"
                    )
                )

        return output_dfs


    def get_first_last_target_series(self, scaled = False):
        """Gets the first and last row of the timeseries dataframe for
        each the target series of each pollutant.

        Args:
            scaled: Boolean indicating whether to apply to the scaled timeseries.

        Returns:
            List of Pandas dataframes.
        """

        if scaled:
            ts_target = self.ts_target_scaled
        else:
            ts_target = self.ts_target_unscaled

        output_dfs = []

        for ds_component, ts_sequence in ts_target.items():

            # Convert to list if needed.
            ts_sequence = self.maybe_convert_ts_sequence_to_list(ts_sequence)

            for i in range(len(ts_sequence)):
                output_dfs.append(
                    self.get_ts_first_last(
                        ts_sequence[i],
                        caption = f"{ds_component}: {self.forecast_pollutants[i]}"
                    )
                )

        return output_dfs


    def concatenate_ts_sequences(self, ts_seq, other_ts_seq, axis = 0):
        """Takes two lists of Darts timeseries and performs pair-wise concatenation.

        Args:
            ts_seq: First list of Darts timeseries.
            other_ts_seq: Second list of Darts timeries.
            axis: Integer representing axis along which to concatenate, 0 being time and 1 being
                component.

        Returns:
            List of concatenated Darts Timeseries.
        """

        # Check that sequences are the same length:
        if len(ts_seq) != len(other_ts_seq):
            raise ValueError(
                f"Sequences of different length({len(ts_seq)} and {len(other_ts_seq)})"
            )

        return [ts_seq[i].concatenate(other_ts_seq[i], axis = axis) for i in range(len(ts_seq))]


    @staticmethod
    def maybe_convert_ts_sequence_to_list(ts_sequence):
        """Handles the case when we have only a single timeseries,
        not a list of timeseries, by converting it to a list.

        Args:
            Darts timeseries or a list of Darts Timeseries

        Returns:
            List of Darts timeseries.
        """

        if not isinstance(ts_sequence, list):
            ts_sequence = [ts_sequence.copy()]
        return ts_sequence


    def get_model_input(self):
        """Restructures timeries and dataset data in to a form suitable for initializing a new
        instance of a model.

        Returns:
            Dictionary of dataset and timeseries data with keys corresponding to the parameters
            os a model instance.
        """

        # Extract the forecast pollutants from dataset_choices as they are
        # specified separately.
        additional_model_info = {
            k : v for k, v in self.dataset_choices.items() if k != 'forecast_pollutants'
        }

        return {
            'target_series_unscaled' : self.ts_target_unscaled,
            'target_series' : self.ts_target_scaled,
            'past_covariates' : self.ts_covariates_scaled['past'],
            'future_covariates' : self.ts_covariates_scaled['future'],
            'target_scalers' : self.target_scalers,
            'covariates_scalers' : self.covariates_scalers,
            'target_series_names' : self.dataset_choices['forecast_pollutants'],
            'additional_model_info' : additional_model_info
        }
