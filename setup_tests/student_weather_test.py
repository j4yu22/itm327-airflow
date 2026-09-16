#%%
import os
import sys
import logging
from datetime import datetime, timedelta

# you may need to install these packages in your environment:
# pip install git+https://github.com/m0rp43us/openmeteopy

# Add the 'dags' directory to the system path so we can import 'libs'
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dags"))

from libs.openmeteopy.client import OpenMeteo
from libs.openmeteopy.options.historical import HistoricalOptions
from libs.openmeteopy.daily.historical import DailyHistorical

# Logging setup (similar to sftp_test.py)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s"
)
logger = logging.getLogger(__name__)

def run_weather_test():
    logger.info("Starting Open-Meteo API Connectivity Test...")

    # 1. Setup Date (Yesterday)
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    logger.info(f"Target Date: {yesterday}")

    # 2. Setup Location (New York City) & Parameters
    lat, lon = 40.7128, -74.0060
    
    daily = DailyHistorical()
    daily.temperature_2m_max()
    daily.temperature_2m_min()
    daily.precipitation_sum()
    daily.windspeed_10m_max()

    options = HistoricalOptions(
        latitude=lat,
        longitude=lon,
        start_date=yesterday,
        end_date=yesterday,
    )
    # Manually attach params (library quirk)
    options.daily_params = daily.daily_params

    # 3. Connect and Fetch
    try:
        logger.info("Connecting to Open-Meteo API...")
        om = OpenMeteo(options, daily=daily)
        om._fetch()
        
        # The library returns a tuple (hourly, daily) or just dataframe depending on what was asked
        # Since we only asked for daily, we check the return
        result = om.get_pandas()
        
        if isinstance(result, tuple):
            df = result[1]
        else:
            df = result

        if df is None or df.empty:
            logger.warning("⚠️ No data received.")
            return

        logger.info("✅ Connection successful. Data received.")
        print(df.head())

        # 4. Save to CSV
        output_file = os.path.join(os.path.dirname(__file__), "weather_test.csv")
        df.to_csv(output_file)
        logger.info(f"✅ Data saved to: {output_file}")

    except Exception as e:
        logger.error(f"❌ API Connection failed: {e}")

if __name__ == "__main__":
    run_weather_test()