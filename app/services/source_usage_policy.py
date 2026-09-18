from dataclasses import dataclass
from urllib.parse import urlsplit

from app.models.source import CommercialUseStatus, RSSUsageStatus


@dataclass(frozen=True, slots=True)
class SourceUsagePolicy:
    commercial_use_status: CommercialUseStatus
    rss_usage_status: RSSUsageStatus
    terms_url: str | None
    note: str


UNKNOWN_POLICY = SourceUsagePolicy(
    commercial_use_status=CommercialUseStatus.UNKNOWN,
    rss_usage_status=RSSUsageStatus.UNKNOWN,
    terms_url=None,
    note="Kaynak kullanım koşulları production öncesinde incelenmeli.",
)

_POLICIES: dict[str, SourceUsagePolicy] = {
    "trthaber.com": SourceUsagePolicy(
        commercial_use_status=CommercialUseStatus.UNKNOWN,
        rss_usage_status=RSSUsageStatus.ALLOWED,
        terms_url="https://www.trthaber.com/sitene_ekle.html",
        note="Resmi RSS sunuluyor; açık ticari yeniden yayın lisansı teyit edilmedi.",
    ),
    "aspor.com.tr": SourceUsagePolicy(
        commercial_use_status=CommercialUseStatus.UNKNOWN,
        rss_usage_status=RSSUsageStatus.ALLOWED,
        terms_url="https://www.aspor.com.tr/rss-bilgi",
        note="Resmi RSS sunuluyor; açık ticari yeniden yayın lisansı teyit edilmedi.",
    ),
    "transfermarkt.com.tr": SourceUsagePolicy(
        commercial_use_status=CommercialUseStatus.RESTRICTED,
        rss_usage_status=RSSUsageStatus.RESTRICTED,
        terms_url="https://www.transfermarkt.com.tr/intern/anb",
        note="İçerik hakları saklı; ticari kullanım için yazılı izin gerekli.",
    ),
    "haberturk.com": SourceUsagePolicy(
        commercial_use_status=CommercialUseStatus.RESTRICTED,
        rss_usage_status=RSSUsageStatus.RESTRICTED,
        terms_url="https://www.haberturk.com/kullanim-kosullari",
        note="Haber ve materyal kullanımı açık yazılı izne bağlı.",
    ),
    "ntvspor.net": SourceUsagePolicy(
        commercial_use_status=CommercialUseStatus.RESTRICTED,
        rss_usage_status=RSSUsageStatus.RESTRICTED,
        terms_url="https://www.ntvspor.net/kullanim-kosullari",
        note="Haber ve materyal kullanımı açık yazılı izne bağlı.",
    ),
}


def _hostname(value: str) -> str:
    return (urlsplit(value).hostname or "").casefold().removeprefix("www.")


def _policy_for_url(value: str) -> SourceUsagePolicy | None:
    hostname = _hostname(value)
    for domain, policy in _POLICIES.items():
        if hostname == domain or hostname.endswith(f".{domain}"):
            return policy
    return None


def classify_source_usage(url: str, rss_url: str) -> SourceUsagePolicy:
    policies = [
        policy
        for value in (url, rss_url)
        if (policy := _policy_for_url(value)) is not None
    ]
    if not policies:
        return UNKNOWN_POLICY
    if any(
        policy.commercial_use_status == CommercialUseStatus.RESTRICTED
        or policy.rss_usage_status == RSSUsageStatus.RESTRICTED
        for policy in policies
    ):
        return next(
            policy
            for policy in policies
            if policy.commercial_use_status == CommercialUseStatus.RESTRICTED
            or policy.rss_usage_status == RSSUsageStatus.RESTRICTED
        )
    return policies[0]


def source_policy_blocks_processing(
    commercial_status: CommercialUseStatus,
    rss_status: RSSUsageStatus,
) -> bool:
    return (
        commercial_status == CommercialUseStatus.PROHIBITED
        or rss_status == RSSUsageStatus.RESTRICTED
    )


def source_policy_warning(
    commercial_status: CommercialUseStatus,
    rss_status: RSSUsageStatus,
) -> bool:
    return (
        commercial_status
        in {CommercialUseStatus.UNKNOWN, CommercialUseStatus.RESTRICTED}
        or rss_status == RSSUsageStatus.UNKNOWN
    )
