""" This module contains utility functions for processing EMG data.

"""
import os
import time
import pywt
import numpy as np
import pandas as pd
from scipy.signal import find_peaks, peak_widths, butter, filtfilt, hilbert, iirnotch
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

# Define constants for windowing parameters and feature extraction
WINDOW_SIZE = 400
OVERLAP = 200

# Define feature extraction functions
def extract_wavelet_features(emg_data, window_size=WINDOW_SIZE, overlap=OVERLAP):
    features = []
    num_samples, num_channels = emg_data.shape
    print(f"Num samples: {num_samples}, Num channels: {num_channels}")
    step = window_size - overlap

    for start in range(0, num_samples - window_size + 1, step):
        window = emg_data[start:start + window_size]
        window_features = []

        for channel_data in window.T:
            # Apply 2-level wavelet decomposition using dbl mother wavelet
            coeffs = pywt.wavedec(channel_data, 'db4', level=2)

            # Extract 19 statistical features from the detail and approximation coefficients
            # Or pick and choose the features you want to extract
            for coeff in coeffs:
                window_features.extend([
                    np.sum(np.abs(coeff)),  # IEMG
                    np.mean(np.abs(coeff)),  # MAV
                    np.sum(coeff ** 2),  # SSI
                    np.sqrt(np.mean(coeff ** 2)),  # RMS
                    np.var(coeff),  # VAR
                    np.mean(coeff > 0),  # MYOP
                    np.sum(np.abs(np.diff(coeff))),  # WL
                    np.mean(np.abs(np.diff(coeff))),  # DAMV
                    np.sum(coeff ** 2) / len(coeff),  # Second-order moment (M2)
                    np.var(np.diff(coeff)),  # DVARV
                    np.std(np.diff(coeff)),  # DASDV
                    np.sum(np.abs(coeff) > 0.05),  # WAMP (threshold = 0.05)
                    np.sum(np.abs(np.diff(coeff, 2))),  # IASD
                    np.sum(np.abs(np.diff(coeff, 3))),  # IATD
                    np.sum(np.exp(np.abs(coeff))),  # IEAV
                    np.sum(np.log(np.abs(coeff) + 1e-6)),  # IALV
                    np.sum(np.exp(coeff)),  # IE
                    np.min(coeff),  # MIN
                    np.max(coeff)  # MAX
                ])
        features.append(window_features)

    return np.array(features)

def read_config_file(config_file):
    # Dictionary to store the key-value pairs
    config_data = {}

    # Open the TRUECONFIG.txt file and read its contents
    with open(config_file, 'r') as file:
        for line in file:
            # Strip whitespace and ignore empty lines or comments
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            # Split the line into key and value at the first '='
            key, value = line.split('=', 1)
            config_data[key.strip()] = value.strip()

    return config_data

def get_metrics_file(metrics_filepath, verbose=False):
    if os.path.isfile(metrics_filepath):
        if verbose:
            print("Metrics file found.")
        return pd.read_csv(metrics_filepath)
    else:
        print(f"Metrics file not found: {metrics_filepath}. Please correct file path or generate the metrics file.")
        return None

def notch_filter(data, fs=4000, f0=60.0, Q=30):
    """Applies a notch filter to the data to remove 60 Hz interference.
        Assumes data shape (n_channels, n_samples).
    """
    b, a = iirnotch(f0, Q, fs)
    return filtfilt(b, a, data, axis=1)

def butter_bandpass(lowcut, highcut, fs, order=5):
    # butterworth bandpass filter
    nyq = 0.5 * fs
    low = lowcut / nyq
    high = highcut / nyq
    b, a = butter(order, [low, high], btype='band')
    return b, a


def butter_lowpass(cutoff, fs, order=5):
    nyq = 0.5 * fs
    norm_cutoff = cutoff / nyq
    b, a = butter(order, norm_cutoff, btype='low')
    return b, a


def butter_lowpass_filter(data, cutoff, fs, order=5, axis=0):
    b, a = butter_lowpass(cutoff, fs, order)
    y = filtfilt(b, a, data, axis=axis)  # Filter along axis 0 (time axis) for all channels simultaneously
    return y


def butter_bandpass_filter(data, lowcut, highcut, fs, order=5, axis=0):
    # function to implement filter on data
    b, a = butter_bandpass(lowcut, highcut, fs, order=order)
    y = filtfilt(b, a, data, axis=axis)  # Filter channels simultaneously
    return y


def filter_emg(emg_data, filter_type='bandpass', lowcut=30, highcut=500, fs=1259, order=5, verbose=False):
    """
    Applies a bandpass or lowpass filter to EMG data using numpy arrays.

    Args:
        emg_data: Numpy array of shape (num_samples, num_channels) with EMG data.
        filter_type: Type of filter to apply ('bandpass' or 'lowpass').
        lowcut: Low cutoff frequency for the bandpass filter.
        highcut: High cutoff frequency for the bandpass filter.
        fs: Sampling rate of the EMG data.
        order: Filter order.
        verbose: Whether to print progress.

    Returns:
        Filtered data as a numpy array (same shape as input data).
    """
    tic = time.process_time()

    if filter_type == 'bandpass':
        filtered_data = butter_bandpass_filter(emg_data, lowcut, highcut, fs, order)
    elif filter_type == 'lowpass':
        filtered_data = butter_lowpass_filter(emg_data, lowcut, fs, order)

    toc = time.process_time()
    if verbose:
        print(f"Filtering time = {1000 * (toc - tic):.2f} ms")

    # Convert list of arrays to a single 2D numpy array
    filtered_data = np.stack(filtered_data, axis=0)  # Stack along axis 0 (channels)

    return filtered_data


def rectify_emg(emg_data):
    """
    Rectifies EMG data by converting all values to their absolute values.

    Args:
        EMGDataDF: List of numpy arrays or pandas DataFrame items with filtered EMG data.

    Returns:
        rectified_data: List of rectified numpy arrays (same shape as input data).
    """
    rectified_data = np.abs(emg_data)

    return rectified_data


def window_rms(emg_data, window_size=400):
    """
    Apply windowed RMS to each channel in the multi-channel EMG data.

    Args:
        emg_data: Numpy array of shape (num_samples, num_channels).
        window_size: Size of the window for RMS calculation.

    Returns:
        Smoothed EMG data with windowed RMS applied to each channel (same shape as input).
    """
    num_channels, num_samples = emg_data.shape
    rms_data = np.zeros((num_channels, num_samples))

    for i in range(num_channels):
        rms_data[i, :] = window_rms_1D(emg_data[i, :], window_size)

    return rms_data


def window_rms_1D(signal, window_size):
    """
    Compute windowed RMS of the signal.

    Args:
        signal: Input EMG signal.
        window_size: Size of the window for RMS calculation.

    Returns:
        Windowed RMS signal.
    """
    return np.sqrt(np.convolve(signal ** 2, np.ones(window_size) / window_size, mode='same'))

# Root mean square (RMS) calculation
def old_calculate_rms(data, window_size=300):
    """
    Calculate RMS over a window.
    Args:
        data (numpy.ndarray): Filtered EMG data.
        window_size (int): Window size in samples (100 ms * 3000 Hz = 300 samples).
    Returns:
        numpy.ndarray: RMS values for each window.
    """
    n_samples = data.shape[0]
    if n_samples < window_size:
        raise ValueError(f"Insufficient data length ({n_samples}) for the specified window size ({window_size}).")

    n_windows = n_samples // window_size
    if n_windows == 0:
        raise ValueError("Not enough data to create any windows for RMS calculation.")

    rms_values = np.sqrt(np.mean(data[:n_windows * window_size].reshape(n_windows, window_size, -1) ** 2, axis=1))
    return rms_values

def calculate_rms(data, window_size):
    """Calculates RMS features for each channel using non-overlapping windows."""
    n_channels, n_samples = data.shape
    n_windows = n_samples // window_size
    rms_features = np.zeros((n_channels, n_windows))

    for ch in range(n_channels):
        for i in range(n_windows):
            window = data[ch, i * window_size:(i + 1) * window_size]
            rms_features[ch, i] = np.sqrt(np.mean(window ** 2))

    return rms_features  # Shape (n_channels, n_windows)



def common_average_reference(emg_data):
    """
    Applies Common Average Referencing (CAR) to the multi-channel EMG data.

    Args:
        emg_data: 2D numpy array of shape (num_channels, num_samples).

    Returns:
        car_data: 2D numpy array after applying CAR (same shape as input).
    """
    # Compute the common average (mean across all channels at each time point)
    common_avg = np.mean(emg_data, axis=0)  # Shape: (num_samples,)

    # Subtract the common average from each channel
    car_data = emg_data - common_avg  # Broadcast subtraction across channels

    return car_data


def envelope_extraction(data, method='hilbert'):
    if method == 'hilbert':
        analytic_signal = hilbert(data, axis=1)
        envelope = np.abs(analytic_signal)
    else:
        raise ValueError("Unsupported method for envelope extraction.")
    return envelope


def process_emg_pipeline(data, lowcut=30, highcut=500, order=5, window_size=400, verbose=False):
    # Processing steps to match the CNN-ECA methodology
    # https://pmc.ncbi.nlm.nih.gov/articles/PMC10669079/
    # Input data is assumed to have shape (N_channels, N_samples)

    emg_data = data['amplifier_data']  # Extract EMG data
    sample_rate = int(data['frequency_parameters']['board_dig_in_sample_rate'])  # Extract sampling rate

    # Overwrite the first and last second of the data with 0 to remove edge effects
    #emg_data[:, :sample_rate] = 0.0
    emg_data[:, -sample_rate:] = 0.0  # Just first second

    # Apply bandpass filter
    bandpass_filtered = filter_emg(emg_data, 'bandpass', lowcut, highcut, sample_rate, order)

    # Rectify
    #rectified = rectify_emg(bandpass_filtered)
    rectified = bandpass_filtered

    # Apply Smoothing
    #smoothed = window_rms(rectified, window_size=window_size)
    smoothed = envelope_extraction(rectified, method='hilbert')

    return smoothed


def sliding_window(data, window_size, step_size):
    """
    Splits the data into overlapping windows.

    Args:
        data: 2D numpy array of shape (channels, samples).
        window_size: Window size in number of samples.
        step_size: Step size in number of samples.

    Returns:
        windows: List of numpy arrays, each representing a window of data.
    """
    num_channels, num_samples = data.shape
    windows = []

    for start in range(0, num_samples - window_size + 1, step_size):
        window = data[:, start:start + window_size]
        windows.append(window)

    return windows


def apply_pca(data, num_components=8, verbose=False):
    """
    Applies PCA to reduce the number of EMG channels to the desired number of components.

    Args:
        data: 2D numpy array of EMG data (channels, samples) -> (128, 500,000).
        num_components: Number of principal components to reduce to (e.g., 8).

    Returns:
        pca_data: 2D numpy array of reduced EMG data (num_components, samples).
        explained_variance_ratio: Percentage of variance explained by each of the selected components.
    """
    # Step 1: Standardize the data across the channels
    scaler = StandardScaler()
    features_std = scaler.fit_transform(data)  # Standardizing along the channels

    # Step 2: Apply PCA
    pca = PCA(n_components=num_components)
    pca_data = pca.fit_transform(features_std) # Apply PCA on the transposed data

    if verbose:
        print("Original shape:", data.shape)
        print("PCA-transformed data shape:", pca_data.shape)

    # Step 3: Get the explained variance ratio (useful for understanding how much variance is retained)
    explained_variance_ratio = pca.explained_variance_ratio_

    return pca_data, explained_variance_ratio


def apply_gesture_label(df, sampling_rate, data_metrics, start_index_name='Start Index', n_trials_name='N_trials', trial_interval_name='Trial Interval (s)', gesture_name='Gesture'):
    """ Applies the Gesture label to the dataframe and fills in the corresponding gesture labels for samples in the
    dataframe. The gesture labels are extracted from the data_metrics dataframe.
    """

    # Initialize a label column in the dataframe
    #df['Gesture'] = 'Rest'  # Default is 'Rest'

    # Collect the data metrics for the current file
    start_idx = data_metrics[start_index_name]
    print(f"Start index: {start_idx}")
    n_trials = data_metrics[n_trials_name]
    print(f"Number of trials: {n_trials}")
    trial_interval = data_metrics[trial_interval_name]
    print(f"Trial interval: {trial_interval}")
    gesture = data_metrics[gesture_name]
    print(f"Gesture: {gesture}")

    # Iterate over each trial and assign the gesture label to the corresponding samples
    for i in range(n_trials):
        # Get start and end indices for the flex (gesture) and relax
        start_flex = start_idx + i * sampling_rate * trial_interval
        end_flex = start_flex + sampling_rate * trial_interval / 2  # Flex is half of interval

        # Label the flex periods as the gesture
        df.loc[start_flex:end_flex, 'Gesture'] = gesture

    return df

def z_score_norm(data):
    """
    Apply z-score normalization to the input data.

    Args:
        data: 2D numpy array of shape (channels, samples).

    Returns:
        normalized_data: 2D numpy array of shape (channels, samples) after z-score normalization.
    """
    mean = np.mean(data, axis=1)[:, np.newaxis]
    std = np.std(data, axis=1)[:, np.newaxis]
    normalized_data = (data - mean) / std
    return normalized_data



def z_score_norm(data):
    """
    Apply z-score normalization to the input data.

    Args:
        data: 2D numpy array of shape (channels, samples).

    Returns:
        normalized_data: 2D numpy array of shape (channels, samples) after z-score normalization.
    """
    mean = np.mean(data, axis=1)[:, np.newaxis]
    std = np.std(data, axis=1)[:, np.newaxis]
    normalized_data = (data - mean) / std
    return normalized_data

# RMS (Root Mean Square)
def compute_rms(emg_window):
    return np.sqrt(np.mean(emg_window**2))

# WL (Waveform Length)
def compute_wl(emg_window):
    return np.sum(np.abs(np.diff(emg_window)))

# MAS (Median Amplitude Spectrum)
def compute_mas(emg_window):
    fft_values = np.fft.fft(emg_window)
    magnitude_spectrum = np.abs(fft_values)
    return np.median(magnitude_spectrum)

# SampEn (Sample Entropy)
import antropy as ant

def compute_sampen(emg_window, m=2, r=0.2):
    return ant.sample_entropy(emg_window, order=m)

# Extract features for a given EMG window
def extract_features(emg_window):
    """https://link.springer.com/article/10.1007/s00521-019-04142-8"""
    features = [
        compute_rms(emg_window),
        compute_wl(emg_window),
        compute_mas(emg_window),
        compute_sampen(emg_window)
    ]
    return np.array(features)
