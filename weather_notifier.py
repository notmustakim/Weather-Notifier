"""
Weather Notifier
-----------------
Fetches weather forecast data once a day (early morning by default) and
sends an email alert if rain is expected at any point that calendar day.

Features:
  - Real logging (console + rotating file)
  - Config file support (config.json) with environment-variable overrides
  - Retry logic for both the weather API and SMTP send
  - Runs once per day at a configurable local time (default 6:00 AM),
    and covers the *entire* calendar day's forecast, not just the next 24h
  - Exact forecast slot times shown for each rain period, with intensity & chance
  - Responsive, table-based HTML email that renders correctly in Outlook/Gmail

Deployment note: two ways to get the "once a day" behavior:
  1. Recommended - external scheduler + `--once`: e.g. a Render.com Cron Job
     (or a plain OS cron entry) that runs `python weather_notifier.py --once`
     once a day. Cheaper (no long-lived process) and simpler to reason about.
  2. Built-in scheduler + `--daemon`: run as a long-lived process (e.g. a
     Render Background Worker) that sleeps until the configured daily_time
     each day, in the configured timezone, then checks and exits back to sleep.
"""

from __future__ import annotations

import json
import logging
import os
import smtplib
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class ConfigError(Exception):
    pass


# Weather condition id -> (emoji, human label, accent color). See OpenWeatherMap condition codes.
CONDITION_LOOKUP = [
    (200, 232, "⛈️", "Thunderstorm", "#7c3aed"),
    (300, 321, "🌦️", "Drizzle", "#38bdf8"),
    (500, 501, "🌧️", "Light rain", "#3b82f6"),
    (502, 504, "🌧️", "Moderate/heavy rain", "#1d4ed8"),
    (511, 511, "🌨️", "Freezing rain", "#ef4444"),
    (520, 531, "🌧️", "Shower rain", "#6366f1"),
]


def classify_condition(weather_id: int) -> tuple[str, str, str]:
    for lo, hi, emoji, label, color in CONDITION_LOOKUP:
        if lo <= weather_id <= hi:
            return emoji, label, color
    return "🌧️", "Rain", "#3b82f6"


@dataclass
class RainPeriod:
    time: datetime
    emoji: str
    label: str
    pop: float  # 0-1 probability of precipitation
    color: str
    temp_c: float | None = None

    def time_str(self) -> str:
        return self.time.strftime("%-I:%M %p") if os.name != "nt" else self.time.strftime("%I:%M %p").lstrip("0")


class WeatherNotifier:
    def __init__(self, config_file: str = "config.json", dry_run: bool = False):
        self.dry_run = dry_run
        self.logger = self._setup_logging()
        self.config = self._load_config(config_file)
        self._apply_config()
        self.session = self._build_session()

    # ---- setup ------------------------------------------------------------- #

    def _setup_logging(self) -> logging.Logger:
        logger = logging.getLogger("weather_notifier")
        level_name = os.environ.get("WEATHER_NOTIFIER_LOG_LEVEL", "INFO").upper()
        logger.setLevel(getattr(logging, level_name, logging.INFO))
        logger.handlers.clear()

        fmt = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s",
            "%Y-%m-%d %H:%M:%S"
        )

        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(fmt)
        logger.addHandler(console)

        try:
            file_handler = RotatingFileHandler(
                "weather_notifier.log",
                maxBytes=1_000_000,
                backupCount=3
            )
            file_handler.setFormatter(fmt)
            logger.addHandler(file_handler)
        except OSError as e:
            # Read-only filesystem (e.g. some PaaS environments) - console logging still works.
            logger.warning(f"Could not open log file, continuing with console logging only: {e}")

        return logger

    def _load_config(self, config_file: str) -> dict:
        path = Path(config_file)

        if not path.exists():
            raise ConfigError(f"Config file not found: {config_file}")

        try:
            with open(path, "r") as f:
                config = json.load(f)
        except json.JSONDecodeError as e:
            raise ConfigError(f"Config file is not valid JSON: {e}") from e

        required = {
            "email": ["sender", "receiver", "smtp_server", "smtp_port"],
            "weather": ["latitude", "longitude"],
        }

        for section, keys in required.items():
            if section not in config:
                raise ConfigError(f"Missing required config section: '{section}'")
            for key in keys:
                if key not in config[section]:
                    raise ConfigError(f"Missing required config key: '{section}.{key}'")

        return config

    def _env_override(self, env_var: str, fallback: Any) -> Any:
        """Environment variables always win over config.json for secrets/overridable values."""
        return os.environ.get(env_var, fallback)

    def _apply_config(self) -> None:
        email_cfg = self.config["email"]

        self.email_sender = self._env_override("WEATHER_NOTIFIER_SENDER", email_cfg["sender"])

        self.email_password = self._env_override(
            "WEATHER_NOTIFIER_SMTP_PASSWORD", email_cfg.get("password")
        )
        if not self.email_password:
            raise ConfigError(
                "No SMTP password found. Set it in config.json under "
                "email.password, or export WEATHER_NOTIFIER_SMTP_PASSWORD "
                "(recommended - never commit real passwords to config.json)."
            )

        receiver_cfg = self._env_override("WEATHER_NOTIFIER_RECEIVER", email_cfg["receiver"])
        # Support a single address or a comma-separated list, from config or env.
        if isinstance(receiver_cfg, str):
            self.email_receivers = [r.strip() for r in receiver_cfg.split(",") if r.strip()]
        else:
            self.email_receivers = list(receiver_cfg)

        self.smtp_server = self._env_override("WEATHER_NOTIFIER_SMTP_SERVER", email_cfg["smtp_server"])
        self.smtp_port = int(self._env_override("WEATHER_NOTIFIER_SMTP_PORT", email_cfg["smtp_port"]))
        self.sender_name = email_cfg.get("sender_name", "Weather Notifier")

        weather_cfg = self.config["weather"]
        self.api_key = self._env_override("WEATHER_NOTIFIER_API_KEY", weather_cfg.get("api_key"))
        if not self.api_key:
            raise ConfigError(
                "No weather API key found. Set it in config.json under "
                "weather.api_key, or export WEATHER_NOTIFIER_API_KEY."
            )

        try:
            self.latitude = float(weather_cfg["latitude"])
            self.longitude = float(weather_cfg["longitude"])
        except (TypeError, ValueError) as e:
            raise ConfigError(f"latitude/longitude must be numeric: {e}") from e

        if not (-90 <= self.latitude <= 90 and -180 <= self.longitude <= 180):
            raise ConfigError("latitude/longitude out of valid range")

        # 14 * 3h = 42h lookahead - generous buffer so that even a 6 AM run has
        # forecast data through the end of that same calendar day; entries
        # outside "today" get filtered out in analyze_weather_conditions().
        self.forecast_count = int(self.config.get("forecast_count", 14))
        self.min_pop = float(self.config.get("min_pop", 0.0))  # ignore forecasts below this rain chance
        self.weather_endpoint = "https://api.openweathermap.org/data/2.5/forecast"

        scheduling_cfg = self.config.get("scheduling", {})
        self.daily_time_str = self._env_override(
            "WEATHER_NOTIFIER_DAILY_TIME", scheduling_cfg.get("daily_time", "06:00")
        )
        try:
            hh, mm = self.daily_time_str.split(":")
            self.daily_hour, self.daily_minute = int(hh), int(mm)
            if not (0 <= self.daily_hour <= 23 and 0 <= self.daily_minute <= 59):
                raise ValueError
        except ValueError as e:
            raise ConfigError(
                f"scheduling.daily_time must be 'HH:MM' 24-hour format, got: {self.daily_time_str!r}"
            ) from e

        tz_name = self._env_override("WEATHER_NOTIFIER_TIMEZONE", scheduling_cfg.get("timezone", "UTC"))
        try:
            self.schedule_tz = ZoneInfo(tz_name)
        except ZoneInfoNotFoundError as e:
            raise ConfigError(
                f"scheduling.timezone {tz_name!r} is not a recognized IANA timezone "
                f"(e.g. 'Asia/Dhaka', 'UTC')."
            ) from e

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
            self.logger.info(f"Fetching weather data for {self.latitude}, {self.longitude}...")
            response = self.session.get(self.weather_endpoint, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            self.logger.info(f"Successfully fetched weather data ({len(data.get('list', []))} forecasts)")
            return data
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Network error fetching weather data: {e}")
            return None
        except ValueError as e:
            self.logger.error(f"Invalid JSON response: {e}")
            return None

    # ---- analysis ---------------------------------------------------------- #

    def analyze_weather_conditions(self, weather_data: dict) -> list[RainPeriod]:
        """Returns one RainPeriod per exact forecast slot where rain is expected."""
        if not weather_data or "list" not in weather_data:
            self.logger.error("Invalid weather data received")
            return []

        # Use the API's own local-time offset for this location rather than a config guess.
        tz_offset_seconds = weather_data.get("city", {}).get("timezone", 0)
        local_tz = timezone(timedelta(seconds=tz_offset_seconds))
        self.local_tz = local_tz
        self.city_name = weather_data.get("city", {}).get("name")

        # "Today" in the *location's* local time - covers the whole calendar day
        # regardless of what time the script actually runs (e.g. a 6 AM run still
        # picks up an 9 PM thunderstorm later that same day).
        target_date: date = datetime.now(timezone.utc).astimezone(local_tz).date()

        periods: list[RainPeriod] = []
        for entry in weather_data["list"]:
            weather_id = entry["weather"][0]["id"]
            pop = float(entry.get("pop", 0.0))
            dt_utc = datetime.strptime(entry["dt_txt"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            dt_local = dt_utc.astimezone(local_tz)

            if dt_local.date() != target_date:
                continue
            if 200 <= weather_id <= 531 and pop >= self.min_pop:
                emoji, label, color = classify_condition(weather_id)
                temp_c = entry.get("main", {}).get("temp")
                periods.append(RainPeriod(dt_local, emoji, label, pop, color, temp_c))

        periods.sort(key=lambda p: p.time)

        if periods:
            self.logger.info(f"Rain expected at {len(periods)} time(s)")
        else:
            self.logger.info("No rain expected")

        return periods

    # ---- email formatting -------------------------------------------------- #

    def prepare_email_content(self, periods: list[RainPeriod]) -> tuple[str, str, str]:
        """Returns (subject, html_body, plain_text_body)."""
        worst = max(periods, key=lambda p: p.pop)
        highest_pct = round(worst.pop * 100)
        location_label = self.city_name or f"{self.latitude:.3f}, {self.longitude:.3f}"
        date_label = periods[0].time.strftime("%A, %B %-d") if os.name != "nt" else periods[0].time.strftime("%A, %B %d").replace(" 0", " ")
        subject = f"{worst.emoji} Rain Alert for {location_label}: {worst.label} expected today"

        rows_html = ""
        rows_text = []
        for i, p in enumerate(periods):
            pct = round(p.pop * 100)
            temp_html = (
                f'<span style="color:#94a3b8;font-size:13px;">&nbsp;•&nbsp;{p.temp_c:.0f}°C</span>'
                if p.temp_c is not None else ""
            )
            bottom_border = "border-bottom:1px solid #eef2f6;" if i < len(periods) - 1 else ""
            rows_html += f"""
                <tr>
                  <td style="padding:14px 4px;{bottom_border}" width="70%">
                    <table role="presentation" cellpadding="0" cellspacing="0"><tr>
                      <td style="width:4px;background:{p.color};border-radius:2px;font-size:0;line-height:0;">&nbsp;</td>
                      <td style="padding-left:12px;">
                        <div style="font-size:15px;font-weight:600;color:#1e293b;">{p.emoji}&nbsp; {p.time_str()}</div>
                        <div style="font-size:13px;color:#64748b;margin-top:2px;">{p.label}{temp_html}</div>
                      </td>
                    </tr></table>
                  </td>
                  <td style="padding:14px 4px;text-align:right;{bottom_border}" width="30%">
                    <span style="display:inline-block;background:{p.color}1a;color:{p.color};padding:4px 10px;border-radius:999px;font-size:13px;font-weight:700;">
                      {pct}%
                    </span>
                  </td>
                </tr>"""
            temp_text = f", {p.temp_c:.0f}°C" if p.temp_c is not None else ""
            rows_text.append(f"- {p.time_str()}: {p.label}{temp_text}, {pct}% chance of rain")

        tz_name = self.local_tz.tzname(datetime.now())
        generated_at = datetime.now(self.local_tz).strftime("%-I:%M %p") if os.name != "nt" else datetime.now(self.local_tz).strftime("%I:%M %p").lstrip("0")

        html_body = f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="color-scheme" content="light">
<meta name="x-apple-disable-message-reformatting">
<title>{subject}</title>
</head>
<body style="margin:0;padding:0;background-color:#eef1f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;">
  <!-- preheader (hidden preview text in inbox) -->
  <div style="display:none;max-height:0;overflow:hidden;opacity:0;">
    {worst.label} expected around {worst.time_str()}, up to {highest_pct}% chance. {len(periods)} rain period(s) today in {location_label}.
  </div>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#eef1f5;padding:24px 12px;">
    <tr>
      <td align="center">
        <table role="presentation" width="560" cellpadding="0" cellspacing="0" style="background-color:#ffffff;border-radius:16px;overflow:hidden;max-width:560px;width:100%;box-shadow:0 2px 10px rgba(15,23,42,0.06);">

          <!-- hero -->
          <tr>
            <td bgcolor="{worst.color}" style="background:linear-gradient(135deg,{worst.color},{worst.color}); padding:32px 30px 26px 30px;">
              <div style="font-size:13px;font-weight:600;color:#ffffff;opacity:0.85;letter-spacing:0.03em;text-transform:uppercase;">{date_label}</div>
              <div style="margin-top:10px;font-size:40px;line-height:1;">{worst.emoji}</div>
              <div style="margin-top:10px;font-size:23px;font-weight:700;color:#ffffff;">Rain expected today</div>
              <div style="margin-top:4px;font-size:14px;color:#ffffff;opacity:0.9;">📍 {location_label} &nbsp;•&nbsp; up to {highest_pct}% chance</div>
            </td>
          </tr>

          <!-- body -->
          <tr>
            <td style="padding:24px 30px 30px 30px;">
              <div style="font-size:12px;font-weight:700;color:#94a3b8;letter-spacing:0.04em;text-transform:uppercase;margin-bottom:8px;">
                {len(periods)} rain period{"s" if len(periods) != 1 else ""} today
              </div>
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                {rows_html}
              </table>

              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:22px;background:#f8fafc;border-radius:10px;">
                <tr>
                  <td style="padding:14px 16px;font-size:14px;color:#334155;font-weight:600;">
                    ☂️ Don't forget an umbrella today.
                  </td>
                </tr>
              </table>

              <div style="text-align:center;margin-top:24px;padding-top:16px;border-top:1px solid #eef2f6;font-size:12px;color:#94a3b8;line-height:1.6;">
                Automated alert from Weather Notifier &nbsp;•&nbsp; generated {generated_at} {tz_name}<br>
                Times shown in local time ({tz_name})
              </div>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""

        plain_text = (
            f"RAIN EXPECTED TODAY — {location_label}\n"
            f"{date_label}\n\n"
            + "\n".join(rows_text)
            + f"\n\nDon't forget an umbrella today.\nTimes shown in local time ({tz_name}). Generated {generated_at}.\n"
        )

        return subject, html_body, plain_text

    # ---- email sending ----------------------------------------------------- #

    def send_email(self, subject: str, html_content: str, plain_text: str, max_attempts: int = 3) -> bool:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = formataddr((self.sender_name, self.email_sender))
        msg["To"] = ", ".join(self.email_receivers)
        msg.attach(MIMEText(plain_text, "plain"))
        msg.attach(MIMEText(html_content, "html"))

        if self.dry_run:
            self.logger.info("[dry-run] Skipping actual send. Subject: %s", subject)
            return True

        last_error: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                with smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=30) as server:
                    server.starttls()
                    server.login(self.email_sender, self.email_password)
                    server.send_message(msg)
                self.logger.info(f"Email sent successfully to {', '.join(self.email_receivers)}")
                return True
            except smtplib.SMTPAuthenticationError as e:
                # Retrying won't fix bad credentials.
                self.logger.error(f"SMTP authentication failed, not retrying: {e}")
                return False
            except (smtplib.SMTPException, OSError) as e:
                last_error = e
                self.logger.warning(f"SMTP send attempt {attempt}/{max_attempts} failed: {e}")
                if attempt < max_attempts:
                    time.sleep(2 ** attempt)

        self.logger.error(f"Failed to send email after {max_attempts} attempts: {last_error}")
        return False

    # ---- main cycle -------------------------------------------------------- #

    def check_and_notify(self) -> None:
        self.logger.info("Checking weather forecast...")

        weather_data = self.fetch_weather_data()
        if not weather_data:
            self.logger.warning("Failed to fetch weather data")
            return

        periods = self.analyze_weather_conditions(weather_data)
        if not periods:
            self.logger.info("No rain expected. No email sent.")
            return

        subject, html_body, plain_text = self.prepare_email_content(periods)
        self.logger.info("Rain expected. Sending email alert...")
        self.send_email(subject, html_body, plain_text)

    def run_once(self) -> None:
        self._log_startup_banner()
        self.check_and_notify()
        self.logger.info("Done.")

    def _log_startup_banner(self) -> None:
        self.logger.info("=" * 60)
        self.logger.info("Weather Notifier")
        self.logger.info(f"From: {self.sender_name} <{self.email_sender}>")
        self.logger.info(f"To: {', '.join(self.email_receivers)}")
        self.logger.info(f"Location: {self.latitude}, {self.longitude}")
        self.logger.info(f"Forecast lookahead: {self.forecast_count * 3}h (filtered to today only)")
        self.logger.info("=" * 60)

    def _next_run_time(self) -> datetime:
        now = datetime.now(self.schedule_tz)
        candidate = now.replace(hour=self.daily_hour, minute=self.daily_minute, second=0, microsecond=0)
        if candidate <= now:
            candidate += timedelta(days=1)
        return candidate

    def run_forever(self) -> None:
        """Long-lived loop: sleep until the configured daily time, run a check, repeat.

        Intended for deployment as a background worker. Catches and logs any
        unexpected exception per cycle so one bad run doesn't kill the process.
        """
        self._log_startup_banner()
        self.logger.info(
            f"Daemon mode: will check once a day at {self.daily_time_str} "
            f"({self.schedule_tz.key})"
        )

        while True:
            next_run = self._next_run_time()
            sleep_seconds = (next_run - datetime.now(self.schedule_tz)).total_seconds()
            self.logger.info(f"Next check scheduled for {next_run.isoformat()} (sleeping {sleep_seconds/3600:.1f}h)")

            # Sleep in chunks so long sleeps don't hide the process being unresponsive
            # to external signals/log flushing, and so clock changes self-correct.
            while sleep_seconds > 0:
                chunk = min(sleep_seconds, 3600)
                time.sleep(chunk)
                sleep_seconds = (next_run - datetime.now(self.schedule_tz)).total_seconds()

            try:
                self.check_and_notify()
            except Exception:
                self.logger.exception("Unhandled error during scheduled check - will retry at next scheduled time")

    def run(self) -> None:
        # Backwards-compatible alias for a single immediate run.
        self.run_once()


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Weather notifier")
    parser.add_argument("--config", default="config.json", help="Path to config.json")
    parser.add_argument(
        "--once", action="store_true",
        help="Run a single check right now and exit. Use this with an external "
             "scheduler (e.g. a daily cron job or Render Cron Job) so it fires once a day."
    )
    parser.add_argument(
        "--daemon", action="store_true",
        help="Run forever, checking once a day at scheduling.daily_time "
             "(default 06:00, scheduling.timezone). Use for a background-worker deployment."
    )
    parser.add_argument("--dry-run", action="store_true", help="Do everything except actually send the email")
    args = parser.parse_args()

    try:
        notifier = WeatherNotifier(args.config, dry_run=args.dry_run)
    except ConfigError as e:
        print(f"Config error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.once:
        notifier.run_once()
    elif args.daemon:
        notifier.run_forever()
    else:
        # No flag given: default to a single immediate run (safe, predictable,
        # scriptable). Pass --daemon explicitly for the always-on scheduler.
        notifier.run_once()


if __name__ == "__main__":
    main()
