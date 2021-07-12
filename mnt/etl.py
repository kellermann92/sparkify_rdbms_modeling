import os
import glob
import psycopg2
import pandas as pd
import yaml

def read_file(path: str) -> str:
    """Method to read content of a file.

    Args:
        path (str): path to file.

    Returns:
        str: content of the file.
    """
    with open(path, 'r', encoding='utf8') as file:
        content = file.read()
    return content


def read_setup() -> dict:
    """Method to read setup of a YAML file.

    Returns:
        dict: setup dictionary.
    """
    with open('setup.yaml', 'r', encoding='utf-8') as stream:
        data = yaml.safe_load(stream)
    return data
    

def process_song_file(cur: object, filepath: str, list_query_path: list) -> None:
    """Method to process song files.
    Args:
        cur (object): psycopg cursor.
        filepath (str): path to song files.
    Returns:
        None: Reads song data and creates songs and artists dimension tables on sparkifydb.
    """
    
    list_query = [read_file(x) for x in list_query_path]
    # open song file
    df = pd.read_json(filepath, lines=True)

    # insert song record
    song_data = df[['song_id',
                    'title',
                    'artist_id',
                    'year',
                    'duration']].values[0]
    
    artist_data = df[['artist_id',
                      'artist_name',
                      'artist_location',
                      'artist_longitude',
                      'artist_latitude']].values[0]

    # Insert data into artists table:
    cur.execute(list_query[0], song_data)

    # Insert data into artists table:
    cur.execute(list_query[1], artist_data)
    return None


def prepare_log_df(df: pd.DataFrame) -> pd.DataFrame:
    """Method to prepare dataframe generated by log json files.

    Args:
        df (pd.DataFrame): raw dataframe from log json files.

    Returns:
        pd.DataFrame: dataframe ready to commit to database.
    """

    # Generates time_df
    df_time = pd.DataFrame(df['ts'])

    # Convert ts to datetime:
    df_time['start_time'] = pd.to_datetime(df['ts'], unit='ms')
    df_time['hour'] = df_time.start_time.dt.hour
    df_time['day'] = df_time.start_time.dt.day

    # Day of the week.
    df_time['week'] = df_time.start_time.dt.strftime('%V').astype(int)
    df_time['month'] = df_time.start_time.dt.month
    df_time['year'] = df_time.start_time.dt.year
    df_time['week_day'] = df_time.start_time.dt.weekday

    # drop 'ts' column
    df_time.drop('ts', axis='columns', inplace=True)
    df_user = df[['userId', 'firstName', 'lastName', 'gender', 'level']]
    return df_time, df_user

    
def process_log_file(cur: object, filepath: str, list_query_path: list) -> None:
    """Method to process log files.
    Args:
        cur (object): psycopg2 cursor object.
        filepath (str): path to log files.
    Returns:
        None: get customer events on sparkify and generates time dimension table.
    """
    # open log file
    df = pd.read_json(filepath, lines=True)
    df = df[df.userId != '' ]
    df = df[df.page == 'NextSong']
    list_query = [read_file(x) for x in list_query_path]
 
    df_time, df_user = prepare_log_df(df)
     
    for i, row in df_time.iterrows():
        cur.execute(list_query[0], list(row))
    
    # insert user records
    for i, row in df_user.iterrows():
        cur.execute(list_query[1], row)

    # # insert songplay records
    for index, row in df.iterrows():

        # get songid and artistid from song and artist tables
        cur.execute(list_query[2], (row.artist, row.song, row.length))
        results = cur.fetchone()

        if results:
            songid, artistid = results
            print(results)
        else:
            songid, artistid = None, None

        # insert songplay record
        songplay_data = (pd.to_datetime(row.ts, unit='ms'),
                         int(row.userId),
                         row.level,
                         songid,
                         artistid,
                         row.sessionId,
                         row.location,
                         row.userAgent,)
        
        cur.execute(list_query[3], songplay_data)
    return None


def process_data(setup: dict, key: str, conn: object, func: object) -> None:
    """Walks through all files under filepath and process them.
     Args:
         cur (object): psycopg2 cursor object.
         conn (object): psycopg2 connection object.
         filepath (str): data filepath
         func (object): function to execute over the files.
     Returns:
         None: look for files, process them and load into sparkifydb.
     """
    # get all files matching extension from directory
    filepath = setup[key]['data_path']
    list_query_path = setup[key]['query_path']
    cur = conn.cursor()
    all_files = []
    for root, dirs, files in os.walk(filepath):
        files = glob.glob(os.path.join(root, '*.json'))

        for f in files:
            all_files.append(os.path.abspath(f))

    # get total number of files found
    num_files = len(all_files)
    print('{} files found in {}'.format(num_files, filepath))

    # iterate over files and process
    for i, datafile in enumerate(all_files, 1):
        func(cur, datafile, list_query_path)
        conn.commit()
        print('{}/{} files processed.'.format(i, num_files))
    cur.close()
    return None


def main():
    print(os.getcwd())
    setup = read_setup()
    
    conn = psycopg2.connect(setup['conn_string'])
       
    process_data(setup, 'song_data', conn, func=process_song_file)
    process_data(setup, 'log_data', conn, func=process_log_file)

    conn.close()


if __name__ == "__main__":
    main()
