# Weather datasets

POST /api/v1/weather/datasets/import accepts JSON content containing an array of records, or CSV content with a header. Required columns: timestamp (timezone-aware ISO8601), latitude, longitude. Wind in m/s, wave height in metres; empty values remain null. Maximum 5 MiB and 20,000 rows. Duplicate coordinates/timestamps are rejected atomically. Uploaded source names/URLs are user declarations, marked uploaded_unverified and never fetched.

POST /api/v1/weather/datasets/fetch uses fixed Open-Meteo endpoints for archive or forecast, at most 31 days. Archives are reanalysis, not station observations or forecasts available at historical decision time. Actual grid coordinates, requested coordinates, retrieval time, source URL and SHA256 of normalized records are retained. Precipitation is a one-hour amount. No wave field is fabricated. Free hosted Open-Meteo usage is subject to its noncommercial terms: https://open-meteo.com/en/terms and https://open-meteo.com/en/docs/historical-weather-api .

GET /datasets and /datasets/{id} enforce account ownership (root may inspect). POST /datasets/{id}/resolve chooses nearest timestamp within 3 hours and position within 25 km; no temporal extrapolation. Missing wind/waves produces status missing with named gaps. These are selection tolerances, not an assertion of navigational safety.

A real 24-hour archive fetch for 2024-01-01 is included in contracts/examples/open_meteo_archive_real.json. Provider wave/Copernicus credentials, storm bulletin ingestion and AIS/port schedules are not implemented by this adapter. Such inputs can be normalized to the import contract with their attribution; uploaded provenance remains unverified.
