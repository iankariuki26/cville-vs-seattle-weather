# DS5220 Data Project 3 — Charlottesville vs. Seattle Weather Tracker

**Ian Kariuki**

---

## Data Source

This project tracks real-time weather conditions for two cities — Charlottesville, VA and Seattle, WA — using the [Open-Meteo API](https://open-meteo.com/). Open-Meteo is a free, open-source weather API that requires no authentication and provides current conditions including temperature and wind speed.

I chose this data source because I wanted to do a simple comparison of two live data sources. A weather comparison between my hometown of Seattle, WA and my current abode in Charlottesville, VA seemed amusing to me, and so that's what I pursued. 

---

## Sampling Cadence & Storage Schema

The ingestion Lambda runs on a **1-hour schedule** via a CloudWatch rate rule, fetching current conditions for both cities on every invocation.

Data is stored in **DynamoDB** in a table named `cville-weather-tracking` with the following schema:

| Attribute | Type | Description |
|---|---|---|
| `location` | String (Partition Key) | `"charlottesville"` or `"seattle"` |
| `timestamp` | String (Sort Key) | ISO 8601 UTC datetime |
| `temperature_celsius` | String | Raw temperature from API |
| `temperature_fahrenheit` | String | Converted value (°C × 1.8 + 32) |
| `windspeed` | String | Wind speed in km/h |

Each city produces one record per hour, yielding 2 records per invocation and 48 records per day across both locations.

---

## API Resources

The API is deployed via AWS Chalice and accessible at:
`https://76gyiem4p5.execute-api.us-east-1.amazonaws.com/api`

It is registered with the course Discord bot under project ID `cville-vs-hometown`.

---

### `GET /` — Zone Apex

Returns a description of the project and a list of available resources.

```json
{
  "about": "Tracks current weather comparison and trends between Charlottesville, VA, and the hometown of Ian Kariuki, the great city of Seattle, WA.",
  "resources": ["current", "trend", "plot"]
}
```

---

### `GET /current` — Point-in-Time Comparison

Queries the most recent record for each city from DynamoDB and returns the current temperatures along with the difference between them.

```json
{
  "charlottesville_temp": 74.3,
  "seattle_temp": 61.2,
  "temperature_difference": "+13.1°F",
  "response": "Difference of +13.1°F between Charlottesville and Seattle."
}
```

---

### `GET /trend` — 5-Hour Rolling Trend

Queries the last 5 records for each city and computes whether each city is warming, cooling, or stable over that window, along with the magnitude of change.

```json
{
  "charlottesville_temp": 74.3,
  "seattle_temp": 61.2,
  "temperature_difference": "+13.1°F",
  "charlottesville_trend": "warming (+2.1°F over 5 hours)",
  "seattle_trend": "cooling (-0.8°F over 5 hours)",
  "response": "Difference of +13.1°F. Charlottesville is warming, and Seattle is cooling."
}
```

---

### `GET /plot` — Temperature Time Series

Queries the last 24 hourly records for each city, generates a matplotlib line chart with real UTC timestamps on the x-axis, uploads it to S3, and returns the public URL.

```json
{
  "response": "https://cville-vs-seattle-weather.s3.amazonaws.com/dp3/plots/latest.png"
}
```

---

## Architecture

| Component | Description |
|---|---|
| **CloudWatch Rate Rule** | Fires the ingestion Lambda every hour |
| **Ingest Lambda** | Fetches weather from Open-Meteo and writes to DynamoDB |
| **DynamoDB** | Stores timestamped weather records for both cities |
| **API Lambda (Chalice)** | Exposes `/current`, `/trend`, and `/plot` over API Gateway |
| **S3** | Stores the publicly readable plot image at a stable key |