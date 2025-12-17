# load a pickle file
import pandas as pd


def load_dbg_pkl(file_path):
    """
    Load a pickle file and return the DataFrame.

    :param file_path: Path to the pickle file.
    :return: DataFrame loaded from the pickle file.
    """
    try:
        df = pd.read_pickle(file_path)
        return df
    except Exception as e:
        print(f"Error loading pickle file {file_path}: {e}")
        return None


if __name__ == '__main__':
    # Example usage
    file_path = '/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls/SERV.pkl'  # Replace with your actual file path
    df = load_dbg_pkl(file_path)
    pass
    # print data from index 2023-01-01 to 2023-01-10
    if df is not None:
        print(df.loc['2025-8-01':'2024-11-01'])
    else:
        print("Failed to load DataFrame.")

