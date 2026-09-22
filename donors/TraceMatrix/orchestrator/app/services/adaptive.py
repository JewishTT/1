from dataclasses import dataclass

@dataclass
class Limits:
    search_limit: int = 15
    email_limit: int = 20
    social_limit: int = 10
    phone_limit: int = 5
    max_cap: int = 200

class AdaptiveLimiter:
    def adjust(self, limits: Limits, observed: dict) -> Limits:
        l = Limits(**limits.__dict__)
        if observed.get("emails_found", 0) < 5:
            l.email_limit = min(l.email_limit * 2, l.max_cap)
        if observed.get("search_hits", 0) < 10:
            l.search_limit = min(int(l.search_limit * 1.5), l.max_cap)
        if observed.get("phones_found", 0) > 0 and not observed.get("phone_input", False):
            l.phone_limit = min(l.phone_limit + 2, 15)
        return l

