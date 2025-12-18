"""
CLI script for cookie analysis.
"""

import sys
from collections import defaultdict, Counter

from cleaner import parse_cookies, calculate_score


def main():
    if len(sys.argv) != 2:
        print("Usage: python main.py <cookies_file>")
        sys.exit(1)

    file_path = sys.argv[1]

    try:
        site_counter, service_counter, auth_detected = parse_cookies(file_path)
        score, level, score_reasons = calculate_score(site_counter, service_counter, auth_detected)

        # Output
        print("📊 UNIQUE COOKIES BY SITES:\n")
        for site, total in site_counter.most_common():
            services = ", ".join(service_counter[site].keys())
            print(f"{site}({total}) - {services}")

        print("\n🔐 AUTH DETECTED:")
        if not auth_detected:
            print("  not found")
        else:
            for site, cookies in auth_detected.items():
                print(f"  {site}: {', '.join(cookies)}")

        print("\n🧠 PROFILE SCORING")
        print(f"SCORE: {score}")
        print(f"VALUE: {level}")

        print("\n📌 SCORE DETAILS:")
        for r in score_reasons:
            print(" ", r)

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
