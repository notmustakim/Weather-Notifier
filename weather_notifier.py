"""
Weather Notifier
-----------------
Fetches weather forecast data and sends email alerts when rain is expected.

Features:
  - Real logging (console + rotating file)
  - Config file support (config.json)
  - Environment variables for sensitive data
  - Configurable location, forecast hours, and timezone
  - HTML email with clean formatting
"""

import json
import logging
import os
import smtplib
import sys
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class ConfigError(Exception):
    pass


class WeatherNotifier:
    def __init__(self, config_file: str = "config.json"):
        self.logger = self._setup_logging()
        self.config = self._load_config(config_file)
        self._apply_config()
        self.session = self._build_session()

    # ---- setup ------------------------------------------------------------- #

    def _setup_logging(self) -> logging.Logger:
        logger = logging.getLogger("weather_notifier")
        logger.setLevel(logging.INFO)
        logger.handlers.clear()

        fmt = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s",
            "%Y-%m-%d %H:%M:%S"
        )

        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(fmt)
        logger.addHandler(console)

        file_handler = RotatingFileHandler(
            "weather_notifier.log",
            maxBytes=1_000_000,
            backupCount=3
        )
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)

        return logger

    def _load_config(self, config_file: str) -> dict:
        path = Path(config_file)

        if not path.exists():
            raise ConfigError(
                f"Config file not found: {config_file}"
            )

        try:
            with open(path, "r") as f:
                config = json.load(f)

        except json.JSONDecodeError as e:
            raise ConfigError(
                f"Config file is not valid JSON: {e}"
            ) from e

        required = {
            "email": [
                "sender",
                "receiver",
                "smtp_server",
                "smtp_port"
            ],
            "weather": [
                "api_key",
                "latitude",
                "longitude"
            ],
        }

        for section, keys in required.items():
            if section not in config:
                raise ConfigError(
                    f"Missing required config section: '{section}'"
                )

            for key in keys:
                if key not in config[section]:
                    raise ConfigError(
                        f"Missing required config key: "
                        f"'{section}.{key}'"
                    )

        return config

    def _apply_config(self) -> None:
        email_cfg = self.config["email"]

        self.email_sender = email_cfg["sender"]

        # Prefer environment variable for password.
        self.email_password = os.environ.get(
            "WEATHER_NOTIFIER_SMTP_PASSWORD",
            email_cfg.get("password")
        )

        if not self.email_password:
            raise ConfigError(
                "No SMTP password found. Set it in config.json under "
                "email.password, or export "
                "WEATHER_NOTIFIER_SMTP_PASSWORD."
            )

        self.email_receiver = email_cfg["receiver"]
        self.smtp_server = email_cfg["smtp_server"]
        self.smtp_port = email_cfg["smtp_port"]

        self.sender_name = email_cfg.get(
            "sender_name",
            "Weather Notifier"
        )

        weather_cfg = self.config["weather"]

        self.api_key = weather_cfg["api_key"]
        self.latitude = weather_cfg["latitude"]
        self.longitude = weather_cfg["longitude"]

        self.forecast_count = self.config.get(
            "forecast_count",
            6
        )

        self.timezone_offset = self.config.get(
            "timezone_offset",
            6
        )

        self.weather_endpoint = "https://api.openweathermap.org/data/2.5/forecast"

    def _build_session(self) -> requests.Session:
        session = requests.Session()

        retries = Retry(
            total=3,
            backoff_factor=1.0,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
            respect_retry_after_header=True,
        )

        adapter = HTTPAdapter(max_retries=retries)
        session.mount("https://", adapter)
        session.mount("http://", adapter)

        return session

    # ---- weather API ------------------------------------------------------- #

    def fetch_weather_data(self) -> dict | None:
        params = {
            "lat": self.latitude,
            "lon": self.longitude,
            "appid": self.api_key,
            "units": "metric",
            "cnt": self.forecast_count,
        }

        try:
            self.logger.info(
                f"Fetching weather data for "
                f"{self.latitude}, {self.longitude}..."
            )

            response = self.session.get(
                self.weather_endpoint,
                params=params,
                timeout=30
            )

            response.raise_for_status()
            data = response.json()

            self.logger.info(
                f"Successfully fetched weather data "
                f"({len(data.get('list', []))} forecasts)"
            )

            return data

        except requests.exceptions.RequestException as e:
            self.logger.error(f"Network error fetching weather data: {e}")
            return None

        except ValueError as e:
            self.logger.error(f"Invalid JSON response: {e}")
            return None

    # ---- analysis ---------------------------------------------------------- #

    def analyze_weather_conditions(self, weather_data: dict) -> tuple[bool, list[str]]:
        rain_times = []

        if not weather_data or "list" not in weather_data:
            self.logger.error("Invalid weather data received")
            return False, rain_times

        for hour_data in weather_data["list"]:
            weather_id = hour_data["weather"][0]["id"]

            # Rain condition codes: 500-531
            if 500 <= weather_id <= 531:
                time_str = hour_data["dt_txt"]
                rain_times.append(time_str)

        will_rain = len(rain_times) > 0

        if will_rain:
            self.logger.info(f"Rain expected at {len(rain_times)} time(s)")
        else:
            self.logger.info("No rain expected")

        return will_rain, rain_times

    # ---- email formatting -------------------------------------------------- #

    def prepare_email_content(self, will_rain: bool, rain_times: list[str]) -> tuple[str | None, str | None]:
        if not will_rain:
            return None, None

        subject = "🌧️ Rain Alert: Bring an Umbrella!"

        # Convert UTC times to local time with timezone offset
        time_list_html = "".join(
            f"<li>{(datetime.strptime(t, '%Y-%m-%d %H:%M:%S') + timedelta(hours=self.timezone_offset)).strftime('%I:%M %p')}</li>"
            for t in rain_times
        )

        timezone_label = f"UTC+{self.timezone_offset}" if self.timezone_offset >= 0 else f"UTC{self.timezone_offset}"

        html_template = f"""\
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif;
            background-color: #f4f4f4;
            padding: 20px;
            margin: 0;
        }}
        .container {{
            background-color: #ffffff;
            padding: 24px 30px;
            border-radius: 12px;
            max-width: 550px;
            margin: 30px auto;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
            border-top: 5px solid #3b82f6;
        }}
        h2 {{
            color: #1e293b;
            text-align: center;
            margin-top: 0;
        }}
        .emoji-large {{
            font-size: 48px;
            text-align: center;
            display: block;
            margin: 10px 0;
        }}
        ul {{
            padding-left: 20px;
            color: #475569;
            list-style-type: none;
            padding: 0;
        }}
        li {{
            padding: 10px 14px;
            margin-bottom: 8px;
            background: #f8fafc;
            border-radius: 8px;
            font-size: 16px;
            border-left: 4px solid #3b82f6;
        }}
        .location {{
            text-align: center;
            color: #64748b;
            font-size: 14px;
            margin-bottom: 16px;
        }}
        .footer {{
            text-align: center;
            margin-top: 25px;
            font-size: 12px;
            color: #94a3b8;
            border-top: 1px solid #e2e8f0;
            padding-top: 16px;
        }}
        .badge {{
            display: inline-block;
            background: #dbeafe;
            color: #1e40af;
            padding: 4px 12px;
            border-radius: 999px;
            font-size: 12px;
            font-weight: 600;
        }}
    </style>
</head>
<body>
    <div class="container">
        <span class="emoji-large">🌧️</span>
        <h2>Rain Expected Today</h2>
        <div class="location">
            📍 {self.latitude}, {self.longitude}
            <span class="badge">Next {len(rain_times)} hour(s)</span>
        </div>
        <p style="color: #475569;">Rain is expected at the following times:</p>
        <ul>{time_list_html}</ul>
        <p style="color: #475569; font-weight: 600;">☂️ Don't forget to take an umbrella!</p>
        <div class="footer">
            This is an automated alert from Weather Notifier<br>
            Times are in {timezone_label}
        </div>
    </div>
</body>
</html>
        """

        return subject, html_template

    # ---- email sending ----------------------------------------------------- #

    def send_email(self, subject: str, html_content: str) -> bool:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = formataddr((self.sender_name, self.email_sender))
            msg["To"] = self.email_receiver

            # Create plain text version
            text_content = html_content.replace("<li>", "- ").replace("</li>", "\n")
            text_content = text_content.replace("<h2>", "").replace("</h2>", "\n")
            text_content = text_content.replace("<p>", "").replace("</p>", "\n")
            text_content = text_content.replace("</div>", "").replace("</style>", "")
            text_content = text_content.replace("<style>", "").replace("</style>", "")
            text_content = text_content.replace("<body>", "").replace("</body>", "")
            text_content = text_content.replace("<html>", "").replace("</html>", "")
            text_content = text_content.replace("<head>", "").replace("</head>", "")
            text_content = text_content.replace("<ul>", "").replace("</ul>", "")
            text_content = text_content.replace("<li>", "- ").replace("</li>", "\n")
            text_content = text_content.replace("<div>", "").replace("</div>", "")
            text_content = text_content.replace("<span>", "").replace("</span>", "")
            text_content = text_content.replace('<span class="badge">', "").replace('</span>', "")
            text_content = text_content.replace('<span class="emoji-large">', "").replace('</span>', "")
            text_content = text_content.replace('<div class="container">', "").replace('</div>', "")
            text_content = text_content.replace('<div class="location">', "").replace('</div>', "")
            text_content = text_content.replace('<div class="footer">', "").replace('</div>', "")
            text_content = text_content.replace('<br>', "\n").strip()

            # Clean up extra whitespace
            text_content = "\n".join(line.strip() for line in text_content.split("\n") if line.strip())

            msg.attach(MIMEText(text_content, "plain"))
            msg.attach(MIMEText(html_content, "html"))

            with smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=30) as server:
                server.starttls()
                server.login(self.email_sender, self.email_password)
                server.send_message(msg)

            self.logger.info(f"Weather alert email sent successfully to {self.email_receiver}")
            return True

        except smtplib.SMTPAuthenticationError as e:
            self.logger.error(f"SMTP Authentication Error: {e}")
            return False

        except smtplib.SMTPException as e:
            self.logger.error(f"SMTP error: {e}")
            return False

        except Exception as e:
            self.logger.error(f"Unexpected error sending email: {e}")
            return False

    # ---- main cycle -------------------------------------------------------- #

    def check_and_notify(self) -> None:
        self.logger.info("Checking weather forecast...")

        weather_data = self.fetch_weather_data()

        if not weather_data:
            self.logger.warning("Failed to fetch weather data")
            return

        will_rain, rain_times = self.analyze_weather_conditions(weather_data)

        if not will_rain:
            self.logger.info("No rain expected. No email sent.")
            return

        subject, html_body = self.prepare_email_content(will_rain, rain_times)

        if subject and html_body:
            self.logger.info(f"Rain expected. Sending email alert...")
            self.send_email(subject, html_body)
        else:
            self.logger.warning("Failed to prepare email content")

    def run_once(self) -> None:
        self.check_and_notify()

    def run(self) -> None:
        self.logger.info("=" * 60)
        self.logger.info("Weather Notifier starting")
        self.logger.info(f"From: {self.sender_name} <{self.email_sender}>")
        self.logger.info(f"To: {self.email_receiver}")
        self.logger.info(f"Location: {self.latitude}, {self.longitude}")
        self.logger.info(f"Forecast hours: {self.forecast_count}")
        self.logger.info("=" * 60)

        self.check_and_notify()

        self.logger.info("Done.")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Weather notifier"
    )

    parser.add_argument(
        "--config",
        default="config.json",
        help="Path to config.json"
    )

    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single check and exit"
    )

    args = parser.parse_args()

    try:
        notifier = WeatherNotifier(args.config)
    except ConfigError as e:
        print(f"Config error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.once:
        notifier.run_once()
    else:
        notifier.run()


if __name__ == "__main__":
    main()
