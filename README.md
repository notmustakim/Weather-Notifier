# Weather Notifier

A Python-based notifier that checks weather forecasts and sends email alerts when rain is expected in your area.

## Features

- 🌧️ **Rain Detection**: Monitors OpenWeatherMap forecast for rain conditions
- 📧 **Email Alerts**: Sends formatted HTML emails when rain is expected
- 🕒 **Customizable Forecast**: Configurable forecast hours and timezone offset
- 🔐 **Secure Configuration**: Supports environment variables for sensitive data
- 📝 **Comprehensive Logging**: Console + rotating file logs for debugging
- 🚀 **GitHub Actions Ready**: Can be scheduled to run automatically
- 🌍 **Configurable Location**: Set any latitude/longitude

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

3. Create a `config.json` file in the project root:
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
    "forecast_count": 6,
    "timezone_offset": 6
}
```

> **Important**: 
> - Do **not** store your SMTP password in `config.json` (use environment variable instead)
> - Get your API key from [OpenWeatherMap](https://openweathermap.org/api)
> - Find your coordinates at [latlong.net](https://www.latlong.net/)

4. Set the SMTP password as an environment variable:

**Linux/macOS:**
```bash
export WEATHER_NOTIFIER_SMTP_PASSWORD="your-app-password"
```

**Windows (Command Prompt):**
```cmd
set WEATHER_NOTIFIER_SMTP_PASSWORD="your-app-password"
```

**Windows (PowerShell):**
```powershell
$env:WEATHER_NOTIFIER_SMTP_PASSWORD="your-app-password"
```

### Running Locally

```bash
# Single check
python weather_notifier.py --once

# Run and exit after check
python weather_notifier.py
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
| `forecast_count` | Number of forecast periods to check | 6 |
| `timezone_offset` | Hours offset from UTC | 6 |

### Finding Your Coordinates

1. Go to [latlong.net](https://www.latlong.net/)
2. Search for your city
3. Copy the latitude and longitude values
4. Add them to `config.json`

### Getting OpenWeatherMap API Key

1. Go to [OpenWeatherMap](https://openweathermap.org/api)
2. Sign up for a free account
3. Go to API Keys section
4. Copy your API key
5. Add it to `config.json`

## How It Works

1. **Fetch Forecast**: Queries OpenWeatherMap API for weather forecast
2. **Analyze Conditions**: Checks for rain condition codes (500-531)
3. **Send Alert**: If rain is expected, sends email with forecast times
4. **Log Results**: All activity is logged to console and file

### Rain Condition Codes

| Code Range | Description |
|------------|-------------|
| 500-504 | Light to moderate rain |
| 511 | Freezing rain |
| 520-531 | Shower rain |

## Email Format

The email includes:
- 🌧️ Rain alert header
- 📍 Your location
- 🕐 Times when rain is expected
- ☂️ Reminder to bring an umbrella

## Logging

The notifier writes logs to both the console and a file:

- **Log file**: `weather_notifier.log` (created in the same directory)
- **Rotation**: Each log file capped at 1 MB; up to 3 backup files kept
- **Format**: Timestamp, log level, and message

## GitHub Actions Deployment

### Setting Up

1. Fork this repository to your GitHub account.

2. Add the following secrets to your repository (Settings → Secrets and Variables → Actions):
   - `WEATHER_NOTIFIER_EMAIL`: Sender email address
   - `WEATHER_NOTIFIER_RECEIVER`: Recipient email address
   - `WEATHER_NOTIFIER_SMTP_PASSWORD`: Email app password
   - `WEATHER_API_KEY`: OpenWeatherMap API key
   - `LATITUDE`: Your latitude (e.g., 24.3746)
   - `LONGITUDE`: Your longitude (e.g., 88.6004)

3. The workflow will automatically check the weather every 6 hours.

### Manual Workflow Triggers

You can manually trigger the workflow from GitHub Actions:
1. Go to Actions tab in your repository
2. Select "Weather Notifier" workflow
3. Click "Run workflow"

## Email Configuration

For Gmail users:
1. Enable 2-factor authentication on your Google account
2. Generate an app password:
   - Go to Google Account → Security → 2-Step Verification → App passwords
   - Select "Mail" and "Other" (name it "Weather Notifier")
   - Copy the generated 16-character password
   - Use this as the `WEATHER_NOTIFIER_SMTP_PASSWORD` environment variable

## Troubleshooting

### Common Issues

1. **"Config file not found"**
   - Ensure `config.json` exists in the project directory

2. **"No SMTP password found"**
   - Set `WEATHER_NOTIFIER_SMTP_PASSWORD` environment variable
   - Or add `password` field to `email` section in config

3. **"Invalid API key"**
   - Verify your OpenWeatherMap API key is correct
   - Make sure you've activated your API key

4. **"Network error fetching weather data"**
   - Check your internet connection
   - OpenWeatherMap API might be temporarily unavailable
   - Check if you've exceeded free tier limits (60 calls/minute)

5. **No rain alerts despite forecast showing rain**
   - Check your `forecast_count` setting (default is 6 periods of 3 hours = 18 hours)
   - Verify your timezone offset is correct

### State File Issues

If the script doesn't work as expected, check the log file for errors:
```bash
cat weather_notifier.log
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

## Security Notes

- Never commit `config.json` containing passwords to version control
- Use environment variables for sensitive data in production
- The `.gitignore` file excludes `config.json` by default
- If you accidentally committed config.json with secrets, change them immediately

## Dependencies

- `requests` – HTTP client for OpenWeatherMap API
- `urllib3` – HTTP client utilities

## License

This project is open source. Feel free to modify and use it as you wish.

## Acknowledgments

- Built with [OpenWeatherMap API](https://openweathermap.org/api)
- Uses [Requests library](https://requests.readthedocs.io/) for HTTP requests
- Inspired by the AniList Episode Notifier project

## Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## Support

For issues, bug reports, or feature requests, please use the GitHub Issues section of the repository.
