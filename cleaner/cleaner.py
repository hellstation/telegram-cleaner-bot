"""
Cookie cleaning and analysis module.
"""

import json
import logging
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone
from functools import lru_cache
from typing import Dict, List, Optional, Set, Tuple

from config import SITES, SCORING_RULES, CATEGORIES

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Category scores for enhanced scoring system
CATEGORY_SCORES = {
    "social": ["facebook", "instagram", "x", "tiktok", "discord"],
    "entertainment": ["netflix", "spotify", "twitch", "youtube"],
    "professional": ["linkedin", "github"],
    "shopping": ["amazon", "ebay", "paypal"],
    "search": ["google"]
}


@lru_cache(maxsize=512)
def get_main_domain(domain: str) -> str:
    """
    Get the main domain (second level domain), with special mappings for known sites.

    Args:
        domain: The domain string.

    Returns:
        Main domain.
    """
    domain = domain.lower().lstrip(".")

    # Domain mappings: more specific patterns first
    domain_mappings = {
        "linkedin": ["linkedin"],
        "github": ["github"],
        "discord": ["discord"],
        "twitch": ["twitch"],
        "netflix": ["netflix"],
        "spotify": ["spotify"],
        "reddit": ["reddit"],
        "tiktok": ["tiktok"],
        "paypal": ["paypal"],
        "x": ["x.com", "twitter"],
        "google": ["google", "youtube", "gmail"],
        "amazon": ["amazon"],
        "ebay": ["ebay"],
        "facebook": ["facebook", "fb"],
        "instagram": ["instagram"],
        "roblox": ["roblox"],
        "steam": ["steam", "steampowered"],
        "epicgames": ["epicgames", "epic"],
        "microsoft": ["microsoft", "live", "outlook"],
        "apple": ["apple", "icloud"],
        "genshin": ["genshin", "mihoyo"],
        "minecraft": ["minecraft", "mojang"],
    }

    # Check for special mappings
    for main_domain, patterns in domain_mappings.items():
        if any(pattern in domain for pattern in patterns):
            return main_domain

    # Default: extract second-level domain
    parts = domain.split(".")
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return domain


def detect_service(main_domain: str, domain: str) -> str:
    """
    Detect the service based on main domain and full domain.

    Args:
        main_domain: The main domain.
        domain: The full domain.

    Returns:
        Service name.
    """
    domain = domain.lower()
    if main_domain in SITES:
        for service, keys in SITES[main_domain]["services"].items():
            if any(k in domain for k in keys):
                return service
        return "other"
    return ""


def detect_auth(main_domain: str, cookie_name: str) -> Optional[str]:
    """
    Detect auth cookie based on main domain.

    Args:
        main_domain: The main domain.
        cookie_name: The cookie name.

    Returns:
        Auth name if matched.
    """
    if main_domain in SITES:
        for auth in SITES[main_domain]["auth"]:
            if auth.lower() in cookie_name.lower():
                return auth
    return None


def parse_cookies(file_path: str) -> Tuple[Counter, defaultdict, defaultdict]:
    """
    Parse cookies from a file and return counters.

    Args:
        file_path: Path to the cookies file.

    Returns:
        Tuple of site_counter, service_counter, auth_detected.
    """
    site_counter = Counter()
    service_counter = defaultdict(Counter)
    auth_detected = defaultdict(set)
    seen_cookies = set()

    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue

                parts = line.split("\t")
                if len(parts) < 7:
                    logger.warning(f"Skipping invalid line {line_num}: {line}")
                    continue

                domain = parts[0]
                cookie_name = parts[5]

                unique_key = f"{domain}|{cookie_name}"
                if unique_key in seen_cookies:
                    continue
                seen_cookies.add(unique_key)

                main_domain = get_main_domain(domain)
                service = detect_service(main_domain, domain)
                site_counter[main_domain] += 1
                service_counter[main_domain][service] += 1

                auth = detect_auth(main_domain, cookie_name)
                if auth:
                    auth_detected[main_domain].add(auth)

    except FileNotFoundError:
        logger.error(f"File not found: {file_path}")
        raise
    except Exception as e:
        logger.error(f"Error parsing cookies file: {e}")
        raise

    return site_counter, service_counter, auth_detected


def calculate_oldest_cookie_age(lines: List[str]) -> str:
    """
    Calculate the age of the oldest cookie from cookie lines.

    Args:
        lines: List of cookie lines.

    Returns:
        Age string like "30 days" or "Unknown".
    """
    oldest_timestamp = None
    current_time = datetime.now(timezone.utc)

    for line in lines:
        parts = line.strip().split("\t")
        if len(parts) >= 5:
            try:
                # Parse expires timestamp (parts[4])
                expires_ts = int(parts[4])
                if expires_ts > 0:  # 0 means session cookie
                    expires_time = datetime.fromtimestamp(expires_ts, timezone.utc)
                    if oldest_timestamp is None or expires_time < oldest_timestamp:
                        oldest_timestamp = expires_time
            except (ValueError, IndexError):
                continue

    if oldest_timestamp:
        age_days = (current_time - oldest_timestamp).days
        if age_days < 1:
            return "Less than 1 day"
        elif age_days < 30:
            return f"{age_days} days"
        elif age_days < 365:
            months = age_days // 30
            return f"{months} months"
        else:
            years = age_days // 365
            return f"{years} years"

    return "Unknown"


def count_tracking_cookies(lines: List[str]) -> int:
    """
    Count tracking cookies (Google Analytics, Facebook Pixel, etc.).

    Args:
        lines: List of cookie lines.

    Returns:
        Number of tracking cookies detected.
    """
    tracking_patterns = [
        "_ga", "_gid", "_gat", "__utma", "__utmb", "__utmc", "__utmz",  # Google Analytics
        "_fbp", "_fbc", "fr",  # Facebook
        "_tt_enable_cookie", "_ttp",  # TikTok
        "mbox", "AMCV_", "s_cc", "s_sq", "s_vi",  # Adobe Analytics
        "utag_main", "_utma", "_utmb", "_utmc", "_utmz",  # Tealium
        "mp_", "__mp",  # Mixpanel
        "amplitude_id",  # Amplitude
        "ajs_user_id", "ajs_anonymous_id",  # Segment
        "_hjid", "_hjClosedSurveyInvites",  # Hotjar
        "intercom-id-", "intercom-session-",  # Intercom
        "zendesk_",  # Zendesk
        "drift_",  # Drift
        "hsCtaTracking", "_hstc", "_hssc",  # HubSpot
    ]

    tracking_count = 0
    for line in lines:
        parts = line.strip().split("\t")
        if len(parts) >= 6:
            cookie_name = parts[5].lower()
            if any(pattern.lower() in cookie_name for pattern in tracking_patterns):
                tracking_count += 1

    return tracking_count


def calculate_privacy_score(cleaned_count: int, total_count: int) -> float:
    """
    Calculate privacy score based on cleaning efficiency.

    Args:
        cleaned_count: Number of cookies kept.
        total_count: Total number of cookies.

    Returns:
        Privacy score from 0.0 to 10.0.
    """
    if total_count == 0:
        return 10.0

    # Higher score for keeping fewer cookies
    retention_ratio = cleaned_count / total_count
    privacy_score = (1 - retention_ratio) * 10

    return round(privacy_score, 1)


def get_sites_by_category(site_counter: Counter) -> Dict[str, List[str]]:
    """
    Group sites by categories.

    Args:
        site_counter: Counter of sites.

    Returns:
        Dict of category to list of sites.
    """
    category_sites = defaultdict(list)
    for site in site_counter:
        for category, sites in CATEGORIES.items():
            if site in sites:
                category_sites[category].append(site)
                break
        else:
            category_sites["other"].append(site)
    return dict(category_sites)



def calculate_category_bonuses(site_counter: Counter) -> List[str]:
    """
    Calculate bonuses for category combinations.

    Args:
        site_counter: Counter of sites.

    Returns:
        List of bonus descriptions.
    """
    bonuses = []

    # Social butterfly: 3+ social networks
    social_sites = set(CATEGORY_SCORES["social"]) & set(site_counter.keys())
    if len(social_sites) >= 3:
        bonuses.append("Social butterfly (+2)")

    # Tech professional: LinkedIn + GitHub
    if "linkedin" in site_counter and "github" in site_counter:
        bonuses.append("Tech professional (+3)")

    # Entertainment addict: 2+ entertainment services
    entertainment_sites = set(CATEGORY_SCORES["entertainment"]) & set(site_counter.keys())
    if len(entertainment_sites) >= 2:
        bonuses.append("Entertainment addict (+1)")

    # Shopaholic: 2+ shopping sites
    shopping_sites = set(CATEGORY_SCORES["shopping"]) & set(site_counter.keys())
    if len(shopping_sites) >= 2:
        bonuses.append("Shopaholic (+2)")

    return bonuses


def calculate_score(site_counter: Counter, service_counter: defaultdict, auth_detected: defaultdict) -> Tuple[int, str, List[str]]:
    """
    Calculate the profile score based on cookies.

    Args:
        site_counter: Counter of sites.
        service_counter: Counter of services per site.
        auth_detected: Detected auth cookies per site.

    Returns:
        Tuple of score, level, score_reasons.
    """

    score = 0
    score_reasons = []

    def add_score(points: int, reason: str) -> None:
        nonlocal score
        score += points
        score_reasons.append(f"+{points} {reason}")

    # Site scores
    for site, points in SCORING_RULES["sites"].items():
        if site in site_counter:
            add_score(points, f"{site.replace('.com', '').capitalize()} cookies")

    # Category bonuses
    category_bonuses = calculate_category_bonuses(site_counter)
    for bonus in category_bonuses:
        # Parse bonus format like "Social butterfly (+2)"
        if "(" in bonus and ")" in bonus:
            bonus_name = bonus.split(" (")[0]
            bonus_points = int(bonus.split("(+")[1].rstrip(")"))
            add_score(bonus_points, bonus_name)

    # Service bonuses
    for site, services in SCORING_RULES["services"].items():
        if site in site_counter:
            for service, points in services.items():
                if service in service_counter.get(site, {}):
                    add_score(points, f"{service.capitalize()} detected")

    # Auth bonus
    if auth_detected:
        add_score(SCORING_RULES["auth_bonus"], "AUTH cookies detected")

    # Determine level
    level = "LOW"
    for lvl, config in SCORING_RULES["levels"].items():
        if score >= config["min_score"]:
            level = lvl
            break

    return score, level, score_reasons

def clean_cookies(input_file_path: str, output_file_path: str) -> Dict:
    """
    Clean cookies file by keeping only auth cookies and return stats.

    Args:
        input_file_path: Path to input cookies file.
        output_file_path: Path to output cleaned file.

    Returns:
        Dict with stats.
    """
    # Read all cookie lines first for analysis
    all_lines = []
    try:
        with open(input_file_path, "r", encoding="utf-8", errors="ignore") as f:
            all_lines = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        logger.error(f"File not found: {file_path}")
        raise

    site_counter, service_counter, auth_detected = parse_cookies(input_file_path)
    cleaned_lines = []

    # Re-parse to collect lines with auth
    seen_cookies = set()
    for line in all_lines:
        parts = line.split("\t")
        if len(parts) < 7:
            continue

        domain = parts[0]
        cookie_name = parts[5]

        unique_key = f"{domain}|{cookie_name}"
        if unique_key in seen_cookies:
            continue
        seen_cookies.add(unique_key)

        main_domain = get_main_domain(domain)
        auth = detect_auth(main_domain, cookie_name)
        if auth:
            cleaned_lines.append(line)

    # Write cleaned file
    try:
        with open(output_file_path, "w", encoding="utf-8") as f:
            for line in cleaned_lines:
                f.write(line + "\n")
    except Exception as e:
        logger.error(f"Error writing cleaned file: {e}")
        raise

    total_unique_cookies = len(seen_cookies)
    unique_sites = len(site_counter)
    most_common = site_counter.most_common(1)
    if most_common:
        site_name = most_common[0][0]
        most_common_site = f"{site_name} ({most_common[0][1]} times)"
    else:
        most_common_site = "None"

    # Calculate new metrics
    oldest_cookie_age = calculate_oldest_cookie_age(all_lines)
    tracking_intensity = count_tracking_cookies(all_lines)
    privacy_score = calculate_privacy_score(len(cleaned_lines), total_unique_cookies)

    # For sites in config, combine detected and config services
    services_dict = {}
    order = ["search", "gmail", "youtube", "other", "shopping", "marketplace", "twitter", "facebook", "tiktok", "reddit", "linkedin", "github", "discord", "twitch", "netflix", "spotify"]
    for site in site_counter:
        detected = [s for s in service_counter[site] if s]
        if site in SITES:
            config_services = list(SITES[site]["services"].keys())
            all_services = set(detected + config_services)
            services_dict[site] = sorted(all_services, key=lambda x: order.index(x) if x in order else 99)
        else:
            services_dict[site] = sorted(detected, key=lambda x: order.index(x) if x in order else 99)

    return {
        "sites": dict(site_counter.most_common()),
        "services": services_dict,
        "auth_detected": {site: list(cookies) for site, cookies in auth_detected.items()},
        "total_cleaned": len(cleaned_lines),
        "total_unique_cookies": total_unique_cookies,
        "unique_sites": unique_sites,
        "most_common_site": most_common_site,
        "oldest_cookie_age": oldest_cookie_age,
        "tracking_intensity": tracking_intensity,
        "privacy_score": privacy_score
    }
