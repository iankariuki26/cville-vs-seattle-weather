import os
import json
import logging
import urllib.request
from datetime import datetime
import boto3
from chalice import Chalice, Rate
from boto3.dynamodb.conditions import Key, Attr

# for my logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

app = Chalice(app_name='weather-app')
app.debug = True

# creating my aws resources
dynamodb = boto3.resource('dynamodb')
s3 = boto3.client('s3')

TABLE_NAME = os.environ.get('TABLE_NAME', 'cville-weather-tracking')
S3_BUCKET_NAME = os.environ.get('S3_BUCKET_NAME', 'cville-vs-seattle-weather')

LOCATIONS = {
    "charlottesville": {"lat": 38.0293, "lon": -78.4767, "name": "Charlottesville, VA"},
    "seattle": {"lat": 47.6062, "lon": -122.3321, "name": "Seattle, WA"}
}


# the ingestion pipeline
@app.schedule(Rate(1, unit=Rate.HOURS))
def ingest_weather(event):
    """Ingest weather data for Charlottesville and Seattle into DynamoDB."""
    logger.info("Starting weather ingestion job.")
    
    table = dynamodb.Table(TABLE_NAME)
    current_time = datetime.utcnow().isoformat()
    
    for loc, coords in LOCATIONS.items():
        api_url = f"https://api.open-meteo.com/v1/forecast?latitude={coords['lat']}&longitude={coords['lon']}&current_weather=true"
        
        try:
            req = urllib.request.Request(api_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as response:
                res_data = json.loads(response.read().decode('utf-8'))
                current_weather = res_data.get("current_weather", {})
                temp_c = current_weather.get("temperature")
                wind_speed = current_weather.get("windspeed")
                
                # converting to fahrenheit since it is natively in celsius
                temp_f = round(temp_c * 1.8 + 32, 2) if temp_c is not None else None
                
                item = {
                    'location': loc,
                    'timestamp': current_time,
                    'temperature_celsius': str(temp_c),
                    'temperature_fahrenheit': str(temp_f),
                    'windspeed': str(wind_speed)
                }
                
                table.put_item(Item=item)
                logger.info(f"Successfully ingested data for {loc} at {current_time}")
                
        except Exception as e:
            logger.error(f"Failed to fetch or save weather data for {loc}: {str(e)}", exc_info=True)


# api portion of my project
@app.route('/', methods=['GET'], cors=True)
def index():
    """Zone apex that returns the description and available resources."""
    return {
        "about": "Tracks current weather comparison and trends between Charlottesville, VA, and the hometown of Ian Kariuki, the great city of Seattle, WA.",
        "resources": ["current", "trend", "plot"]
    }


@app.route('/current', methods=['GET'], cors=True)
def current():
    """Returns the point-in-time weather comparison."""
    try:
        table = dynamodb.Table(TABLE_NAME)
        
        # Query the latest record for Charlottesville
        cville_response = table.query(
            KeyConditionExpression=Key('location').eq('charlottesville'),
            ScanIndexForward=False,  # Get the most recent item first
            Limit=1
        )
        
        # Query the latest record for Seattle
        sea_response = table.query(
            KeyConditionExpression=Key('location').eq('seattle'),
            ScanIndexForward=False,  # Get the most recent item first
            Limit=1
        )
        
        cville_items = cville_response.get('Items', [])
        sea_items = sea_response.get('Items', [])
        
        latest_cville = float(cville_items[0]['temperature_fahrenheit']) if cville_items else None
        latest_sea = float(sea_items[0]['temperature_fahrenheit']) if sea_items else None
        
        if latest_cville is not None and latest_sea is not None:
            diff = round(latest_cville - latest_sea, 2)
            direction = "+" if diff >= 0 else ""
            
            return {
                "charlottesville_temp": latest_cville,
                "seattle_temp": latest_sea,
                "temperature_difference": f"{direction}{diff}°F",
                "response": f"Difference of {direction}{diff}°F between Charlottesville and Seattle."
            }
        else:
            return {"response": "Insufficient data to calculate current comparison."}
            
    except Exception as e:
        logger.error(f"Error in /current endpoint: {str(e)}", exc_info=True)
        return {"response": f"Error: {str(e)}"}


@app.route('/trend', methods=['GET'], cors=True)
def trend():
    """Returns the dynamic temperature difference trend between locations over the last 5 hours."""
    try:
        table = dynamodb.Table(TABLE_NAME)
        
        # Query the last 5 records for Charlottesville
        cville_response = table.query(
            KeyConditionExpression=Key('location').eq('charlottesville'),
            ScanIndexForward=False, # Get the most recent items first
            Limit=5
        )
        
        # Query the last 5 records for Seattle
        sea_response = table.query(
            KeyConditionExpression=Key('location').eq('seattle'),
            ScanIndexForward=False,
            Limit=5
        )
        
        cville_items = cville_response.get('Items', [])
        sea_items = sea_response.get('Items', [])
        
        if len(cville_items) > 0 and len(sea_items) > 0:
            # Extract latest values
            latest_cville = float(cville_items[0]['temperature_fahrenheit'])
            latest_sea = float(sea_items[0]['temperature_fahrenheit'])
            
            # Extract oldest values from the window to determine trend direction
            oldest_cville = float(cville_items[-1]['temperature_fahrenheit'])
            oldest_sea = float(sea_items[-1]['temperature_fahrenheit'])
            
            # Calculate changes over the time window
            cville_delta = latest_cville - oldest_cville
            sea_delta = latest_sea - oldest_sea
            
            cville_trend = "warming" if cville_delta > 0 else "cooling" if cville_delta < 0 else "stable"
            sea_trend = "warming" if sea_delta > 0 else "cooling" if sea_delta < 0 else "stable"
            
            current_diff = round(latest_cville - latest_sea, 2)
            direction = "+" if current_diff >= 0 else ""
            
            return {
                "charlottesville_temp": latest_cville,
                "seattle_temp": latest_sea,
                "temperature_difference": f"{direction}{current_diff}°F",
                "charlottesville_trend": f"{cville_trend} ({'+' if cville_delta >= 0 else ''}{round(cville_delta, 2)}°F over {len(cville_items)} hours)",
                "seattle_trend": f"{sea_trend} ({'+' if sea_delta >= 0 else ''}{round(sea_delta, 2)}°F over {len(sea_items)} hours)",
                "response": f"Difference of {direction}{current_diff}°F. Charlottesville is {cville_trend}, and Seattle is {sea_trend}."
            }
        else:
            return {"response": "Insufficient data to calculate trend."}
            
    except Exception as e:
        logger.error(f"Error in /trend endpoint: {str(e)}", exc_info=True)
        return {"response": f"Error: {str(e)}"}

# had help from gemini with the plotting portion
@app.route('/plot', methods=['GET'], cors=True)
def plot():
    """Renders a plot and uploads it to S3, returning the URL."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from datetime import datetime

    try:
        table = dynamodb.Table(TABLE_NAME)

        cville_response = table.query(
            KeyConditionExpression=Key('location').eq('charlottesville'),
            ScanIndexForward=False,
            Limit=24
        )
        sea_response = table.query(
            KeyConditionExpression=Key('location').eq('seattle'),
            ScanIndexForward=False,
            Limit=24
        )

        cville_items = sorted(cville_response.get('Items', []), key=lambda x: x['timestamp'])
        sea_items = sorted(sea_response.get('Items', []), key=lambda x: x['timestamp'])

        cville_times = [datetime.fromisoformat(i['timestamp']) for i in cville_items]
        cville_temps = [float(i['temperature_fahrenheit']) for i in cville_items]

        sea_times = [datetime.fromisoformat(i['timestamp']) for i in sea_items]
        sea_temps = [float(i['temperature_fahrenheit']) for i in sea_items]

        fig, ax = plt.subplots(figsize=(10, 5))
        ax.plot(cville_times, cville_temps, label='Charlottesville', color='steelblue')
        ax.plot(sea_times, sea_temps, label='Seattle', color='darkorange')

        ax.set_title("Temperature Over Time (Last 24 Hours)")
        ax.set_xlabel("Time (UTC)")
        ax.set_ylabel("Temp (°F)")
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d %H:%M'))
        fig.autofmt_xdate(rotation=45)
        ax.legend()
        ax.grid(True, alpha=0.3)

        file_path = '/tmp/temp_trend.png'
        plt.savefig(file_path, bbox_inches='tight')
        plt.close()

        s3_key = 'dp3/plots/latest.png'
        s3.upload_file(file_path, S3_BUCKET_NAME, s3_key)

        s3_url = f"https://{S3_BUCKET_NAME}.s3.amazonaws.com/{s3_key}"
        return {"response": s3_url}

    except Exception as e:
        logger.error(f"Error generating or saving plot: {str(e)}", exc_info=True)
        return {"response": f"Error generating plot: {str(e)}"}