# Weather Notifier

A Python-based notifier that checks weather forecasts once a day and sends email alerts when rain is expected in your area.

## Features

- 🌧️ **Rain Detection**: Monitors OpenWeatherMap forecast for rain conditions (drizzle, light rain, heavy rain, thunderstorms, freezing rain)
- 📧 **Email Alerts**: Beautiful HTML email with exact rain times, intensity, chance percentage, and temperature
- 📊 **Detailed Forecast**: Each rain period shows time, rain type, chance (%), and temperature
- 🕐 **Once Daily**: Runs once per day via GitHub Actions (6 AM Bangladesh time by default)
- 🔐 **Secure Configuration**: Environment variables for sensitive data (API keys, passwords)
- 📝 **Comprehensive Logging**: Console + rotating file logs
- 🚀 **GitHub Actions Ready**: Pre-configured workflow for automated daily runs
- 🌍 **Configurable**: Latitude, longitude, timezone, forecast hours, minimum rain chance

## Prerequisites

- Python 3.13 or higher
- OpenWeatherMap API key ([free tier available](https://openweathermap.org/api))
- Email account with SMTP access (Gmail recommended)
- GitHub account (for automated deployment)

## Installation

### Local Setup

1. Clone the repository:
```bash
git clone https://github.com/yourusername/weather-notifier.git
cd weather-notifier
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Create a `config.json` file:
```json
{
    "email": {
        "sender": "your-email@gmail.com",
        "receiver": "receiver-email@gmail.com",
        "sender_name": "Weather Notifier",
        "smtp_server": "smtp.gmail.com",
        "smtp_port": 587
    },
    "weather": {
        "api_key": "your-openweathermap-api-key",
        "latitude": 24.3746,
        "longitude": 88.6004
    },
    "forecast_count": 14,
    "min_pop": 0.3,
    "scheduling": {
        "daily_time": "06:00",
        "timezone": "Asia/Dhaka"
    }
}
```

4. Set the SMTP password as an environment variable:

**Linux/macOS:**
```bash
export WEATHER_NOTIFIER_SMTP_PASSWORD="your-app-password"
```

**Windows (PowerShell):**
```powershell
$env:WEATHER_NOTIFIER_SMTP_PASSWORD="your-app-password"
```

### Running Locally

```bash
# Single check (for cron/GitHub Actions)
python weather_notifier.py --once

# Run as daemon (long-running process)
python weather_notifier.py --daemon

# Dry run (don't actually send email)
python weather_notifier.py --once --dry-run
```

## Configuration Options

| Option | Description | Default |
|--------|-------------|---------|
| `email.sender` | Sender email address | Required |
| `email.receiver` | Recipient email address | Required |
| `email.sender_name` | Display name for sender | "Weather Notifier" |
| `email.smtp_server` | SMTP server address | Required |
| `email.smtp_port` | SMTP server port | Required |
| `weather.api_key` | OpenWeatherMap API key | Required |
| `weather.latitude` | Your location latitude | Required |
| `weather.longitude` | Your location longitude | Required |
| `forecast_count` | Number of forecast periods (3h each) | 14 |
| `min_pop` | Minimum rain chance threshold (0.0-1.0) | 0.3 |
| `scheduling.daily_time` | Time to run daily check (HH:MM) | "06:00" |
| `scheduling.timezone` | IANA timezone name | "UTC" |

### What is `min_pop`?

The **Probability of Precipitation (PoP)** from OpenWeatherMap:

| Value | Meaning |
|-------|---------|
| `0.0` | Alert on any rain chance (even 1%) |
| `0.3` | Alert only if chance is 30% or higher (recommended) |
| `0.5` | Alert only if chance is 50% or higher |
| `0.7` | Alert only if chance is 70% or higher |

### Finding Your Coordinates

1. Go to [latlong.net](https://www.latlong.net/)
2. Search for your city
3. Copy latitude and longitude values

### Getting OpenWeatherMap API Key

1. Go to [OpenWeatherMap](https://openweathermap.org/api)
2. Sign up for a free account
3. Go to API Keys section
4. Copy your API key

### Common Timezones

| Region | Timezone Value |
|--------|---------------|
| Bangladesh | `Asia/Dhaka` |
| USA (Eastern) | `America/New_York` |
| USA (Pacific) | `America/Los_Angeles` |
| UK | `Europe/London` |
| India | `Asia/Kolkata` |
| Japan | `Asia/Tokyo` |
| Australia (Sydney) | `Australia/Sydney` |

## How It Works

1. **Fetch Forecast**: Queries OpenWeatherMap API for forecast
2. **Filter Rain**: Checks for rain condition codes (200-531)
3. **Apply Threshold**: Only includes forecasts with chance >= `min_pop`
4. **Send Alert**: If rain expected, sends email with forecast details

### Rain Condition Codes

| Code Range | Type |
|------------|------|
| 200-232 | Thunderstorm ⛈️ |
| 300-321 | Drizzle 🌦️ |
| 500-504 | Light/Moderate Rain 🌧️ |
| 511 | Freezing Rain 🌨️ |
| 520-531 | Shower Rain 🌧️ |

## Email Format

The email includes:
- 🌧️ Rain alert header with date
- 📍 Your location
- 📊 Each forecast slot with:
  - Time
  - Rain type
  - Chance percentage
  - Temperature
- ☂️ Umbrella reminder
- 🕐 Generation timestamp with timezone

### Example Email Preview:

```
🌧️ Rain Alert for Dhaka: Light rain expected today
─────────────────────────────────────────
📅 Thursday, August 27

6:00 PM   🌧️ Light rain   80%   28°C
9:00 PM   🌧️ Light rain   75%   27°C
12:00 AM  🌧️ Light rain   60%   26°C

☂️ Don't forget an umbrella today.
```

## GitHub Actions Deployment

### Setting Up

1. Fork this repository to your GitHub account.

2. Add these secrets (Settings → Secrets and Variables → Actions):

| Secret | Description |
|--------|-------------|
| `WEATHER_NOTIFIER_EMAIL` | Sender email address |
| `WEATHER_NOTIFIER_RECEIVER` | Recipient email address |
| `WEATHER_NOTIFIER_SMTP_PASSWORD` | Email app password |
| `WEATHER_API_KEY` | OpenWeatherMap API key |
| `LATITUDE` | Your latitude |
| `LONGITUDE` | Your longitude |
| `TIMEZONE` | Your timezone (e.g., "Asia/Dhaka") |

3. The workflow will automatically run **once daily at 6 AM Bangladesh time (midnight UTC)**.

### Manual Trigger

You can manually trigger the workflow:
1. Go to Actions tab in your repository
2. Select "Weather Notifier" workflow
3. Click "Run workflow"

### Changing the Schedule

Edit `.github/workflows/weather-notifier.yml`:

```yaml
on:
  schedule:
    # Change this cron expression
    - cron: "0 0 * * *"   # Midnight UTC = 6 AM Bangladesh
```

| Schedule | Cron Expression | Local Time (Bangladesh) |
|----------|----------------|-------------------------|
| 6 AM | `0 0 * * *` | 6:00 AM |
| 7 AM | `0 1 * * *` | 7:00 AM |
| 8 AM | `0 2 * * *` | 8:00 AM |
| 12 PM | `0 6 * * *` | 12:00 PM |

## Logging

The notifier writes logs to both console and file:

- **Log file**: `weather_notifier.log` (created in same directory)
- **Rotation**: Each file capped at 1 MB; up to 3 backups
- **Format**: `2026-08-27 06:00:00 [INFO] Fetching weather data...`

## Troubleshooting

### Common Issues

1. **"Config file not found"**
   - Ensure `config.json` exists in the project directory

2. **"No SMTP password found"**
   - Set `WEATHER_NOTIFIER_SMTP_PASSWORD` environment variable
   - Or add `password` field to `email` section in config (not recommended)

3. **"Invalid API key"**
   - Verify OpenWeatherMap API key is correct
   - Make sure API key is activated (takes a few minutes after signup)

4. **"No rain expected" despite forecast showing rain**
   - Check `min_pop` setting (default is 30%)
   - Forecast might be below the threshold

5. **"Network error fetching weather data"**
   - Check internet connection
   - OpenWeatherMap might be temporarily unavailable
   - Check if you've exceeded free tier limits (60 calls/minute)

### Viewing Logs

```bash
# Local
cat weather_notifier.log

# GitHub Actions
# Download logs from the workflow run artifacts (if failure)
```

## Project Structure

```
weather-notifier/
├── .github/
│   └── workflows/
│       └── weather-notifier.yml
├── weather_notifier.py
├── config.json              (ignored by git)
├── weather_notifier.log     (generated)
├── requirements.txt
├── README.md
└── .gitignore
```

## Dependencies

```txt
requests==2.32.3
urllib3==2.3.0
tzdata==2024.2
```

- `requests` – HTTP client for OpenWeatherMap API
- `urllib3` – HTTP client utilities
- `tzdata` – Timezone database support (required for timezone formatting)

## Security Notes

- Never commit `config.json` with passwords to version control
- Use environment variables for sensitive data in production
- The `.gitignore` file excludes `config.json` by default
- If you accidentally committed `config.json` with secrets, change them immediately

## License

This project is open source. Feel free to modify and use it as you wish.

## Acknowledgments

- Built with [OpenWeatherMap API](https://openweathermap.org/api)
- Uses [Requests library](https://requests.readthedocs.io/)
- Inspired by the AniList Episode Notifier project

## Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## Support

For issues, bug reports, or feature requests, please use the GitHub Issues section of the repository.
