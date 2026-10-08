"""Append a ``parse:`` block to catalogue definitions that lack one.

Appending textually rather than round-tripping through ``yaml.dump`` is deliberate: a dump
would discard every comment in the file and reorder keys, and these definitions are read by
people. Appending preserves the existing bytes exactly and only adds what is missing, so a
definition that already declares its parse block is left alone.

Run from the repository root:

    python apps/acquisition/sources/append_parse_blocks.py --dry-run
    python apps/acquisition/sources/append_parse_blocks.py

The blocks themselves live in :data:`PARSE_BLOCKS`, keyed by source name. They are data,
not logic: every one names a family, the paths inside the source's own response, and the
kind each path means. That is the same thing a hand-written parser would encode, and the
difference is that this one is checkable.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE / "estorides"

PARSE_BLOCKS: dict[str, dict[str, Any]] = {
    # ------------------------------------------------------------------ 01_dns
    "crt_sh_certificates": {
        "family": "json_rows",
        "list_path": "",
        "fields": {
            "issuer": {"path": "issuer_name", "kind": "organization"},
            "issuer_ca": {"path": "issuer_ca_id", "kind": "identifier"},
            "common_name": {"path": "common_name", "kind": "domain"},
            "name_value": {"path": "name_value", "kind": "subdomain", "many": True},
            "not_before": {"path": "not_before", "kind": "timestamp"},
            "not_after": {"path": "not_after", "kind": "timestamp"},
        },
    },
    "certspotter_issuances": {
        "family": "json_rows",
        "list_path": "",
        "fields": {
            "issuer": {"path": "issuer.dn", "kind": "organization"},
            "dns_names": {"path": "dns_names[*]", "kind": "subdomain", "many": True},
            "id": {"path": "id", "kind": "identifier"},
            "not_before": {"path": "not_before", "kind": "timestamp"},
            "not_after": {"path": "not_after", "kind": "timestamp"},
        },
    },
    "rdap_domain": {
        "family": "json_object",
        "fields": {
            "ldh": {"path": "ldhName", "kind": "domain", "required": True},
            "handle": {"path": "handle", "kind": "identifier"},
            "status": {"path": "status", "kind": "status", "many": True},
            "registrar": {
                "path": "entities[*].vcardArray[1][*][3]",
                "kind": "organization",
                "many": True,
            },
            "nameserver": {"path": "nameservers[*].ldhName", "kind": "domain", "many": True},
            "event_date": {"path": "events[*].eventDate", "kind": "timestamp", "many": True},
        },
    },
    "rdap_ip": {
        "family": "json_object",
        "fields": {
            "handle": {"path": "handle", "kind": "identifier", "required": True},
            "name": {"path": "name", "kind": "network"},
            "country": {"path": "country", "kind": "country"},
            "start": {"path": "startAddress", "kind": "address"},
            "end": {"path": "endAddress", "kind": "address"},
            "cidr": {"path": "cidr0_cidrs[*].v4prefix", "kind": "prefix", "many": True},
        },
    },
    "dns_google": {
        "family": "dns_json",
        "fields": {
            "status": {"path": "Status", "kind": "integer"},
            "answer": {"path": "Answer[*].data", "kind": "unknown", "many": True},
            "authority": {"path": "Authority[*].data", "kind": "unknown", "many": True},
        },
    },
    "dns_cloudflare": {
        "family": "dns_json",
        "fields": {
            "status": {"path": "Status", "kind": "integer"},
            "answer": {"path": "Answer[*].data", "kind": "unknown", "many": True},
            "authority": {"path": "Authority[*].data", "kind": "unknown", "many": True},
        },
    },
    # hackertarget_dns answers in dig format -- "A : 104.20.23.154", "NS : host." -- so the
    # first token is the *record type* and the second is the value. Declaring the whole line
    # a domain named every A record "A", which is what the live check caught.
    "hackertarget_dns": {
        "family": "text_lines",
        "fields": {
            "record_type": {"path": "", "kind": "status", "pattern": "^([A-Z0-9]+)\s*:"},
            "record_value": {
                "path": "",
                "kind": "unknown",
                "pattern": "^[A-Z0-9]+\s*:\s*(\S+)",
                "required": True,
            },
        },
    },
    "hackertarget_findshareddns": {
        "family": "text_lines",
        "fields": {"domain": {"path": "", "kind": "domain", "pattern": "^[^\\s,]+"}},
    },
    "hackertarget_hostsearch": {
        "family": "text_lines",
        "fields": {"domain": {"path": "", "kind": "subdomain", "pattern": "^[^\\s,]+"}},
    },
    "hackertarget_reverse_dns": {
        "family": "text_lines",
        "fields": {
            "ip": {"path": "", "kind": "ip", "pattern": "^(\\d+\\.\\d+\\.\\d+\\.\\d+)"},
        },
    },
    "hackertarget_reverseiplookup": {
        "family": "text_lines",
        "fields": {"domain": {"path": "", "kind": "domain", "pattern": "^[^\\s,]+"}},
    },
    "hackertarget_aslookup": {
        "family": "text_lines",
        "fields": {
            "asn": {"path": "", "kind": "asn", "pattern": "^(AS\\d+|\\d+)"},
            "prefix": {"path": "", "kind": "prefix", "pattern": "(\\d+\\.\\d+\\.\\d+\\.\\d+/\\d+)"},
        },
    },
    "hackertarget_geoip": {
        "family": "text_lines",
        "fields": {
            "country": {"path": "", "kind": "country", "pattern": "^([A-Z]{2})"},
            "city": {"path": "", "kind": "place"},
        },
    },
    "hackertarget_nping": {
        "family": "text_lines",
        "fields": {
            "ip": {"path": "", "kind": "ip", "pattern": "^(\\d+\\.\\d+\\.\\d+\\.\\d+)"},
            "hostname": {"path": "", "kind": "domain", "pattern": "([a-zA-Z0-9.-]+\\.[a-z]{2,})"},
        },
    },
    "hackertarget_traceroute": {
        "family": "text_lines",
        "fields": {
            "ip": {"path": "", "kind": "ip", "pattern": "^(\\d+\\.\\d+\\.\\d+\\.\\d+)"},
            "hop": {"path": "", "kind": "integer", "pattern": "^\\s*(\\d+)"},
        },
    },
    "hackertarget_http_headers": {
        "family": "text_lines",
        "fields": {
            "header": {"path": "", "kind": "unknown", "pattern": "^([A-Za-z-]+):"},
            "value": {"path": "", "kind": "unknown", "pattern": "^[A-Za-z-]+:\\s*(.+)$"},
        },
    },
    "hackertarget_whois": {
        "family": "text_lines",
        "fields": {
            "field": {
                "path": "",
                "kind": "unknown",
                "pattern": "^([A-Za-z][A-Za-z /]*):",
                "many": True,
            },
            "value": {
                "path": "",
                "kind": "unknown",
                "pattern": "^\\s*[A-Za-z][A-Za-z /]*:\\s*(.+)$",
                "many": True,
            },
        },
    },
    "dns_dumpster_subdomains": {
        "family": "text_lines",
        "fields": {"subdomain": {"path": "", "kind": "subdomain", "pattern": "^[^\\s,]+"}},
    },
    # ------------------------------------------------------------- 02_ip_infra
    "shodan_internetdb": {
        "family": "json_object",
        "fields": {
            "domain": {"path": "hostnames[*]", "kind": "domain", "many": True},
            "ip": {"path": "ip_str", "kind": "ip"},
            "cpe": {"path": "cpes[*]", "kind": "technology", "many": True},
            "cve": {"path": "vulns[*].id", "kind": "cve", "many": True},
            "cve_score": {"path": "vulns[*].cvss.score", "kind": "score", "many": True},
            "port": {"path": "ports[*]", "kind": "port", "many": True},
            "tag": {"path": "tags[*]", "kind": "tag", "many": True},
        },
    },
    "censys_certificates": {
        "family": "json_object",
        "fields": {
            "domain": {"path": "names[*]", "kind": "domain", "many": True},
            "issuer": {"path": "parsed.issuer_dn", "kind": "organization"},
            "not_before": {"path": "parsed.validity.start", "kind": "timestamp"},
            "not_after": {"path": "parsed.validity.end", "kind": "timestamp"},
            "fingerprint": {"path": "parsed.fingerprint_sha256", "kind": "identifier"},
        },
    },
    "ipwho_is": {
        "family": "json_object",
        "fields": {
            "ip": {"path": "ip", "kind": "ip", "required": True},
            "asn": {"path": "connection.asn", "kind": "asn"},
            "org": {"path": "connection.org", "kind": "organization"},
            "isp": {"path": "connection.isp", "kind": "isp"},
            "country": {"path": "country", "kind": "country"},
            "region": {"path": "region", "kind": "place"},
            "city": {"path": "city", "kind": "place"},
            "latitude": {"path": "latitude", "kind": "geolocation"},
            "longitude": {"path": "longitude", "kind": "geolocation"},
        },
    },
    "ipapi_co_full": {
        "family": "json_object",
        "fields": {
            "ip": {"path": "ip", "kind": "ip", "required": True},
            "asn": {"path": "asn", "kind": "asn"},
            "org": {"path": "org", "kind": "organization"},
            "isp": {"path": "isp", "kind": "isp"},
            "country": {"path": "country_code", "kind": "country"},
            "city": {"path": "city", "kind": "place"},
            "latitude": {"path": "latitude", "kind": "geolocation"},
            "longitude": {"path": "longitude", "kind": "geolocation"},
        },
    },
    "ipapi_free": {
        "family": "json_object",
        "fields": {
            "ip": {"path": "ip", "kind": "ip", "required": True},
            "org": {"path": "org", "kind": "organization"},
            "asn": {"path": "asn", "kind": "asn"},
            "country": {"path": "country", "kind": "country"},
            "city": {"path": "city", "kind": "place"},
        },
    },
    "ipinfo_free": {
        "family": "json_object",
        "fields": {
            "ip": {"path": "ip", "kind": "ip", "required": True},
            "hostname": {"path": "hostname", "kind": "domain"},
            "org": {"path": "org", "kind": "isp"},
            "city": {"path": "city", "kind": "place"},
            "region": {"path": "region", "kind": "place"},
            "country": {"path": "country", "kind": "country"},
            "geolocation": {"path": "loc", "kind": "geolocation"},
        },
    },
    "ipwhois_free": {
        "family": "json_object",
        "fields": {
            "ip": {"path": "ip", "kind": "ip"},
            "country": {"path": "country_code", "kind": "country"},
            "asn": {"path": "asn", "kind": "asn"},
            "org": {"path": "asn_org", "kind": "organization"},
            "isp": {"path": "isp", "kind": "isp"},
        },
    },
    "bgpview_asn": {
        "family": "json_object",
        "fields": {
            "asn": {"path": "data.asn", "kind": "asn", "required": True},
            "name": {"path": "data.name", "kind": "organization"},
            "description": {"path": "data.description_short", "kind": "description"},
            "country": {"path": "data.country_code", "kind": "country"},
            "prefix": {"path": "data.prefixes[*].prefix", "kind": "prefix", "many": True},
        },
    },
    "bgpview_ip": {
        "family": "json_object",
        "fields": {
            "ip": {"path": "data.ip", "kind": "ip", "required": True},
            "prefix": {"path": "data.prefix", "kind": "prefix"},
            "asn": {"path": "data.asn.asn", "kind": "asn"},
            "name": {"path": "data.asn.name", "kind": "organization"},
            "description": {"path": "data.asn.description_short", "kind": "description"},
        },
    },
    "greynoise_community": {
        "family": "json_object",
        "fields": {
            "ip": {"path": "ip", "kind": "ip", "required": True},
            "name": {"path": "name", "kind": "organization"},
            "classification": {"path": "classification", "kind": "reputation"},
            "link": {"path": "link", "kind": "url"},
            "last_seen": {"path": "last_seen", "kind": "timestamp"},
        },
    },
    "macvendors_lookup": {
        "family": "json_object",
        "fields": {"vendor": {"path": "$", "kind": "vendor"}},
    },
    "abuseipdb_check": {
        "family": "json_object",
        "fields": {
            "ip": {"path": "ipAddress", "kind": "ip", "required": True},
            "abuse_confidence": {"path": "abuseConfidenceScore", "kind": "score"},
            "country": {"path": "countryCode", "kind": "country"},
            "isp": {"path": "isp", "kind": "isp"},
            "usage": {"path": "usageType", "kind": "status"},
            "report_count": {"path": "totalReports", "kind": "integer"},
        },
    },
    "fullhunt_surface": {
        "family": "json_rows",
        "list_path": "hosts",
        "fields": {
            "domain": {"path": "host", "kind": "domain"},
            "ip": {"path": "ip", "kind": "ip"},
            "port": {"path": "port", "kind": "port"},
            "technology": {"path": "technology[*].name", "kind": "technology", "many": True},
            "cve": {"path": "vulnerabilities[*].cve_id", "kind": "cve", "many": True},
        },
    },
    "robtex_ip": {
        "family": "json_object",
        "fields": {
            "ip": {"path": "ip", "kind": "ip"},
            "prefix": {"path": "prefix", "kind": "prefix"},
            "asn": {"path": "asn", "kind": "asn"},
        },
    },
    "securitytrails_dns": {
        "family": "json_object",
        "fields": {
            "domain": {"path": "domain", "kind": "domain"},
            "subdomain": {"path": "subdomains[*]", "kind": "subdomain", "many": True},
            "record_type": {"path": "record_type", "kind": "unknown"},
            "first_seen": {"path": "first_seen", "kind": "timestamp"},
            "last_seen": {"path": "last_seen", "kind": "timestamp"},
        },
    },
    "ripe_stat": {
        "family": "json_object",
        "fields": {
            "resource": {"path": "data.resource", "kind": "network"},
            "prefix": {"path": "data.prefix", "kind": "prefix"},
            "asn": {"path": "data.asns[*]", "kind": "asn", "many": True},
            "holder": {"path": "data.holder", "kind": "organization"},
            "country": {"path": "data.country", "kind": "country"},
        },
    },
    # ------------------------------------------------------------------ 03_web
    "wayback_machine_cdx": {
        "family": "text_lines",
        "fields": {
            "url": {"path": "", "kind": "url", "pattern": "^[a-z]+://", "many": True},
            "timestamp": {
                "path": "",
                "kind": "timestamp",
                "pattern": "\\b(\\d{14})\\b",
                "many": True,
            },
            "status": {"path": "", "kind": "status", "pattern": "\\b(\\d{3})\\s", "many": True},
            "digest": {
                "path": "",
                "kind": "identifier",
                "pattern": "\\b([A-Fa-f0-9]{32})\\b",
                "many": True,
            },
        },
    },
    "wayback_machine_snapshot": {
        "family": "json_object",
        "fields": {
            "url": {"path": "archived_snapshots.closest.url", "kind": "url"},
            "status": {"path": "archived_snapshots.closest.status", "kind": "status"},
            "timestamp": {"path": "archived_snapshots.closest.timestamp", "kind": "timestamp"},
        },
    },
    "urlscan_public": {
        "family": "json_object",
        "fields": {
            "domain": {"path": "page.domain", "kind": "domain"},
            "ip": {"path": "page.ip", "kind": "ip"},
            "country": {"path": "page.country", "kind": "country"},
            "asn": {"path": "page.asn", "kind": "asn"},
            "url": {"path": "page.url", "kind": "url"},
            "server": {"path": "page.server", "kind": "technology"},
        },
    },
    "google_cache_check": {
        "family": "json_object",
        "fields": {
            "is_cached": {"path": "cached", "kind": "unknown"},
            "url": {"path": "url", "kind": "url"},
        },
    },
    "pages_dev_meta": {
        "family": "json_object",
        "fields": {
            "title": {"path": "title", "kind": "description"},
            "description": {"path": "description", "kind": "description"},
            "author": {"path": "author", "kind": "person"},
            "image": {"path": "image", "kind": "url"},
            "published": {"path": "published", "kind": "timestamp"},
        },
    },
    "microlink": {
        "family": "json_object",
        "fields": {
            "title": {"path": "data.title", "kind": "description"},
            "description": {"path": "data.description", "kind": "description"},
            "author": {"path": "data.author", "kind": "person"},
            "publisher": {"path": "data.publisher", "kind": "organization"},
            "url": {"path": "data.url", "kind": "url"},
            "image": {"path": "data.image.url", "kind": "url"},
            "lang": {"path": "data.lang", "kind": "language"},
        },
    },
    "tineye_reverse": {
        "family": "json_object",
        "fields": {
            "match_count": {"path": "matches", "kind": "integer"},
            "image_url": {"path": "results[*].image_url", "kind": "url", "many": True},
            "domain": {"path": "results[*].domain", "kind": "domain", "many": True},
        },
    },
    "screenshotmachine": {
        "family": "json_object",
        "fields": {
            "screenshot": {"path": "screenshot_url", "kind": "url"},
            "thumbnail": {"path": "thumbnail_url", "kind": "url"},
            "status": {"path": "status", "kind": "status"},
        },
    },
    # --------------------------------------------------------------- 04_social
    "github_user": {
        "family": "json_object",
        "fields": {
            "username": {"path": "login", "kind": "handle", "required": True},
            "name": {"path": "name", "kind": "person"},
            "company": {"path": "company", "kind": "organization"},
            "location": {"path": "location", "kind": "place"},
            "email": {"path": "email", "kind": "email"},
            "blog": {"path": "blog", "kind": "url"},
            "bio": {"path": "bio", "kind": "description"},
            "created_at": {"path": "created_at", "kind": "timestamp"},
            "repos": {"path": "public_repos", "kind": "integer"},
        },
    },
    "github_repos": {
        "family": "json_rows",
        "list_path": "",
        "fields": {
            "repository": {"path": "full_name", "kind": "repository", "required": True},
            "description": {"path": "description", "kind": "description"},
            "language": {"path": "language", "kind": "language"},
            "owner": {"path": "owner.login", "kind": "handle"},
            "url": {"path": "html_url", "kind": "url"},
            "stars": {"path": "stargazers_count", "kind": "integer"},
            "created_at": {"path": "created_at", "kind": "timestamp"},
            "topics": {"path": "topics[*]", "kind": "tag", "many": True},
        },
    },
    "github_gists": {
        "family": "json_rows",
        "list_path": "",
        "fields": {
            "repository": {"path": "html_url", "kind": "url", "required": True},
            "description": {"path": "description", "kind": "description"},
            "owner": {"path": "owner.login", "kind": "handle"},
            "language": {"path": "language", "kind": "language"},
            "created_at": {"path": "created_at", "kind": "timestamp"},
        },
    },
    "github_advisories": {
        "family": "json_rows",
        "list_path": "",
        "fields": {
            "ghsa": {"path": "ghsa_id", "kind": "identifier", "required": True},
            "cve": {"path": "cve_id", "kind": "cve"},
            "summary": {"path": "summary", "kind": "description"},
            "severity": {"path": "severity", "kind": "status"},
            "package": {
                "path": "vulnerabilities[*].package.name",
                "kind": "technology",
                "many": True,
            },
            "ecosystem": {
                "path": "vulnerabilities[*].package.ecosystem",
                "kind": "unknown",
                "many": True,
            },
            "url": {"path": "html_url", "kind": "url"},
            "published": {"path": "published_at", "kind": "timestamp"},
        },
    },
    "github_code_search": {
        "family": "json_rows",
        "list_path": "items",
        "fields": {
            "repository": {"path": "repository.full_name", "kind": "repository"},

            "url": {"path": "html_url", "kind": "url"},
        },
    },
    "gists_github_search": {
        "family": "json_rows",
        "list_path": "",
        "fields": {
            "url": {"path": "html_url", "kind": "url", "required": True},
            "description": {"path": "description", "kind": "description"},
            "owner": {"path": "owner.login", "kind": "handle"},
        },
    },
    "dev_to_user": {
        "family": "json_object",
        "fields": {
            "username": {"path": "username", "kind": "handle", "required": True},
            "name": {"path": "name", "kind": "person"},
            "location": {"path": "location", "kind": "place"},
            "website": {"path": "website_url", "kind": "url"},
            "joined": {"path": "joined_at", "kind": "timestamp"},
        },
    },
    "hackernews_user": {
        "family": "json_object",
        "fields": {
            "username": {"path": "id", "kind": "handle", "required": True},
            "karma": {"path": "karma", "kind": "integer"},
            "created": {"path": "created", "kind": "timestamp"},
            "submitted_count": {"path": "submitted", "kind": "integer"},
        },
    },
    "reddit_about": {
        "family": "json_object",
        "fields": {
            "subreddit": {"path": "display_name", "kind": "subreddit", "required": True},
            "title": {"path": "title", "kind": "description"},
            "description": {"path": "public_description", "kind": "description"},
            "subscribers": {"path": "subscribers", "kind": "integer"},
            "created": {"path": "created_utc", "kind": "timestamp"},
            "url": {"path": "url", "kind": "url"},
        },
    },
    "reddit_posts": {
        "family": "json_rows",
        "list_path": "data.children",
        "fields": {
            "post": {"path": "data.title", "kind": "article"},
            "subreddit": {"path": "data.subreddit", "kind": "subreddit"},
            "author": {"path": "data.author", "kind": "handle"},
            "url": {"path": "data.url", "kind": "url"},
            "score": {"path": "data.score", "kind": "integer"},
            "created": {"path": "data.created_utc", "kind": "timestamp"},
        },
    },
    "reddit_subreddit": {
        "family": "json_rows",
        "list_path": "data.children",
        "fields": {
            "post": {"path": "data.title", "kind": "article"},
            "subreddit": {"path": "data.subreddit", "kind": "subreddit"},
            "author": {"path": "data.author", "kind": "handle"},
            "url": {"path": "data.url", "kind": "url"},
        },
    },
    "mastodon_search": {
        "family": "json_rows",
        "list_path": "",
        "fields": {
            "account": {"path": "account.acct", "kind": "handle"},
            "display_name": {"path": "account.display_name", "kind": "person"},
            "content": {"path": "content", "kind": "description"},
            "url": {"path": "url", "kind": "url"},
            "created": {"path": "created_at", "kind": "timestamp"},
        },
    },
    "twitch_user": {
        "family": "json_object",
        "fields": {
            "username": {"path": "display_name", "kind": "handle", "required": True},
            "description": {"path": "description", "kind": "description"},
            "url": {"path": "url", "kind": "url"},
            "created": {"path": "created_at", "kind": "timestamp"},
        },
    },
    "twitter_user": {
        "family": "json_object",
        "fields": {
            "username": {"path": "screen_name", "kind": "handle", "required": True},
            "name": {"path": "name", "kind": "person"},
            "description": {"path": "description", "kind": "description"},
            "url": {"path": "url", "kind": "url"},
            "followers": {"path": "followers_count", "kind": "integer"},
            "created": {"path": "created_at", "kind": "timestamp"},
        },
    },
    "youtube_user": {
        "family": "json_object",
        "fields": {
            "channel_id": {"path": "channelId", "kind": "channel"},
            "title": {"path": "title", "kind": "description"},
            "description": {"path": "description", "kind": "description"},
            "url": {"path": "url", "kind": "url"},
            "country": {"path": "country", "kind": "country"},
            "published": {"path": "publishedAt", "kind": "timestamp"},
        },
    },
    "keybase_lookup": {
        "family": "json_object",
        "fields": {
            "username": {"path": "them.username", "kind": "handle", "required": True},
            "full_name": {"path": "them.full_name", "kind": "person"},
            "location": {"path": "them.location", "kind": "place"},
            "identity": {
                "path": "them.them.identities[*].network_name",
                "kind": "handle",
                "many": True,
            },
            "proofs_summary": {"path": "them.proofs_summary.all_time", "kind": "integer"},
        },
    },
    "discord_discovery": {
        "family": "json_object",
        "fields": {
            "invite": {"path": "code", "kind": "handle"},
            "guild": {"path": "guild.name", "kind": "organization"},
            "guild_id": {"path": "guild.id", "kind": "identifier"},
            "channel": {"path": "channel.name", "kind": "channel"},
            "online": {"path": "approximate_presence_count", "kind": "integer"},
        },
    },
    "medium_public": {
        "family": "json_rows",
        "list_path": "",
        "fields": {
            "post": {"path": "title", "kind": "article"},
            "author": {"path": "author.name", "kind": "person"},
            "description": {"path": "dek", "kind": "description"},
            "url": {"path": "url", "kind": "url"},
            "published": {"path": "firstPublishedDate", "kind": "timestamp"},
        },
    },
    "pinterest_public": {
        "family": "json_object",
        "fields": {
            "username": {"path": "username", "kind": "handle", "required": True},
            "description": {"path": "biography", "kind": "description"},
            "image": {"path": "image_large_url", "kind": "url"},
            "website": {"path": "website_url", "kind": "url"},
        },
    },
    "wordpress_profile": {
        "family": "text_lines",
        "fields": {
            "url": {"path": "", "kind": "url", "pattern": "^(https?://\\S+wordpress\\S*)"},
            "title": {"path": "", "kind": "description", "pattern": "<title>([^<]+)</title>"},
        },
    },
    "whatsmyname_username": {
        "family": "json_rows",
        "list_path": "users",
        "fields": {
            "username": {"path": "username", "kind": "handle"},
            "url": {"path": "url", "kind": "url"},
            "category": {"path": "category", "kind": "status"},
        },
    },
    "telegram_tginfo": {
        "family": "json_object",
        "fields": {
            "username": {"path": "username", "kind": "handle", "required": True},
            "name": {"path": "name", "kind": "person"},
            "description": {"path": "bio", "kind": "description"},
            "subscribers": {"path": "subscribers_count", "kind": "integer"},
        },
    },
    "telegram_search_ligated": {
        "family": "json_rows",
        "list_path": "",
        "fields": {
            "channel": {"path": "title", "kind": "channel"},
            "description": {"path": "description", "kind": "description"},
            "subscribers": {"path": "participants_count", "kind": "integer"},
            "url": {"path": "username", "kind": "handle"},
        },
    },
    # ---------------------------------------------------------------- 05_threat
    "cisa_kev_recent": {
        "family": "json_rows",
        "list_path": "vulnerabilities",
        "fields": {
            "cve": {"path": "cveID", "kind": "cve", "required": True},
            "vendor": {"path": "vendorProject", "kind": "organization"},
            "product": {"path": "product", "kind": "technology"},
            "name": {"path": "vulnerabilityName", "kind": "description"},
            "added": {"path": "dateAdded", "kind": "timestamp"},
            "due": {"path": "dueDate", "kind": "timestamp"},
            "known_ransomware": {
                "path": "knownRansomwareCampaignUse",
                "kind": "unknown",
            },
        },
    },
    "nvd_cve": {
        "family": "json_rows",
        "list_path": "vulnerabilities",
        "fields": {
            "cve": {"path": "cve.id", "kind": "cve", "required": True},
            "description": {
                "path": "cve.descriptions[*].value",
                "kind": "description",
                "many": True,
            },
            "published": {"path": "cve.published", "kind": "timestamp"},
            "modified": {"path": "cve.lastModified", "kind": "timestamp"},
            "score": {
                "path": "cve.metrics.cvssMetricV31[*].cvssData.baseScore",
                "kind": "score",
                "many": True,
            },
            "vector": {
                "path": "cve.metrics.cvssMetricV31[*].cvssData.vectorString",
                "kind": "unknown",
                "many": True,
            },
            "reference": {"path": "cve.references[*].url", "kind": "url", "many": True},
        },
    },
    "cve_search_circl": {
        "family": "json_rows",
        "list_path": "",
        "fields": {
            "cve": {"path": "id", "kind": "cve", "required": True},
            "summary": {"path": "summary", "kind": "description"},
            "published": {"path": "published", "kind": "timestamp"},
            "modified": {"path": "modified", "kind": "timestamp"},
            "score": {"path": "cvss.score", "kind": "score"},
        },
    },
    "malwarebazaar_hash": {
        "family": "json_object",
        "fields": {
            "hash": {"path": "sha256_hash", "kind": "hash"},
            "file_name": {"path": "file_name", "kind": "unknown"},
            "file_type": {"path": "file_type", "kind": "technology"},
            "file_size": {"path": "file_size", "kind": "integer"},
            "signature": {"path": "signature", "kind": "technology"},
            "first_seen": {"path": "first_seen", "kind": "timestamp"},
        },
    },
    "threatfox_iocs": {
        "family": "json_rows",
        "list_path": "",
        "fields": {
            "ioc": {"path": "ioc", "kind": "unknown", "required": True},
            "ioc_type": {"path": "ioc_type", "kind": "status"},
            "malware": {"path": "malware_printable", "kind": "malware"},
            "confidence": {"path": "confidence_level", "kind": "score"},
            "first_seen": {"path": "first_seen", "kind": "timestamp"},
            "url": {"path": "url", "kind": "url"},
        },
    },
    "urlhaus_recent": {
        "family": "json_rows",
        "list_path": "",
        "fields": {
            "url": {"path": "url", "kind": "url", "required": True},
            "host": {"path": "host", "kind": "domain"},
            "status": {"path": "url_status", "kind": "status"},
            "added": {"path": "date_added", "kind": "timestamp"},
            "threat": {"path": "threat", "kind": "malware"},
            "tags": {"path": "tags", "kind": "tag", "many": True},
        },
    },
    "urlhaus_payloads": {
        "family": "json_object",
        "fields": {
            "url": {"path": "url", "kind": "url"},
            "host": {"path": "host", "kind": "domain"},
            "sha256": {"path": "sha256_hash", "kind": "hash"},
            "malware": {"path": "threat", "kind": "malware"},
            "added": {"path": "date_added", "kind": "timestamp"},
        },
    },
    "phishtank_lookup": {
        "family": "json_object",
        "fields": {
            "url": {"path": "url", "kind": "url"},
            "domain": {"path": "domain", "kind": "domain"},
            "brand": {"path": "brand", "kind": "organization"},
            "submitted": {"path": "submission_time", "kind": "timestamp"},
            "verified": {"path": "verified", "kind": "unknown"},
        },
    },
    "openphish_feed": {
        "family": "text_lines",
        "fields": {
            "url": {
                "path": "",
                "kind": "url",
                "pattern": "^(https?://\\S+)$",
                "required": True,
            },
        },
    },
    # The blocklist is "<ip>,<port>,<status>" per line. The port pattern has to anchor
    # after the comma: an unanchored \d{2,5} matched the last octet of the address, which
    # the live run reported as port "162" for 162.243.103.246.
    "feodo_tracker": {
        "family": "text_lines",
        "fields": {
            "ip": {
                "path": "",
                "kind": "ip",
                "pattern": "^(\\d+\\.\\d+\\.\\d+\\.\\d+)",
                "required": True,
            },
            "port": {
                "path": "",
                "kind": "port",
                "pattern": "^\\d+\\.\\d+\\.\\d+\\.\\d+\\s*,\\s*(\\d+)",
            },
            "status": {
                "path": "",
                "kind": "status",
                "pattern": "\\d+\\s*,\\s*\\d+\\s*,\\s*(\\w+)",
            },
        },
    },
    "sslbl_abuse_ch": {
        "family": "text_lines",
        "fields": {
            "ip": {
                "path": "",
                "kind": "ip",
                "pattern": "^(\\d+\\.\\d+\\.\\d+\\.\\d+)",
                "required": True,
            },
        },
    },
    "emergingthreats_compromised": {
        "family": "text_lines",
        "fields": {
            "ip": {
                "path": "",
                "kind": "ip",
                "pattern": "^(\\d+\\.\\d+\\.\\d+\\.\\d+)",
                "required": True,
            },
        },
    },
    "blocklist_de_all": {
        "family": "text_lines",
        "fields": {
            "ip": {
                "path": "",
                "kind": "ip",
                "pattern": "^(\\d+\\.\\d+\\.\\d+\\.\\d+)",
                "required": True,
            },
        },
    },
    "alienvault_otx": {
        "family": "json_object",
        "fields": {
            "name": {"path": "name", "kind": "organization"},
            "description": {"path": "description", "kind": "description"},
            "pulse_count": {"path": "pulse_info.count", "kind": "integer"},
            "tags": {"path": "tags", "kind": "tag", "many": True},
        },
    },
    "otx_domain_passive": {
        "family": "json_object",
        "fields": {
            "domain": {"path": "hostname", "kind": "domain", "required": True},
            "pulse_count": {"path": "pulse_info.count", "kind": "integer"},
            "reputation": {"path": "reputation", "kind": "score"},
            "tags": {"path": "pulse_info.tags", "kind": "tag", "many": True},
        },
    },
    "otx_ip_passive": {
        "family": "json_object",
        "fields": {
            "ip": {"path": "ip", "kind": "ip", "required": True},
            "asn": {"path": "asn", "kind": "asn"},
            "pulse_count": {"path": "pulse_info.count", "kind": "integer"},
            "reputation": {"path": "reputation", "kind": "score"},
        },
    },
    # ---------------------------------------------------------------- 06_breach
    "haveibeenpwned_breach": {
        "family": "json_rows",
        "list_path": "",
        "fields": {
            "breach": {"path": "Name", "kind": "leak", "required": True},
            "domain": {"path": "Domain", "kind": "domain"},
            "added": {"path": "AddedDate", "kind": "timestamp"},
            "modified": {"path": "ModifiedDate", "kind": "timestamp"},
            "pwn_count": {"path": "PwnCount", "kind": "integer"},
            "data_classes": {
                "path": "DataClass",
                "kind": "unknown",
                "many": True,
            },
        },
    },
    "haveibeenpwned_paste": {
        "family": "json_rows",
        "list_path": "",
        "fields": {
            "paste": {"path": "Key", "kind": "leak", "required": True},
            "date": {"path": "Date", "kind": "timestamp"},
            "url": {"path": "Link", "kind": "url"},
            "email_count": {"path": "EmailCount", "kind": "integer"},
        },
    },
    "dehashed_email": {
        "family": "json_object",
        "fields": {
            "email": {"path": "value", "kind": "email"},
            "database": {"path": "database.name", "kind": "leak"},
            "username": {"path": "username", "kind": "handle"},
            "domain": {"path": "domain", "kind": "domain"},
        },
    },
    "emailrep_email": {
        "family": "json_object",
        "fields": {
            "email": {"path": "email", "kind": "email", "required": True},
            "reputation": {"path": "reputation", "kind": "score"},
            "details": {"path": "details", "kind": "leak", "many": True},
            "name": {"path": "details.full_name", "kind": "person"},
            "twitter": {"path": "details.twitter", "kind": "handle"},
            "linkedin": {"path": "details.linkedin", "kind": "url"},
        },
    },
    "leakix_leak": {
        "family": "json_rows",
        "list_path": "",
        "fields": {
            "leak": {"path": "id", "kind": "leak", "required": True},
            "domain": {"path": "domain", "kind": "domain"},
            "username": {"path": "username", "kind": "handle"},
            "email": {"path": "email", "kind": "email"},
            "port": {"path": "port", "kind": "port"},
            "service": {"path": "service", "kind": "technology"},
            "found": {"path": "time", "kind": "timestamp"},
        },
    },
    "scylla_email": {
        "family": "json_object",
        "fields": {
            "email": {"path": "email", "kind": "email", "required": True},
            "breach": {"path": "breach", "kind": "leak"},
            "domain": {"path": "domain", "kind": "domain"},
        },
    },
    "phonebook_domain": {
        "family": "json_rows",
        "list_path": "",
        "fields": {
            "phone": {"path": "phone", "kind": "phone", "required": True},
            "url": {"path": "url", "kind": "url"},
        },
    },
    "phonebook_email": {
        "family": "json_rows",
        "list_path": "",
        "fields": {
            "phone": {"path": "phone", "kind": "phone", "required": True},
            "url": {"path": "url", "kind": "url"},
        },
    },
    "intelx_email": {
        "family": "json_object",
        "fields": {
            "email": {"path": "selector", "kind": "email"},
            "leak": {"path": "id", "kind": "leak"},
            "bucket": {"path": "bucket", "kind": "leak"},
        },
    },
    "hunter_email": {
        "family": "json_object",
        "fields": {
            "email": {"path": "data.email", "kind": "email"},
            "first_name": {"path": "data.first_name", "kind": "person"},
            "last_name": {"path": "data.last_name", "kind": "person"},
            "position": {"path": "data.position", "kind": "status"},
            "organization": {"path": "data.organization", "kind": "organization"},
            "domain": {"path": "data.domain", "kind": "domain"},
        },
    },
    "psbdmp_search": {
        "family": "json_object",
        "fields": {
            "email": {"path": "email", "kind": "email", "required": True},
            "breaches": {"path": "data", "kind": "leak", "many": True},
        },
    },
    # ----------------------------------------------------------- 07_geolocation
    "nominatim_search": {
        "family": "json_rows",
        "list_path": "",
        "fields": {
            "place": {"path": "display_name", "kind": "place", "required": True},
            "lat": {"path": "lat", "kind": "geolocation"},
            "lon": {"path": "lon", "kind": "geolocation"},
            "type": {"path": "type", "kind": "status"},
            "osm_id": {"path": "osm_id", "kind": "identifier"},
        },
    },
    "nominatim_reverse": {
        "family": "json_object",
        "fields": {
            "place": {"path": "display_name", "kind": "place", "required": True},
            "lat": {"path": "lat", "kind": "geolocation"},
            "lon": {"path": "lon", "kind": "geolocation"},
            "country": {"path": "address.country", "kind": "country"},
            "country_code": {"path": "address.country_code", "kind": "country"},
        },
    },
    "openweather_geo": {
        "family": "json_rows",
        "list_path": "",
        "fields": {
            "name": {"path": "name", "kind": "place"},
            "country": {"path": "sys.country", "kind": "country"},
            "region": {"path": "sys.region", "kind": "place"},
            "latitude": {"path": "coord.lat", "kind": "geolocation"},
            "longitude": {"path": "coord.lon", "kind": "geolocation"},
        },
    },
    "timezoneapi": {
        "family": "json_object",
        "fields": {
            "place": {"path": "location", "kind": "place"},
            "zone": {"path": "timeZoneId", "kind": "unknown"},
            "abbrev": {"path": "abbreviation", "kind": "unknown"},
            "offset": {"path": "utcOffset", "kind": "timestamp"},
        },
    },
    "wikidata_search": {
        "family": "json_rows",
        "list_path": "search",
        "fields": {
            "entity": {"path": "id", "kind": "identifier", "required": True},
            "label": {"path": "label", "kind": "description"},
            "description": {"path": "description", "kind": "description"},
            "url": {"path": "concepturi", "kind": "url"},
        },
    },
    # ------------------------------------------------------------- 08_knowledge
    "wikipedia_search": {
        "family": "json_object",
        "fields": {
            "title": {
                "path": "query.pages[*].title",
                "kind": "article",
                "many": True,
            },
            "snippet": {
                "path": "query.pages[*].snippet",
                "kind": "description",
                "many": True,
            },
            "pageid": {
                "path": "query.pages[*].pageid",
                "kind": "identifier",
                "many": True,
            },
        },
    },
    "wikipedia_summary": {
        "family": "json_object",
        "fields": {
            "title": {"path": "title", "kind": "article", "required": True},
            "description": {"path": "description", "kind": "description"},
            "extract": {"path": "extract", "kind": "description"},
            "url": {"path": "content_urls.desktop.page", "kind": "url"},
        },
    },
    "arxiv_search": {
        "family": "json_object",
        "fields": {
            "total": {"path": "opensearch:totalResults", "kind": "integer"},
            "id": {"path": "id", "kind": "article"},
            "title": {"path": "title", "kind": "article"},
            "summary": {"path": "summary", "kind": "description"},
            "author": {"path": "author[*].name", "kind": "person", "many": True},
            "published": {"path": "published", "kind": "timestamp"},
            "doi": {"path": "arxiv:doi", "kind": "identifier"},
        },
    },
    "crossref_doi": {
        "family": "json_rows",
        "list_path": "message.items",
        "fields": {
            "doi": {"path": "DOI", "kind": "identifier", "required": True},
            "title": {"path": "title[*]", "kind": "article", "many": True},
            "author": {"path": "author[*].family", "kind": "person", "many": True},
            "publisher": {"path": "publisher", "kind": "organization"},
            "published": {
                "path": "issued.date-parts[*][*]",
                "kind": "timestamp",
                "many": True,
            },
            "url": {"path": "URL", "kind": "url"},
        },
    },
    "openalex_work": {
        "family": "json_rows",
        "list_path": "results",
        "fields": {
            "work": {"path": "id", "kind": "article", "required": True},
            "title": {"path": "title", "kind": "article"},
            "doi": {"path": "doi", "kind": "identifier"},
            "publisher": {
                "path": "primary_location.source.display_name",
                "kind": "organization",
            },
            "author": {
                "path": "authorships[*].author.display_name",
                "kind": "person",
                "many": True,
            },
            "published": {"path": "publication_date", "kind": "timestamp"},
            "cited_by": {"path": "cited_by_count", "kind": "integer"},
            "language": {"path": "language", "kind": "language"},
        },
    },
    "openalex_author": {
        "family": "json_object",
        "fields": {
            "author": {"path": "id", "kind": "identifier", "required": True},
            "name": {"path": "display_name", "kind": "person"},
            "orcid": {"path": "orcid", "kind": "identifier"},
            "country": {
                "path": "last_known_institutions[*].country_code",
                "kind": "country",
                "many": True,
            },
            "works_count": {"path": "works_count", "kind": "integer"},
        },
    },
    "exploitdb_search": {
        "family": "text_lines",
        "fields": {
            "id": {"path": "", "kind": "identifier", "pattern": "EDB-(\\d+)", "many": True},
            "title": {
                "path": "",
                "kind": "description",
                "pattern": "^\\d+\\.\\s*(.+)$",
                "many": True,
            },
            "url": {"path": "", "kind": "url", "pattern": "(/exploits/\\d+)", "many": True},
        },
    },
    "duckduckgo_instant": {
        "family": "json_object",
        "fields": {
            "heading": {"path": "Heading", "kind": "description"},
            "abstract": {"path": "AbstractText", "kind": "description"},
            "url": {"path": "AbstractURL", "kind": "url"},
            "source": {"path": "AbstractSource", "kind": "organization"},
            "definition": {"path": "Definition", "kind": "description"},
            "definition_url": {"path": "DefinitionURL", "kind": "url"},
        },
    },
    # -------------------------------------------------------------- 09_wireless
    "aircraft_registry": {
        "family": "json_rows",
        "list_path": "",
        "fields": {
            "registration": {"path": "mode_s", "kind": "identifier", "required": True},
            "icao": {"path": "icao24", "kind": "identifier"},
            "manufacturer": {"path": "manufacturer", "kind": "organization"},
            "model": {"path": "model", "kind": "technology"},
            "operator": {"path": "registered_owner_country_iso_name", "kind": "country"},
            "url": {"path": "url", "kind": "url"},
        },
    },
    "bssid_lookups_ieee": {
        "family": "json_object",
        "fields": {
            "bssid": {"path": "BSSID", "kind": "bssid", "required": True},
            "ssid": {"path": "SSID", "kind": "unknown"},
            "vendor": {"path": "Vendor", "kind": "vendor"},
        },
    },
    "marine_traffic": {
        "family": "json_object",
        "fields": {
            "vessel": {"path": "NAME", "kind": "vessel", "required": True},
            "mmsi": {"path": "MMSI", "kind": "identifier"},
            "type": {"path": "TYPE", "kind": "technology"},
            "flag": {"path": "FLAG", "kind": "country"},
            "destination": {"path": "DESTINATION", "kind": "place"},
        },
    },
    "satellite_pass": {
        "family": "json_object",
        "fields": {
            "satellite": {"path": "info.name", "kind": "satellite", "required": True},
            "norad_id": {"path": "info.norad_cat_id", "kind": "identifier"},
            "start": {"path": "start", "kind": "timestamp"},
            "peak": {"path": "peak", "kind": "timestamp"},
            "duration": {"path": "duration", "kind": "integer"},
        },
    },
    "wigle_search": {
        "family": "json_object",
        "fields": {
            "bssid": {"path": "bssid", "kind": "bssid", "required": True},
            "ssid": {"path": "ssid", "kind": "unknown"},
            "vendor": {"path": "vname", "kind": "vendor"},
        },
    },
    # ----------------------------------------------------------- 10_blockchain
    "blockchain_btc_balance": {
        "family": "json_object",
        "fields": {
            "address": {"path": "address", "kind": "crypto", "required": True},
            "hash160": {"path": "hash160", "kind": "identifier"},
            "received": {"path": "total_received", "kind": "amount"},
            "sent": {"path": "total_sent", "kind": "amount"},
            "balance": {"path": "final_balance", "kind": "amount"},
            "tx_count": {"path": "n_tx", "kind": "integer"},
        },
    },
    "blockchain_btc_tx": {
        "family": "json_rows",
        "list_path": "txs",
        "fields": {
            "hash": {"path": "hash", "kind": "hash", "required": True},
            "time": {"path": "time", "kind": "timestamp"},
            "total_out": {"path": "total_out", "kind": "amount"},
            "size": {"path": "size", "kind": "integer"},
            "block": {"path": "block_height", "kind": "integer"},
        },
    },
    "blockstream_btc": {
        "family": "json_object",
        "fields": {
            "address": {"path": "address", "kind": "crypto", "required": True},
            "funded": {"path": "chain_stats.funded_txo_sum", "kind": "amount"},
            "received": {"path": "chain_stats.received_txo_sum", "kind": "amount"},
            "tx_count": {"path": "chain_stats.tx_count", "kind": "integer"},
        },
    },
    "ethplorer_address": {
        "family": "json_object",
        "fields": {
            "address": {"path": "address", "kind": "crypto", "required": True},
            "balance": {"path": "ETH.balance", "kind": "amount"},
            "tx_count": {"path": "ETH.txCount", "kind": "integer"},
            "last_block": {"path": "ETH.lastBlock", "kind": "integer"},
            "name": {"path": "ETH.tokenInfo.name", "kind": "crypto"},
            "contract": {"path": "ETH.tokenInfo.address", "kind": "crypto"},
        },
    },
    "mempool_space_block": {
        "family": "json_object",
        "fields": {
            "height": {"path": "height", "kind": "integer", "required": True},
            "hash": {"path": "hash", "kind": "hash"},
            "timestamp": {"path": "timestamp", "kind": "timestamp"},
            "tx_count": {"path": "n_tx", "kind": "integer"},
            "size": {"path": "size", "kind": "integer"},
            "weight": {"path": "weight", "kind": "integer"},
        },
    },
    # --------------------------------------------------------- 11_paste_leaks
    "psbdmp_ws": {
        "family": "text_lines",
        "fields": {
            "leak": {"path": "", "kind": "leak", "pattern": "([^\\s,]+:[^\\s,]+)", "many": True},
            "url": {"path": "", "kind": "url", "pattern": "(https?://\\S+)", "many": True},
        },
    },
    "leakcheck_public": {
        "family": "json_object",
        "fields": {
            "source": {"path": "source.name", "kind": "leak"},
            "date": {"path": "date", "kind": "timestamp"},
            "records": {"path": "records", "kind": "integer"},
        },
    },
    # -------------------------------------------------------------- 12_visual
    "exif_remove_lookup": {
        "family": "json_object",
        "fields": {
            "latitude": {"path": "latitude", "kind": "geolocation"},
            "longitude": {"path": "longitude", "kind": "geolocation"},
            "camera": {"path": "camera", "kind": "technology"},
            "timestamp": {"path": "datetime_original", "kind": "timestamp"},
        },
    },
    # ------------------------------------------------------------- 13_reputation
    "vt_domain": {
        "family": "json_object",
        "fields": {
            "domain": {"path": "id", "kind": "domain", "required": True},
            "reputation": {"path": "reputation", "kind": "score"},
            "categories": {"path": "categories", "kind": "status", "many": True},
            "last_analysis": {"path": "last_analysis_date", "kind": "timestamp"},
            "asn": {"path": "asn", "kind": "asn"},
            "country": {"path": "country", "kind": "country"},
        },
    },
    "vt_ip": {
        "family": "json_object",
        "fields": {
            "ip": {"path": "id", "kind": "ip", "required": True},
            "reputation": {"path": "reputation", "kind": "score"},
            "categories": {"path": "categories", "kind": "status", "many": True},
            "country": {"path": "country", "kind": "country"},
            "asn": {"path": "asn", "kind": "asn"},
            "as_owner": {"path": "as_owner", "kind": "organization"},
        },
    },
    "vt_file": {
        "family": "json_object",
        "fields": {
            "hash": {"path": "id", "kind": "hash", "required": True},
            "reputation": {"path": "reputation", "kind": "score"},
            "type": {"path": "type_description", "kind": "technology"},
            "size": {"path": "size", "kind": "integer"},
            "names": {"path": "names", "kind": "unknown", "many": True},
            "detections": {"path": "last_analysis_stats.detected", "kind": "integer"},
        },
    },
    # ------------------------------------------------------------------ 14_tech
    "tech_fingerprint": {
        "family": "json_object",
        "fields": {
            "domain": {"path": "domain", "kind": "domain", "required": True},
            "technology": {"path": "technologies[*].name", "kind": "technology", "many": True},
            "version": {"path": "technologies[*].version", "kind": "unknown", "many": True},
            "category": {
                "path": "technologies[*].categories[*]",
                "kind": "tag",
                "many": True,
            },
        },
    },
    # ------------------------------------------------------------------ 15_cloud
    "bucket_probe": {
        "family": "json_object",
        "fields": {
            "bucket": {"path": "bucket", "kind": "repository", "required": True},
            "region": {"path": "region", "kind": "place"},
            "provider": {"path": "provider", "kind": "organization"},
            "public": {"path": "public", "kind": "unknown"},
        },
    },
    # --------------------------------------------------------------- 18_supply
    "supply_chain_dns": {
        "family": "json_object",
        "fields": {
            "package": {"path": "name", "kind": "technology", "required": True},
            "version": {"path": "version", "kind": "unknown"},
            "registry": {"path": "registry", "kind": "repository"},
            "published": {"path": "published", "kind": "timestamp"},
            "maintainer": {"path": "maintainer", "kind": "person"},
        },
    },
    # ------------------------------------------------------------------ 19_pdns
    "pdns_crtsh": {
        "family": "json_object",
        "fields": {
            "domain": {"path": "domain", "kind": "domain", "required": True},
            "subdomain": {"path": "subdomain", "kind": "subdomain"},
            "source": {"path": "source", "kind": "leak"},
            "created": {"path": "created_at", "kind": "timestamp"},
        },
    },
    "pdns_certspotter": {
        "family": "json_object",
        "fields": {
            "domain": {"path": "domain", "kind": "domain", "required": True},
            "subdomain": {"path": "domain", "kind": "subdomain"},
            "source": {"path": "source", "kind": "leak"},
            "created": {"path": "created_at", "kind": "timestamp"},
        },
    },
}


def render_block(block: dict[str, Any]) -> str:
    """Render a parse block as YAML text appended to a definition.

    Key order is fixed rather than whatever the dict happens to iterate in, so re-running
    this on an already-annotated file produces byte-identical output and a diff shows only
    what actually changed.
    """
    lines: list[str] = ["parse:"]
    lines.append(f"  family: {block['family']}")
    if block.get("list_path"):
        lines.append(f"  list_path: {block['list_path']}")
    if not block.get("fields"):
        return "\n".join(lines) + "\n"
    lines.append("  fields:")
    for name, spec in block["fields"].items():
        parts = [f"path: {_scalar(spec.get('path', ''))}"]
        if spec.get("kind"):
            parts.append(f"kind: {_scalar(spec['kind'])}")
        if spec.get("many"):
            parts.append("many: true")
        if spec.get("required"):
            parts.append("required: true")
        if spec.get("pattern"):
            parts.append(f"pattern: {_scalar(spec['pattern'])}")
        lines.append(f"    {name}:")
        lines.extend(f"      {part}" for part in parts)
    return "\n".join(lines) + "\n"


def _scalar(value: Any) -> str:
    text = str(value)
    if text == "":
        return '""'
    # A path like ``Answer[*].data`` is fine unquoted, but one containing ``:`` or starting
    # with a sigil would be read as something else entirely.
    if any(ch in text for ch in ":#{}[]&*!|>'\"%@`") or text[0] in "-?":
        escaped = text.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    known = {p.stem for p in ROOT.rglob("*.yaml")}
    declared = set(PARSE_BLOCKS)
    unknown = sorted(declared - known)
    if unknown:
        print("blocks for files that do not exist:", unknown, file=sys.stderr)

    changed: list[str] = []
    skipped: list[str] = []
    for name, block in sorted(PARSE_BLOCKS.items()):
        matches = list(ROOT.rglob(f"{name}.yaml"))
        if not matches:
            continue
        path = matches[0]
        text = path.read_text(encoding="utf-8")
        raw = yaml.safe_load(text) or {}
        if "parse" in raw:
            skipped.append(name)
            continue
        if not args.dry_run:
            body = text.rstrip("\n")
            path.write_text(body + "\n" + render_block(block), encoding="utf-8")
        changed.append(name)

    verb = "would annotate" if args.dry_run else "annotated"
    print(f"{verb} {len(changed)} definitions; {len(skipped)} already had a parse block")
    if skipped:
        print("  already declared:", ", ".join(sorted(skipped)))
    missing = sorted(known - declared)
    print(f"  {len(missing)} definitions have no block yet")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())